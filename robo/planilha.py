"""Leitura da planilha de empresas (CNPJ + Inscrição Municipal)."""
import csv
import re
import unicodedata
from dataclasses import dataclass, field

from openpyxl import load_workbook


@dataclass
class Empresa:
    linha: int
    cnpj: str
    im: str = ""
    nome: str = ""
    # preenchidos durante a execução
    ims_encontradas: list = field(default_factory=list)


def _norm(txt) -> str:
    txt = "" if txt is None else str(txt)
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt).strip().upper()


def so_digitos(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return re.sub(r"\D", "", str(valor))


def formatar_cnpj(cnpj: str) -> str:
    d = so_digitos(cnpj)
    if 0 < len(d) < 14 and len(d) > 11:  # Excel comeu zeros à esquerda
        d = d.zfill(14)
    return d


ALIAS_CNPJ = ("CNPJ", "CPF/CNPJ", "CNPJ/CPF")
ALIAS_IM = ("IM", "I.M", "I.M.", "INSCRICAO MUNICIPAL", "INSC MUNICIPAL", "INSC. MUNICIPAL",
            "INSCR MUNICIPAL", "INSCRICAO", "CAE", "INSCRICAO CAE", "INSC. MUN.", "INSC MUN")
ALIAS_NOME = ("RAZAO SOCIAL", "RAZAO", "EMPRESA", "NOME", "CLIENTE", "NOME EMPRESARIAL")
ALIAS_MUNICIPIO = ("MUNICIPIO", "CIDADE", "MUNICIPIO/UF", "CIDADE/UF")


def _achar_coluna(cabecalho, aliases, contem=False):
    for i, c in enumerate(cabecalho):
        if c in aliases:
            return i
    if contem:
        for i, c in enumerate(cabecalho):
            if any(a in c for a in aliases if len(a) > 3):
                return i
    return None


def _ler_linhas(caminho):
    if caminho.lower().endswith(".csv"):
        with open(caminho, "r", encoding="utf-8-sig", errors="replace") as f:
            amostra = f.read(2048)
            f.seek(0)
            sep = ";" if amostra.count(";") >= amostra.count(",") else ","
            return [row for row in csv.reader(f, delimiter=sep)]
    wb = load_workbook(caminho, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    linhas = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return linhas


def ler_empresas(caminho: str, municipio: str = "") -> list[Empresa]:
    """Lê CNPJ + IM. Se `municipio` vier preenchido e a planilha tiver coluna
    Município/Cidade, só entram as linhas daquele município (comparação exata,
    sem acento: "GOIANIA" não pega "APARECIDA DE GOIANIA" nem "GOIANIRA")."""
    linhas = _ler_linhas(caminho)
    # procura o cabeçalho nas 15 primeiras linhas
    idx_cab = None
    for i, row in enumerate(linhas[:15]):
        cab = [_norm(c) for c in row]
        if _achar_coluna(cab, ALIAS_CNPJ, contem=True) is not None:
            idx_cab = i
            break
    if idx_cab is None:
        raise ValueError("Não achei a coluna CNPJ na planilha (procurei nas 15 primeiras linhas).")

    cab = [_norm(c) for c in linhas[idx_cab]]
    c_cnpj = _achar_coluna(cab, ALIAS_CNPJ, contem=True)
    c_im = _achar_coluna(cab, ALIAS_IM, contem=True)
    c_nome = _achar_coluna(cab, ALIAS_NOME, contem=True)
    if c_nome is None and cab and cab[0] == "":
        c_nome = 0  # ex.: "Controle de Licenças" – 1ª coluna sem título = nome da empresa
    c_mun = _achar_coluna(cab, ALIAS_MUNICIPIO, contem=True)
    filtro = _norm(municipio)
    if filtro and c_mun is None:
        raise ValueError(f"Filtro de município '{municipio}' ligado, mas não achei a coluna Município/Cidade.")

    empresas = []
    for n, row in enumerate(linhas[idx_cab + 1:], start=idx_cab + 2):
        get = lambda c: row[c] if c is not None and c < len(row) else None
        cnpj = formatar_cnpj(get(c_cnpj))
        im = so_digitos(get(c_im))
        if not cnpj and not im:
            continue
        if filtro and _norm(get(c_mun)) != filtro:
            continue
        nome = str(get(c_nome) or "").strip()
        empresas.append(Empresa(linha=n, cnpj=cnpj, im=im, nome=nome))
    return empresas
