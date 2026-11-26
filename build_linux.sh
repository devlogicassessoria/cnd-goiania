#!/usr/bin/env bash
# Gera o executável Linux: dist/linux/CND_Goiania (+ config.json editável)
set -euo pipefail
cd "$(dirname "$0")"
bash scripts/_python_linux.sh
.venv-linux/bin/python -m pytest tests -q
.venv-linux/bin/pyinstaller --noconfirm --clean --onefile --windowed \
  --name CND_Goiania --add-data "$PWD/config.json:." --add-data "$PWD/assets:assets" --collect-all selenium \
  --distpath dist/linux --workpath build/linux --specpath build/linux \
  app.py
cp -f config.json dist/linux/config.json
echo; echo "Pronto: dist/linux/CND_Goiania (+ dist/linux/config.json)"
