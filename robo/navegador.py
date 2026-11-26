"""Automação Selenium dos sites da Prefeitura de Goiânia.

Fluxos:
  1) emitir_cnd_por_im(im)      -> Certidões > Débitos Mobiliários (CAE) >
                                   Conjunta de Débitos Mobiliários > Inscrição CAE + "." > Emitir
  2) buscar_ims_por_cnpj(cnpj)  -> Situação do Contribuinte > CNPJ sem pontuação + "." > Consulta

Os sites usam frames (ASP antigo). Toda busca de elemento percorre os frames
recursivamente, então o robô não depende da posição exata do frame.
"""
import base64
import os
import re
import time
import unicodedata

from selenium import webdriver
from selenium.common.exceptions import (NoAlertPresentException, NoSuchFrameException,
                                        StaleElementReferenceException, WebDriverException)
from selenium.webdriver.common.by import By

# ---------------------------------------------------------------- seletores
XP_LINK_DEB_MOBILIARIOS = "//a[contains(normalize-space(.),'bitos Mobili') and not(contains(.,'Conjunta'))]"
XP_LINK_CONJUNTA = "//a[contains(normalize-space(.),'Conjunta de D') and contains(.,'bitos Mobili')]"
XP_CAMPO_CAE = ("//td[contains(normalize-space(.),'Inscri') and contains(.,'CAE')]/following-sibling::td//input"
                "[not(@type) or @type='text']")
XP_CAMPO_CNPJ = ("//td[contains(normalize-space(.),'CNPJ/CPF')]/following-sibling::td//input"
                 "[not(@type) or @type='text']")
XP_IMG_CAPTCHA = ("//img[contains(translate(@src,'GERAL','geral'),'geral00005') "
                  "or following-sibling::a[contains(.,'Trocar caracteres')] "
                  "or ../a[contains(.,'Trocar caracteres')]]")
XP_INPUTS_TEXTO = "//input[not(@type) or @type='text']"

# textos que só aparecem na certidão emitida (não no menu nem no formulário)
MARCADORES_CERTIDAO = ("REGULARIDADE FISCAL MOBILIARIA", "NEGATIVA DE DEBITOS MOBILIARIOS",
                       "POSITIVA DE DEBITOS MOBILIARIOS", "NUMERO DA CERTIDAO",
                       "CERTIDAO NEGATIVA DE DEB", "CERTIDAO POSITIVA", "CONJUNTA NEGATIVA",
                       "CONJUNTA POSITIVA", "EFEITO DE NEGATIVA", "EFEITOS DE NEGATIVA",
                       "RESSALVADO O DIREITO", "CONSTAM DEBITOS", "CONSTAM PENDENCIAS",
                       "CODIGO DE CONTROLE", "CODIGO DE AUTENTICIDADE", "AUTENTICACAO")


def botao_xpath(texto):
    return (f"//input[(@type='submit' or @type='button' or @type='image') and contains(@value,'{texto}')]"
            f" | //button[contains(normalize-space(.),'{texto}')]")


def _norm(txt):
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt).upper()


class ErroRobo(Exception):
    pass


class RoboCND:
    def __init__(self, cfg, pasta_saida, log=print, pedir_captcha=None, deve_parar=lambda: False):
        self.cfg = cfg
        self.saida = pasta_saida
        self.log = log
        self.pedir_captcha = pedir_captcha
        self.deve_parar = deve_parar
        self.timeout = cfg.get("timeout_segundos", 30)
        self.driver = None
        self.janela_principal = None

    # ------------------------------------------------------------ navegador
    def iniciar(self, headless=None):
        headless = self.cfg.get("headless", False) if headless is None else headless
        op = webdriver.ChromeOptions()
        if headless:
            op.add_argument("--headless=new")
        op.add_argument("--window-size=1280,1000")
        op.add_argument("--disable-gpu")
        op.add_argument("--no-first-run")
        for arg in self.cfg.get("chrome_argumentos_extras", []):
            op.add_argument(arg)
        op.add_experimental_option("excludeSwitches", ["enable-logging"])
        op.add_experimental_option("prefs", {
            "download.default_directory": os.path.abspath(self.saida),
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
        })
        self.log("Abrindo o Google Chrome...")
        # Selenium 4.6+ baixa o chromedriver certo sozinho (Selenium Manager)
        from selenium.webdriver.chrome.service import Service
        servico = Service(executable_path=self.cfg.get("chromedriver_caminho") or None,
                          service_args=self.cfg.get("chromedriver_argumentos", []))
        self.driver = webdriver.Chrome(options=op, service=servico)
        self.driver.set_page_load_timeout(self.timeout * 2)
        self.janela_principal = self.driver.current_window_handle

    def fechar(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    # ------------------------------------------------------------ frames
    def _dfs(self, xpath, so_visivel=True, prof=0):
        for el in self.driver.find_elements(By.XPATH, xpath):
            try:
                if not so_visivel or el.is_displayed():
                    return el
            except StaleElementReferenceException:
                continue
        if prof > 4:
            return None
        frames = self.driver.find_elements(By.XPATH, "//frame | //iframe")
        for i in range(len(frames)):
            try:
                frames = self.driver.find_elements(By.XPATH, "//frame | //iframe")
                self.driver.switch_to.frame(frames[i])
            except (NoSuchFrameException, IndexError, StaleElementReferenceException):
                continue
            achado = self._dfs(xpath, so_visivel, prof + 1)
            if achado is not None:
                return achado
            self.driver.switch_to.parent_frame()
        return None

    def procurar(self, xpath, timeout=None, obrigatorio=True):
        """Procura o elemento em todos os frames. Deixa o driver DENTRO do frame achado."""
        fim = time.time() + (self.timeout if timeout is None else timeout)
        while True:
            self._alerta()  # alerta pendente trava tudo
            self.driver.switch_to.default_content()
            el = self._dfs(xpath)
            if el is not None:
                return el
            if time.time() > fim:
                if obrigatorio:
                    raise ErroRobo(f"Elemento não encontrado: {xpath}")
                return None
            time.sleep(0.5)

    def texto_completo(self):
        """Texto visível de todos os frames da janela atual."""
        partes = []

        def coleta(prof=0):
            try:
                partes.append(self.driver.find_element(By.TAG_NAME, "body").text)
            except Exception:
                pass
            if prof > 4:
                return
            n = len(self.driver.find_elements(By.XPATH, "//frame | //iframe"))
            for i in range(n):
                try:
                    self.driver.switch_to.frame(self.driver.find_elements(By.XPATH, "//frame | //iframe")[i])
                    coleta(prof + 1)
                    self.driver.switch_to.parent_frame()
                except Exception:
                    continue

        self.driver.switch_to.default_content()
        coleta()
        self.driver.switch_to.default_content()
        return "\n".join(p for p in partes if p)

    def _alerta(self):
        try:
            al = self.driver.switch_to.alert
            txt = al.text
            al.accept()
            return txt
        except NoAlertPresentException:
            return None
        except WebDriverException:
            return None

    def _voltar_janela_principal(self):
        for h in list(self.driver.window_handles):
            if h != self.janela_principal:
                try:
                    self.driver.switch_to.window(h)
                    self.driver.close()
                except Exception:
                    pass
        self.driver.switch_to.window(self.janela_principal)

    # ------------------------------------------------------------ formulário genérico
    def _captcha_png(self):
        img = self._dfs(XP_IMG_CAPTCHA)
        return img.screenshot_as_png if img is not None else self.driver.get_screenshot_as_png()

    def _enviar_formulario(self, abrir, xp_campo, valor, texto_botao, descricao):
        """Abre o formulário, preenche, coloca '.' na verificação e envia.
        Se o '.' for recusado e o modo manual estiver ligado, pede o captcha na interface.
        Retorna quando a página de resultado estiver carregada (driver na janela do resultado)."""
        modos = ["auto"]
        if self.cfg.get("captcha_manual_se_falhar", True) and self.pedir_captcha:
            modos.append("manual")

        ultimo_erro = ""
        for modo in modos:
            self._voltar_janela_principal()
            abrir()
            campo = self.procurar(xp_campo)
            inputs = [i for i in self.driver.find_elements(By.XPATH, XP_INPUTS_TEXTO) if i.is_displayed()]
            verif = inputs[-1] if inputs and inputs[-1] != campo else None
            if verif is None:
                raise ErroRobo("Campo de verificação (captcha) não encontrado.")

            if modo == "auto":
                codigo = self.cfg.get("texto_verificacao", ".")
            else:
                self.log(f"   O '.' foi recusado. Aguardando você digitar os caracteres ({descricao})...")
                codigo = self.pedir_captcha(self._captcha_png(), descricao)
                if not codigo:
                    raise ErroRobo("Verificação cancelada pelo usuário.")

            campo.clear()
            campo.send_keys(valor)
            verif.clear()
            verif.send_keys(codigo)
            janelas_antes = set(self.driver.window_handles)
            botao = self._dfs(botao_xpath(texto_botao))
            (botao.click() if botao is not None else verif.submit())

            status, msg = self._aguardar_resultado(campo, janelas_antes)
            if status == "ok":
                return
            ultimo_erro = msg
            if status != "captcha":
                raise ErroRobo(msg)
        raise ErroRobo(f"Verificação recusada: {ultimo_erro}")

    def _aguardar_resultado(self, campo, janelas_antes):
        fim = time.time() + self.timeout
        while time.time() < fim:
            alerta = self._alerta()
            if alerta:
                n = _norm(alerta)
                if any(k in n for k in ("CARACTER", "CODIGO", "VERIFICA", "CAPTCHA", "IMAGEM")):
                    return "captcha", alerta
                return "erro", f"Site respondeu: {alerta.strip()}"

            novas = set(self.driver.window_handles) - janelas_antes
            if novas:
                self.driver.switch_to.window(novas.pop())
                time.sleep(1.5)
                return "ok", ""

            try:
                campo.is_displayed()  # se a página mudou, vira "stale"
            except StaleElementReferenceException:
                time.sleep(1.5)
                if self._alerta():
                    continue
                txt = _norm(self.texto_completo())
                if "CARACTER" in txt and any(k in txt for k in ("INVALID", "INCORRET", "NAO CONFERE", "ERRAD")):
                    return "captcha", "caracteres inválidos"
                return "ok", ""
            except WebDriverException:
                pass
            time.sleep(0.5)
        return "erro", "Tempo esgotado esperando a resposta do site."

    # ------------------------------------------------------------ PDF
    def _html_do_frame_com(self, marcadores, prof=0):
        """Procura o frame mais interno cujo texto tem um dos marcadores.
        Retorna (html, url) ou None. Usado para imprimir só a certidão, sem o menu do site."""
        n = len(self.driver.find_elements(By.XPATH, "//frame | //iframe"))
        for i in range(n):
            try:
                self.driver.switch_to.frame(self.driver.find_elements(By.XPATH, "//frame | //iframe")[i])
            except Exception:
                continue
            r = self._html_do_frame_com(marcadores, prof + 1) if prof < 4 else None
            if r:
                return r
            try:
                txt = _norm(self.driver.find_element(By.TAG_NAME, "body").text)
                if any(m in txt for m in marcadores):
                    return self.driver.execute_script(
                        "return [document.documentElement.outerHTML, location.href];")
            except Exception:
                pass
            finally:
                self.driver.switch_to.parent_frame()
        return None

    def salvar_pdf(self, caminho, marcadores=None):
        self.driver.switch_to.default_content()
        aba_extra = None
        if marcadores:
            achado = self._html_do_frame_com(marcadores)
            self.driver.switch_to.default_content()
            if achado:
                html, url = achado
                html = re.sub(r"(<head[^>]*>)", rf'\1<base href="{url}">', html, count=1, flags=re.I)
                origem = self.driver.current_window_handle
                self.driver.switch_to.new_window("tab")
                aba_extra = (self.driver.current_window_handle, origem)
                self.driver.execute_script("document.open();document.write(arguments[0]);document.close();", html)
                time.sleep(1.5)
        try:
            dados = self._imprimir()
        finally:
            if aba_extra:
                self.driver.close()
                self.driver.switch_to.window(aba_extra[1])
        with open(caminho, "wb") as f:
            f.write(dados)
        return caminho

    def _imprimir(self):
        try:
            r = self.driver.execute_cdp_cmd("Page.printToPDF", {
                "printBackground": True, "paperWidth": 8.27, "paperHeight": 11.69,
                "marginTop": 0.4, "marginBottom": 0.4, "marginLeft": 0.4, "marginRight": 0.4,
            })
            dados = base64.b64decode(r["data"])
        except Exception:
            from selenium.webdriver.common.print_page_options import PrintOptions
            dados = base64.b64decode(self.driver.print_page(PrintOptions()))
        return dados

    # ------------------------------------------------------------ fluxo 1: CND por IM
    def _abrir_form_cnd(self):
        urls = self.cfg["urls"]
        try:
            self.driver.get(urls["menu_certidoes"])
            self.procurar(XP_LINK_DEB_MOBILIARIOS, timeout=15).click()
            self.procurar(XP_LINK_CONJUNTA, timeout=15).click()
            self.procurar(XP_CAMPO_CAE, timeout=15)
        except Exception:
            # plano B: abre o formulário direto
            self.driver.get(urls["cnd_mobiliario_direto"])

    def emitir_cnd_por_im(self, im, nome_arquivo):
        """Emite a CND mobiliária e salva o PDF. Retorna (caminho_pdf, texto_da_tela)."""
        self._enviar_formulario(self._abrir_form_cnd, XP_CAMPO_CAE, im, "Emitir", f"CND – IM {im}")
        texto = self.texto_completo()
        n = _norm(texto)
        if not any(m in n for m in MARCADORES_CERTIDAO):
            raise ErroRobo(f"A página de resposta não parece uma certidão: {texto.strip()[:200]}")
        caminho = os.path.join(self.saida, nome_arquivo)
        self.salvar_pdf(caminho, MARCADORES_CERTIDAO)
        self._voltar_janela_principal()
        return caminho, texto

    # ------------------------------------------------------------ fluxo 2: IM pelo CNPJ
    def buscar_ims_por_cnpj(self, cnpj, pasta_consultas=None):
        url = self.cfg["urls"]["situacao_contribuinte"]
        self._enviar_formulario(lambda: self.driver.get(url), XP_CAMPO_CNPJ, cnpj, "Consulta",
                                f"Situação do contribuinte – CNPJ {cnpj}")
        texto = self.texto_completo()
        if pasta_consultas:
            os.makedirs(pasta_consultas, exist_ok=True)
            try:
                self.salvar_pdf(os.path.join(pasta_consultas, f"Situacao_{cnpj}.pdf"))
            except Exception:
                pass
        self._voltar_janela_principal()
        ims = extrair_ims(texto, cnpj)
        if not ims:
            raise ErroRobo(f"Nenhuma inscrição municipal encontrada para o CNPJ. Resposta: {texto.strip()[:200]}")
        return ims


def extrair_ims(texto, cnpj=""):
    """Acha números de inscrição municipal na tela de Situação do Contribuinte."""
    n = _norm(texto)
    achados = []
    padroes = [
        r"INSCRICAO(?: MUNICIPAL| CAE| NO CAE)?\s*(?:N[O0º]\.?)?\s*[:\-]?\s*(\d[\d.\-/]{3,})",
        r"\bCAE\s*[:\-]?\s*(\d[\d.\-/]{3,})",
        r"\bI\.?M\.?\s*[:\-]\s*(\d[\d.\-/]{3,})",
    ]
    for p in padroes:
        for m in re.finditer(p, n):
            d = re.sub(r"\D", "", m.group(1))
            if d and d != re.sub(r"\D", "", cnpj) and len(d) <= 12 and d not in achados:
                achados.append(d)
    return achados
