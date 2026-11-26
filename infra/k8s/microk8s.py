"""Distribuzione Kubernetes MicroK8s.

Responsabilita' separate in risorse Pulumi distinte, nell'ordine:

1. ``install``  - snap MicroK8s sul channel fissato (per ogni nodo)
2. ``registry`` - mirror containerd per il registry interno (opzionale)
3. ``join``     - join dei worker al control plane, uno alla volta
4. ``addons``   - addon sul control plane (dns, storage, ingress, ...)
5. ``kubeconfig`` - kubeconfig esportato come output secret

Ogni script e' idempotente: rieseguire ``pulumi up`` non reinstalla, non
rifa' join gia' fatti e non riabilita addon gia' attivi.
I comandi arrivano ai nodi solo tramite ``VirtualMachine.exec_prefix``: questo
modulo non conosce Multipass.
"""

from __future__ import annotations

import ipaddress
import shlex
from typing import List

import pulumi
import pulumi_command as command

from ..config import KubernetesConfig
from ..vm import VirtualMachine
from .base import ClusterResult, KubernetesDistribution

_BASH = ["/usr/bin/env", "bash", "-c"]

_INSTALL = r"""
set -euo pipefail
CH={channel}
if snap list microk8s >/dev/null 2>&1; then
  cur="$(snap info microk8s | awk '/^tracking:/{{print $2}}')"
  if [ "$cur" != "$CH" ]; then
    # Solo upgrade: il downgrade di MicroK8s non e' supportato.
    lowest="$(printf '%s\n%s\n' "${{cur%%/*}}" "${{CH%%/*}}" | sort -V | head -n1)"
    if [ "$lowest" = "${{CH%%/*}}" ] && [ "${{cur%%/*}}" != "${{CH%%/*}}" ]; then
      echo "MicroK8s su $cur: downgrade a $CH non supportato" >&2
      exit 1
    fi
    snap refresh microk8s --channel="$CH"
  fi
else
  snap install microk8s --classic --channel="$CH"
fi
usermod -a -G microk8s ubuntu
install -d -o ubuntu -g ubuntu -m 0700 /home/ubuntu/.kube
microk8s status --wait-ready --timeout 600 >/dev/null
microk8s version
"""

# Mirror containerd -> registry interno via NodePort (comportamento originale
# di pulumi_microk8s_provisioning2404.py), scritto in modo idempotente.
_REGISTRY = r"""
set -euo pipefail
d=/var/snap/microk8s/current/args/certs.d/docker-registry.kube-system.svc.cluster.local:5000
mkdir -p "$d"
cat > "$d/hosts.toml.new" <<'EOF'
server = "http://docker-registry.kube-system.svc.cluster.local:5000"

[host."http://localhost:30500"]
  capabilities = ["pull", "resolve"]
EOF
if ! cmp -s "$d/hosts.toml.new" "$d/hosts.toml" 2>/dev/null; then
  mv "$d/hosts.toml.new" "$d/hosts.toml"
  snap restart microk8s.daemon-containerd
else
  rm -f "$d/hosts.toml.new"
fi
"""

_JOIN = r"""
set -euo pipefail
if echo "microk8s kubectl get node $NODE" | $MASTER_EXEC >/dev/null 2>&1; then
  echo "$NODE e' gia' nel cluster: join saltato"
  exit 0
fi
out="$(echo "microk8s add-node --token-ttl 900 --format short" | $MASTER_EXEC)"
join="$(echo "$out" | grep "microk8s join" | grep -F "$MASTER_IP" | head -n1 || true)"
[ -n "$join" ] || join="$(echo "$out" | grep -m1 "microk8s join")"
echo "$join $JOIN_FLAGS" | $NODE_EXEC
echo "microk8s kubectl wait --for=condition=Ready node/$NODE --timeout=600s" | $MASTER_EXEC
"""

_LEAVE = r"""
echo "microk8s remove-node $NODE --force" | $MASTER_EXEC >/dev/null 2>&1 || true
"""

_ADDONS = r"""
set -euo pipefail
microk8s status --wait-ready --timeout 600 >/dev/null
for spec in {addons}; do
  name="${{spec%%:*}}"
  if [ "$(microk8s status -a "$name" 2>/dev/null | head -n1)" = "enabled" ]; then
    echo "addon $name gia' abilitato"
  else
    microk8s enable "$spec"
  fi
done
microk8s status --wait-ready --timeout 600 >/dev/null
microk8s status --format short
"""


def _metallb_auto_range(ip: str) -> str:
    """Pool LoadBalancer di default: .240-.250 della subnet /24 della VM master."""
    net = ipaddress.ip_network(f"{ip}/24", strict=False)
    base = str(net.network_address).rsplit(".", 1)[0]
    return f"{base}.240-{base}.250"


def _resolve_addons(addons: List[str], master_ip: str) -> List[str]:
    out = []
    for a in addons:
        if a in ("metallb", "metallb:auto"):
            a = f"metallb:{_metallb_auto_range(master_ip)}"
        out.append(a)
    return out


class MicroK8s(KubernetesDistribution):
    name = "microk8s"

    def provision(self, cfg: KubernetesConfig, control_plane: VirtualMachine,
                  workers: List[VirtualMachine]) -> ClusterResult:
        install_script = _INSTALL.format(channel=shlex.quote(cfg.channel))
        installs = {}
        for vm in [control_plane] + workers:
            installs[vm.spec.name] = command.local.Command(
                f"microk8s-install-{vm.spec.name}",
                create=vm.exec_prefix,
                interpreter=_BASH,
                stdin=install_script,
                triggers=[cfg.channel],
                opts=pulumi.ResourceOptions(depends_on=[vm.resource]),
            )

        ready = dict(installs)
        if cfg.registry_mirror:
            for vm in [control_plane] + workers:
                ready[vm.spec.name] = command.local.Command(
                    f"microk8s-registry-mirror-{vm.spec.name}",
                    create=vm.exec_prefix,
                    interpreter=_BASH,
                    stdin=_REGISTRY,
                    opts=pulumi.ResourceOptions(depends_on=[installs[vm.spec.name]]),
                )

        # Join sequenziali: join paralleli sullo stesso control plane MicroK8s
        # possono fallire.
        joins: List[pulumi.Resource] = []
        previous: pulumi.Resource = ready[control_plane.spec.name]
        for vm in workers:
            join = command.local.Command(
                f"microk8s-join-{vm.spec.name}",
                create=_JOIN,
                delete=_LEAVE,
                interpreter=_BASH,
                environment={
                    "NODE": vm.spec.name,
                    "MASTER_EXEC": control_plane.exec_prefix,
                    "NODE_EXEC": vm.exec_prefix,
                    "MASTER_IP": control_plane.ip,
                    "JOIN_FLAGS": "--worker" if cfg.join_as_worker else "",
                },
                opts=pulumi.ResourceOptions(depends_on=[previous, ready[vm.spec.name]]),
            )
            joins.append(join)
            previous = join

        addons_script = control_plane.ip.apply(
            lambda ip: _ADDONS.format(addons=" ".join(shlex.quote(a) for a in _resolve_addons(cfg.addons, ip)))
            if cfg.addons else "true"
        )
        addons = command.local.Command(
            "microk8s-addons",
            create=control_plane.exec_prefix,
            interpreter=_BASH,
            stdin=addons_script,
            triggers=[addons_script],
            opts=pulumi.ResourceOptions(depends_on=[previous] + joins),
        )

        kubeconfig = command.local.Command(
            "microk8s-kubeconfig",
            create=control_plane.exec_prefix,
            interpreter=_BASH,
            stdin="microk8s config",
            triggers=[cfg.channel, control_plane.ip],
            opts=pulumi.ResourceOptions(depends_on=[addons], additional_secret_outputs=["stdout"]),
        )

        return ClusterResult(
            kubeconfig=pulumi.Output.secret(kubeconfig.stdout),
            version=installs[control_plane.spec.name].stdout.apply(lambda s: s.strip()),
            addons=addons.stdout,
        )
