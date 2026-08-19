"""
Conversão de odds fracionárias (formato do feed Bet365) para decimais,
e lógica de resolução de apostas Under (linha cheia, meia linha e linha quebrada/asiática).
"""
import re


def fracionario_para_decimal(odd_str: str) -> float:
    """
    O feed Bet365 retorna odds no formato fracionário, ex: "11/5", "2/1", "4/5".
    Decimal = 1 + numerador/denominador.
    Se já vier em formato decimal (ex: "1.85"), retorna direto.
    """
    odd_str = str(odd_str).strip()
    if "/" in odd_str:
        try:
            num, den = odd_str.split("/")
            return round(1 + (float(num) / float(den)), 3)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return round(float(odd_str), 3)
    except ValueError:
        return None


def _componentes_da_linha(linha: float):
    """
    Decompõe uma linha de gols em 1 ou 2 componentes "simples" pra resolução:
      - linha inteira (3, 4)        -> 1 componente, pode dar Void (push)
      - linha .5 (3.5, 2.5)         -> 1 componente, nunca dá Void
      - linha .25 / .75 (2.75,3.25) -> 2 componentes (linha-0.25 e linha+0.25), meia stake cada
    """
    resto = round(linha % 1, 2)
    if resto == 0.0 or resto == 0.5:
        return [linha]
    # .25 ou .75 -> quebrada / asiática
    return [round(linha - 0.25, 2), round(linha + 0.25, 2)]


def _resultado_componente(componente: float, total_gols: int) -> str:
    """Resultado de um componente simples de Under: 'green', 'void' ou 'red'."""
    if total_gols < componente:
        return "green"
    if total_gols == componente:
        return "void"   # só acontece em linha inteira
    return "red"


def resolver_aposta(linha: float, odd: float, total_gols: int, stake: float = 1000.0):
    """
    Retorna (resultado_label, retorno_bruto) para uma aposta Under <linha> @<odd>,
    dado o total de gols final do jogo.

    resultado_label ∈ {"Green", "Void", "Red", "Meio Green", "Meio Red"}
    retorno_bruto = valor que volta (stake incluso se não for perda total)
    """
    componentes = _componentes_da_linha(linha)
    stake_por_componente = stake / len(componentes)

    retorno_total = 0.0
    resultados = []
    for c in componentes:
        r = _resultado_componente(c, total_gols)
        resultados.append(r)
        if r == "green":
            retorno_total += stake_por_componente * odd
        elif r == "void":
            retorno_total += stake_por_componente
        else:  # red
            retorno_total += 0.0

    if len(componentes) == 1:
        label = {"green": "Green", "void": "Void", "red": "Red"}[resultados[0]]
    else:
        # dois componentes (linha quebrada)
        if resultados == ["green", "green"]:
            label = "Green"
        elif resultados == ["red", "red"]:
            label = "Red"
        elif "green" in resultados and "red" not in resultados:
            label = "Meio Green"   # green + void
        elif "red" in resultados and "green" not in resultados:
            label = "Meio Red"     # red + void
        else:
            # green + red misto (não deveria ocorrer numa linha quebrada real, mas por segurança)
            label = "Meio Green" if retorno_total >= stake else "Meio Red"

    retorno_liquido = round(retorno_total - stake, 2)
    return label, retorno_liquido


def linha_para_texto(linha: float) -> str:
    """3.0 -> '3', 2.75 -> '2.75', 3.5 -> '3.5'"""
    if linha == int(linha):
        return str(int(linha))
    return str(linha)
