"""Lê o texto da certidão e decide a pasta de destino.

Estrutura gerada:
    <saída>/Com Pendencia/Positiva
    <saída>/Com Pendencia/Negativa
    <saída>/Sem Pendencia/Positiva
    <saída>/Sem Pendencia/Negativa
    <saída>/_Nao Classificadas
As palavras-chave ficam no config.json (bloco "classificacao").
"""
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass

from pypdf import PdfReader


def normalizar(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt).upper()


def texto_do_pdf(caminho: str) -> str:
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(caminho).pages)
    except Exception:
        return ""


@dataclass
class Resultado:
    tipo: str          # POSITIVA | NEGATIVA | INDEFINIDA
    pendencia: str     # COM | SEM
    detalhe: str = ""  # ex.: "Positiva com efeito de negativa"


def classificar(texto: str, regras: dict) -> Resultado:
    t = normalizar(texto)
    tem = lambda chaves: any(normalizar(k) in t for k in chaves)

    efeito_neg = tem(regras["palavras_efeito_negativa"])
    if efeito_neg:
        tipo = regras.get("efeito_negativa_vai_para", "NEGATIVA").upper()
        detalhe = "Positiva com efeito de negativa"
    elif tem(regras["palavras_positiva"]):
        tipo, detalhe = "POSITIVA", "Certidão positiva"
    elif tem(regras["palavras_negativa"]):
        tipo, detalhe = "NEGATIVA", "Certidão negativa"
    else:
        tipo, detalhe = "INDEFINIDA", "Tipo não identificado no texto"

    # pendência: remove as frases que NEGAM pendência e procura o que sobrou
    t_limpo = t
    for frase in regras["frases_sem_pendencia"]:
        t_limpo = t_limpo.replace(normalizar(frase), " ")
    com_pend = any(normalizar(k) in t_limpo for k in regras["palavras_pendencia"])
    if efeito_neg and regras.get("efeito_negativa_conta_como_pendencia", True):
        com_pend = True

    return Resultado(tipo=tipo, pendencia="COM" if com_pend else "SEM", detalhe=detalhe)


def pasta_destino(base: str, res: Resultado, nomes: dict) -> str:
    if res.tipo == "INDEFINIDA":
        return os.path.join(base, nomes["nao_classificada"])
    p1 = nomes["com_pendencia"] if res.pendencia == "COM" else nomes["sem_pendencia"]
    p2 = nomes["positiva"] if res.tipo == "POSITIVA" else nomes["negativa"]
    return os.path.join(base, p1, p2)


def criar_estrutura(base: str, nomes: dict):
    for p1 in (nomes["com_pendencia"], nomes["sem_pendencia"]):
        for p2 in (nomes["positiva"], nomes["negativa"]):
            os.makedirs(os.path.join(base, p1, p2), exist_ok=True)
    os.makedirs(os.path.join(base, nomes["nao_classificada"]), exist_ok=True)


def mover(arquivo: str, destino_dir: str) -> str:
    os.makedirs(destino_dir, exist_ok=True)
    destino = os.path.join(destino_dir, os.path.basename(arquivo))
    if os.path.exists(destino):
        raiz, ext = os.path.splitext(destino)
        i = 2
        while os.path.exists(f"{raiz} ({i}){ext}"):
            i += 1
        destino = f"{raiz} ({i}){ext}"
    shutil.move(arquivo, destino)
    return destino
