# pulumi_cluster

Cluster Kubernetes **MicroK8s** su VM **Ubuntu** create con **Multipass**, dichiarato con **Pulumi** (Python),
con toolchain riproducibile **Nix** e **Task** come interfaccia operativa. Gli ambienti DEV/UAT/PROD sono
**stack Pulumi** dello stesso codice. Il cluster è dimensionato per ospitare **Apache OpenServerless**.

```
Developer/Operator → Nix → Task → Pulumi → Multipass → cloud-init → Ubuntu → MicroK8s → Kubernetes → Helm/Manifest → Applicazioni
```

## Avvio rapido

Prerequisiti sull'host: [Nix](https://nixos.org/download) con i flakes abilitati e
[Multipass](https://multipass.run/install). Multipass è un demone di sistema, quindi non lo fornisce Nix.

```bash
git clone https://github.com/mobs75/pulumi_cluster.git
cd pulumi_cluster
nix develop
```

```bash
export PULUMI_CONFIG_PASSPHRASE='...'   # passphrase dei secret Pulumi (mai nel repo)
task setup                              # una tantum: backend locale, dipendenze, stack dev/uat/prod
task dev:preview
task dev:up
task cluster:status
```

Forma parametrica equivalente: `task infra:preview ENV=dev`, `task infra:up ENV=uat`, `task infra:up ENV=prod`.

## Task principali

| Task | Cosa fa |
|---|---|
| `task setup` | `pulumi login --local` (se serve), `pulumi install`, crea gli stack mancanti |
| `task dev:preview` / `uat:preview` / `prod:preview` | `pulumi preview` sullo stack |
| `task dev:up` / `uat:up` / `prod:up` | `pulumi up` e poi scrive il kubeconfig in `.kube/<env>.yaml` (`YES=true` per non chiedere conferma) |
| `task dev:down` · `task destroy ENV=uat` | `pulumi destroy`, che elimina **solo** le VM di quello stack |
| `task infra:<preview\|up\|down\|refresh\|outputs\|kubeconfig> ENV=<env>` | Le stesse operazioni in forma parametrica |
| `task cluster:status ENV=dev` | `vm:status` + `k8s:status` |
| `task vm:status` · `task vm:shell NODE=dev-master` | Stato delle VM e shell su un nodo (Multipass) |
| `task k8s:status` · `task k8s:kubectl -- get pods -A` | Nodi, StorageClass, LoadBalancer, pod non Running |
| `task logs NODE=dev-node1 LOG=kubelite\|containerd\|cloud-init` | Log di un nodo |

`ENV` vale `dev` se non è indicato. I valori ammessi sono `dev`, `uat` e `prod`.

## Responsabilità dei layer

| Layer | Responsabilità | Dove |
|---|---|---|
| Nix | Toolchain riproducibile: go-task, pulumi, python 3.12, kubectl 1.33, helm, jq, yq | `flake.nix`, `flake.lock` |
| Dev Container | Stesso flake dentro un container, senza toolchain duplicate | `.devcontainer/` |
| Task | Interfaccia operativa: richiama Pulumi, kubectl e Multipass, senza configurazione propria | `Taskfile.yml`, `taskfiles/` |
| Pulumi | Stato, configurazione per ambiente, lifecycle e dipendenze, output | `__main__.py`, `infra/`, `Pulumi.<env>.yaml` |
| Multipass | Creazione e cancellazione delle VM | `infra/vm/multipass.py` |
| cloud-init | Bootstrap del solo sistema operativo della VM | `cloud-init/base.yaml`, `infra/cloudinit.py` |
| MicroK8s | Installazione, join dei nodi, addon | `infra/k8s/microk8s.py` |
| Helm/manifest | Piattaforma e applicazioni (es. OpenServerless) | usano solo il kubeconfig esportato |

Il resto del codice dipende solo da `infra/vm/base.py` (`VmProvider`) e da `infra/k8s/base.py`
(`KubernetesDistribution`). Per aggiungere un backend come libvirt/KVM o kubeadm basta implementare
quell'interfaccia e registrarla, senza toccare gli altri layer.

### Perché MicroK8s non si installa da cloud-init

cloud-init prepara solo il sistema operativo: hostname, chiavi SSH, pacchetti, DNS, proxy, CA, moduli kernel e sysctl.
Installazione, join e addon sono risorse Pulumi separate, per tre motivi:

- i log e gli errori compaiono in `pulumi up` invece che dentro `/var/log/cloud-init-output.log` della VM;
- ogni passo ha dipendenze esplicite (prima l'installazione, poi i join uno alla volta, poi gli addon);
- sostituire MicroK8s con kubeadm non richiede di toccare né cloud-init né il VM provider.

## Configurazione degli ambienti (stack Pulumi)

Tutta la configurazione sta in `Pulumi.dev.yaml`, `Pulumi.uat.yaml` e `Pulumi.prod.yaml`:

| Chiave | Default nei tre stack | Note |
|---|---|---|
| `cluster:namePrefix` | `dev` / `uat` / `prod` | VM `<prefix>-master`, `<prefix>-node1..N` |
| `cluster:image` | `24.04` | Ubuntu, come nell'ultimo script originale |
| `cluster:nodes.controlPlane` | 4 CPU, 12G, 50G | RAM e disco presi dallo script originale |
| `cluster:nodes.workers` | 3 × (2 CPU, 12G, 50G) | OpenServerless richiede almeno 3 worker da 4GB |
| `cluster:sshAuthorizedKeys` | vuoto | Solo chiavi **pubbliche** |
| `cluster:httpProxy` | — | **Sempre** `--secret` (può contenere credenziali) |
| `cluster:dnsServers`, `caCerts`, `packages`, `timezone`, `noProxy` | — | Opzionali |
| `k8s:channel` | `1.33/stable` | Mai `latest`. Il programma rifiuta `latest` e blocca i downgrade |
| `k8s:joinAsWorker` | `true` | I nodi `nodeN` entrano come worker |
| `k8s:addons` | `dns hostpath-storage ingress cert-manager metallb:auto` | Vedi sotto |
| `k8s:registryMirror` | `false` | Mirror containerd per il registry interno, dal vecchio script 24.04 |

Esempi:

```bash
pulumi config set --path 'cluster:nodes.workers.count' 2 -s dev
pulumi config set --path 'cluster:sshAuthorizedKeys[0]' "$(cat ~/.ssh/id_ed25519.pub)" -s prod
pulumi config set --secret cluster:httpProxy 'http://user:pass@proxy:3128' -s prod
```

Se cambi CPU, RAM, disco, immagine o cloud-init di un nodo, Pulumi **ricrea** quella VM (`preview` lo mostra).
Gli addon tolti dalla lista non vengono disabilitati in automatico: si disabilitano con `microk8s disable`.

## OpenServerless

- **Versione Kubernetes:** il dev cluster ufficiale di OpenServerless usa `kindest/node:v1.33.1`
  ([openserverless-task `setup/docker/kind.yaml`](https://github.com/apache/openserverless-task/blob/main/setup/docker/kind.yaml)).
  Per questo il channel è `1.33/stable` e kubectl nel flake è la 1.33.
- **Addon:** sono gli stessi che abilita l'installer MicroK8s di OpenServerless (`ops cloud mk8s create`):
  `hostpath-storage dns ingress cert-manager`
  ([mk8s.sh](https://github.com/apache/openserverless-task/blob/main/cloud/mk8s/mk8s.sh)).
  In più c'è `metallb` per i Service LoadBalancer, richiesti dai [prerequisiti cluster](https://openserverless.apache.org/docs/installation/prereq/kubernetes/cluster/).
  `metallb:auto` usa gli IP .240-.250 della subnet della VM master. In alternativa puoi indicare un range esplicito.
- **Storage:** `hostpath-storage` è la StorageClass di default. È adatta a DEV/UAT, ma i volumi restano sul nodo
  in cui vengono creati. Per PROD valuta uno storage replicato: `nfs-common` e `open-iscsi` sono già installati
  da cloud-init.
- **Installazione:** dopo `task dev:up`, `export KUBECONFIG=$PWD/.kube/dev.yaml` e poi la procedura OpenServerless
  per un cluster esistente (`ops setup cluster`).

## Dev Container

`.devcontainer/devcontainer.json` installa solo Nix e apre ogni terminale dentro `nix develop`, quindi la toolchain
è quella del flake. Lo stato Pulumi (`~/.pulumi`) e `PULUMI_CONFIG_PASSPHRASE` arrivano dall'host.

**Limite:** Multipass è un demone dell'host e non gira dentro il container. Nel Dev Container puoi modificare il codice,
lanciare `preview` e usare i comandi `k8s:*`. `up`, `down` e i comandi `vm:*` vanno eseguiti sull'host con `nix develop`.

## Sicurezza

- Nel repository non ci sono password, token, chiavi private, certificati privati o kubeconfig.
- Il kubeconfig è un output **secret** di Pulumi. `task <env>:kubeconfig` lo scrive in `.kube/<env>.yaml` con permessi 600,
  e la cartella `.kube/` è in `.gitignore`.
- Il proxy si imposta come Pulumi secret: lo user-data che lo contiene è cifrato nello stato.

## Idempotenza

- Ogni VM viene creata solo se non esiste. `destroy` elimina solo le VM dello stack, non `multipass delete --all`.
- MicroK8s viene installato solo se assente e aggiornato solo se il channel cambia verso l'alto.
- I join vengono saltati se il nodo è già nel cluster e girano uno alla volta.
- Gli addon vengono abilitati solo se non sono già attivi.
- Un secondo `pulumi up` senza modifiche non fa nulla.

## Script originali

I vecchi script di provisioning (`ops_pulumi.py`, `pulumi_microk8s_provisioning*.py`, `setup_pulumi_env.sh`,
`get-ops.sh`) sono in [`legacy/`](legacy/) come riferimento e non vengono più usati. `delete_cluster.sh`
ora richiama `task destroy` ed elimina solo le VM dello stack indicato.
