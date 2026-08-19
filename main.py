"""
Bot de monitoramento "Under Gols".

Fluxo a cada ciclo:
  1. Busca jogos de futebol ao vivo na Betsapi (pacote Bet365) -- essa
     chamada já traz placar e um minuto ESTIMADO (de graça, sem custo
     extra de API), calculado a partir do horário de início do jogo.
  2. Ignora ligas de categoria de base (U19/U20/etc) e Esoccer.
  3. Pra jogos cujo minuto estimado está dentro da janela ao redor do
     minuto-gatilho (ainda não verificados), confirma o minuto EXATO
     com uma chamada extra (/bet365/event) -- só nesses, não em todos.
  4. Se bateu o padrão (minuto exato >= gatilho e placar 0x0):
       - manda alerta no Telegram
       - registra apostas simuladas nas 3 linhas, com odd real
  5. Resolve apostas simuladas cujo jogo já não está mais ao vivo
  6. Uma vez por dia, manda o resumo consolidado no chat de simulação

Rodar com: python main.py
"""

import time
from datetime import datetime

import config
import estado
import betsapi_client
import telegram_client


def liga_excluida(nome_liga: str) -> bool:
    nome = (nome_liga or "").lower()
    return any(termo in nome for termo in config.LIGAS_EXCLUIDAS_TERMOS)


def dentro_da_janela_de_confirmacao(minuto_estimado) -> bool:
    if minuto_estimado is None:
        return False
    diff = abs(minuto_estimado - config.MINUTO_GATILHO)
    return diff <= config.JANELA_CONFIRMACAO_MINUTOS


def processar_jogo(jogo: dict, est: dict) -> None:
    fi = jogo["fi"]
    if estado.jogo_ja_verificado(est, fi):
        return
    if not jogo["jogo_comecou"]:
        return
    if not dentro_da_janela_de_confirmacao(jogo["minuto_estimado"]):
        return  # ainda longe do gatilho (ou já passou muito) -- barato, sem chamada extra

    # a partir daqui vale a pena gastar uma chamada de API pra confirmar
    # o minuto exato e, se bater o padrão, já pegar as odds junto
    try:
        detalhe = betsapi_client.obter_detalhe_evento(fi)
    except Exception as e:
        print(f"[erro] Falha ao buscar detalhe do jogo {fi}: {e}")
        return

    minuto_exato = detalhe["minuto_exato"]

    # DEBUG temporário: se não conseguimos calcular o minuto, mostra a
    # resposta bruta pra diagnosticar o formato real dos campos.
    if minuto_exato is None:
        print(f"[debug] Não consegui calcular minuto exato do jogo {fi} "
              f"({jogo['time_casa']} x {jogo['time_fora']}). "
              f"Resposta bruta (primeiros 3 itens): {detalhe.get('_bruto_debug', [])[:3]}")
        return

    if minuto_exato < config.MINUTO_GATILHO:
        return  # ainda não chegou -- tenta de novo no próximo ciclo

    # a partir daqui, ou bate o padrão agora, ou nunca mais vai bater
    # (minuto só cresce) -- marca como verificado de qualquer forma
    estado.marcar_jogo_verificado(est, fi)

    placar_bate = (jogo["gols_casa"], jogo["gols_fora"]) == config.PLACAR_GATILHO
    if not placar_bate:
        return

    descricao = f"{jogo['time_casa']} x {jogo['time_fora']} ({jogo['liga']})"

    texto_alerta = (
        f"⚽ <b>{descricao}</b>\n"
        f"0x0 aos {minuto_exato}min\n\n"
        f"Padrão batido — considerar Under 3.5 / 3 / 2.75"
    )
    telegram_client.enviar_alerta(texto_alerta)

    odds = detalhe["odds_under"]
    for linha in config.LINHAS_SIMULADAS:
        odd = odds.get(linha)
        if odd:
            estado.registrar_aposta_simulada(est, fi, linha, odd, descricao)
        else:
            print(f"[simulacao] Odd de '{linha}' não encontrada pro jogo {fi}, pulando essa linha.")


def resolver_apostas_pendentes(est: dict) -> None:
    """
    Verifica apostas simuladas em aberto: se o jogo já não está mais
    na lista de jogos ao vivo, consideramos que terminou e checamos
    o placar final pra apurar o resultado.
    """
    if not est["apostas_abertas"]:
        return

    jogos_ao_vivo = {j["fi"] for j in betsapi_client.listar_jogos_ao_vivo()}
    ainda_abertas = []

    for aposta in est["apostas_abertas"]:
        fi = aposta["fi"]
        if fi in jogos_ao_vivo:
            ainda_abertas.append(aposta)
            continue

        # TODO: jogo não está mais na lista de ao vivo -- assumimos
        # encerrado, mas ainda falta confirmar o placar final oficial
        # (essa lista só cobre jogos em andamento, não dá o resultado).
        # Próximo passo: integrar /bet365/result?event_id=... pra pegar
        # o placar final real antes de apurar a aposta.
        gols_totais_final = _placar_final_estimado(fi)
        if gols_totais_final is None:
            ainda_abertas.append(aposta)
            continue

        resolvida = estado.resolver_aposta(est, aposta, gols_totais_final)
        emoji = "✅" if resolvida["resultado"] == "green" else "❌"
        print(f"{emoji} {aposta['linha']} | {aposta['jogo']} | lucro: R${resolvida['lucro']}")

    est["apostas_abertas"] = ainda_abertas


def _placar_final_estimado(fi: str):
    """Placeholder -- ver TODO acima. Ainda não implementado."""
    return None


def enviar_relatorio_diario_se_necessario(est: dict) -> None:
    hoje = datetime.now().strftime("%Y-%m-%d")
    if est.get("ultimo_relatorio_enviado") == hoje:
        return

    agora = datetime.now().strftime("%H:%M")
    if agora < config.HORARIO_RELATORIO_DIARIO:
        return

    linhas_relatorio = [f"📊 <b>Relatório diário — {hoje}</b>\n"]
    for linha in config.LINHAS_SIMULADAS:
        banca_atual = est["banca"][linha]
        lucro_total = banca_atual - config.BANCA_INICIAL
        apostas_hoje = [
            a for a in est["apostas_resolvidas"]
            if a["linha"] == linha and a["data_resolucao"].startswith(hoje)
        ]
        greens = sum(1 for a in apostas_hoje if a["resultado"] == "green")
        reds = sum(1 for a in apostas_hoje if a["resultado"] == "red")

        linhas_relatorio.append(
            f"\n<b>{linha}</b>\n"
            f"Entradas hoje: {len(apostas_hoje)} ({greens}✅ / {reds}❌)\n"
            f"Banca atual: R${banca_atual:,.2f}\n"
            f"Lucro acumulado: R${lucro_total:,.2f}"
        )

    telegram_client.enviar_relatorio_simulacao("\n".join(linhas_relatorio))
    est["ultimo_relatorio_enviado"] = hoje


def ciclo() -> None:
    est = estado.carregar()

    jogos = betsapi_client.listar_jogos_ao_vivo()
    jogos = [j for j in jogos if not liga_excluida(j["liga"])]

    # DEBUG temporário: confirma visualmente que o ciclo está rodando e
    # conseguindo falar com a Betsapi. Remover depois que confirmarmos
    # que está tudo funcionando.
    na_janela = [j for j in jogos if dentro_da_janela_de_confirmacao(j["minuto_estimado"])]
    print(f"[ciclo {datetime.now().strftime('%H:%M:%S')}] {len(jogos)} jogos ao vivo (após filtro) | "
          f"{len(na_janela)} dentro da janela do minuto-gatilho")

    for jogo in jogos:
        processar_jogo(jogo, est)

    resolver_apostas_pendentes(est)
    enviar_relatorio_diario_se_necessario(est)

    estado.salvar(est)


def main() -> None:
    print("Bot Under Gols iniciado.")
    while True:
        try:
            ciclo()
        except Exception as e:
            print(f"[erro] {e}")
        time.sleep(config.INTERVALO_POLLING_SEGUNDOS)


if __name__ == "__main__":
    main()
