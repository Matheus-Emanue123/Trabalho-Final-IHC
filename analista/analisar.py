"""Classificação de erros, assinaturas MAC e métricas do piloto (analista).

Rupturas e mecanismos de prevenção/recuperação são detectados SÓ por
assinaturas no log de eventos, nunca pelo texto livre do LLM.

  python -m analista.analisar dados/piloto
"""
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .klm import todas as klm_todas
from .verificador import campo_ok

RAIZ = Path(__file__).resolve().parent.parent


def eventos(d, tipo):
    return [e for e in d["eventos"] if e["tipo"] == tipo]


def classificar(d, g):
    """Erros (Reason) por sessão, com oportunidades."""
    chave = g["chave"]
    figs = g.get("figuras_por_campo", {})
    erros = Counter()
    filtro_ativo = any(e["dados"].get("mecanismo") == "filtro_leitura" for e in eventos(d, "restricao_aplicada"))
    for e in eventos(d, "erro_capturado"):
        erros["deslize"] += 1
    for e in eventos(d, "acao_executada"):
        if e["fala"] != "enviar" or e["resposta"] not in ("d_campo_preenchido", "d_campo_substituido"):
            continue
        campo, texto = e["dados"]["campo"], e["dados"]["texto"]
        if campo_ok(texto, chave[campo]):
            continue
        outro = [c for c in chave if c != campo and campo_ok(texto, chave[c])]
        if outro:
            erros["deslize"] += 1              # campo trocado
        elif campo in figs:
            erros["engano_interpretacao"] += 1
        else:
            erros["engano_localizacao"] += 1
    final = d["estado_final"]
    vazios = [c for c in chave if not final["campos"].get(c, "").strip()]
    errados = [c for c in chave if final["campos"].get(c, "").strip() and not campo_ok(final["campos"][c], chave[c])]
    if vazios:
        erros["lapso"] += len(vazios)
    if final["status"] == "encerrada" and errados:
        erros["engano_avaliacao"] += 1
    oport = {"interpretacao": len(figs), "campo": len(chave), "encerramento": 1}
    return erros, oport, {"filtro_ativo": filtro_ativo, "campos_errados_fim": errados, "campos_vazios_fim": vazios}


def assinaturas_mac(d, erros):
    """Rupturas de comunicabilidade (de Souza e Leitão, 2009) por assinatura de log."""
    tags = Counter()
    execs = eventos(d, "acao_executada")
    rolou = False
    tinha_oculto = any("rolar_historico" in e["dados"].get("falas_habilitadas", [])
                       for e in eventos(d, "observacao_exposta"))
    anterior = None
    sem_prog = 0
    for e in execs:
        f = e["fala"]
        if f == "rolar_historico":
            rolou = True
        if f == "enviar" and tinha_oculto and not rolou:
            tags["Cadê?"] += 1
        if f == "reformular":
            tags["O que é isto?"] += 1
        if f in ("ajuda_como_fazer",):
            tags["Socorro!"] += 1
        if e["resposta"] == "d_campo_substituido" or f == "ajuda_corrigir":
            tags["Epa!"] += 1
        if f == "nova_pergunta" and anterior == "reformular":
            tags["Assim não dá"] += 1
        mudou = e["dados"]["campos_antes"] != e["dados"]["campos_depois"]
        sem_prog = 0 if mudou else sem_prog + 1
        if sem_prog == 2 and e["cena"] == "conversa":
            tags["E agora?"] += 1
        anterior = f
    if erros.get("engano_avaliacao"):
        tags["Para mim está bom"] += 1
    if any(e["dados"].get("mecanismo") == "limite_tentativas" for e in eventos(d, "restricao_aplicada")) \
            or any(e["fala"] == "confirmar_encerrar" for e in execs) \
            or d["estado_final"]["status"] == "interrompida":
        tags["Desisto"] += 1
    return tags


def mecanismos_ihc(d):
    """Prevenção e recuperação acionadas (PP, PA, AL, RA, CE) por assinatura."""
    m = Counter()
    m["PA"] = sum(1 for e in eventos(d, "acao_executada") if e["resposta"] == "d_pede_confirmacao")
    m["AL"] = len(eventos(d, "alerta_exibido"))
    m["RA"] = sum(1 for e in eventos(d, "acao_executada")
                  if e["resposta"] == "d_campo_substituido" or e["fala"] == "ajuda_corrigir")
    m["CE"] = len(eventos(d, "erro_capturado"))
    m["PP"] = sum(1 for e in eventos(d, "observacao_exposta")
                  if "rolar_historico" not in e["dados"].get("falas_habilitadas", []))
    return m


def main(pasta):
    gab = json.loads((RAIZ / "analista" / "gabaritos.json").read_text(encoding="utf-8"))
    base = klm_todas()
    grupos = defaultdict(list)
    for arq in sorted(Path(pasta).glob("*.json")):
        d = json.loads(arq.read_text(encoding="utf-8"))
        if "estado_final" not in d:
            continue
        av = eventos(d, "avaliacao_externa")
        if not av:
            raise SystemExit("Rode antes: python -m analista.verificador " + pasta)
        t, c = d["meta"]["tarefa_id"], d["meta"]["condicao"]
        g = gab["tarefas"][t]
        erros, oport, info = classificar(d, g)
        execs = eventos(d, "acao_executada")
        ajudas = Counter(e["dados"]["tipo_ajuda"] for e in eventos(d, "ajuda_solicitada"))
        props = eventos(d, "acao_proposta")
        grupos[(t, c)].append({
            "execucao_id": d["meta"]["execucao_id"], "sucesso": av[-1]["dados"]["sucesso"],
            "status": d["estado_final"]["status"], "A": len(execs), "A_excesso": len(execs) - g["A_min"],
            "U_s": ajudas.get("significado", 0), "ajudas": dict(ajudas), "erros": dict(erros), "oport": oport,
            "mac": dict(assinaturas_mac(d, erros)), "ihc": dict(mecanismos_ihc(d)),
            "mecanismos": dict(Counter(e["dados"]["mecanismo"] for e in eventos(d, "restricao_aplicada"))),
            "rejeitadas": len(eventos(d, "acao_rejeitada")), "falhas": len(eventos(d, "falha_tecnica")),
            "tempo_simulado_s": d["estado_final"]["tempo_simulado_s"],
            "latencia_llm_media_s": round(st.mean([p["dados"]["latencia_llm_s"] for p in props]), 3) if props else None,
            "tokens": sum((p["dados"].get("uso") or {}).get("total_tokens", 0) for p in props),
            "amostra": eventos(d, "sessao_iniciada")[0]["dados"]["amostra"], **info})
    resumo = []
    for (t, c), ss in sorted(grupos.items()):
        n = len(ss)
        tot_err = Counter()
        for s in ss:
            tot_err.update(s["erros"])
        op = ss[0]["oport"]
        A = [s["A"] for s in ss]
        r = {
            "tarefa": t, "condicao": c, "n": n,
            "S": round(sum(s["sucesso"] for s in ss) / n, 3),
            "erros_total": dict(tot_err),
            "R_e_interp": round(tot_err["engano_interpretacao"] / (op["interpretacao"] * n), 3) if op["interpretacao"] else None,
            "R_e_campo": round(sum(len(s["campos_errados_fim"]) + len(s["campos_vazios_fim"]) for s in ss) / (op["campo"] * n), 3),
            "R_e_aval": round(tot_err["engano_avaliacao"] / n, 3),
            "A_mediana": st.median(A), "A_min_obs": min(A), "A_max_obs": max(A),
            "A_min_klm": base[t]["A_min"], "A_excesso_mediano": st.median([s["A_excesso"] for s in ss]),
            "U_s_medio": round(st.mean([s["U_s"] for s in ss]), 3),
            "frac_com_suporte": round(sum(1 for s in ss if s["U_s"] > 0) / n, 3),
            "ajudas_total": dict(sum((Counter(s["ajudas"]) for s in ss), Counter())),
            "tempo_sim_mediano_s": round(st.median([s["tempo_simulado_s"] for s in ss]), 2),
            "tempo_klm_s": base[t]["tempo_klm_s"],
            "razao_tempo_klm": round(st.median([s["tempo_simulado_s"] for s in ss]) / base[t]["tempo_klm_s"], 2),
            "mac_total": dict(sum((Counter(s["mac"]) for s in ss), Counter())),
            "ihc_total": dict(sum((Counter(s["ihc"]) for s in ss), Counter())),
            "mecanismos_disparados": dict(sum((Counter(s["mecanismos"]) for s in ss), Counter())),
            "rejeitadas": sum(s["rejeitadas"] for s in ss), "falhas_tecnicas": sum(s["falhas"] for s in ss),
            "latencia_llm_mediana_s": st.median([s["latencia_llm_media_s"] for s in ss if s["latencia_llm_media_s"] is not None]) if any(s["latencia_llm_media_s"] is not None for s in ss) else None,
            "tokens_total": sum(s["tokens"] for s in ss),
        }
        resumo.append(r)
    saida = RAIZ / "dados" / "resultados"
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "metricas.json").write_text(json.dumps({"resumo": resumo, "sessoes": {f"{k[0]}_{k[1]}": v for k, v in grupos.items()},
                                                     "klm": base}, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in resumo:
        print(f"{r['tarefa']} {r['condicao']:<10} n={r['n']:<3} S={r['S']:.2f} A~={r['A_mediana']} (min {r['A_min_klm']}) "
              f"Us={r['U_s_medio']:.2f} t_sim~={r['tempo_sim_mediano_s']}s KLM={r['tempo_klm_s']}s "
              f"erros={r['erros_total']} mac={r['mac_total']}")
    return resumo


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(RAIZ / "dados" / "piloto"))
