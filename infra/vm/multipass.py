"""VM provider Multipass (provider VM corrente).

Ogni VM e' una risorsa Pulumi ``command.local.Command``:

* ``create``: lancia la VM solo se non esiste (idempotente, adotta anche VM gia'
  presenti con lo stesso nome), passa lo user-data cloud-init via stdin e
  attende la fine di cloud-init; stampa l'IPv4 della VM.
* ``delete``: elimina SOLO quella VM (``multipass delete --purge <nome>``).

Un cambio di CPU/RAM/disco/immagine/user-data sostituisce la VM
(delete-before-replace, perche' il nome e' lo stesso).
Nessuna logica Kubernetes in questo modulo.
"""

from __future__ import annotations

import hashlib

import pulumi
import pulumi_command as command

from ..config import NodeSpec
from .base import VirtualMachine, VmProvider

_CREATE = r"""
set -eu
if multipass info "$VM" >/dev/null 2>&1; then
  echo "VM $VM gia' presente: la adotto senza ricrearla" >&2
else
  multipass launch --name "$VM" --cpus "$CPUS" --memory "$MEMORY" --disk "$DISK" \
    --timeout 1200 --cloud-init - "$IMAGE" >&2
fi
rc=0
multipass exec "$VM" -- cloud-init status --wait >&2 || rc=$?
# rc=2: completato con warning non bloccanti
if [ "$rc" -eq 1 ]; then
  echo "cloud-init fallito su $VM: 'task logs NODE=$VM LOG=cloud-init'" >&2
  exit 1
fi
multipass info --format json "$VM" | jq -r --arg vm "$VM" '.info[$vm].ipv4[0]'
"""

_DELETE = r"""
multipass delete --purge "$VM" 2>/dev/null || true
"""


class MultipassProvider(VmProvider):
    name = "multipass"

    def create(self, spec: NodeSpec, user_data, opts=None) -> VirtualMachine:
        ud_hash = pulumi.Output.from_input(user_data).apply(
            lambda s: hashlib.sha256(s.encode()).hexdigest()
        )
        vm = command.local.Command(
            f"vm-{spec.name}",
            create=_CREATE,
            delete=_DELETE,
            interpreter=["/usr/bin/env", "bash", "-c"],
            stdin=user_data,
            environment={
                "VM": spec.name,
                "CPUS": str(spec.cpus),
                "MEMORY": spec.memory,
                "DISK": spec.disk,
                "IMAGE": spec.image,
            },
            triggers=[spec.cpus, spec.memory, spec.disk, spec.image, ud_hash],
            opts=pulumi.ResourceOptions.merge(
                opts,
                pulumi.ResourceOptions(delete_before_replace=True, custom_timeouts=pulumi.CustomTimeouts(create="30m")),
            ),
        )
        return VirtualMachine(
            spec=spec,
            resource=vm,
            ip=vm.stdout.apply(lambda s: s.strip().splitlines()[-1] if s.strip() else ""),
            exec_prefix=f"multipass exec {spec.name} -- sudo bash -s",
        )
