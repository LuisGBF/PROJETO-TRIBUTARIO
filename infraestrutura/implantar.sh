#!/usr/bin/env bash
# Transfere o simulador da máquina hospedeira para a VM por SCP
# e constrói a imagem Docker dentro da VM
set -euo pipefail

DIR_INFRA="$(cd "$(dirname "$0")" && pwd)"
RAIZ="$(dirname "$DIR_INFRA")"
CHAVE="${CHAVE_SSH:-$HOME/.ssh/vm_pipeline}"
USUARIO="${USUARIO_VM:-pipeline}"
DESTINO="/opt/simulador"
IMAGEM="simulador-tributario"
IP="$(tofu -chdir="$DIR_INFRA" output -raw ip_vm)"

echo "Transferindo o simulador para $USUARIO@$IP:$DESTINO ..."
scp -i "$CHAVE" \
    "$RAIZ/simulador/Dockerfile" \
    "$RAIZ/simulador/.dockerignore" \
    "$RAIZ/simulador/simulador.py" \
    "$RAIZ/simulador/requirements.txt" \
    "$USUARIO@$IP:$DESTINO/"

echo
echo "Construindo a imagem Docker $IMAGEM na VM ..."
ssh -i "$CHAVE" "$USUARIO@$IP" "docker build -t $IMAGEM $DESTINO"

echo
echo "Imagens disponíveis na VM:"
ssh -i "$CHAVE" "$USUARIO@$IP" "docker images $IMAGEM"
