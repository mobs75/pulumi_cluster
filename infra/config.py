"""Lettura e validazione della configurazione dello stack Pulumi.

Tutta la configurazione infrastrutturale (numero nodi, risorse, versioni,
addon...) vive nei file ``Pulumi.<stack>.yaml``. Questo modulo la traduce
in oggetti tipizzati, cosi' che gli altri layer non leggano mai
``pulumi.Config`` direttamente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pulumi

ROLE_CONTROL_PLANE = "control-plane"
ROLE_WORKER = "worker"


@dataclass(frozen=True)
class NodeSpec:
    """Descrizione di una singola VM, indipendente dal provider."""

    name: str
    role: str
    cpus: int
    memory: str
    disk: str
    image: str


@dataclass(frozen=True)
class BootstrapConfig:
    """Parametri del bootstrap OS (cloud-init)."""

    ssh_authorized_keys: List[str] = field(default_factory=list)
    packages: List[str] = field(default_factory=list)
    dns_servers: List[str] = field(default_factory=list)
    ca_certs: List[str] = field(default_factory=list)
    timezone: Optional[str] = None
    # Il proxy puo' contenere credenziali: viene letto come secret.
    http_proxy: Optional[pulumi.Output[str]] = None
    no_proxy: Optional[str] = None


@dataclass(frozen=True)
class KubernetesConfig:
    """Parametri del layer Kubernetes."""

    distribution: str
    channel: str
    addons: List[str]
    join_as_worker: bool
    registry_mirror: bool


@dataclass(frozen=True)
class ClusterConfig:
    env: str
    name_prefix: str
    vm_provider: str
    nodes: List[NodeSpec]
    bootstrap: BootstrapConfig
    kubernetes: KubernetesConfig

    @property
    def control_plane(self) -> NodeSpec:
        return next(n for n in self.nodes if n.role == ROLE_CONTROL_PLANE)

    @property
    def workers(self) -> List[NodeSpec]:
        return [n for n in self.nodes if n.role == ROLE_WORKER]


def _node_group(raw: dict, defaults: dict, key: str) -> dict:
    group = dict(defaults)
    group.update(raw.get(key) or {})
    return group


def load() -> ClusterConfig:
    env = pulumi.get_stack()
    cluster = pulumi.Config("cluster")
    k8s = pulumi.Config("k8s")

    prefix = cluster.require("namePrefix")
    image = cluster.get("image") or "24.04"

    nodes_cfg = cluster.require_object("nodes")
    defaults = {"cpus": 2, "memory": "4G", "disk": "20G"}
    cp = _node_group(nodes_cfg, defaults, "controlPlane")
    wk = _node_group(nodes_cfg, defaults, "workers")

    # Naming compatibile con il progetto originale: <prefix>-master, <prefix>-node<N>
    nodes: List[NodeSpec] = [
        NodeSpec(
            name=f"{prefix}-master",
            role=ROLE_CONTROL_PLANE,
            cpus=int(cp["cpus"]),
            memory=str(cp["memory"]),
            disk=str(cp["disk"]),
            image=str(cp.get("image", image)),
        )
    ]
    for i in range(1, int(wk.get("count", 0)) + 1):
        nodes.append(
            NodeSpec(
                name=f"{prefix}-node{i}",
                role=ROLE_WORKER,
                cpus=int(wk["cpus"]),
                memory=str(wk["memory"]),
                disk=str(wk["disk"]),
                image=str(wk.get("image", image)),
            )
        )

    bootstrap = BootstrapConfig(
        ssh_authorized_keys=cluster.get_object("sshAuthorizedKeys") or [],
        packages=cluster.get_object("packages") or [],
        dns_servers=cluster.get_object("dnsServers") or [],
        ca_certs=cluster.get_object("caCerts") or [],
        timezone=cluster.get("timezone"),
        http_proxy=cluster.get_secret("httpProxy"),
        no_proxy=cluster.get("noProxy"),
    )

    channel = k8s.require("channel")
    if channel in ("latest", "latest/stable") or channel.startswith("latest/"):
        raise ValueError("k8s:channel deve essere una versione esplicita (es. 1.33/stable), non 'latest'")

    kubernetes = KubernetesConfig(
        distribution=k8s.get("distribution") or "microk8s",
        channel=channel,
        addons=k8s.get_object("addons") or [],
        join_as_worker=k8s.get_bool("joinAsWorker") if k8s.get_bool("joinAsWorker") is not None else True,
        registry_mirror=bool(k8s.get_bool("registryMirror")),
    )

    return ClusterConfig(
        env=env,
        name_prefix=prefix,
        vm_provider=cluster.get("vmProvider") or "multipass",
        nodes=nodes,
        bootstrap=bootstrap,
        kubernetes=kubernetes,
    )
