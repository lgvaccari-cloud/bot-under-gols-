"""
Configurações centrais do Bot Under Gols.
Todas as credenciais vêm de variáveis de ambiente (nunca hardcode tokens aqui).
"""
import os

# ---------- Credenciais / IDs (definir no .env ou nas env vars do Render) ----------
BETSAPI_TOKEN = os.environ.get("BETSAPI_TOKEN", "")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID_ALERTAS = os.environ.get("TELEGRAM_CHAT_ID_ALERTAS", "")       # chat privado de alertas
TELEGRAM_CHAT_ID_SIMULACAO = os.environ.get("TELEGRAM_CHAT_ID_SIMULACAO", "")  # grupo "Alerta Under"

GOOGLE_SHEETS_CREDENTIALS_JSON = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")  # conteúdo JSON da service account (string)
GOOGLE_SHEETS_SPREADSHEET_NAME = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_NAME", "Under Backtest")

STATE_FILE_PATH = os.environ.get("STATE_FILE_PATH", "/data/state.json")  # /data = disco persistente no Render

# ---------- Regras da estratégia ----------
SPORT_ID_FUTEBOL = 1

MINUTO_GATILHO = 21          # a partir daqui já pode alertar
MINUTO_RECHECK_LIMITE = 26   # continua rechecando até esse minuto se ainda 0x0

LINHAS_MONITORADAS = [4.5, 4.25, 4.0, 3.75, 3.5, 3.25, 3.0, 2.75]

ODD_MINIMA = 1.72
ODD_MAXIMA = 2.00
ODD_ALVO = 1.90               # entre as linhas elegíveis, escolhe a odd mais próxima disso

# ---------- Simulação / banca fictícia ----------
BANCA_INICIAL = 100_000.0
STAKE_PADRAO = 1_000.0        # 1 unidade

# ---------- Operação do bot ----------
INTERVALO_CICLO_SEGUNDOS = 30
FOLGA_ESTIMATIVA_MINUTOS = 8   # tolerância extra pra jogos que começam atrasados

# Modo teste: ignora o filtro de placar 0x0 e a janela de minuto-gatilho,
# pra validar rapidamente o fluxo de ponta a ponta (alerta -> simulação ->
# planilha) em qualquer jogo ao vivo, sem esperar bater o padrão real.
# NUNCA deixar True em produção real.
MODO_TESTE = os.environ.get("MODO_TESTE", "false").lower() == "true"

# Termos de busca ampliados pra capturar linhas quebradas/asiáticas de gols
TERMOS_MERCADO_GOLS = [
    "goals over/under",
    "over/under",
    "asian total goals",
    "total goals",
    "match goals",
]

# Ligas/competições de base a excluir (case-insensitive, substring match)
PALAVRAS_EXCLUIR_LIGA = [
    "sub-23", "sub-22", "sub-21", "sub-20", "sub-19", "sub-18", "sub-17",
    "u23", "u-23", "u22", "u-22", "u21", "u-21", "u20", "u-20", "u19", "u-19",
    "u18", "u-18", "u17", "u-17",
    "youth", "junior", "juvenil", "academy", "reserves", "reserve", "b team",
]
