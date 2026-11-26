"""Interface para acompanhar o robô de CND Mobiliária - Prefeitura de Goiânia.

Uso:
    python app.py                 -> abre a interface
    python app.py planilha.xlsx C:\\saida [--headless]   -> roda sem interface
"""
import base64
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from robo.config import carregar_config, recurso_empacotado
from robo.processo import Processo

CORES = {
    "Sem pendência / Negativa": "#d9f2d9",
    "Sem pendência / Positiva": "#fff2cc",
    "Com pendência / Negativa": "#fde9d9",
    "Com pendência / Positiva": "#f4c7c3",
    "Não classificada": "#ffe699",
    "Erro": "#f8cbad",
}
# cores da identidade Logic (azul-marinho da logo)
NAVY = "#0F1B35"
NAVY_HOVER = "#24365F"
NAVY_CLARO = "#DCE3F0"
FUNDO = "#F4F6FA"
TEXTO = "#1F2A44"
CINZA = "#6B7489"
FONTE = "Segoe UI" if sys.platform == "win32" else "Helvetica"
FONTE_MONO = "Consolas" if sys.platform == "win32" else "Courier"

CONTADORES = ["Sem pendência / Negativa", "Sem pendência / Positiva",
              "Com pendência / Negativa", "Com pendência / Positiva",
              "Não classificada", "Erro"]


def _abrir_no_sistema(caminho):
    """Abre arquivo/pasta no programa padrão. No Linux, descarta as mensagens
    do Firefox/GTK que o xdg-open joga no terminal."""
    if sys.platform == "win32":
        os.startfile(caminho)
    else:
        subprocess.Popen(["xdg-open", caminho], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Logic • Robô CND Mobiliária – Prefeitura de Goiânia")
        self.configure(bg=FUNDO)
        self._imagens = {}
        try:
            self._imagens["icone"] = tk.PhotoImage(file=recurso_empacotado("assets/icone.png"))
            self.iconphoto(True, self._imagens["icone"])
        except tk.TclError:
            pass
        self.geometry("1150x760")
        self.minsize(950, 620)
        try:
            self.cfg = carregar_config()
        except Exception as e:
            messagebox.showerror("Configuração", str(e))
            self.destroy()
            return
        self.fila = queue.Queue()
        self.processo = None
        self.thread = None
        self.pausado = False
        self.var_planilha = tk.StringVar()
        self.var_saida = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Documents", "CND Goiania"))
        self.var_headless = tk.BooleanVar(value=self.cfg.get("headless", False))
        self.var_manual = tk.BooleanVar(value=self.cfg.get("captcha_manual_se_falhar", True))
        self.contagem = {k: tk.IntVar(value=0) for k in CONTADORES}
        self._montar()
        self.after(100, self._ler_fila)
        self.protocol("WM_DELETE_WINDOW", self._sair)

    # ---------------------------------------------------------------- layout
    def _montar(self):
        self._tema()

        # cabeçalho: logo Logic + título, com faixa azul-marinho embaixo
        topo = tk.Frame(self, bg="white", padx=16, pady=10)
        topo.pack(fill="x")
        try:
            self._imagens["logo"] = tk.PhotoImage(file=recurso_empacotado("assets/logo_logic_header.png"))
            tk.Label(topo, image=self._imagens["logo"], bg="white").pack(side="left")
            tk.Frame(topo, bg=NAVY_CLARO, width=2).pack(side="left", fill="y", padx=16)
        except tk.TclError:
            pass
        tit = tk.Frame(topo, bg="white")
        tit.pack(side="left", fill="y")
        tk.Label(tit, text="Robô CND Mobiliária", font=(FONTE, 15, "bold"), fg=NAVY, bg="white").pack(anchor="w")
        tk.Label(tit, text="Certidão de Regularidade Fiscal Mobiliária – Prefeitura de Goiânia",
                 font=(FONTE, 9), fg=CINZA, bg="white").pack(anchor="w")
        filtro = self.cfg.get("filtro_municipio", "")
        if filtro:
            tk.Label(topo, text=f"  Município: {filtro}  ", font=(FONTE, 9, "bold"), fg="white", bg=NAVY,
                     padx=6, pady=3).pack(side="right")
        tk.Frame(self, bg=NAVY, height=4).pack(fill="x")
        tk.Frame(self, bg=FUNDO, height=8).pack(fill="x")

        f = ttk.LabelFrame(self, text="Arquivos", padding=10)
        f.pack(fill="x", padx=12)
        ttk.Label(f, text="Planilha (CNPJ + IM):").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_planilha).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(f, text="Procurar...", command=self._escolher_planilha).grid(row=0, column=2)
        ttk.Label(f, text="Pasta de saída:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(f, textvariable=self.var_saida).grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(f, text="Procurar...", command=self._escolher_saida).grid(row=1, column=2, pady=(6, 0))
        opc = ttk.Frame(f)
        opc.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(opc, text="Rodar com o Chrome escondido (segundo plano)",
                        variable=self.var_headless).pack(side="left")
        ttk.Checkbutton(opc, text="Se o \".\" for recusado, pedir os caracteres para mim",
                        variable=self.var_manual).pack(side="left", padx=20)
        f.columnconfigure(1, weight=1)

        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x")
        self.bt_iniciar = ttk.Button(bar, text="▶  Iniciar", command=self._iniciar, style="Primario.TButton")
        self.bt_pausar = ttk.Button(bar, text="❚❚  Pausar", command=self._pausar, state="disabled")
        self.bt_parar = ttk.Button(bar, text="■  Parar", command=self._parar, state="disabled")
        self.bt_abrir = ttk.Button(bar, text="📂  Abrir pasta de saída", command=self._abrir_saida)
        for b in (self.bt_iniciar, self.bt_pausar, self.bt_parar):
            b.pack(side="left", padx=(0, 6))
        self.bt_abrir.pack(side="right")

        prog = ttk.Frame(self, padding=(12, 0))
        prog.pack(fill="x")
        self.pb = ttk.Progressbar(prog, mode="determinate")
        self.pb.pack(side="left", fill="x", expand=True)
        self.lb_prog = ttk.Label(prog, text="0 / 0", width=12, anchor="e")
        self.lb_prog.pack(side="left")

        cont = ttk.Frame(self, padding=(12, 8))
        cont.pack(fill="x")
        for i, k in enumerate(CONTADORES):
            box = tk.Frame(cont, bg=CORES[k], highlightthickness=1, highlightbackground=NAVY_CLARO, padx=8, pady=4)
            box.grid(row=0, column=i, sticky="nsew", padx=3)
            tk.Label(box, textvariable=self.contagem[k], font=(FONTE, 16, "bold"), fg=NAVY, bg=CORES[k]).pack()
            tk.Label(box, text=k, font=(FONTE, 8), fg=TEXTO, bg=CORES[k]).pack()
            cont.columnconfigure(i, weight=1)

        corpo = ttk.PanedWindow(self, orient="vertical")
        corpo.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        tabela = ttk.Frame(corpo)
        cols = ("n", "empresa", "cnpj", "im", "etapa", "resultado")
        self.tv = ttk.Treeview(tabela, columns=cols, show="headings")
        for c, t, w in zip(cols, ("#", "Empresa", "CNPJ", "IM", "Etapa", "Resultado"),
                           (45, 300, 140, 110, 230, 220)):
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w, anchor="w" if c in ("empresa", "etapa", "resultado") else "center")
        for k, cor in CORES.items():
            self.tv.tag_configure(k, background=cor)
        self.tv.tag_configure("rodando", background=NAVY_CLARO)
        sb = ttk.Scrollbar(tabela, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv.bind("<Double-1>", self._abrir_arquivo_linha)
        corpo.add(tabela, weight=3)

        logf = ttk.LabelFrame(corpo, text="Log", padding=4)
        self.txt = tk.Text(logf, height=9, font=(FONTE_MONO, 9), bg=NAVY, fg="#E6EBF5",
                           insertbackground="white", relief="flat", padx=6, pady=4, wrap="word")
        sb2 = ttk.Scrollbar(logf, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb2.set, state="disabled")
        self.txt.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
        corpo.add(logf, weight=1)

        self.arquivos_linha = {}

    def _tema(self):
        st = ttk.Style(self)
        st.theme_use("clam")  # "clam" aceita cores personalizadas em todos os sistemas
        self.option_add("*Font", (FONTE, 10))
        st.configure(".", background=FUNDO, foreground=TEXTO, font=(FONTE, 10), bordercolor=NAVY_CLARO,
                     focuscolor=NAVY_CLARO)
        st.configure("TFrame", background=FUNDO)
        st.configure("TLabel", background=FUNDO, foreground=TEXTO)
        st.configure("TLabelframe", background=FUNDO, bordercolor=NAVY_CLARO)
        st.configure("TLabelframe.Label", background=FUNDO, foreground=NAVY, font=(FONTE, 10, "bold"))
        st.configure("TCheckbutton", background=FUNDO, foreground=TEXTO)
        st.map("TCheckbutton", background=[("active", FUNDO)], indicatorcolor=[("selected", NAVY), ("!selected", "white")])
        st.configure("TEntry", fieldbackground="white", bordercolor=NAVY_CLARO, lightcolor=NAVY_CLARO)
        st.map("TEntry", bordercolor=[("focus", NAVY)], lightcolor=[("focus", NAVY)])
        st.configure("TButton", background="white", foreground=NAVY, bordercolor=NAVY_CLARO,
                     padding=(12, 6), font=(FONTE, 10))
        st.map("TButton", background=[("disabled", FUNDO), ("active", NAVY_CLARO)],
               foreground=[("disabled", "#A0A7B8")])
        st.configure("Primario.TButton", background=NAVY, foreground="white", bordercolor=NAVY,
                     font=(FONTE, 10, "bold"))
        st.map("Primario.TButton", background=[("disabled", "#8A93A8"), ("active", NAVY_HOVER)],
               foreground=[("disabled", "#E6EBF5"), ("active", "white")])
        st.configure("Horizontal.TProgressbar", background=NAVY, troughcolor=NAVY_CLARO,
                     bordercolor=NAVY_CLARO, lightcolor=NAVY, darkcolor=NAVY, thickness=14)
        st.configure("Treeview", rowheight=24, background="white", fieldbackground="white",
                     foreground=TEXTO, bordercolor=NAVY_CLARO)
        st.map("Treeview", background=[("selected", NAVY_HOVER)], foreground=[("selected", "white")])
        st.configure("Treeview.Heading", background=NAVY, foreground="white", font=(FONTE, 10, "bold"),
                     relief="flat", bordercolor=NAVY)
        st.map("Treeview.Heading", background=[("active", NAVY_HOVER)])
        st.configure("Vertical.TScrollbar", background=NAVY_CLARO, troughcolor=FUNDO, bordercolor=FUNDO,
                     arrowcolor=NAVY)
        st.configure("TPanedwindow", background=FUNDO)

    # ---------------------------------------------------------------- ações
    def _escolher_planilha(self):
        p = filedialog.askopenfilename(title="Planilha de empresas",
                                       filetypes=[("Planilhas", "*.xlsx *.xlsm *.csv"), ("Todos", "*.*")])
        if p:
            self.var_planilha.set(p)

    def _escolher_saida(self):
        p = filedialog.askdirectory(title="Pasta onde salvar as certidões")
        if p:
            self.var_saida.set(p)

    def _abrir_saida(self):
        p = self.var_saida.get()
        if os.path.isdir(p):
            _abrir_no_sistema(p)

    def _abrir_arquivo_linha(self, _e):
        sel = self.tv.selection()
        if sel and self.arquivos_linha.get(sel[0]) and os.path.exists(self.arquivos_linha[sel[0]]):
            arq = self.arquivos_linha[sel[0]]
            _abrir_no_sistema(arq)

    def _iniciar(self):
        planilha, saida = self.var_planilha.get().strip(), self.var_saida.get().strip()
        if not os.path.isfile(planilha):
            messagebox.showwarning("Planilha", "Escolha a planilha com CNPJ e IM.")
            return
        if not saida:
            messagebox.showwarning("Saída", "Escolha a pasta de saída.")
            return
        os.makedirs(saida, exist_ok=True)
        self.tv.delete(*self.tv.get_children())
        self.arquivos_linha.clear()
        for v in self.contagem.values():
            v.set(0)
        self.pb["value"] = 0

        cfg = dict(self.cfg)
        cfg["captcha_manual_se_falhar"] = self.var_manual.get()
        self.processo = Processo(cfg, planilha, saida, self._evento, pedir_captcha=self._pedir_captcha,
                                 headless=self.var_headless.get())
        self.thread = threading.Thread(target=self.processo.executar, daemon=True)
        self.thread.start()
        self.bt_iniciar.config(state="disabled")
        self.bt_pausar.config(state="normal", text="❚❚  Pausar")
        self.bt_parar.config(state="normal")
        self.pausado = False

    def _pausar(self):
        if not self.processo:
            return
        if self.pausado:
            self.processo.continuar()
            self.bt_pausar.config(text="❚❚  Pausar")
            self._log("▶ Continuando...")
        else:
            self.processo.pausar()
            self.bt_pausar.config(text="▶  Continuar")
            self._log("❚❚ Pausado (termina a empresa atual e espera).")
        self.pausado = not self.pausado

    def _parar(self):
        if self.processo and messagebox.askyesno("Parar", "Parar após a empresa atual?"):
            self.processo.parar()
            self.bt_parar.config(state="disabled")
            self.bt_pausar.config(state="disabled")

    def _sair(self):
        if self.thread and self.thread.is_alive():
            if not messagebox.askyesno("Sair", "O robô ainda está rodando. Parar e sair?"):
                return
            self.processo.parar()
        self.destroy()

    # ---------------------------------------------------------------- captcha manual
    def _pedir_captcha(self, png_bytes, descricao):
        """Chamado pela thread do robô; bloqueia até o usuário responder na janela."""
        resp = {"v": None}
        pronto = threading.Event()
        self.fila.put(("captcha", {"png": png_bytes, "desc": descricao, "resp": resp, "evt": pronto}))
        pronto.wait()
        return resp["v"]

    def _janela_captcha(self, d):
        win = tk.Toplevel(self)
        win.title("Digite os caracteres")
        win.transient(self)
        win.grab_set()
        win.attributes("-topmost", True)
        ttk.Label(win, text=d["desc"], padding=(12, 10, 12, 4)).pack()
        try:
            img = tk.PhotoImage(data=base64.b64encode(d["png"]).decode())
            if img.width() < 200:
                img = img.zoom(2, 2)
            lb = ttk.Label(win, image=img)
            lb.image = img
            lb.pack(padx=12)
        except tk.TclError:
            ttk.Label(win, text="(não consegui mostrar a imagem — veja no Chrome)").pack()
        ent = ttk.Entry(win, font=(FONTE, 14), justify="center", width=14)
        ent.pack(pady=10)
        ent.focus_set()

        def ok(_e=None, valor=True):
            d["resp"]["v"] = ent.get().strip() if valor else None
            d["evt"].set()
            win.destroy()

        bts = ttk.Frame(win, padding=(0, 0, 0, 10))
        bts.pack()
        ttk.Button(bts, text="Confirmar", command=ok, style="Primario.TButton").pack(side="left", padx=4)
        ttk.Button(bts, text="Pular empresa", command=lambda: ok(valor=False)).pack(side="left", padx=4)
        ent.bind("<Return>", ok)
        win.protocol("WM_DELETE_WINDOW", lambda: ok(valor=False))
        self.bell()

    # ---------------------------------------------------------------- eventos do robô
    def _evento(self, tipo, dados):
        self.fila.put((tipo, dados))

    def _log(self, msg):
        self.txt.configure(state="normal")
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _ler_fila(self):
        try:
            while True:
                tipo, d = self.fila.get_nowait()
                if tipo == "log":
                    self._log(d["msg"])
                elif tipo == "empresas":
                    for i, e in enumerate(d["lista"]):
                        self.tv.insert("", "end", iid=str(i),
                                       values=(i + 1, e.nome, e.cnpj, e.im or "—", "Aguardando", ""))
                    self.pb["maximum"] = max(1, len(d["lista"]))
                    self.lb_prog.config(text=f"0 / {len(d['lista'])}")
                elif tipo == "status":
                    iid = str(d["idx"])
                    self.tv.set(iid, "etapa", d["etapa"])
                    self.tv.item(iid, tags=("rodando",))
                    self.tv.see(iid)
                elif tipo == "resultado":
                    iid = str(d["idx"])
                    atual = self.tv.set(iid, "resultado")
                    novo = d["categoria"] if not atual else f"{atual} | {d['categoria']}"
                    self.tv.set(iid, "resultado", novo)
                    self.tv.set(iid, "etapa", "Concluído" if d["categoria"] != "Erro" else d["detalhe"][:80])
                    if d.get("im") and self.tv.set(iid, "im") == "—":
                        self.tv.set(iid, "im", d["im"])
                    self.tv.item(iid, tags=(d["categoria"],))
                    if d.get("arquivo"):
                        self.arquivos_linha[iid] = d["arquivo"]
                    if d["categoria"] in self.contagem:
                        self.contagem[d["categoria"]].set(self.contagem[d["categoria"]].get() + 1)
                elif tipo == "progresso":
                    self.pb["value"] = d["feitos"]
                    self.lb_prog.config(text=f"{d['feitos']} / {d['total']}")
                elif tipo == "captcha":
                    self._janela_captcha(d)
                elif tipo == "fim":
                    self.bt_iniciar.config(state="normal")
                    self.bt_pausar.config(state="disabled", text="❚❚  Pausar")
                    self.bt_parar.config(state="disabled")
                    msg = "Processo finalizado."
                    if d.get("relatorio"):
                        msg += f"\n\nRelatório:\n{d['relatorio']}"
                    messagebox.showinfo("CND Goiânia", msg)
        except queue.Empty:
            pass
        self.after(100, self._ler_fila)


def modo_linha_de_comando(args):
    cfg = carregar_config()
    headless = "--headless" in args
    planilha, saida = [a for a in args if not a.startswith("--")][:2]
    os.makedirs(saida, exist_ok=True)

    def ev(tipo, d):
        if tipo == "log":
            print(d["msg"], flush=True)

    def captcha_console(png, desc):
        caminho = os.path.join(saida, "_captcha.png")
        with open(caminho, "wb") as f:
            f.write(png)
        return input(f"{desc} – veja {caminho} e digite os caracteres (Enter vazio = pular): ").strip() or None

    Processo(cfg, planilha, saida, ev, pedir_captcha=captcha_console, headless=headless).executar()


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        modo_linha_de_comando(sys.argv[1:])
    else:
        App().mainloop()
