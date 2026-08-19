"""
Registro das apostas simuladas numa planilha do Google Sheets.

Escreve na primeira aba (o "Log" bruto, uma linha por aposta
resolvida). A segunda aba (métricas por país/campeonato/linha) é
feita com fórmula QUERY direto na planilha, não por código -- ver
README.

Colunas do Log: Data | Jogo | País | Campeonato | Linha | Tip |
Stake | Odd | Resultado | Retorno Líquido (tudo em unidades, mesma
convenção da outra planilha -- 1 stake = 1 unidade = R$1.000)

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
    país (ex: "Poland III Liga" -> "Poland", "England Premier League"
    -> "England"). Não é perfeito -- ligas continentais/regionais
    (ex: "Europe Friendlies", "CONCACAF Central American Cup") vão
    aparecer com a região no lugar do país. Dá pra ajustar manualmente
    na planilha depois se precisar.
    """
    if not campeonato:
        return ""
    return campeonato.split()[0]


def registrar_linha(data_hora: str, campeonato: str, partida: str, linha,
                     odd: float, resultado: str, lucro_reais: float) -> None:
    """
    Adiciona uma linha no Log com o resultado de uma aposta simulada
    já resolvida. Tudo em unidades (stake sempre "1", retorno líquido
    convertido de reais pra unidades usando STAKE_UNIDADE).
    """
    try:
        aba = _conectar()
        pais = _estimar_pais(campeonato)
        tip = f"Under {linha}"
        retorno_liquido_unidades = round(lucro_reais / config.STAKE_UNIDADE, 4)

        aba.append_row([
            data_hora, partida, pais, campeonato, linha, tip, 1,
            odd, resultado.title(), retorno_liquido_unidades,
        ])
    except Exception as e:
        # Nunca deixa um erro na planilha derrubar o bot -- só loga.
        print(f"[erro] Falha ao registrar na planilha: {e}")
