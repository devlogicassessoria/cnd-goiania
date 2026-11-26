#!/usr/bin/env bash
# Roda o robô no Linux direto pelo Python (abre a interface).
# Uso:  ./rodar_linux.sh                      -> interface
#       ./rodar_linux.sh planilha.xlsx ~/saida [--headless]   -> sem interface
set -euo pipefail
cd "$(dirname "$0")"
bash scripts/_python_linux.sh
exec .venv-linux/bin/python app.py "$@"
