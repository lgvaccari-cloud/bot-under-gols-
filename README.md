# Bot Under Gols

Monitora jogos de futebol ao vivo via BetsAPI (feed Bet365), detecta jogos 0x0
no minuto-gatilho e manda alerta no Telegram quando a odd de alguma linha de
Under gols está numa faixa alvo. Simula as apostas com banca fictícia e
registra tudo numa planilha do Google Sheets.

## Estrutura

| Arquivo             | Responsabilidade |
|----------------------|-------------------|
| `config.py`          | Constantes e variáveis de ambiente |
| `betsapi_client.py`  | Chamadas à BetsAPI (jogos ao vivo, odds, placar final) |
| `odds_utils.py`      | Conversão de odds e lógica de resolução de apostas (linha cheia/quebrada) |
| `telegram_client.py` | Envio de mensagens (alerta, simulação, resumo diário) |
| `sheets_client.py`   | Registro das apostas no Google Sheets |
| `state_manager.py`   | Persistência do estado (jogos alertados, apostas abertas, banca) em JSON |
| `main.py`            | Loop principal |

## Regras da estratégia (configuráveis em `config.py`)

- Placar 0x0 obrigatório.
- Minuto-gatilho: 21. Recheca a cada ciclo até o minuto 26 enquanto seguir 0x0
  (a odd muda com o tempo, então não desiste na primeira checagem).
- Linhas monitoradas: Under 4.5, 4.25, 4, 3.75, 3.5, 3.25, 3, 2.75.
- Só entra a linha cuja odd no momento está entre 1.72 e 2.00.
- Se várias linhas qualificarem no mesmo jogo, escolhe a com odd mais próxima
  de 1.90 — só uma por alerta.
- Exclui ligas de base (sub-19/sub-20/U19/U20 etc. — lista em
  `PALAVRAS_EXCLUIR_LIGA`).
- Banca fictícia: R$100.000, stake fixo de R$1.000 (1 unidade) por entrada.

## Setup

1. `pip install -r requirements.txt`
2. Copie `.env.example` para `.env` e preencha:
   - `BETSAPI_TOKEN`: token da BetsAPI.
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID_ALERTAS`, `TELEGRAM_CHAT_ID_SIMULACAO`.
   - `GOOGLE_SHEETS_CREDENTIALS_JSON`: conteúdo do JSON da service account
     (compartilhe a planilha "Under Backtest" com o e-mail da service account).
3. No Render: crie um Background Worker apontando pro repositório, configure
   as mesmas variáveis de ambiente, **adicione um disco persistente** montado
   em `/data` (bate com `STATE_FILE_PATH=/data/state.json`), e rode
   `python -u main.py`.

## Pontos que precisam de validação com dados reais (não dá pra confirmar sem token ativo)

A BetsAPI não documenta publicamente o payload completo de `/bet365/event`
para mercados de gols quebrados/asiáticos — a extração em
`betsapi_client.obter_odds_under()` foi escrita com base na documentação
geral de campos (`MG`/`MA`/`PA`, odds em formato fracionário tipo `"11/5"`)
e pode precisar de ajuste fino nos seguintes pontos, os mesmos que você já
tinha depurado na versão anterior:

- Nome exato do grupo de mercado (`MG.NA`) onde aparecem as linhas
  quebradas/asiáticas — pode não bater 100% com `TERMOS_MERCADO_GOLS`.
- Formato exato do nome do participante (`PA.NA`) para as linhas — o regex
  `under\s*([\d.]+)` assume algo como `"Under 3.5"`.
- Se a odd (`PA.OD`) realmente vem sempre em formato fracionário ou às vezes
  já decimal — o conversor trata os dois casos, mas vale conferir no log.

Recomendo rodar em modo teste (como você já fazia) logando o payload bruto de
`obter_odds_under` pra um jogo real antes de confiar 100% na extração.

## O que NÃO foi incluído

- Credenciais reais (óbvio).
- O deploy em si no Render — você recria o serviço do zero, como combinado.
