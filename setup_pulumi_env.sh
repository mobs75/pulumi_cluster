#!/bin/bash

# Nome dell'env e script
VENV_DIR="venv"
SCRIPT_NAME="pulumi_microk8s_provisioning.py"

# Controlla se venv esiste, altrimenti lo crea
if [ ! -d "$VENV_DIR" ]; then
    echo "[+] Creo virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Attiva il virtual environment
echo "[+] Attivo virtual environment..."
source "$VENV_DIR/bin/activate"

# Installa pulumi se non già presente
if ! python -c "import pulumi" &> /dev/null; then
    echo "[+] Installo pulumi..."
    pip install --upgrade pip
    pip install pulumi
else
    echo "[✓] Pulumi già installato."
fi

# Avvia lo script
echo "[🚀] Avvio script: $SCRIPT_NAME"
python "$SCRIPT_NAME"
