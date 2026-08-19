"""
Registro das apostas simuladas na planilha "Under Backtest" (Google Sheets).

Colunas da aba principal (linha 1 = cabeçalho):
A: Data | B: Jogo | C: País | D: Campeonato | E: Linha | F: Tip | G: Stake
H: Odd | I: Resultado | J: Retorno Líquido | K: ID (técnica, oculta)

Usa a coluna K (ID único da aposta) pra achar a linha certa e atualizar
Resultado/Retorno quando a aposta resolve, em vez de só escrever no final.

Requer: pip install gspread google-auth
"""
import json

import gspread
from google.oauth2.service_account import Credentials

import config

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_CABECALHO = ["Data", "Jogo", "País", "Campeonato", "Linha", "Tip", "Stake", "Odd", "Resultado", "Retorno Líquido", "ID"]

_cliente = None
_planilha = None
_aba_principal = None


def _conectar():
    global _cliente, _planilha, _aba_principal
    if _aba_principal is not None:
        return _aba_principal

    if not config.GOOGLE_SHEETS_CREDENTIALS_JSON:
        raise RuntimeError("GOOGLE_SHEETS_CREDENTIALS_JSON não configurado")

    info = json.loads(config.GOOGLE_SHEETS_CREDENTIALS_JSON)
    credenciais = Credentials.from_service_account_info(info, scopes=_SCOPES)
    _cliente = gspread.authorize(credenciais)
    _planilha = _cliente.open(config.GOOGLE_SHEETS_SPREADSHEET_NAME)

    try:
        _aba_principal = _planilha.worksheet("Apostas")
    except gspread.WorksheetNotFound:
        _aba_principal = _planilha.add_worksheet(title="Apostas", rows=2000, cols=len(_CABECALHO))
        _aba_principal.append_row(_CABECALHO)

    return _aba_principal


def registrar_entrada(id_aposta: str, data: str, jogo: str, pais: str, campeonato: str,
                       linha: float, tip: str, stake: float, odd: float):
    """Escreve a linha assim que a aposta é aberta, com Resultado/Retorno em branco."""
    aba = _conectar()
    aba.append_row([data, jogo, pais, campeonato, linha, tip, stake, odd, "", "", id_aposta])


def atualizar_resultado(id_aposta: str, resultado: str, retorno_liquido: float):
    """Encontra a linha pelo ID (coluna K) e preenche Resultado (I) e Retorno Líquido (J)."""
    aba = _conectar()
    celula = aba.find(id_aposta, in_column=11)  # coluna K = 11
    if celula is None:
        print(f"[sheets] ID de aposta não encontrado na planilha: {id_aposta}")
        return
    aba.update_cell(celula.row, 9, resultado)          # coluna I
    aba.update_cell(celula.row, 10, retorno_liquido)   # coluna J
