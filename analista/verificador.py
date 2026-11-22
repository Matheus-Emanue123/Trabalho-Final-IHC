"""Verificador externo de sucesso (instrumento do analista).

Lê apenas o `estado_final` gravado pela interface e aplica a chave de
`gabaritos.json`. A afirmação do agente não é lida. Acrescenta um evento
`avaliacao_externa` (origem=verificador) a cada arquivo de sessão.

  python -m analista.verificador dados/piloto
"""
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def normalizar(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def campo_ok(valor, regra):
    v = normalizar(valor)
    return all(normalizar(x) in v for x in regra.get("contem", [])) and \
        not any(normalizar(x) in v for x in regra.get("nao_contem", []))


def verificar_estado(final, gab_tarefa):
    por_campo = {c: campo_ok(final["campos"].get(c, ""), r) for c, r in gab_tarefa["chave"].items()}
    sucesso = final["status"] == "encerrada" and all(por_campo.values())
    return {"sucesso": sucesso, "status": final["status"], "campos_ok": por_campo}


def main(pasta):
    gab = json.loads((RAIZ / "analista" / "gabaritos.json").read_text(encoding="utf-8"))
    res = []
    for arq in sorted(Path(pasta).glob("*.json")):
        d = json.loads(arq.read_text(encoding="utf-8"))
        if "estado_final" not in d:
            continue
        d["eventos"] = [e for e in d["eventos"] if e["tipo"] != "avaliacao_externa"]
        v = verificar_estado(d["estado_final"], gab["tarefas"][d["meta"]["tarefa_id"]])
        d["eventos"].append({"execucao_id": d["meta"]["execucao_id"], "tipo": "avaliacao_externa",
                             "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                             "origem": "verificador", "dados": v})
        arq.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        res.append({"execucao_id": d["meta"]["execucao_id"], **v})
    print(f"{len(res)} sessões verificadas; sucesso em {sum(r['sucesso'] for r in res)}.")
    return res


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(RAIZ / "dados" / "piloto"))
