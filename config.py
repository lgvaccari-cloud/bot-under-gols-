"""
Configuração central do bot de monitoramento Under Gols.

As credenciais reais (tokens) NUNCA devem ficar escritas neste arquivo.
Elas são lidas de variáveis de ambiente (definidas no Render, ou num
arquivo .env local que não vai pro Git).
"""

import os

# ---------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

# Chat onde os alertas em tempo real são enviados (seu chat privado)
CHAT_ID_ALERTAS = os.environ.get("CHAT_ID_ALERTAS", "5511216910")

# Chat onde o relatório diário da simulação é enviado (grupo "Alerta Under")
CHAT_ID_SIMULACAO = os.environ.get("CHAT_ID_SIMULACAO", "-1004404899807")

# ---------------------------------------------------------------------
# Betsapi
# ---------------------------------------------------------------------
BETSAPI_TOKEN = os.environ.get("BETSAPI_TOKEN", "")
BETSAPI_BASE_URL = "https://api.b365api.com/v1"

# ---------------------------------------------------------------------
# Regra do padrão (gatilho do alerta)
# ---------------------------------------------------------------------
MINUTO_GATILHO = 21          # minuto do jogo em que verificamos o placar
PLACAR_GATILHO = (0, 0)      # (gols_casa, gols_fora) que dispara o alerta

# Linhas simuladas em paralelo (usadas só na simulação, não no alerta)
LINHAS_SIMULADAS = ["Under 3.5", "Under 3", "Under 2.75"]

# ---------------------------------------------------------------------
# Filtro de competições a ignorar (categorias de base)
# Qualquer liga cujo nome contenha um destes termos (case-insensitive)
# é ignorada tanto pro alerta quanto pra simulação.
# ---------------------------------------------------------------------
LIGAS_EXCLUIDAS_TERMOS = [
    "u17", "u18", "u19", "u20", "u21", "u22", "u23",
    "sub-17", "sub-18", "sub-19", "sub-20", "sub-21", "sub-22", "sub-23",
    "sub 17", "sub 18", "sub 19", "sub 20", "sub 21", "sub 22", "sub 23",
    "youth", "junior", "juvenil", "reserve", "reservas",
    "esoccer", "e-soccer", "efootball", "e-football", "cyber", "fifa",
]

# ---------------------------------------------------------------------
# Estratégia de checagem em 2 estágios (economiza chamadas de API):
# 1. /inplay_filter dá o horário de início -> estimamos o minuto de graça
# 2. só chamamos /bet365/event (que tem o relógio exato) pros jogos cujo
#    minuto ESTIMADO já está dentro dessa janela ao redor do gatilho
# ---------------------------------------------------------------------
JANELA_CONFIRMACAO_MINUTOS = 3   # confirma exato entre (21-3) e (21+3) min estimados


# ---------------------------------------------------------------------
# Simulação (banca fictícia)
# ---------------------------------------------------------------------
BANCA_INICIAL = 100_000.00   # R$100.000
STAKE_UNIDADE = 1_000.00     # R$1.000 = 1 unidade por entrada

# ---------------------------------------------------------------------
# Operação
# ---------------------------------------------------------------------
INTERVALO_POLLING_SEGUNDOS = 30   # frequência de checagem dos jogos ao vivo
HORARIO_RELATORIO_DIARIO = "23:55"  # horário (HH:MM, fuso do servidor) do resumo

# Arquivo onde o estado persiste entre reinicializações do processo
# (jogos já notificados, apostas simuladas em aberto, histórico)
ARQUIVO_ESTADO = "estado.json"

# ---------------------------------------------------------------------
# Modo teste (temporário)
# ---------------------------------------------------------------------
# Se True, IGNORA o placar/minuto reais e força o alerta a disparar no
# primeiro jogo ao vivo elegível que encontrar -- só pra validar o fluxo
# completo (mensagem no Telegram + busca de odds + registro da simulação)
# sem precisar esperar um 0x0 de verdade no minuto 21.
# IMPORTANTE: desligar (False) antes de rodar valendo de verdade.
MODO_TESTE = True

