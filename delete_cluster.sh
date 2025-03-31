#!/bin/bash

echo "🔥Eliminazione delle VM del cluster Kubernetes..."

multipass delete --all 2>/dev/null
multipass purge

echo "✅ Cluster rimosso con successo!"
