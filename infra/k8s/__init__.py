"""Selezione della distribuzione Kubernetes (oggi solo MicroK8s)."""

from .base import ClusterResult, KubernetesDistribution
from .microk8s import MicroK8s

_DISTRIBUTIONS = {MicroK8s.name: MicroK8s}


def get_distribution(name: str) -> KubernetesDistribution:
    try:
        return _DISTRIBUTIONS[name]()
    except KeyError:
        raise ValueError(f"distribuzione Kubernetes '{name}' non supportata (disponibili: {', '.join(_DISTRIBUTIONS)})")


__all__ = ["ClusterResult", "KubernetesDistribution", "get_distribution"]
