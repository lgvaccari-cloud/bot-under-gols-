"""
Bot Under Gols — loop principal.

A cada ciclo:
 1. Busca jogos de futebol ao vivo na Betsapi.
 2. Filtra: sem ligas de base, placar 0x0, minuto estimado entre
    MINUTO_GATILHO e MINUTO_RECHECK_LIMITE.
 3. Pra cada jogo candidato (ainda não alertado), busca as odds de Under
    e escolhe a linha com odd mais próxima de ODD_ALVO dentro da faixa
    [ODD_MINIMA, ODD_MAXIMA].
 4. Se achou: manda alerta no Telegram, abre aposta simulada, registra
    entrada na planilha.
 5. Verifica apostas abertas: se o jogo já terminou, resolve a aposta,
    manda mensagem de resultado, atualiza planilha e banca.
 6. Ao virar o dia, manda o resumo diário e zera os contadores.

Rodar com: python -u main.py
"""
import datetime
import time
import traceback

import config
import betsapi_client
import telegram_client
import sheets_client
import state_manager
from odds_utils import resolver_aposta, linha_para_texto


def _melhor_linha(odds_under: dict):
    """
    Entre as linhas com odd dentro de [ODD_MINIMA, ODD_MAXIMA],
    escolhe a que tem odd mais próxima de ODD_ALVO.
    Retorna (linha, odd) ou (None, None) se nenhuma qualificar.
    """
    candidatas = {
        linha: odd for linha, odd in odds_under.items()
        if config.ODD_MINIMA <= odd <= config.ODD_MAXIMA
    }
    if not candidatas:
        return None, None
    melhor_linha = min(candidatas, key=lambda l: abs(candidatas[l] - config.ODD_ALVO))
    return melhor_linha, candidatas[melhor_linha]


def _ciclo_busca_alertas(estado: dict):
    jogos = betsapi_client.listar_jogos_ao_vivo()
    dentro_da_janela = 0

    for jogo in jogos:
        fi = str(jogo.get("id"))
        liga_info = jogo.get("league") or {}
        nome_liga = liga_info.get("name", "")

        if betsapi_client.liga_e_de_base(nome_liga):
            continue

        if not config.MODO_TESTE:
            placar_casa, placar_fora = betsapi_client.extrair_placar_atual(jogo.get("ss", ""))
            if placar_casa != 0 or placar_fora != 0:
                continue  # só interessa 0x0

            kickoff = jogo.get("time")
            if not kickoff:
                continue
            minuto_estimado = betsapi_client.calcular_minuto_estimado(kickoff)

            janela_min = config.MINUTO_GATILHO
            janela_max = config.MINUTO_RECHECK_LIMITE + config.FOLGA_ESTIMATIVA_MINUTOS
            if not (janela_min <= minuto_estimado <= janela_max):
                continue

        dentro_da_janela += 1

        if fi in estado["jogos_alertados"]:
            continue  # já alertado, não repete

        try:
            odds_under = betsapi_client.obter_odds_under(fi)
        except betsapi_client.BetsapiError as e:
            print(f"[erro] falha ao buscar odds do jogo {fi}: {e}")
            continue

        linha, odd = _melhor_linha(odds_under)
        if linha is None:
            continue

        time_casa = (jogo.get("home") or {}).get("name", "?")
        time_fora = (jogo.get("away") or {}).get("name", "?")
        pais = liga_info.get("cc", "")
        linha_texto = linha_para_texto(linha)

        telegram_client.enviar_alerta(time_casa, time_fora, nome_liga, linha_texto, odd)

        id_aposta = f"{fi}_{int(time.time())}"
        data_hoje = datetime.date.today().isoformat()
        estado["apostas_abertas"][id_aposta] = {
            "fi": fi,
            "time_casa": time_casa,
            "time_fora": time_fora,
            "liga": nome_liga,
            "pais": pais,
            "linha": linha,
            "odd": odd,
            "data_abertura": data_hoje,
            "stake": config.STAKE_PADRAO,
        }
        estado["jogos_alertados"].append(fi)

        telegram_client.enviar_abertura_simulada(time_casa, time_fora, nome_liga, linha_texto, odd, config.STAKE_PADRAO)

        try:
            sheets_client.registrar_entrada(
                id_aposta, data_hoje, f"{time_casa} x {time_fora}", pais, nome_liga,
                linha, f"Under {linha_texto}", config.STAKE_PADRAO, odd,
            )
        except Exception as e:
            print(f"[erro] falha ao registrar entrada na planilha: {e}")

    print(f"[ciclo {time.strftime('%H:%M:%S')}] {len(jogos)} jogos ao vivo | "
          f"{dentro_da_janela} dentro da janela do minuto-gatilho")


def _ciclo_resolver_apostas(estado: dict):
    apostas_resolvidas = []

    for id_aposta, aposta in list(estado["apostas_abertas"].items()):
        try:
            resultado_final = betsapi_client.obter_placar_final(aposta["fi"])
        except betsapi_client.BetsapiError as e:
            print(f"[erro] falha ao checar resultado do jogo {aposta['fi']}: {e}")
            continue

        if resultado_final is None:
            continue  # ainda não terminou

        _, _, total_gols = resultado_final
        resultado_label, retorno_liquido = resolver_aposta(
            aposta["linha"], aposta["odd"], total_gols, aposta["stake"]
        )

        estado["banca_atual"] += retorno_liquido

        linha_texto = linha_para_texto(aposta["linha"])
        telegram_client.enviar_resultado_simulado(
            aposta["time_casa"], aposta["time_fora"], aposta["liga"], linha_texto,
            aposta["odd"], resultado_label, retorno_liquido, estado["banca_atual"],
        )

        try:
            sheets_client.atualizar_resultado(id_aposta, resultado_label, retorno_liquido)
        except Exception as e:
            print(f"[erro] falha ao atualizar resultado na planilha: {e}")

        _atualizar_resumo_dia(estado, aposta["data_abertura"], resultado_label, retorno_liquido)
        apostas_resolvidas.append(id_aposta)

    for id_aposta in apostas_resolvidas:
        del estado["apostas_abertas"][id_aposta]


def _atualizar_resumo_dia(estado: dict, data_abertura: str, resultado_label: str, retorno_liquido: float):
    resumo = estado["resumo_dia"]
    hoje = datetime.date.today().isoformat()

    if resumo["data"] != hoje:
        # novo dia: manda resumo do dia anterior (se houver) e zera
        if resumo["data"] and resumo["total"] > 0:
            telegram_client.enviar_resumo_diario(
                resumo["data"], resumo["total"], resumo["greens"], resumo["reds"],
                resumo["voids_e_meios"], resumo["resultado"], estado["banca_atual"],
            )
        resumo = {"data": hoje, "total": 0, "greens": 0, "reds": 0, "voids_e_meios": 0, "resultado": 0.0}

    resumo["total"] += 1
    if resultado_label == "Green":
        resumo["greens"] += 1
    elif resultado_label == "Red":
        resumo["reds"] += 1
    else:
        resumo["voids_e_meios"] += 1
    resumo["resultado"] += retorno_liquido

    estado["resumo_dia"] = resumo


def main():
    print("Bot Under Gols iniciado.")
    if config.MODO_TESTE:
        print("[modo teste] placar 0x0 e janela de minuto IGNORADOS — só pra validar o fluxo até a planilha.")
    while True:
        estado = state_manager.carregar_estado()
        try:
            _ciclo_busca_alertas(estado)
            _ciclo_resolver_apostas(estado)
        except Exception:
            print("[erro] exceção não tratada no ciclo:")
            traceback.print_exc()
        finally:
            state_manager.salvar_estado(estado)

        time.sleep(config.INTERVALO_CICLO_SEGUNDOS)


if __name__ == "__main__":
    main()
