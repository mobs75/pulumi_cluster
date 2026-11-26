"""Contratto del layer VM provider.

Il resto del progetto (layer Kubernetes, output, Taskfile applicativo) dipende
solo da :class:`VmProvider` e :class:`VirtualMachine`, mai da Multipass
direttamente. Un futuro backend (es. libvirt/KVM) deve solo implementare
questa interfaccia.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Sequence

import pulumi

from ..config import NodeSpec


@dataclass
class VirtualMachine:
    """Una VM creata dal provider.

    ``exec_prefix`` e' il comando shell (sull'host operatore) che esegue lo
    stdin come script ``bash`` con privilegi root dentro la VM. Il layer
    Kubernetes lo usa per tutte le operazioni sul nodo, senza sapere quale
    provider c'e' sotto (``multipass exec``, ``ssh``, ...).
    """

    spec: NodeSpec
    resource: pulumi.Resource
    ip: pulumi.Output[str]
    exec_prefix: str


class VmProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    def create(
        self,
        spec: NodeSpec,
        user_data: pulumi.Output[str],
        opts: pulumi.ResourceOptions | None = None,
    ) -> VirtualMachine:
        """Crea (in modo idempotente) la VM e attende la fine di cloud-init."""

    def create_all(
        self,
        specs: Sequence[NodeSpec],
        user_data: dict,
        opts: pulumi.ResourceOptions | None = None,
    ) -> list[VirtualMachine]:
        return [self.create(s, user_data[s.name], opts) for s in specs]
