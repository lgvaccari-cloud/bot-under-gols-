"""
Persistência simples em arquivo JSON.

Guarda:
- jogos já verificados no minuto-gatilho (pra não notificar 2x)
- apostas simuladas em aberto (aguardando o jogo terminar)
- histórico de apostas simuladas já resolvidas
- banca única simulada (uma linha por alerta agora, não mais 3
  estratégias em paralelo -- então uma banca só faz mais sentido)

Isso roda num único processo (sem concorrência), então um arquivo
JSON simples resolve -- se um dia precisar de mais robustez, trocamos
por SQLite sem mudar a interface destas funções.
"""

import json
import os
from datetime import datetime

import config


def _estado_vazio() -> dict:
    return {
        "jogos_verificados": [],       # FIs já checados no minuto-gatilho
        "apostas_abertas": [],          # apostas simuladas aguardando resultado
        "apostas_resolvidas": [],       # histórico completo
        "banca": config.BANCA_INICIAL,
        "ultimo_relatorio_enviado": None,  # data (YYYY-MM-DD) do último resumo diário
    }


def carregar() -> dict:
    if not os.path.exists(config.ARQUIVO_ESTADO):
        return _estado_vazio()
    with open(config.ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar(estado: dict) -> None:
    with open(config.ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def marcar_jogo_verificado(estado: dict, fi: str) -> None:
    estado["jogos_verificados"].append(fi)
    # evita o arquivo crescer pra sempre: mantém só os últimos 5000 FIs
    estado["jogos_verificados"] = estado["jogos_verificados"][-5000:]


def jogo_ja_verificado(estado: dict, fi: str) -> bool:
    return fi in estado["jogos_verificados"]


def registrar_aposta_simulada(estado: dict, fi: str, linha, odd: float,
                               jogo_descricao: str, liga: str = "") -> None:
    estado["apostas_abertas"].append({
        "fi": fi,
        "linha": linha,       # numérico (ex: 2.75, 3, 3.5) -- não mais "Under X"
        "odd": odd,
        "stake": config.STAKE_UNIDADE,
        "jogo": jogo_descricao,
        "liga": liga,          # separado, pra dar pra filtrar por campeonato depois
        "data_entrada": datetime.now().isoformat(),
    })


def _resultado_perna(gols_totais_final: int, linha_perna: float) -> str:
    """
    Resolve UMA perna (linha inteira ou meia) de Under X gols:
    - linha inteira (ex: 3): "win" se gols < linha, "push" se gols ==
      linha (empate/void), "lose" se gols > linha
    - linha meia (ex: 3.5): nunca dá push -- "win" se gols < linha,
      senão "lose"
    """
    if linha_perna == int(linha_perna):  # linha inteira -- pode empatar
        if gols_totais_final < linha_perna:
            return "win"
        elif gols_totais_final == linha_perna:
            return "push"
        else:
            return "lose"
    else:  # linha meia (X.5) -- nunca empata
        return "win" if gols_totais_final < linha_perna else "lose"


def resolver_aposta(estado: dict, aposta: dict, gols_totais_final: int) -> dict:
    """
    Aplica o resultado de uma aposta simulada de Under X gols e atualiza
    a banca única. Retorna a aposta já resolvida (com resultado).

    Linhas quebradas (terminam em .25 ou .75) são apostas "asiáticas"
    partidas em duas pernas de meia unidade cada (ex: Under 2.75 =
    metade Under 2.5 + metade Under 3). Cada perna resolve
    independente, e o resultado final pode ser:
      - green: as duas pernas ganham
      - red: as duas pernas perdem
      - void: linha inteira sozinha (não quebrada) e o placar bateu
        exatamente nela -- toda a stake é devolvida
      - meio green: uma perna ganha, a outra empata (push)
      - meio red: uma perna perde, a outra empata (push)
    """
    numero_linha = float(aposta["linha"])
    stake = aposta["stake"]
    odd = aposta["odd"]
    eh_quebrada = abs(numero_linha * 4 - round(numero_linha * 4)) < 1e-9 and \
        (round(numero_linha * 4) % 2 != 0)  # termina em .25 ou .75

    if eh_quebrada:
        perna_baixa = numero_linha - 0.25
        perna_alta = numero_linha + 0.25
        r1 = _resultado_perna(gols_totais_final, perna_baixa)
        r2 = _resultado_perna(gols_totais_final, perna_alta)
        resultados_pernas = {r1, r2}

        if resultados_pernas == {"win"}:
            resultado, lucro = "green", stake * (odd - 1)
        elif resultados_pernas == {"lose"}:
            resultado, lucro = "red", -stake
        elif resultados_pernas == {"win", "push"}:
            resultado, lucro = "meio green", (stake / 2) * (odd - 1)
        else:  # {"lose", "push"}
            resultado, lucro = "meio red", -(stake / 2)
    else:
        r = _resultado_perna(gols_totais_final, numero_linha)
        if r == "win":
            resultado, lucro = "green", stake * (odd - 1)
        elif r == "push":
            resultado, lucro = "void", 0.0
        else:
            resultado, lucro = "red", -stake

    estado["banca"] += lucro

    aposta_resolvida = {
        **aposta,
        "resultado": resultado,
        "lucro": round(lucro, 2),
        "gols_totais_final": gols_totais_final,
        "data_resolucao": datetime.now().isoformat(),
    }
    estado["apostas_resolvidas"].append(aposta_resolvida)
    return aposta_resolvida
