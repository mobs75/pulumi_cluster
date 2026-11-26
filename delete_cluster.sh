#!/bin/bash
# Compatibilita' con il vecchio script: ora elimina SOLO le VM dello stack
# indicato (default dev) tramite Pulumi, non tutte le VM Multipass dell'host.
# Uso: ./delete_cluster.sh [dev|uat|prod]
set -euo pipefail
ENV="${1:-dev}"
echo "Eliminazione del cluster '$ENV' (pulumi destroy)..."
exec task destroy ENV="$ENV"
