"""Selezione del VM provider (oggi solo Multipass)."""

from .base import VirtualMachine, VmProvider
from .multipass import MultipassProvider

_PROVIDERS = {MultipassProvider.name: MultipassProvider}


def get_provider(name: str) -> VmProvider:
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise ValueError(f"VM provider '{name}' non supportato (disponibili: {', '.join(_PROVIDERS)})")


__all__ = ["VirtualMachine", "VmProvider", "get_provider"]
