"""
Teste rápido e isolado: escreve uma linha de teste na planilha, pra
confirmar que a credencial do Google e o ID da planilha estão certos,
sem precisar esperar um jogo real terminar.

Rodar com: python test_sheets.py
"""

from datetime import datetime

import sheets_client

print("Tentando escrever uma linha de teste na planilha...")

sheets_client.registrar_linha(
    data_hora=datetime.now().isoformat(),
    campeonato="Teste - Liga Fictícia",
    partida="Time A x Time B (TESTE)",
    linha=3.0,
    odd=1.85,
    resultado="green",
    lucro_reais=850.0,
)

print("Pronto. Confere a planilha 'Under Backtest' -- deve ter uma linha nova "
      "com 'Time A x Time B (TESTE)'. Se não aparecer nada e não deu erro "
      "acima, alguma coisa está silenciosamente falhando -- me avisa.")
