"""Linha de base GOMS/KLM de especialista (instrumento do analista).

Usa o caminho mínimo da HTA e a resposta canônica de cada campo.
  python -m analista.klm
"""
import json
from pathlib import Path

from uxagent.tempo import tempo_operadores

RAIZ = Path(__file__).resolve().parent.parent


def linha_de_base(tarefa_id, gab, klm):
    g = gab["tarefas"][tarefa_id]
    passos, total = [], 0.0
    for p in g["caminho_minimo"]:
        fala, _, campo = p.partition(":")
        texto = g["resposta_canonica"][campo] if campo else None
        t, ops = tempo_operadores(fala, klm, texto)
        passos.append({"passo": p, "operadores": "".join(ops), "tempo_s": t})
        total += t
    return {"tarefa": tarefa_id, "A_min": g["A_min"], "tempo_klm_s": round(total, 2), "passos": passos}


def todas():
    gab = json.loads((RAIZ / "analista" / "gabaritos.json").read_text(encoding="utf-8"))
    klm = json.loads((RAIZ / "config" / "theta.json").read_text(encoding="utf-8"))["klm"]
    return {t: linha_de_base(t, gab, klm) for t in gab["tarefas"]}


if __name__ == "__main__":
    for t, b in todas().items():
        print(f"{t}: A_min={b['A_min']}  KLM={b['tempo_klm_s']} s")
        for p in b["passos"]:
            print(f"   {p['passo']:<18} {p['operadores']:<40} {p['tempo_s']:.2f} s")
