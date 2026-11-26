import pulumi
import subprocess

# Funzione per eseguire comandi Multipass
def run_multipass(cmd):
    subprocess.run(['multipass'] + cmd.split(), check=True)

# Funzione per verificare se una VM esiste già
def vm_exists(name):
    result = subprocess.run(['multipass', 'list'], capture_output=True, text=True)
    return name in result.stdout

# Definizione dello Stack Pulumi
class ClusterStack(pulumi.ComponentResource):
    def __init__(self, name, opts=None):
        super().__init__("custom:resource:ClusterStack", name, {}, opts)

        # Creare il master node solo se non esiste
        if not vm_exists("k8s-master"):
            run_multipass("launch --name k8s-master --mem 12G --disk 50G 24.04")  # ← CAMBIATO

        # Configurare MicroK8s
        run_multipass("exec k8s-master -- sudo snap install microk8s --classic")
        run_multipass("exec k8s-master -- sudo usermod -a -G microk8s ubuntu")
        run_multipass("exec k8s-master -- sudo mkdir -p /home/ubuntu/.kube")
        run_multipass("exec k8s-master -- sudo chown -f -R ubuntu /home/ubuntu/.kube")
        run_multipass("exec k8s-master -- microk8s.status --wait-ready")
        run_multipass("exec k8s-master -- microk8s.enable dns dashboard")

        # Creare e configurare i worker nodes
        worker_nodes = ['k8s-node1', 'k8s-node2', 'k8s-node3']
        for node in worker_nodes:
            if not vm_exists(node):
                run_multipass(f"launch --name {node} --mem 12G --disk 50G 24.04")  # ← CAMBIATO

            run_multipass(f"exec {node} -- sudo snap install microk8s --classic")
            run_multipass(f"exec {node} -- sudo usermod -a -G microk8s ubuntu")
            run_multipass(f"exec {node} -- sudo mkdir -p /home/ubuntu/.kube")
            run_multipass(f"exec {node} -- sudo chown -f -R ubuntu /home/ubuntu/.kube")
            run_multipass(f"exec {node} -- microk8s.status --wait-ready")

        # Recuperare il comando di join
        join_output = subprocess.check_output(
            ["multipass", "exec", "k8s-master", "--", "microk8s.add-node", "--token-ttl", "3600"], 
            encoding='utf-8'
        )
        join_command = next((line for line in join_output.split("\n") if "microk8s join" in line), None)

        if not join_command:
            raise RuntimeError("Errore: impossibile trovare il comando di join")

        # Aggiungere i worker al cluster
        for node in worker_nodes:
            node_check = subprocess.run(
                ["multipass", "exec", "k8s-master", "--", "microk8s.kubectl", "get", "nodes"], 
                capture_output=True, text=True
            )
            if node in node_check.stdout:
                print(f"Il nodo {node} è già nel cluster, salto il join.")
            else:
                run_multipass(f"exec {node} -- {join_command}")

        # Configurare containerd su ogni nodo per risolvere il registry interno
        # via NodePort (localhost:30500) invece del DNS cluster (non risolvibile dal kubelet)
        hosts_toml = (
            'server = "http://docker-registry.kube-system.svc.cluster.local:5000"\n'
            '\n'
            '[host."http://localhost:30500"]\n'
            '  capabilities = ["pull", "resolve"]\n'
        )
        certs_d_path = (
            "/var/snap/microk8s/current/args/certs.d"
            "/docker-registry.kube-system.svc.cluster.local:5000/hosts.toml"
        )
        for node in ["k8s-master"] + worker_nodes:
            subprocess.run(
                ["multipass", "exec", node, "--",
                 "sudo", "bash", "-c", f"printf '%s' '{hosts_toml}' > {certs_d_path}"],
                check=True
            )
            print(f"Configured containerd registry mirror on {node} -> localhost:30500")

        # Esportare informazioni del cluster
        self.masterNode = pulumi.Output.from_input('k8s-master')
        self.workerNodes = pulumi.Output.from_input(worker_nodes)

        # Registrazione output
        self.register_outputs({
            'masterNode': self.masterNode,
            'workerNodes': self.workerNodes
        })

# Crea una stack di Pulumi valida
stack = ClusterStack("my-cluster", opts=pulumi.ResourceOptions(parent=None))