"""Programma Pulumi del cluster.

Pipeline: configurazione stack -> cloud-init -> VM provider -> distribuzione
Kubernetes -> output. DEV/UAT/PROD sono stack Pulumi (Pulumi.<env>.yaml) dello
stesso codice.
"""

import pulumi

from infra import cloudinit, config
from infra.k8s import get_distribution
from infra.vm import get_provider

cfg = config.load()

provider = get_provider(cfg.vm_provider)
user_data = {n.name: cloudinit.user_data(n, cfg.bootstrap) for n in cfg.nodes}
vms = {vm.spec.name: vm for vm in provider.create_all(cfg.nodes, user_data)}

control_plane = vms[cfg.control_plane.name]
workers = [vms[n.name] for n in cfg.workers]

cluster = get_distribution(cfg.kubernetes.distribution).provision(cfg.kubernetes, control_plane, workers)

pulumi.export("env", cfg.env)
pulumi.export("vmProvider", provider.name)
pulumi.export("kubernetesDistribution", cfg.kubernetes.distribution)
pulumi.export("kubernetesChannel", cfg.kubernetes.channel)
# Compatibilita' con gli output del progetto originale.
pulumi.export("masterNode", control_plane.spec.name)
pulumi.export("workerNodes", [w.spec.name for w in workers])
pulumi.export("vmNames", [n.name for n in cfg.nodes])
pulumi.export("nodeIps", {name: vm.ip for name, vm in vms.items()})
pulumi.export("kubernetesVersion", cluster.version)
pulumi.export("addons", cluster.addons)
pulumi.export("kubeconfig", cluster.kubeconfig)
