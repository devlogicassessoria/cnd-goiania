#!/usr/bin/env bash
# Gera o CND_Goiania.exe (Windows) a partir do Linux, usando Docker + Wine
# (imagem tobix/pywine = Python para Windows rodando no Wine + PyInstaller).
# Saída: dist/windows/CND_Goiania.exe (+ config.json editável)
set -euo pipefail
cd "$(dirname "$0")"
IMG=${PYWINE_IMAGE:-tobix/pywine:3.12}
docker run --rm -v "$PWD":/src -w /src "$IMG" bash -c '
  set -e
  wine python -m pip install -q --upgrade pip
  wine python -m pip install -q -r requirements.txt
  wine pyinstaller --noconfirm --clean --onefile --windowed \
    --name CND_Goiania --add-data "Z:/src/config.json;." --add-data "Z:/src/assets;assets" --icon "Z:/src/assets/icone.ico" --collect-all selenium \
    --distpath dist/windows --workpath build/windows --specpath build/windows \
    app.py
  chown -R '"$(id -u):$(id -g)"' dist build
'
cp -f config.json dist/windows/config.json
echo; echo "Pronto: dist/windows/CND_Goiania.exe (+ dist/windows/config.json)"

# deixa o .exe na raiz do repositório: quem clonar só dá dois cliques
cp -f dist/windows/CND_Goiania.exe ./CND_Goiania.exe
echo "Copiado para ./CND_Goiania.exe (versionado no git)"
