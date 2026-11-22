"""Executor de sessões do UX-Agent.

Exemplos:
  python -m uxagent.executar --tarefas C1 C2 --condicoes perfil comparador --n 10 --agente openai
  python -m uxagent.executar --tarefas C1 --n 1 --agente controle_sucesso
"""
import argparse
import hashlib
import json
from pathlib import Path

from . import molic
from .agente import AgenteLLM, AgenteControle, PROMPT_SISTEMA, INSTRUCAO_PROTOCOLO
from .interface import EstadoInterface, carregar_tarefa, RAIZ
from .mecanismos import Controlador
from .observacao import traduzir
from .registrador import Registrador
from .tempo import tempo_operadores


def config_id(theta, versao_roteiro, modelo):
    base = json.dumps(theta, sort_keys=True) + PROMPT_SISTEMA + INSTRUCAO_PROTOCOLO + versao_roteiro + modelo
    return hashlib.sha256(base.encode()).hexdigest()[:12]


def hash_prompt():
    return hashlib.sha256((PROMPT_SISTEMA + INSTRUCAO_PROTOCOLO).encode()).hexdigest()[:12]


def executar_sessao(tarefa_id, condicao, semente, agente, theta, pasta, permitir_validacao=False,
                    origem="sintetica", verbose=False):
    item = carregar_tarefa(tarefa_id, permitir_validacao)
    estado = EstadoInterface(item, theta["limite_acoes"], theta["alerta_acoes_restantes"])
    ctrl = Controlador(theta, item, condicao, semente)
    cid = config_id(theta, item["versao_roteiro"], agente.nome)
    exec_id = f"{tarefa_id}_{condicao}_s{semente}"
    meta = {"execucao_id": exec_id, "persona_id": theta["persona_id"], "tarefa_id": tarefa_id,
            "conjunto": item["conjunto"], "condicao": condicao, "config_id": cid, "semente": semente,
            "origem": origem, "modelo": agente.nome, "versao_theta": theta["versao"],
            "versao_roteiro": item["versao_roteiro"], "hash_prompt": hash_prompt(),
            "prompt_sistema": PROMPT_SISTEMA, "instrucao_protocolo": INSTRUCAO_PROTOCOLO}
    log = Registrador(meta, pasta)
    log.evento("sessao_iniciada", cena=estado.cena, resposta="d_mostra_cartao",
               amostra=ctrl.amostra.como_dict(), filtro_leitura=ctrl.filtro)
    memoria, invalidas, tempo_total = [], 0, 0.0
    while estado.status == "em_andamento":
        log.passo += 1
        habilitadas = molic.falas_habilitadas(estado)
        falas, restricoes = ctrl.restringir(estado, habilitadas)
        tela = estado.tela()
        exposta, _ = traduzir(tela, habilitadas, item["campos"], None)
        o_t, transf = traduzir(tela, falas, item["campos"], ctrl)
        log.evento("observacao_exposta", cena=estado.cena, texto=exposta, falas_habilitadas=habilitadas)
        for r in restricoes + transf:
            log.evento("restricao_aplicada", cena=estado.cena, **r)
        log.evento("observacao_transformada", cena=estado.cena, texto=o_t, falas_permitidas=falas)
        try:
            out = agente.propor(o_t, falas, item["campos"], memoria)
        except Exception as e:  # API fora do ar, timeout, cota
            invalidas += 1
            log.evento("falha_tecnica", cena=estado.cena, erro=repr(e)[:300], consecutivas=invalidas)
            if invalidas >= theta["limite_propostas_invalidas"]:
                estado.interromper("falha técnica")
                log.evento("interrompida", cena=estado.cena, resposta="d_interrompe", motivo="falha_tecnica")
                break
            continue
        prop = out["proposta"]
        log.evento("acao_proposta", cena=estado.cena, fala=(prop or {}).get("acao"),
                   proposta=prop, bruto=out["bruto"], mensagens=out["mensagens"],
                   modelo_devolvido=out["modelo_devolvido"], latencia_llm_s=out["latencia_llm_s"],
                   uso=out.get("uso"), system_fingerprint=out.get("system_fingerprint"))
        valida = prop is not None and prop.get("acao") in falas
        if valida and prop["acao"] == "enviar" and prop.get("campo") is None:
            valida = False
        if not valida:
            invalidas += 1
            log.evento("acao_rejeitada", cena=estado.cena, proposta=prop, consecutivas=invalidas)
            if invalidas >= theta["limite_propostas_invalidas"]:
                estado.interromper("três propostas inválidas seguidas")
                log.evento("falha_tecnica", cena=estado.cena, erro="tres_propostas_invalidas")
                log.evento("interrompida", cena=estado.cena, resposta="d_interrompe", motivo="falha_tecnica")
            continue
        invalidas = 0
        fala = prop["acao"]
        cena_antes = estado.cena
        campos_antes = dict(estado.campos)
        hes = ctrl.hesitacao(estado)
        t_ops, ops = tempo_operadores(fala, theta["klm"], prop.get("texto"))
        res = estado.executar(fala, prop.get("campo"), prop.get("texto"))
        ctrl.registrar_acao(fala, res)
        tempo_total += hes + t_ops
        log.evento("acao_executada", cena=cena_antes, fala=fala, resposta=res["resposta"],
                   campo=prop.get("campo"), texto=prop.get("texto"), campos_antes=campos_antes,
                   campos_depois=dict(estado.campos), operadores_klm=ops, tempo_operadores_s=t_ops,
                   hesitacao_s=hes, tempo_simulado_acumulado_s=round(tempo_total, 3),
                   acoes=estado.acoes)
        if res.get("tipo_ajuda"):
            log.evento("ajuda_solicitada", cena=cena_antes, fala=fala, resposta=res["resposta"],
                       tipo_ajuda=res["tipo_ajuda"])
        if res.get("erro_capturado"):
            log.evento("erro_capturado", cena=cena_antes, fala=fala, resposta=res["resposta"],
                       motivo=res["erro_capturado"])
        if res.get("alerta"):
            log.evento("alerta_exibido", cena=estado.cena, resposta=res["alerta"],
                       acoes_restantes=estado.acoes_restantes())
        log.evento("estado_interface", cena=estado.cena, status=estado.status,
                   campos=dict(estado.campos), revelados=sorted(estado.revelados))
        resumo = f"passo {log.passo}: {fala}"
        if fala == "enviar":
            resumo += f"(campo={prop.get('campo')}, texto=\"{prop.get('texto')}\")"
        memoria.append(resumo + f" -> {molic.FALAS_D[res['resposta']]}")
        if verbose:
            print("  ", resumo, "->", res["resposta"])
    if estado.status == "encerrada":
        log.evento("encerrada", cena=estado.cena, resposta="d_encerra")
    elif estado.status == "interrompida" and not any(e["tipo"] == "interrompida" for e in log.eventos):
        log.evento("interrompida", cena=estado.cena, resposta="d_interrompe", motivo="limite_acoes")
    final = estado.estado_final()
    final["tempo_simulado_s"] = round(tempo_total, 3)
    return log.salvar(final)


def main():
    ap = argparse.ArgumentParser(description="Executa sessões do UX-Agent.")
    ap.add_argument("--tarefas", nargs="+", default=["C1", "C2"])
    ap.add_argument("--condicoes", nargs="+", default=["perfil", "comparador"])
    ap.add_argument("--n", type=int, default=10, help="execuções por tarefa e condição")
    ap.add_argument("--semente-base", type=int, default=20261026)
    ap.add_argument("--agente", default="openai",
                    choices=["openai", "ollama", "controle_sucesso", "controle_falha"])
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--saida", default=str(RAIZ / "dados" / "piloto"))
    ap.add_argument("--validacao-congelada", action="store_true",
                    help="libera V1/V2; proibido no piloto e na calibração")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    theta = json.loads((RAIZ / "config" / "theta.json").read_text(encoding="utf-8"))
    for t in a.tarefas:
        for c in a.condicoes:
            for i in range(a.n):
                semente = a.semente_base + i
                if a.agente in ("openai", "ollama"):
                    ag = AgenteLLM(a.agente, a.modelo, semente=semente)
                    cond = c
                else:
                    gab = json.loads((RAIZ / "analista" / "gabaritos.json").read_text(encoding="utf-8"))
                    ag = AgenteControle(a.agente, gab["tarefas"][t])
                    cond = "controle"
                arq = executar_sessao(t, cond, semente, ag, theta, a.saida, a.validacao_congelada,
                                      verbose=a.verbose)
                print(f"{t} {cond} semente={semente} -> {arq.name}")
                if cond == "controle":
                    break


if __name__ == "__main__":
    main()
