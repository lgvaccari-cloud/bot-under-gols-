"""Envio de mensagens pro Telegram."""

import requests
import config


def enviar_mensagem(chat_id: str, texto: str) -> None:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "HTML",
    }
    resp = requests.post(url, json=payload, timeout=10)
    if not resp.ok:
        print(f"[telegram] Falha ao enviar mensagem: {resp.status_code} {resp.text}")


def enviar_alerta(texto: str) -> None:
    enviar_mensagem(config.CHAT_ID_ALERTAS, texto)


def enviar_relatorio_simulacao(texto: str) -> None:
    enviar_mensagem(config.CHAT_ID_SIMULACAO, texto)
