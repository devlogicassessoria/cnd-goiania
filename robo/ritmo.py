"""Controle de ritmo das requisições ao site da Prefeitura.

Objetivo: não sobrecarregar o sistema e não ser bloqueado por excesso de acessos.
- intervalo aleatório entre uma consulta e outra (nada de rajadas em ritmo fixo);
- pausa longa a cada N consultas;
- teto de consultas por hora (espera a janela abrir quando atinge o limite);
- espera crescente (backoff) quando o site falha ou demora, e pausa de resfriamento
  depois de vários erros seguidos.
Tudo configurável em config.json > "controle_requisicoes".
Todas as esperas são interrompíveis pelo botão Parar.
"""
import random
import time
from collections import deque

PADRAO = {
    "intervalo_min_segundos": 6,
    "intervalo_max_segundos": 15,
    "pausa_longa_a_cada": 25,
    "pausa_longa_min_segundos": 60,
    "pausa_longa_max_segundos": 150,
    "maximo_por_hora": 120,
    "espera_apos_erro_segundos": 20,
    "espera_maxima_apos_erro_segundos": 300,
    "erros_seguidos_para_resfriar": 3,
    "resfriamento_segundos": 600,
}


class ControleRitmo:
    def __init__(self, cfg: dict, log=print, parar_evt=None, relogio=time.monotonic, dormir=None):
        c = dict(PADRAO)
        c.update((cfg or {}).get("controle_requisicoes", {}))
        self.c = c
        self.log = log
        self.parar_evt = parar_evt
        self.relogio = relogio
        self._dormir_func = dormir
        self.feitas = 0
        self.erros_seguidos = 0
        self.historico = deque()  # instantes das requisições da última hora
        self.ultima = None

    # ------------------------------------------------------------ espera
    def _dormir(self, segundos, motivo=""):
        if segundos <= 0:
            return
        if motivo and segundos >= 20:
            self.log(f"   ⏳ {motivo}: aguardando {segundos:.0f}s...")
        if self._dormir_func:
            self._dormir_func(segundos)
        elif self.parar_evt is not None:
            self.parar_evt.wait(segundos)  # acorda na hora se clicarem em Parar
        else:
            time.sleep(segundos)

    def _parado(self):
        return self.parar_evt is not None and self.parar_evt.is_set()

    # ------------------------------------------------------------ API
    def antes_de_requisitar(self):
        """Chamar imediatamente antes de cada acesso ao site (consulta ou emissão)."""
        c = self.c
        agora = self.relogio()

        # 1) pausa longa a cada N requisições
        n = int(c["pausa_longa_a_cada"] or 0)
        if n and self.feitas and self.feitas % n == 0:
            self._dormir(random.uniform(c["pausa_longa_min_segundos"], c["pausa_longa_max_segundos"]),
                         f"Pausa programada após {self.feitas} consultas")
        # 2) intervalo aleatório desde a última requisição
        elif self.ultima is not None:
            alvo = random.uniform(c["intervalo_min_segundos"], c["intervalo_max_segundos"])
            self._dormir(alvo - (agora - self.ultima), "Intervalo entre consultas")

        # 3) teto por hora
        limite = int(c["maximo_por_hora"] or 0)
        if limite and not self._parado():
            agora = self.relogio()
            while self.historico and agora - self.historico[0] >= 3600:
                self.historico.popleft()
            if len(self.historico) >= limite:
                espera = 3600 - (agora - self.historico[0]) + random.uniform(5, 30)
                self._dormir(espera, f"Limite de {limite} consultas/hora atingido")

        agora = self.relogio()
        self.historico.append(agora)
        self.ultima = agora
        self.feitas += 1

    def sucesso(self):
        self.erros_seguidos = 0

    def erro(self):
        """Chamar quando a requisição falhar. Espera mais a cada erro seguido."""
        c = self.c
        self.erros_seguidos += 1
        if self.erros_seguidos >= int(c["erros_seguidos_para_resfriar"] or 0) > 0:
            self._dormir(c["resfriamento_segundos"],
                         f"{self.erros_seguidos} erros seguidos — o site pode estar instável ou limitando acessos")
            self.erros_seguidos = 0
            return
        base = c["espera_apos_erro_segundos"] * (2 ** (self.erros_seguidos - 1))
        self._dormir(min(base, c["espera_maxima_apos_erro_segundos"]) * random.uniform(0.8, 1.2),
                     "Site falhou, esperando antes de tentar de novo")
