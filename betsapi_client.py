"""
Cliente da BetsAPI (feed Bet365).
Docs: https://betsapi.com/docs/bet365/

Endpoints usados:
  - GET /v1/bet365/inplay_filter  -> lista de jogos ao vivo
  - GET /v1/bet365/event          -> odds/markets de um jogo (via FI)
  - GET /v1/bet365/result         -> placar final de um jogo encerrado
"""
import re
import time
import requests

import config
from odds_utils import fracionario_para_decimal

BASE_URL = "https://api.b365api.com/v1"


class BetsapiError(Exception):
    pass


def _get(path: str, params: dict, tentativas: int = 3, timeout: int = 10) -> dict:
    params = dict(params)
    params["token"] = config.BETSAPI_TOKEN
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get("success") != 1:
                raise BetsapiError(f"Betsapi retornou success != 1: {data}")
            return data
        except (requests.RequestException, BetsapiError, ValueError) as e:
            ultimo_erro = e
            if tentativa < tentativas:
                time.sleep(2 * tentativa)  # backoff simples
            continue
    raise BetsapiError(f"Falha após {tentativas} tentativas em {path}: {ultimo_erro}")


def listar_jogos_ao_vivo(sport_id: int = config.SPORT_ID_FUTEBOL) -> list:
    """Retorna a lista bruta de jogos ao vivo (sem paginação nessa API)."""
    data = _get("/bet365/inplay_filter", {"sport_id": sport_id})
    return data.get("results", [])


def calcular_minuto_estimado(kickoff_timestamp: int) -> float:
    """
    Estimativa simples: (agora - horário programado de início) em minutos.
    Não desconta intervalo/acréscimos — é só uma estimativa pra decidir se o
    jogo está na janela de checagem (com FOLGA_ESTIMATIVA_MINUTOS de tolerância
    pra jogos que atrasam pra começar).
    """
    agora = time.time()
    minutos = (agora - float(kickoff_timestamp)) / 60.0
    return minutos


def liga_e_de_base(nome_liga: str) -> bool:
    nome_lower = (nome_liga or "").lower()
    return any(termo in nome_lower for termo in config.PALAVRAS_EXCLUIR_LIGA)


def extrair_placar_atual(ss: str):
    """'0-0' -> (0, 0). Retorna (None, None) se não der pra parsear (ex: tênis com sets)."""
    if not ss:
        return None, None
    try:
        casa, fora = ss.split("-")
        return int(casa), int(fora)
    except (ValueError, AttributeError):
        return None, None


def obter_odds_under(fi: str) -> dict:
    """
    Busca o evento completo (bet365/event) e extrai as odds de "Under" pra
    cada linha de gols disponível (incluindo linhas quebradas/asiáticas,
    que às vezes vêm numa aba de mercado separada tipo "Asian Total Goals").

    Retorna dict {linha_float: odd_decimal}, ex: {3.5: 1.85, 2.75: 1.9}
    """
    data = _get("/bet365/event", {"FI": fi})
    results = data.get("results", [])
    if not results:
        return {}

    # A resposta é uma lista "achatada" de nós: MG (market group), MA (market), PA (participant/odd)
    nos = results[0] if isinstance(results[0], list) else results

    odds_under = {}
    mercado_atual_nome = ""
    dentro_de_mercado_gols = False

    for no in nos:
        tipo = no.get("type")

        if tipo == "MG":
            # início de um novo grupo de mercado — reseta contexto
            nome_grupo = (no.get("NA") or "").lower()
            dentro_de_mercado_gols = any(t in nome_grupo for t in config.TERMOS_MERCADO_GOLS)

        elif tipo == "MA":
            mercado_atual_nome = (no.get("NA") or "").lower()

        elif tipo == "PA" and dentro_de_mercado_gols:
            nome_participante = (no.get("NA") or "")
            odd_bruta = no.get("OD")
            suspenso = no.get("SU") == "1"
            if suspenso or not odd_bruta:
                continue

            # nome costuma vir como "Under 3.5" ou similar; pega o número
            match = re.search(r"under\s*([\d.]+)", nome_participante, re.IGNORECASE)
            if not match:
                continue

            try:
                linha = float(match.group(1))
            except ValueError:
                continue

            if linha not in config.LINHAS_MONITORADAS:
                continue

            odd_decimal = fracionario_para_decimal(odd_bruta)
            if odd_decimal:
                # se a mesma linha aparecer em mais de um mercado (ex: principal + asiático),
                # fica com a última encontrada (geralmente a mais específica)
                odds_under[linha] = odd_decimal

    return odds_under


def obter_placar_final(fi: str):
    """
    Consulta o resultado final do jogo.
    Retorna (gols_casa, gols_fora, total_gols) se o jogo já encerrou (time_status == "3"),
    ou None se ainda não tem resultado disponível.
    """
    data = _get("/bet365/result", {"event_id": fi})
    results = data.get("results", [])
    if not results:
        return None

    jogo = results[0]
    if str(jogo.get("time_status")) != "3":
        return None  # ainda não terminou / não confirmado

    ss = jogo.get("ss", "")
    gols_casa, gols_fora = extrair_placar_atual(ss)
    if gols_casa is None:
        return None

    return gols_casa, gols_fora, gols_casa + gols_fora
