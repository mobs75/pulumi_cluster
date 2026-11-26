"""Contratto del layer distribuzione Kubernetes.

MicroK8s e' l'implementazione attuale. Un futuro backend (es. kubeadm) deve
solo implementare :class:`KubernetesDistribution`, riusando le stesse VM
(:class:`infra.vm.VirtualMachine`) e lo stesso deployment applicativo, che
dipende solo dal kubeconfig esportato.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import List

import pulumi

from ..config import KubernetesConfig
from ..vm import VirtualMachine


@dataclass
class ClusterResult:
    kubeconfig: pulumi.Output[str]
    version: pulumi.Output[str]
    addons: pulumi.Output[str]


class KubernetesDistribution(abc.ABC):
    name: str

    @abc.abstractmethod
    def provision(self, cfg: KubernetesConfig, control_plane: VirtualMachine,
                  workers: List[VirtualMachine]) -> ClusterResult:
        """Installa la distribuzione, crea il cluster, fa il join e abilita gli addon."""
