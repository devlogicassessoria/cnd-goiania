"""Orquestra a execução: planilha -> site -> PDF -> leitura -> pasta -> relatório.
Independente da interface: a GUI e o modo linha de comando usam esta mesma classe."""
import os
import re
import threading
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .classificador import (classificar, criar_estrutura, mover, pasta_destino,
                            texto_do_pdf)
from .navegador import ErroRobo, RoboCND
from .planilha import Empresa, ler_empresas
from .ritmo import ControleRitmo


def _nome_arquivo(emp: Empresa, im: str) -> str:
    nome = re.sub(r'[\\/:*?"<>|]+', " ", emp.nome).strip()[:60]
    partes = [p for p in (nome, emp.cnpj, f"IM {im}") if p]
    return "CND " + " - ".join(partes) + ".pdf"


class Processo:
    """Eventos enviados para a interface via callback `evento(tipo, dados)`:
        log            {"msg"}
        empresas       {"lista": [Empresa]}
        status         {"idx", "etapa"}
        resultado      {"idx", "categoria", "arquivo", "detalhe"}
        progresso      {"feitos", "total"}
        fim            {"relatorio"}
    """

    def __init__(self, cfg, planilha, pasta_saida, evento, pedir_captcha=None, headless=None):
        self.cfg = cfg
        self.planilha = planilha
        self.saida = pasta_saida
        self.evento = evento
        self.pedir_captcha = pedir_captcha
        self.headless = headless
        self.parar_evt = threading.Event()
        self.pausa_evt = threading.Event()
        self.pausa_evt.set()  # set = rodando
        self.linhas_relatorio = []
        self.ritmo = ControleRitmo(cfg, log=self.log, parar_evt=self.parar_evt)

    def log(self, msg):
        self.evento("log", {"msg": f"{datetime.now():%H:%M:%S}  {msg}"})

    # controle
    def parar(self):
        self.parar_evt.set()
        self.pausa_evt.set()

    def pausar(self):
        self.pausa_evt.clear()

    def continuar(self):
        self.pausa_evt.set()

    # ------------------------------------------------------------------
    def executar(self):
        relatorio = None
        robo = None
        try:
            municipio = self.cfg.get("filtro_municipio", "")
            empresas = ler_empresas(self.planilha, municipio)
            self.log(f"Planilha lida: {len(empresas)} empresa(s)"
                     + (f" do município {municipio}." if municipio else "."))
            self.evento("empresas", {"lista": empresas})
            nomes = self.cfg["pastas"]
            criar_estrutura(self.saida, nomes)
            tmp = os.path.join(self.saida, "_temp")
            os.makedirs(tmp, exist_ok=True)

            robo = RoboCND(self.cfg, tmp, log=self.log, pedir_captcha=self.pedir_captcha,
                           deve_parar=self.parar_evt.is_set)
            robo.iniciar(self.headless)

            for idx, emp in enumerate(empresas):
                self.pausa_evt.wait()
                if self.parar_evt.is_set():
                    self.log("Execução interrompida pelo usuário.")
                    break
                self._processar(robo, idx, emp, tmp, nomes)
                self.evento("progresso", {"feitos": idx + 1, "total": len(empresas)})
        except Exception as e:
            self.log(f"ERRO GERAL: {e}")
        finally:
            if robo:
                robo.fechar()
            try:
                os.rmdir(os.path.join(self.saida, "_temp"))
            except OSError:
                pass
            if self.linhas_relatorio:
                relatorio = self._gravar_relatorio()
                self.log(f"Relatório salvo: {relatorio}")
            self.evento("fim", {"relatorio": relatorio})

    def _processar(self, robo, idx, emp, tmp, nomes):
        rotulo = emp.nome or emp.cnpj or emp.im
        self.log(f"[{idx + 1}] {rotulo}")
        try:
            # 1) descobrir a(s) inscrição(ões)
            if emp.im:
                ims = [emp.im]
            else:
                if not emp.cnpj:
                    raise ErroRobo("Linha sem CNPJ e sem IM.")
                self.evento("status", {"idx": idx, "etapa": "Consultando IM pelo CNPJ..."})
                self.log(f"   Sem IM na planilha → consultando Situação do Contribuinte ({emp.cnpj})")
                ims = self._com_tentativas(lambda: robo.buscar_ims_por_cnpj(
                    emp.cnpj, os.path.join(self.saida, "_Consultas Contribuinte")))
                emp.ims_encontradas = ims
                self.log(f"   IM encontrada(s): {', '.join(ims)}")

            # 2) emitir a CND de cada inscrição
            for im in ims:
                self.evento("status", {"idx": idx, "etapa": f"Emitindo CND (IM {im})..."})
                pdf, texto_tela = self._com_tentativas(
                    lambda: robo.emitir_cnd_por_im(im, _nome_arquivo(emp, im)))

                # 3) ler a certidão salva e classificar
                self.evento("status", {"idx": idx, "etapa": "Lendo certidão..."})
                texto = texto_do_pdf(pdf)
                res = classificar(texto, self.cfg["classificacao"])
                if res.tipo == "INDEFINIDA" and texto_tela:
                    res = classificar(texto_tela, self.cfg["classificacao"])
                destino = mover(pdf, pasta_destino(self.saida, res, nomes))

                categoria = ("Não classificada" if res.tipo == "INDEFINIDA" else
                             f"{'Com' if res.pendencia == 'COM' else 'Sem'} pendência / "
                             f"{res.tipo.capitalize()}")
                self.log(f"   ✔ {categoria} → {os.path.relpath(destino, self.saida)}")
                self.evento("resultado", {"idx": idx, "categoria": categoria,
                                          "arquivo": destino, "detalhe": res.detalhe, "im": im})
                self._linha(emp, im, categoria, res.detalhe, destino)
        except Exception as e:
            msg = str(e).split("\n")[0][:250]
            self.log(f"   ✖ ERRO: {msg}")
            self.evento("resultado", {"idx": idx, "categoria": "Erro", "arquivo": "", "detalhe": msg,
                                      "im": emp.im})
            self._linha(emp, emp.im, "Erro", msg, "")

    def _com_tentativas(self, func):
        """Cada tentativa é um acesso ao site: passa pelo controle de ritmo antes.
        Falhas técnicas (site fora, lento, erro do navegador) aumentam a espera;
        respostas do próprio site (ErroRobo, ex.: inscrição inválida) não."""
        n = max(1, int(self.cfg.get("tentativas_por_empresa", 2)))
        for t in range(1, n + 1):
            if self.parar_evt.is_set():
                raise ErroRobo("Interrompido pelo usuário.")
            self.ritmo.antes_de_requisitar()
            try:
                r = func()
                self.ritmo.sucesso()
                return r
            except Exception as e:
                cancelado = "cancelada pelo usuário" in str(e)
                falha_tecnica = not isinstance(e, ErroRobo) or "Tempo esgotado" in str(e)
                if t == n or self.parar_evt.is_set() or cancelado:
                    if falha_tecnica and not cancelado and not self.parar_evt.is_set():
                        self.ritmo.erro()
                    raise
                self.log(f"   tentativa {t} falhou ({str(e)[:120]}). Tentando de novo...")
                if falha_tecnica:
                    self.ritmo.erro()

    def _linha(self, emp, im, categoria, detalhe, arquivo):
        self.linhas_relatorio.append([emp.linha, emp.nome, emp.cnpj, emp.im, im, categoria, detalhe,
                                      arquivo, datetime.now().strftime("%d/%m/%Y %H:%M")])

    def _gravar_relatorio(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Resultado"
        cab = ["Linha planilha", "Empresa", "CNPJ", "IM (planilha)", "IM consultada", "Resultado",
               "Detalhe", "Arquivo", "Data/hora"]
        ws.append(cab)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F3864")
        cores = {"Erro": "F8CBAD", "Não classificada": "FFE699"}
        for linha in self.linhas_relatorio:
            ws.append(linha)
            cor = cores.get(linha[5]) or ("C6EFCE" if "Sem pendência / Negativa" in linha[5] else None)
            if cor:
                for c in ws[ws.max_row]:
                    c.fill = PatternFill("solid", fgColor=cor)
        for col, larg in zip("ABCDEFGHI", (8, 40, 18, 14, 14, 28, 45, 60, 17)):
            ws.column_dimensions[col].width = larg
        ws.freeze_panes = "A2"
        caminho = os.path.join(self.saida, f"Relatorio CND {datetime.now():%Y-%m-%d %H-%M}.xlsx")
        wb.save(caminho)
        return caminho
