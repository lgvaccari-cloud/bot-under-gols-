"""
Envio de mensagens pro Telegram via API HTTP direta (sem lib extra).
Dois destinos: chat de alertas (privado) e grupo de simulação ("Alerta Under").
"""
import requests

import config

API_URL = f"https://api.telegram.org/bot{{token}}/sendMessage"


def _enviar(chat_id: str, texto: str):
    if not config.TELEGRAM_BOT_TOKEN or not chat_id:
        print(f"[telegram] token/chat_id não configurado, mensagem não enviada: {texto}")
        return
    url = API_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "text": texto}, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[telegram] erro ao enviar mensagem: {e}")


def enviar_alerta(time_casa: str, time_fora: str, liga: str, linha_texto: str, odd: float):
    texto = f"{time_casa} x {time_fora} / {liga} / Under {linha_texto} @{odd}"
    _enviar(config.TELEGRAM_CHAT_ID_ALERTAS, texto)


def enviar_abertura_simulada(time_casa: str, time_fora: str, liga: str, linha_texto: str, odd: float, stake: float):
    texto = (
        f"🟢 Aposta aberta\n"
        f"{time_casa} x {time_fora} / {liga}\n"
        f"Under {linha_texto} @{odd} | Stake R${stake:,.2f}"
    )
    _enviar(config.TELEGRAM_CHAT_ID_SIMULACAO, texto)


def enviar_resultado_simulado(time_casa: str, time_fora: str, liga: str, linha_texto: str,
                               odd: float, resultado: str, retorno_liquido: float, banca_atual: float):
    sinal = "+" if retorno_liquido >= 0 else ""
    texto = (
        f"Resultado: {resultado}\n"
        f"{time_casa} x {time_fora} / {liga}\n"
        f"Under {linha_texto} @{odd} | {sinal}R${retorno_liquido:,.2f}\n"
        f"Banca atual: R${banca_atual:,.2f}"
    )
    _enviar(config.TELEGRAM_CHAT_ID_SIMULACAO, texto)


def enviar_resumo_diario(data_str: str, total_apostas: int, greens: int, reds: int,
                          voids_e_meios: int, resultado_dia: float, banca_atual: float):
    sinal = "+" if resultado_dia >= 0 else ""
    texto = (
        f"📊 Resumo do dia {data_str}\n"
        f"Apostas: {total_apostas} | Green: {greens} | Red: {reds} | Void/Meio: {voids_e_meios}\n"
        f"Resultado do dia: {sinal}R${resultado_dia:,.2f}\n"
        f"Banca atual: R${banca_atual:,.2f}"
    )
    _enviar(config.TELEGRAM_CHAT_ID_SIMULACAO, texto)
