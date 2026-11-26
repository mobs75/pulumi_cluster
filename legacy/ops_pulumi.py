import pulumi
import subprocess
import os

def vm_exists(name):
    result = subprocess.run(["multipass", "list"], capture_output=True, text=True)
    return name in result.stdout

def run_multipass(command):
    subprocess.run(["multipass"] + command.split(), check=True)

# Definizione dello Stack Pulumi
class ClusterStack(pulumi.ComponentResource):
    def __init__(self, name, opts=None):
        super().__init__("custom:resource:ClusterStack", name, {}, opts)

        # Creare il master node solo se non esiste
        if not vm_exists("k8s-master"):
            run_multipass("launch --name k8s-master --mem 4G --disk 10G")

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
                run_multipass(f"launch --name {node} --mem 4G --disk 10G")

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

        # Installare il CLI di OpenServerless
        self.install_openserverless_cli()

        # Deploy di OpenServerless
        self.deploy_openserverless()

        # Verificare l'installazione di OpenServerless
        self.verify_openserverless_installation()

        # Esportare informazioni del cluster
        self.masterNode = pulumi.Output.from_input('k8s-master')
        self.workerNodes = pulumi.Output.from_input(worker_nodes)

        # Registrare gli output
        self.register_outputs({
            'masterNode': self.masterNode,
            'workerNodes': self.workerNodes
        })

    def install_openserverless_cli(self):
        # Scaricare il CLI di OpenServerless
        subprocess.run(["curl", "-L", "bit.ly/get-ops", "-o", "get-ops.sh"], check=True)
        # Rendere eseguibile lo script
        subprocess.run(["chmod", "+x", "get-ops.sh"], check=True)
        # Eseguire lo script
        try:
            subprocess.run(["./get-ops.sh"], check=True)
        except subprocess.CalledProcessError as e:
            # Mostrare il contenuto dello script in caso di errore
            with open("get-ops.sh", "r") as file:
                script_content = file.read()
            raise RuntimeError(f"Errore durante l'esecuzione dello script get-ops.sh: {e}\nContenuto dello script:\n{script_content}") from e

    def deploy_openserverless(self):
        # Aggiungere la logica di deploy di OpenServerless qui
        pass

    def verify_openserverless_installation(self):
        # Verificare l'installazione di OpenServerless
        try:
            subprocess.run(["ops", "-version"], check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError("Errore: il file scaricato non è un eseguibile valido o non può essere eseguito") from e

# Creare uno stack
stack = ClusterStack("my-cluster", opts=pulumi.ResourceOptions(parent=None))