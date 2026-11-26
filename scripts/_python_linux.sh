#!/usr/bin/env bash
# Prepara .venv-linux com um Python que TENHA tkinter.
# Se o python3 do sistema não tiver tkinter (falta o pacote python3-tk),
# usa o "uv" para baixar um Python completo, sem precisar de sudo.
set -euo pipefail
cd "$(dirname "$0")/.."
VENV=.venv-linux
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c "import tkinter" 2>/dev/null; then
    rm -rf "$VENV"
    if python3 -c "import tkinter" 2>/dev/null; then
        echo ">> Criando ambiente com o python3 do sistema..."
        python3 -m venv "$VENV"
    else
        echo ">> python3 do sistema sem tkinter -> usando uv (Python standalone, sem sudo)..."
        UV=$(command -v uv || true)
        if [ -z "$UV" ]; then
            python3 -m venv .tools
            .tools/bin/pip install -q uv
            UV=.tools/bin/uv
        fi
        "$UV" venv --python 3.12 --seed "$VENV"
    fi
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -r requirements.txt pytest pyflakes
