"""
Teste rápido e isolado: só confirma que os tokens do Telegram estão
certos, mandando uma mensagem em cada um dos 2 chats.

Rodar com: python test_telegram.py
Não depende da Betsapi nem de jogo nenhum -- só testa a "última milha"
(conseguir mandar mensagem de fato).
"""

import telegram_client

print("Mandando mensagem de teste pro chat de alertas...")
telegram_client.enviar_alerta("🧪 Teste de notificação -- se você está vendo isso, o chat de alertas está funcionando!")

print("Mandando mensagem de teste pro chat de simulação...")
telegram_client.enviar_relatorio_simulacao("🧪 Teste de notificação -- se você está vendo isso, o chat de simulação está funcionando!")

print("Pronto. Confira os dois chats no Telegram.")
