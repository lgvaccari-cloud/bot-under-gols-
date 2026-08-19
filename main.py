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
    """
    True a partir de (MINUTO_GATILHO - JANELA_CONFIRMACAO_MINUTOS) em
    diante, até MINUTO_LIMITE_RECHECK -- ou seja, começamos a checar
    um pouco antes do gatilho (pra não perder o momento exato) e
    continuamos checando a cada ciclo até o limite, não só uma vez.
    """
    if minuto_estimado is None:
        return False
    inicio = config.MINUTO_GATILHO - config.JANELA_CONFIRMACAO_MINUTOS
    return inicio <= minuto_estimado <= config.MINUTO_LIMITE_RECHECK


def processar_jogo(jogo: dict, est: dict, forcar_teste: bool = False) -> None:
    fi = jogo["fi"]
    if estado.jogo_ja_verificado(est, fi):
        return
    if not jogo["jogo_comecou"]:
        return

    # checagem BARATA (sem gastar API): se o placar já não é mais 0x0,
    # o jogo nunca mais vai bater o padrão -- marca como verificado e
    # para de gastar chamadas com ele, sem precisar confirmar odd.
    if not forcar_teste and (jogo["gols_casa"], jogo["gols_fora"]) != config.PLACAR_GATILHO:
        estado.marcar_jogo_verificado(est, fi)
        return

    if not forcar_teste and not dentro_da_janela_de_confirmacao(jogo["minuto_estimado"]):
        return  # ainda longe do gatilho, ou já passou do limite de recheck

    # a partir daqui vale a pena gastar uma chamada de API pra confirmar
    # o minuto exato e as odds atuais
    try:
        detalhe = betsapi_client.obter_detalhe_evento(fi)
    except Exception as e:
        print(f"[erro] Falha ao buscar detalhe do jogo {fi}: {e}")
        return

    minuto_exato = detalhe["minuto_exato"]

    if minuto_exato is None:
        print(f"[debug] Não consegui calcular minuto exato do jogo {fi} "
              f"({jogo['time_casa']} x {jogo['time_fora']}). "
              f"Resposta bruta (primeiros 3 itens): {detalhe.get('_bruto_debug', [])[:3]}")
        if not forcar_teste:
            return

    if not forcar_teste and minuto_exato < config.MINUTO_GATILHO:
        return  # ainda não chegou no minuto exato -- tenta de novo no próximo ciclo

    if not forcar_teste and minuto_exato > config.MINUTO_LIMITE_RECHECK:
        # passou do limite de tentativas -- desiste desse jogo
        estado.marcar_jogo_verificado(est, fi)
        return

    placar_bate = (jogo["gols_casa"], jogo["gols_fora"]) == config.PLACAR_GATILHO
    if not forcar_teste and not placar_bate:
        estado.marcar_jogo_verificado(est, fi)
        return

    odds = detalhe["odds_under"]
    descricao_debug = f"{jogo['time_casa']} x {jogo['time_fora']}"
    print(f"[debug] Odds encontradas pro jogo {fi} ({descricao_debug}, minuto {minuto_exato}): {odds}")

    # só entram no alerta/simulação as linhas cuja odd está dentro da
    # faixa configurada (ODD_MINIMA a ODD_MAXIMA) -- fora da faixa,
    # a linha é ignorada mesmo que o placar bata o padrão.
    linhas_na_faixa = {
        linha: odd for linha, odd in odds.items()
        if odd is not None and config.ODD_MINIMA <= odd <= config.ODD_MAXIMA
    }

    if not linhas_na_faixa and not forcar_teste:
        print(f"[debug] Nenhuma linha na faixa de odd pro jogo {fi} no minuto {minuto_exato} "
              f"-- tenta de novo no próximo ciclo (ainda dentro do limite de recheck).")
        return  # NÃO marca como verificado -- tenta de novo no próximo ciclo

    # a partir daqui, ou disparou o alerta, ou (modo teste) segue mesmo
    # sem linha -- de qualquer forma, esse jogo está resolvido
    estado.marcar_jogo_verificado(est, fi)

    minuto_exibido = minuto_exato if minuto_exato is not None else jogo["minuto_estimado"]
    prefixo_teste = "🧪 [MODO TESTE — ignora placar/minuto real] " if forcar_teste else ""
    descricao = f"{jogo['time_casa']} x {jogo['time_fora']} ({jogo['liga']})"

    linhas_texto = "\n".join(
        f"• {linha}: odd {odd}" for linha, odd in linhas_na_faixa.items()
    ) if linhas_na_faixa else "(nenhuma linha na faixa de odd — modo teste)"

    texto_alerta = (
        f"{prefixo_teste}⚽ <b>{descricao}</b>\n"
        f"placar real: {jogo['gols_casa']}x{jogo['gols_fora']} aos ~{minuto_exibido}min\n\n"
        f"Padrão batido — linhas na faixa de odd ({config.ODD_MINIMA}-{config.ODD_MAXIMA}):\n"
        f"{linhas_texto}"
    )
    telegram_client.enviar_alerta(texto_alerta)

    for linha, odd in linhas_na_faixa.items():
        estado.registrar_aposta_simulada(est, fi, linha, odd, descricao)


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

    # MODO TESTE: força o alerta uma única vez, no primeiro jogo já
    # começado que achar, ignorando placar/minuto real. Serve só pra
    # validar o fluxo completo (Telegram + odds + simulação).
    if config.MODO_TESTE and not est.get("teste_ja_disparado"):
        # Evita jogos já em prorrogação/pênaltis (minuto estimado > 85),
        # que não têm mais mercado normal de Under gols -- prioriza um
        # jogo dentro do tempo normal pra validar o fluxo completo.
        candidatos = [
            j for j in jogos
            if j["jogo_comecou"]
            and j["minuto_estimado"] is not None
            and 5 <= j["minuto_estimado"] <= 80
        ]
        if not candidatos:
            candidatos = [j for j in jogos if j["jogo_comecou"]]
        if candidatos:
            print(f"[modo teste] Forçando alerta no jogo: "
                  f"{candidatos[0]['time_casa']} x {candidatos[0]['time_fora']}")
            processar_jogo(candidatos[0], est, forcar_teste=True)
            est["teste_ja_disparado"] = True
        else:
            print("[modo teste] Nenhum jogo já começado encontrado ainda, tentando de novo no próximo ciclo.")

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
