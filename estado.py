"""
Persistência simples em arquivo JSON.

Guarda:
- jogos já verificados no minuto-gatilho (pra não notificar 2x)
- apostas simuladas em aberto (aguardando o jogo terminar)
- histórico de apostas simuladas já resolvidas
- saldo atual de cada linha simulada (banca por estratégia)

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
        "banca": {
            linha: config.BANCA_INICIAL for linha in config.LINHAS_SIMULADAS
        },
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


def registrar_aposta_simulada(estado: dict, fi: str, linha: str, odd: float,
                               jogo_descricao: str) -> None:
    estado["apostas_abertas"].append({
        "fi": fi,
        "linha": linha,
        "odd": odd,
        "stake": config.STAKE_UNIDADE,
        "jogo": jogo_descricao,
        "data_entrada": datetime.now().isoformat(),
    })


def resolver_aposta(estado: dict, aposta: dict, gols_totais_final: int) -> dict:
    """
    Aplica o resultado de uma aposta simulada de Under X gols e atualiza
    a banca daquela linha. Retorna a aposta já resolvida (com resultado).
    """
    numero_linha = float(aposta["linha"].replace("Under ", ""))
    green = gols_totais_final < numero_linha

    if green:
        lucro = aposta["stake"] * (aposta["odd"] - 1)
    else:
        lucro = -aposta["stake"]

    estado["banca"][aposta["linha"]] += lucro

    aposta_resolvida = {
        **aposta,
        "resultado": "green" if green else "red",
        "lucro": round(lucro, 2),
        "gols_totais_final": gols_totais_final,
        "data_resolucao": datetime.now().isoformat(),
    }
    estado["apostas_resolvidas"].append(aposta_resolvida)
    return aposta_resolvida
