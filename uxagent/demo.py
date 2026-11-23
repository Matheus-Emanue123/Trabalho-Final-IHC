"""Demonstração ao vivo (E5): uma execução completa do UX-Agent narrada no terminal.

  python -m uxagent.demo                     # C2, persona, semente 20261046, pausa a cada passo
  python -m uxagent.demo --tarefa C1 --auto  # sem pausas

Mostra: tarefa recebida, parâmetros sorteados fora do prompt, a tela que o agente
recebe em cada passo, os mecanismos que agiram, a resposta do GPT, a ação executada,
os eventos gravados no log e, no fim, o veredito do verificador externo.
"""
import argparse
import json
import os

from . import molic
from .agente import AgenteLLM
from .executar import executar_sessao
from .interface import RAIZ

os.system("")  # habilita cores ANSI no terminal do Windows
COR = {"tit": "\033[1;36m", "mec": "\033[33m", "gpt": "\033[1;35m", "ok": "\033[1;32m",
       "no": "\033[1;31m", "dim": "\033[90m", "fim": "\033[0m"}


def c(cor, txt):
    return f"{COR[cor]}{txt}{COR['fim']}"


class Narrador:
    def __init__(self, pausar):
        self.pausar = pausar
        self.eventos_passo = []

    def __call__(self, e):
        t, d = e["tipo"], e["dados"]
        self.eventos_passo.append(t)
        if t == "sessao_iniciada":
            a = d["amostra"]
            print(c("tit", "\n=== 1. A PERSONA É SORTEADA (fora do prompt; o GPT não vê isto) ==="))
            print(f"  habilidade de linguagem: {a['h']}")
            print(f"  prob. de leitura literal por tipo de figura: {a['p_lit']}")
            print(f"  prob. de explorar mais: {a['p_explore']} | de pedir explicação: {a['p_sup']} | "
                  f"de aceitar resposta incompleta: {a['p_accept']}")
            print(f"  hesitação média: {a['hesitacao_media_s']} s | desiste após {a['k_desistencia']} ações sem progresso")
            disp = [b for b, v in d["filtro_leitura"].items() if v]
            print("  filtro de leitura literal vai agir no(s) bloco(s): " + (", ".join(disp) if disp else "nenhum"))
            self.pausa()
        elif t == "observacao_exposta":
            print(c("tit", f"\n=== PASSO {e['passo']} ==="))
        elif t == "restricao_aplicada":
            if d.get("mecanismo") == "filtro_leitura":
                print(c("mec", f"  [mecanismo] filtro de leitura: o bloco {d['bloco']} chega ao GPT na versão superficial"))
            else:
                print(c("mec", f"  [mecanismo] {d['mecanismo']}: botões retirados neste passo -> {', '.join(d['removidas'])}"))
        elif t == "observacao_transformada":
            print(c("dim", "  --- tela enviada ao GPT (o_t) ---"))
            for linha in d["texto"].splitlines():
                print(c("dim", "  | ") + linha)
        elif t == "acao_proposta":
            print(c("gpt", f"  GPT respondeu: {d['bruto']}") + c("dim", f"   ({d['latencia_llm_s']} s de API)"))
        elif t == "acao_rejeitada":
            print(c("no", "  proposta fora da lista de ações permitidas: rejeitada"))
        elif t == "acao_executada":
            print(f"  ação executada  u: {e['fala']}  ->  resposta do sistema  d: {molic.FALAS_D[e['resposta']]}")
            print(c("dim", f"  tempo simulado: +{d['tempo_operadores_s']} s (KLM) +{d['hesitacao_s']} s (hesitação)"))
        elif t == "estado_interface":
            campos = ", ".join(f"{k}=\"{v}\"" if v else f"{k}=(vazio)" for k, v in d["campos"].items())
            print(f"  campos agora: {campos}")
            print(c("dim", f"  eventos gravados neste passo: {', '.join(self.eventos_passo)}"))
            self.eventos_passo = []
            self.pausa()
        elif t in ("encerrada", "interrompida"):
            print(c("tit", f"\n=== FIM DA SESSÃO: {t} ==="))

    def pausa(self):
        if self.pausar:
            input(c("dim", "  [Enter para continuar]"))


def main():
    ap = argparse.ArgumentParser(description="Demonstração narrada de uma execução do UX-Agent.")
    ap.add_argument("--tarefa", default="C2", choices=["C1", "C2"])
    ap.add_argument("--condicao", default="perfil", choices=["perfil", "comparador"])
    ap.add_argument("--semente", type=int, default=20261046)
    ap.add_argument("--agente", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--auto", action="store_true", help="não pausar entre os passos")
    a = ap.parse_args()
    theta = json.loads((RAIZ / "config" / "theta.json").read_text(encoding="utf-8"))
    pasta = RAIZ / "dados" / "demo"
    ag = AgenteLLM(a.agente, semente=a.semente)
    print(c("tit", "=== UX-AGENT: DEMONSTRAÇÃO DE UMA EXECUÇÃO COMPLETA ==="))
    print(f"Tarefa {a.tarefa} | condição {a.condicao} | semente {a.semente} | modelo {ag.nome}")
    print("O GPT faz o papel da estudante E. e só recebe o que a tela mostra. "
          "O gabarito fica com o verificador externo, fora do alcance do agente.")
    narr = Narrador(not a.auto)
    arq = executar_sessao(a.tarefa, a.condicao, a.semente, ag, theta, pasta, ao_evento=narr)
    d = json.loads(arq.read_text(encoding="utf-8"))
    print(f"\nLog salvo em {arq.relative_to(RAIZ)} com {len(d['eventos'])} eventos.")
    narr.pausa()

    # Verificação externa: módulo do analista, aplicado só ao estado final
    from analista.verificador import verificar_estado
    gab = json.loads((RAIZ / "analista" / "gabaritos.json").read_text(encoding="utf-8"))
    v = verificar_estado(d["estado_final"], gab["tarefas"][a.tarefa])
    print(c("tit", "\n=== VERIFICAÇÃO EXTERNA (lê só o estado final; ignora o que o GPT acha) ==="))
    for campo, ok in v["campos_ok"].items():
        print(f"  {campo}: \"{d['estado_final']['campos'][campo]}\"  ->  " + (c("ok", "dentro da chave") if ok else c("no", "fora da chave")))
    print("  resultado: " + (c("ok", "SUCESSO") if v["sucesso"] else c("no", "FALHA")))
    # acrescenta o evento avaliacao_externa só ao log desta sessão
    from datetime import datetime, timezone
    d["eventos"] = [e for e in d["eventos"] if e["tipo"] != "avaliacao_externa"]
    d["eventos"].append({"execucao_id": d["meta"]["execucao_id"], "tipo": "avaliacao_externa",
                         "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                         "origem": "verificador", "dados": v})
    arq.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(c("dim", f"  evento avaliacao_externa acrescentado ao log {arq.name}"))


if __name__ == "__main__":
    main()
