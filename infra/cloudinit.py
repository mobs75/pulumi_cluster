"""Generazione dello user-data cloud-init per una singola VM.

cloud-init si occupa SOLO del bootstrap del sistema operativo:
hostname, utenti/SSH, pacchetti base, DNS, proxy, CA, moduli kernel e
sysctl richiesti da Kubernetes. Nessuna logica Kubernetes qui: l'installazione
di MicroK8s, il join e gli addon sono gestiti dal layer ``infra.k8s``.

Il template dichiarativo e' in ``cloud-init/base.yaml``; questo modulo aggiunge
soltanto i valori specifici del nodo/ambiente.
"""

from __future__ import annotations

import copy
import os
from typing import Optional

import pulumi
import yaml

from .config import BootstrapConfig, NodeSpec

_TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cloud-init", "base.yaml")


class _Dumper(yaml.SafeDumper):
    """Stringhe multilinea in stile blocco (|), piu' leggibili negli user-data."""


def _str_representer(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str_representer)


def _load_template() -> dict:
    with open(_TEMPLATE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _render(node: NodeSpec, bootstrap: BootstrapConfig, proxy: Optional[str]) -> str:
    data = {"hostname": node.name, "fqdn": node.name, "preserve_hostname": False}
    data.update(copy.deepcopy(_load_template()))

    if bootstrap.ssh_authorized_keys:
        # Chiavi PUBBLICHE per l'utente di default (ubuntu). Mai chiavi private.
        data["ssh_authorized_keys"] = list(bootstrap.ssh_authorized_keys)

    if bootstrap.packages:
        data["packages"] = sorted(set(data.get("packages", [])) | set(bootstrap.packages))

    if bootstrap.timezone:
        data["timezone"] = bootstrap.timezone

    if bootstrap.ca_certs:
        data["ca_certs"] = {"trusted": list(bootstrap.ca_certs)}

    write_files = data.setdefault("write_files", [])
    if bootstrap.dns_servers:
        write_files.append({
            "path": "/etc/systemd/resolved.conf.d/10-cluster-dns.conf",
            "permissions": "0644",
            "content": "[Resolve]\nDNS={}\n".format(" ".join(bootstrap.dns_servers)),
        })
        data.setdefault("runcmd", []).append(["systemctl", "restart", "systemd-resolved"])

    if proxy:
        no_proxy = bootstrap.no_proxy or "localhost,127.0.0.1,10.0.0.0/8,10.152.183.0/24,10.1.0.0/16,.svc,.cluster.local"
        data["apt"] = {"http_proxy": proxy, "https_proxy": proxy}
        env = (
            f"http_proxy={proxy}\nhttps_proxy={proxy}\nno_proxy={no_proxy}\n"
            f"HTTP_PROXY={proxy}\nHTTPS_PROXY={proxy}\nNO_PROXY={no_proxy}\n"
        )
        write_files.append({"path": "/etc/environment.d/90-proxy.conf", "permissions": "0644", "content": env})
        # snapd (e quindi l'installazione di MicroK8s) legge il proxy da qui.
        data.setdefault("snap", {}).setdefault("commands", []).extend([
            ["snap", "set", "system", f"proxy.http={proxy}"],
            ["snap", "set", "system", f"proxy.https={proxy}"],
        ])

    return "#cloud-config\n" + yaml.dump(data, Dumper=_Dumper, sort_keys=False, default_flow_style=False)


def user_data(node: NodeSpec, bootstrap: BootstrapConfig) -> pulumi.Output[str]:
    """Restituisce lo user-data come Output (secret se contiene il proxy)."""
    if bootstrap.http_proxy is None:
        return pulumi.Output.from_input(_render(node, bootstrap, None))
    return pulumi.Output.secret(bootstrap.http_proxy).apply(lambda p: _render(node, bootstrap, p))
