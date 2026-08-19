"""
Cliente para a Betsapi (pacote Bet365 API).

Endpoints usados:
- /bet365/inplay_filter  -> lista de eventos ao vivo (id, liga, placar,
                              horário de início). NÃO traz o minuto corrido.
- /bet365/event          -> detalhe de um evento (odds/markets + campos
                              TT/TU/TM/TS pra calcular o minuto exato)

Formato confirmado em 2026-08-18 com token real (ver estrutura de
/bet365/inplay_filter abaixo). Documentação: https://betsapi.com/docs/bet365/

Exemplo real de item de /bet365/inplay_filter:
{
    "id": "199725497", "sport_id": "1", "time": "1787101200",
    "time_status": "1",
    "league": {"id": "10079113", "name": "CONCACAF Central American Cup"},
    "home": {"id": "10360186", "name": "Cartagines"},
    "away": {"id": "10785052", "name": "Verdes FC"},
    "ss": "3-0", ...
}
"ss" pode vir null quando o jogo ainda não começou de fato (apesar de
listado). "time" é o horário de início em timestamp Unix.
"""

import time as time_module

import requests

import config


class BetsapiError(Exception):
    pass


def _get(path: str, params: dict) -> dict:
    params = {**params, "token": config.BETSAPI_TOKEN}
    url = f"{config.BETSAPI_BASE_URL}{path}"
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("success") != 1:
        raise BetsapiError(f"Betsapi retornou erro em {path}: {data}")
    return data


def listar_jogos_ao_vivo(sport_id: int = 1) -> list[dict]:
    """
    Retorna a lista de jogos de futebol ao vivo agora, com placar e
    MINUTO ESTIMADO (calculado a partir do horário de início -- é uma
    aproximação sem gastar chamada de API extra; ver
    obter_detalhe_evento() pra confirmar com precisão quando necessário).

    Cada item normalizado:
    {
        "fi": ...,             # ID do evento (usado em /bet365/event)
        "liga": ...,
        "time_casa": ...,
        "time_fora": ...,
        "gols_casa": int,
        "gols_fora": int,
        "minuto_estimado": int | None,
        "jogo_comecou": bool,  # False se "ss" ainda é null
    }
    """
    data = _get("/bet365/inplay_filter", {"sport_id": sport_id})
    jogos = []
    for item in data.get("results", []):
        jogo = _normalizar_evento_inplay(item)
        if jogo is not None:
            jogos.append(jogo)
    return jogos


def _normalizar_evento_inplay(item: dict) -> dict | None:
    try:
        fi = item.get("id")
        if fi is None:
            return None

        liga = (item.get("league") or {}).get("name", "")
        home = (item.get("home") or {}).get("name", "")
        away = (item.get("away") or {}).get("name", "")

        ss = item.get("ss")
        jogo_comecou = ss is not None
        gols_casa, gols_fora = _parse_placar(ss) if ss else (0, 0)

        minuto_estimado = _estimar_minuto(item.get("time"))

        return {
            "fi": fi,
            "liga": liga,
            "time_casa": home,
            "time_fora": away,
            "gols_casa": gols_casa,
            "gols_fora": gols_fora,
            "minuto_estimado": minuto_estimado,
            "jogo_comecou": jogo_comecou,
        }
    except Exception:
        return None


def _parse_placar(ss: str) -> tuple[int, int]:
    try:
        casa, fora = ss.split("-")
        return int(casa), int(fora)
    except Exception:
        return 0, 0


def _estimar_minuto(kickoff_timestamp) -> int | None:
    """
    Estimativa GROSSEIRA do minuto, só usando o horário de início.
    Não desconta intervalo, acréscimos, VAR etc -- serve só pra decidir
    quais jogos merecem checagem exata via obter_detalhe_evento(), sem
    gastar chamada de API em jogos que claramente ainda não chegaram
    perto do minuto-gatilho.
    """
    if kickoff_timestamp is None:
        return None
    try:
        inicio = int(kickoff_timestamp)
        agora = int(time_module.time())
        decorrido_min = (agora - inicio) // 60
        if decorrido_min < 0:
            return None  # jogo ainda nem começou
        return decorrido_min
    except (TypeError, ValueError):
        return None


def obter_detalhe_evento(fi: str) -> dict:
    """
    Busca o detalhe completo de um evento (relógio exato + odds).
    Retorna: {"minuto_exato": int | None, "odds_under": {"Under 3.5": 1.85, ...}}

    O cálculo do minuto exato segue a fórmula oficial da Betsapi
    (https://betsapi.com/docs/bet365/faq.html):
      passed_seconds = agora - TU (kickoff daquele período) + TM*60 + TS
      (se TT indicar "tempo rolando"; senão passed_seconds = TM*60 + TS)
    Isso ainda precisa ser validado contra um jogo ao vivo de futebol
    de verdade (o formato de TT/TU pode variar) -- o cálculo abaixo é
    a melhor interpretação da documentação até agora.
    """
    data = _get("/bet365/event", {"FI": fi})
    resultados = data.get("results", [])

    # A Betsapi retorna "results" com um nível de aninhamento a mais do
    # que a documentação sugere: [[{...}, {...}, ...]] em vez de
    # [{...}, {...}, ...]. Achatamos aqui (confirmado em 2026-08-19 com
    # dado real -- sem isso, minuto_exato e odds_under vinham sempre
    # vazios mesmo com a chamada funcionando).
    if resultados and isinstance(resultados[0], list):
        resultados = resultados[0]

    minuto_exato = _calcular_minuto_exato(resultados)
    odds_under = _extrair_odds_under(resultados)

    return {
        "minuto_exato": minuto_exato,
        "odds_under": odds_under,
        "_bruto_debug": resultados,  # temporário: pra diagnosticar formato real
    }


def _calcular_minuto_exato(resultados: list) -> int | None:
    for item in resultados:
        if not isinstance(item, dict):
            continue
        if "TM" in item and "TS" in item:
            try:
                tm = int(item.get("TM", 0))
                ts = int(item.get("TS", 0))
                tt = item.get("TT")
                # TT vem como STRING ("0" ou "1"), não bool -- "0" é uma
                # string não-vazia e portanto truthy em Python, então
                # comparamos o valor de verdade, não só a presença.
                tempo_rolando = tt not in (None, "", "0", 0)
                if tempo_rolando:
                    tu = item.get("TU", "")
                    segundos_desde_tu = _segundos_desde_tu(tu)
                    if segundos_desde_tu is not None:
                        total_segundos = segundos_desde_tu + tm * 60 + ts
                        return total_segundos // 60
                return tm
            except (TypeError, ValueError):
                continue
    return None


def _segundos_desde_tu(tu: str) -> int | None:
    """TU vem no formato YYYYMMDDHHMMSS, horário de Londres."""
    if not tu or len(tu) < 14:
        return None
    try:
        from datetime import datetime, timezone
        import zoneinfo

        dt_londres = datetime.strptime(tu, "%Y%m%d%H%M%S").replace(
            tzinfo=zoneinfo.ZoneInfo("Europe/London")
        )
        agora = datetime.now(timezone.utc)
        return int((agora - dt_londres).total_seconds())
    except Exception:
        return None


def _extrair_odds_under(resultados: list) -> dict:
    """
    Filtra, entre os markets retornados, as odds de Under gols que
    interessam pra simulação.

    A estrutura real (confirmada em 2026-08-19 com dado de jogo real)
    é sequencial, não aninhada: um item 'MG' (market group) abre um
    mercado (ex: NA='Goals Over/Under'), seguido por pares de itens
    'MA' (a seleção, ex: NA='Over'/'Under') + 'PA' (o preço daquela
    seleção, com 'HA' = linha/handicap e 'OD' = odd fracionária).
    Percorremos a lista mantendo qual o último MG visto, e quando
    achamos uma seleção 'Under' dentro de um grupo de gols, com uma
    linha (HA) que bate com uma das nossas linhas simuladas, pegamos
    o OD do PA seguinte.

    Termos usados pra identificar o grupo certo (ex: 'Goals
    Over/Under', 'Total Goals') ainda podem não cobrir 100% dos
    nomes possíveis -- ajustar aqui se aparecerem variações novas.
    """
    odds_under = {}
    grupo_atual = ""
    selecao_atual = None  # "Over" ou "Under", da última MA vista

    termos_grupo_gols = ["goals over/under", "total goals", "match goals"]
    termos_grupo_excluir = ["corner", "card", "shootout", "penalt", "booking"]

    for item in resultados:
        if not isinstance(item, dict):
            continue
        tipo = item.get("type")

        if tipo == "MG":
            grupo_atual = (item.get("NA") or "").lower()
            selecao_atual = None
            continue

        if tipo == "MA":
            nome_selecao = (item.get("NA") or "").strip().lower()
            if nome_selecao in ("over", "under"):
                selecao_atual = nome_selecao
            else:
                selecao_atual = None
            continue

        if tipo == "PA" and selecao_atual == "under":
            grupo_e_de_gols = any(t in grupo_atual for t in termos_grupo_gols)
            grupo_e_excluido = any(t in grupo_atual for t in termos_grupo_excluir)
            if grupo_e_de_gols and not grupo_e_excluido:
                linha_ha = item.get("HA")
                od = item.get("OD")
                if linha_ha and od:
                    linha_encontrada = _casar_linha_numerica(linha_ha)
                    if linha_encontrada:
                        odds_under[linha_encontrada] = _odd_fracionaria_para_decimal(od)

    return odds_under


def _casar_linha_numerica(linha_ha: str):
    """
    Compara o valor numérico de HA com as linhas configuradas
    (LINHAS_SIMULADAS), tolerando formatos diferentes de escrita do
    mesmo número (ex: API manda '3.0', nós configuramos 'Under 3').
    """
    try:
        valor_ha = float(linha_ha)
    except (TypeError, ValueError):
        return None
    for linha_alvo in config.LINHAS_SIMULADAS:
        numero_alvo = float(linha_alvo.replace("Under ", ""))
        if abs(valor_ha - numero_alvo) < 0.001:
            return linha_alvo
    return None


def _odd_fracionaria_para_decimal(od: str):
    """Bet365 às vezes retorna odds em formato fracionário 'a/b'."""
    try:
        if "/" in od:
            num, den = od.split("/")
            return round(1 + (float(num) / float(den)), 3)
        return float(od)
    except Exception:
        return None

