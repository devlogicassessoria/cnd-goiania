"""Carrega o config.json que fica ao lado do .exe (ou do app.py)."""
import json
import os
import sys


def pasta_base() -> str:
    """Pasta onde está o .exe (PyInstaller) ou o código-fonte."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def recurso_empacotado(nome: str) -> str:
    """Arquivo embutido no .exe (fica em sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", pasta_base())
    return os.path.join(base, nome)


def carregar_config() -> dict:
    # 1º: config.json ao lado do .exe (editável pelo usuário)
    # 2º: config.json embutido no .exe (padrão)
    for caminho in (os.path.join(pasta_base(), "config.json"), recurso_empacotado("config.json")):
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("config.json não encontrado ao lado do executável.")
