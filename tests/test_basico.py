"""Testes offline (não acessam o site). Rodar: python -m pytest tests -q"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openpyxl import Workbook

from robo.classificador import classificar, pasta_destino
from robo.navegador import extrair_ims
from robo.planilha import ler_empresas

CFG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config.json"), encoding="utf-8"))
R = CFG["classificacao"]


def test_planilha_com_e_sem_im():
    wb = Workbook()
    ws = wb.active
    ws.append(["Relação de clientes"])
    ws.append(["Razão Social", "CNPJ", "Inscrição Municipal"])
    ws.append(["Farmácia A", "12.345.678/0001-90", 1234567])
    ws.append(["Empresa B", 1234567000190, None])   # Excel comeu o zero
    ws.append([None, None, None])
    p = os.path.join(tempfile.mkdtemp(), "t.xlsx")
    wb.save(p)
    emp = ler_empresas(p)
    assert len(emp) == 2
    assert emp[0].cnpj == "12345678000190" and emp[0].im == "1234567" and emp[0].nome == "Farmácia A"
    assert emp[1].cnpj == "01234567000190" and emp[1].im == ""


def test_negativa_sem_pendencia():
    r = classificar("CERTIDÃO NEGATIVA DE DÉBITOS MOBILIÁRIOS ... não constam pendências", R)
    assert (r.tipo, r.pendencia) == ("NEGATIVA", "SEM")


def test_positiva_com_pendencia():
    r = classificar("CERTIDÃO POSITIVA DE DÉBITOS. Constam débitos em aberto (pendências)", R)
    assert (r.tipo, r.pendencia) == ("POSITIVA", "COM")


def test_positiva_efeito_negativa():
    r = classificar("CERTIDÃO POSITIVA COM EFEITO DE NEGATIVA - débitos parcelados", R)
    assert (r.tipo, r.pendencia) == ("NEGATIVA", "COM")


def test_indefinida_vai_para_nao_classificadas():
    r = classificar("texto qualquer", R)
    assert pasta_destino("X", r, CFG["pastas"]).endswith("_Nao Classificadas")
    r2 = classificar("CERTIDAO NEGATIVA DE DEBITOS", R)
    assert pasta_destino("X", r2, CFG["pastas"]) == os.path.join("X", "Sem Pendencia", "Negativa")


def test_extrair_ims():
    txt = "CNPJ: 12.345.678/0001-90\nInscrição Municipal: 123.456-7\nSituação: ATIVA"
    assert extrair_ims(txt, "12345678000190") == ["1234567"]


def test_planilha_controle_licencas_filtra_goiania():
    wb = Workbook()
    ws = wb.active
    ws.append([" ", "SITUAÇÃO", "CNPJ", "INSCRIÇÃO MUNICIPAL", "INSCRIÇÃO ESTADUAL", "MUNICIPIO", "ESTADO"])
    ws.append(["EMPRESA A", "ATIVA", "21.085.714/0001-10", 3921301, 106178016, "GOIÂNIA", "GOIÁS"])
    ws.append(["EMPRESA B", "ATIVA", "63.696.485/0001-10", 3110162959, 203422783, "APARECIDA DE GOIÂNIA", "GOIÁS"])
    ws.append(["EMPRESA C", "ATIVA", "11.111.111/0001-11", 1, 2, "GOIANIRA", "GOIÁS"])
    ws.append(["EMPRESA D", "ATIVA", 294440000107, "Pendente", "NA", "GOIANIA ", "GOIÁS"])
    p = os.path.join(tempfile.mkdtemp(), "licencas.xlsx")
    wb.save(p)
    emp = ler_empresas(p, "GOIANIA")
    assert [(e.nome, e.cnpj, e.im) for e in emp] == [
        ("EMPRESA A", "21085714000110", "3921301"),   # IM certa, não a estadual
        ("EMPRESA D", "00294440000107", ""),          # zeros repostos; sem IM -> busca pelo CNPJ
    ]
    assert len(ler_empresas(p)) == 4                  # sem filtro lê tudo


# trechos reais das certidões emitidas pelo site em 26/11/2026
CND_NEGATIVA_REAL = """PREFEITURA MUNICIPAL DE GOIÂNIA
CERTIDÃO DE REGULARIDADE FISCAL MOBILIÁRIA
NEGATIVA DE DÉBITOS MOBILIÁRIOS
NÚMERO DA CERTIDÃO: 2.917.572-0
Certifica-se que até a presente data NÃO CONSTA DÉBITO VENCIDO OU A VENCER referente aos tributos
de natureza mobiliária desta inscrição, e que estão cumpridas as obrigações acessórias"""
CND_POSITIVA_REAL = """PREFEITURA MUNICIPAL DE GOIÂNIA
CERTIDÃO DE REGULARIDADE FISCAL MOBILIÁRIA
POSITIVA DE DÉBITOS MOBILIÁRIOS
NÚMERO DA CERTIDÃO: 2.917.541-2
Certifica-se que até a presente data CONSTAM DÉBITOS VENCIDOS
(AJUIZADOS OU NÃO) referente aos tributos de natureza mobiliária desta inscrição,
e/ou que não foram cumpridas as obrigações acessórias"""


def test_certidoes_reais_reconhecidas_e_classificadas():
    from robo.navegador import MARCADORES_CERTIDAO, _norm
    for txt in (CND_NEGATIVA_REAL, CND_POSITIVA_REAL):
        assert any(m in _norm(txt) for m in MARCADORES_CERTIDAO)
    neg = classificar(CND_NEGATIVA_REAL, R)
    assert (neg.tipo, neg.pendencia) == ("NEGATIVA", "SEM")
    pos = classificar(CND_POSITIVA_REAL, R)
    assert (pos.tipo, pos.pendencia) == ("POSITIVA", "COM")


def test_controle_ritmo():
    from robo.ritmo import ControleRitmo
    t = [0.0]
    esperas = []

    def dormir(s):
        esperas.append(s)
        t[0] += s

    cfg = {"controle_requisicoes": {"intervalo_min_segundos": 5, "intervalo_max_segundos": 5,
                                    "pausa_longa_a_cada": 3, "pausa_longa_min_segundos": 100,
                                    "pausa_longa_max_segundos": 100, "maximo_por_hora": 0,
                                    "espera_apos_erro_segundos": 10, "espera_maxima_apos_erro_segundos": 15,
                                    "erros_seguidos_para_resfriar": 3, "resfriamento_segundos": 600}}
    r = ControleRitmo(cfg, log=lambda m: None, relogio=lambda: t[0], dormir=dormir)
    for _ in range(4):
        r.antes_de_requisitar()
    assert esperas == [5, 5, 100]            # intervalo, intervalo, pausa longa na 4ª
    esperas.clear()
    r.erro(); r.erro(); r.erro()
    assert 8 <= esperas[0] <= 12 and 12 <= esperas[1] <= 18 and esperas[2] == 600  # backoff e resfriamento

    # teto por hora: 2/h -> a 3ª espera a janela de 1h abrir
    t[0] = 0.0
    esperas.clear()
    cfg["controle_requisicoes"].update(maximo_por_hora=2, pausa_longa_a_cada=0, intervalo_min_segundos=0,
                                       intervalo_max_segundos=0)
    r = ControleRitmo(cfg, log=lambda m: None, relogio=lambda: t[0], dormir=dormir)
    for _ in range(3):
        r.antes_de_requisitar()
    assert esperas and esperas[-1] >= 3600 - 1
