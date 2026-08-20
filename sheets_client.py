"""
Registro das apostas simuladas numa planilha do Google Sheets.

Escreve na primeira aba (o "Log" bruto) em DOIS momentos:
1. Na hora que a aposta é aberta -- linha nova com status "Aguardando"
2. Quando a aposta resolve -- atualiza ESSA MESMA linha com o
   resultado final (Green/Red/Void/Meio Green/Meio Red) e o retorno

A segunda aba (métricas por país/campeonato/linha) é feita com
fórmula QUERY direto na planilha, não por código -- ver README.

Colunas do Log: Data | Jogo | País | Campeonato | Linha | Tip |
Stake | Odd | Resultado | Retorno Líquido | ID (tudo em unidades,
mesma convenção da outra planilha -- 1 stake = 1 unidade = R$1.000).
A coluna K (ID) é só técnica, pra achar a linha certa na hora de
atualizar -- pode ficar escondida/estreita na planilha.

Precisa de uma conta de serviço do Google (arquivo JSON de credencial)
com acesso de Editor na planilha -- ver README para o passo a passo
de criação.
"""

import json

import gspread
from google.oauth2.service_account import Credentials

import config

_ESCOPOS = ["https://www.googleapis.com/auth/spreadsheets"]

_cliente = None
_planilha = None

COLUNA_ID = 11  # K -- 1-indexado (A=1, B=2, ..., K=11)
COLUNA_RESULTADO = 9   # I
COLUNA_RETORNO = 10    # J


def _conectar():
    """Conecta preguiçosamente (só na primeira vez que for usado)."""
    global _cliente, _planilha
    if _planilha is not None:
        return _planilha

    if not config.GOOGLE_SERVICE_ACCOUNT_JSON or not config.GOOGLE_SHEET_ID:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON ou GOOGLE_SHEET_ID não configurados -- "
            "registro na planilha desativado."
        )

    info_credencial = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
    credenciais = Credentials.from_service_account_info(info_credencial, scopes=_ESCOPOS)
    _cliente = gspread.authorize(credenciais)
    _planilha = _cliente.open_by_key(config.GOOGLE_SHEET_ID).sheet1
    return _planilha


def _estimar_pais(campeonato: str) -> str:
    """
    Estimativa simples: usa a primeira palavra do nome da liga como
    país (ex: "Poland III Liga" -> "Poland"). Não é perfeito -- ligas
    continentais/regionais (ex: "Europe Friendlies") vão aparecer com
    a região no lugar do país.
    """
    if not campeonato:
        return ""
    return campeonato.split()[0]


def registrar_entrada(id_aposta: str, data_hora: str, campeonato: str,
                       partida: str, linha, odd: float) -> None:
    """
    Adiciona uma linha no Log assim que a aposta é aberta, com status
    "Aguardando" -- id_aposta precisa ser único (ex: "{fi}_{linha}"),
    usado depois pra achar e atualizar essa mesma linha.
    """
    try:
        aba = _conectar()
        pais = _estimar_pais(campeonato)
        tip = f"Under {linha}"

        aba.append_row([
            data_hora, partida, pais, campeonato, linha, tip, 1,
            odd, "Aguardando", "", id_aposta,
        ])
    except Exception as e:
        # Nunca deixa um erro na planilha derrubar o bot -- só loga.
        print(f"[erro] Falha ao registrar entrada na planilha: {e}")


def atualizar_resultado(id_aposta: str, resultado: str, lucro_reais: float) -> None:
    """
    Acha a linha com esse id_aposta (coluna K) e atualiza Resultado
    e Retorno Líquido. Se não achar a linha (ex: foi escrita antes
    dessa função existir), não faz nada.
    """
    try:
        aba = _conectar()
        celula = aba.find(id_aposta, in_column=COLUNA_ID)
        if celula is None:
            print(f"[aviso] Não achei a linha da aposta {id_aposta} na planilha "
                  f"pra atualizar o resultado -- talvez tenha sido registrada antes "
                  f"dessa função existir.")
            return

        retorno_liquido_unidades = round(lucro_reais / config.STAKE_UNIDADE, 4)
        aba.update_cell(celula.row, COLUNA_RESULTADO, resultado.title())
        aba.update_cell(celula.row, COLUNA_RETORNO, retorno_liquido_unidades)
    except Exception as e:
        print(f"[erro] Falha ao atualizar resultado na planilha: {e}")
