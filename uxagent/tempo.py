"""Tempo comportamental simulado por operadores KLM (Card, Moran e Newell, 1980).

Cada fala u: vira uma sequência de operadores. O mesmo cálculo gera a linha de
base de especialista (analista/klm.py) e o tempo simulado do agente, que soma
a hesitação sorteada pelo controlador. A latência do LLM é gravada à parte e
nunca entra aqui.
"""


def operadores(fala, texto=None):
    if fala == "enviar":
        n = len(texto or "")
        return ["M", "P", "B", "H"] + ["K"] * n + ["H", "P", "B"]
    return ["M", "P", "B"]


def tempo_operadores(fala, klm, texto=None):
    ops = operadores(fala, texto)
    return round(sum(klm[o] for o in ops), 3), ops
