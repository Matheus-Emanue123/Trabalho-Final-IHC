"""Tela humana do chat de estudo e visualizador de sessões (demonstração).

  python -m uxagent.web            -> http://localhost:8765
  /?tarefa=C1                       sessão humana (origem=humana), mesma MoLIC e mesmo log
  /replay?arquivo=C2_perfil_s20261026.json   reprodução passo a passo de uma sessão do agente
"""
import html
import json
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import molic
from .interface import EstadoInterface, carregar_tarefa, RAIZ
from .observacao import traduzir
from .registrador import Registrador
from .tempo import tempo_operadores

THETA = json.loads((RAIZ / "config" / "theta.json").read_text(encoding="utf-8"))
SESSAO = {}

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2433;--muted:#5b6475;--line:#d9dde5;--acc:#2457c5;--warn:#9a5b00}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1c2027;--ink:#e6e9ef;--muted:#a3abba;--line:#323844;--acc:#7aa2ff;--warn:#f0b35a}}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--ink);margin:0;padding:16px}
.wrap{max-width:1100px;margin:auto;display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:800px){.wrap{grid-template-columns:1fr}}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px}
h1{font-size:18px;margin:0 0 10px} h2{font-size:14px;color:var(--muted);margin:12px 0 6px;text-transform:uppercase;letter-spacing:.04em}
.msg{padding:8px 10px;border-radius:6px;margin:6px 0;border:1px solid var(--line)} .sis{color:var(--muted);font-size:14px}
button{font:inherit;padding:7px 12px;margin:3px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
button.pri{background:var(--acc);color:#fff;border-color:var(--acc)} input{font:inherit;padding:6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);width:60%}
.alerta{color:var(--warn);font-weight:600} pre{white-space:pre-wrap;font-size:12.5px;background:var(--bg);padding:10px;border-radius:6px;border:1px solid var(--line)}
.campo{margin:6px 0} label{display:inline-block;width:80px;font-weight:600}
"""


def pagina(titulo, corpo):
    return (f"<!doctype html><html lang='pt-br'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{titulo}</title><style>{CSS}</style>"
            f"</head><body>{corpo}</body></html>").encode("utf-8")


def render_tela(estado):
    t = estado.tela()
    e = html.escape
    h = [f"<h1>{e(t['titulo'])}</h1>", f"<div class='box'><b>Cartão da tarefa:</b> {e(t['cartao'])}</div>"]
    if t["cena"] == molic.AJUDA:
        h.append(f"<div class='box'><b>Ajuda</b><p>{e(t['texto_ajuda'])}</p>"
                 "<form method='post' action='/acao'><button name='fala' value='voltar'>Voltar ao chat</button></form></div>")
    h.append("<h2>Histórico</h2>")
    for m in t["historico"]:
        cls = "msg" if m["autor"] == "chat" else "msg sis"
        h.append(f"<div class='{cls}'><b>{'Chat' if m['autor']=='chat' else 'Sistema'}:</b> {e(m['texto'])}</div>")
    if t["continua"]:
        h.append("<div class='sis'>A mensagem continua abaixo. Use “Rolar histórico”.</div>")
    if t["mensagem_sistema"]:
        h.append(f"<p class='alerta'>{e(t['mensagem_sistema'])}</p>")
    falas = molic.falas_habilitadas(estado)
    if t["cena"] == molic.CONVERSA:
        h.append("<h2>Campos da resposta</h2>")
        for c, v in t["campos"].items():
            h.append(f"<form class='campo' method='post' action='/acao'><label>{e(c)}</label>"
                     f"<input name='texto' value='{e(v)}' aria-label='{e(c)}'><input type='hidden' name='campo' value='{e(c)}'>"
                     "<button class='pri' name='fala' value='enviar'>Enviar</button></form>")
        h.append("<form method='post' action='/acao'>")
        for f in falas:
            if f != "enviar":
                h.append(f"<button name='fala' value='{f}'>{e(molic.FALAS_U[f]['rotulo'])}</button>")
        h.append("</form>")
    elif t["cena"] == molic.CONFIRMACAO:
        h.append("<form method='post' action='/acao'>" + "".join(
            f"<button name='fala' value='{f}'>{e(molic.FALAS_U[f]['rotulo'])}</button>" for f in falas) + "</form>")
    cls = "alerta" if t["alerta_acoes"] else "sis"
    h.append(f"<p class='{cls}'>Ações restantes: {t['acoes_restantes']} de 12</p>")
    if t["status"] != "em_andamento":
        h.append(f"<p><b>Status: {t['status']}</b>. Log salvo. <a href='/'>Nova sessão</a></p>")
    return "\n".join(h)


class Handler(BaseHTTPRequestHandler):
    def _ok(self, corpo, tipo="text/html; charset=utf-8"):
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/replay":
            return self._ok(self.replay(q.get("arquivo", [""])[0]))
        if u.path == "/":
            tarefa = q.get("tarefa", [None])[0]
            if tarefa and tarefa in ("C1", "C2"):
                self.nova(tarefa)
            if "estado" not in SESSAO:
                arqs = sorted((RAIZ / "dados" / "piloto").glob("*.json"))
                links = "".join(f"<li><a href='/replay?arquivo={a.name}'>{a.name}</a></li>" for a in arqs[:400])
                return self._ok(pagina("UX-Agent", "<div class='box'><h1>UX-Agent: chat de estudo</h1>"
                                       "<p>Sessão humana: <a href='/?tarefa=C1'>C1</a> · <a href='/?tarefa=C2'>C2</a> "
                                       "(V1 e V2 bloqueadas)</p><h2>Sessões do agente</h2><ul>" + links + "</ul></div>"))
            est = SESSAO["estado"]
            o_t, _ = traduzir(est.tela(), molic.falas_habilitadas(est), est.item["campos"], None)
            corpo = (f"<div class='wrap'><div class='box'>{render_tela(est)}</div>"
                     f"<div class='box'><h1>O que o agente receberia (o_t)</h1><pre>{html.escape(o_t)}</pre></div></div>")
            return self._ok(pagina("Chat de estudo", corpo))
        self.send_error(404)

    def nova(self, tarefa):
        item = carregar_tarefa(tarefa)
        est = EstadoInterface(item, THETA["limite_acoes"], THETA["alerta_acoes_restantes"])
        sid = f"{tarefa}_humano_{random.randint(1000, 9999)}"
        meta = {"execucao_id": sid, "persona_id": "humano", "tarefa_id": tarefa, "conjunto": item["conjunto"],
                "condicao": "humano", "config_id": "-", "semente": None, "origem": "humana", "modelo": None}
        log = Registrador(meta, RAIZ / "dados" / "humano")
        log.evento("sessao_iniciada", cena=est.cena, resposta="d_mostra_cartao")
        SESSAO.clear()
        SESSAO.update(estado=est, log=log)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        f = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8")).items()}
        est, log = SESSAO.get("estado"), SESSAO.get("log")
        if est and est.status == "em_andamento" and f.get("fala") in molic.falas_habilitadas(est):
            log.passo += 1
            exp, _ = traduzir(est.tela(), molic.falas_habilitadas(est), est.item["campos"], None)
            log.evento("observacao_exposta", cena=est.cena, texto=exp, falas_habilitadas=molic.falas_habilitadas(est))
            antes, cena = dict(est.campos), est.cena
            res = est.executar(f["fala"], f.get("campo"), f.get("texto"))
            t_ops, ops = tempo_operadores(f["fala"], THETA["klm"], f.get("texto"))
            log.evento("acao_executada", cena=cena, fala=f["fala"], resposta=res["resposta"], campo=f.get("campo"),
                       texto=f.get("texto"), campos_antes=antes, campos_depois=dict(est.campos), operadores_klm=ops,
                       tempo_operadores_s=t_ops, hesitacao_s=0, acoes=est.acoes)
            if res.get("tipo_ajuda"):
                log.evento("ajuda_solicitada", cena=cena, fala=f["fala"], tipo_ajuda=res["tipo_ajuda"])
            if res.get("erro_capturado"):
                log.evento("erro_capturado", cena=cena, fala=f["fala"], motivo=res["erro_capturado"])
            log.evento("estado_interface", cena=est.cena, status=est.status, campos=dict(est.campos))
            if est.status != "em_andamento":
                log.evento("encerrada" if est.status == "encerrada" else "interrompida", cena=est.cena)
                fin = est.estado_final()
                fin["tempo_simulado_s"] = None
                log.salvar(fin)
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def replay(self, nome):
        arq = RAIZ / "dados" / "piloto" / Path(nome).name
        if not arq.exists():
            return pagina("Replay", "<p>Arquivo não encontrado.</p>")
        d = json.loads(arq.read_text(encoding="utf-8"))
        e = html.escape
        h = [f"<div class='box'><h1>Sessão {e(d['meta']['execucao_id'])}</h1><p>modelo {e(str(d['meta']['modelo']))} · "
             f"condição {e(d['meta']['condicao'])} · config {e(d['meta']['config_id'])}</p>"]
        ini = next(x for x in d["eventos"] if x["tipo"] == "sessao_iniciada")
        h.append(f"<pre>Amostra do controlador: {e(json.dumps(ini['dados'].get('amostra'), ensure_ascii=False))}</pre>")
        for ev in d["eventos"]:
            tp = ev["tipo"]
            if tp == "observacao_transformada":
                h.append(f"<h2>Passo {ev['passo']}: observação o_t</h2><pre>{e(ev['dados']['texto'])}</pre>")
            elif tp == "restricao_aplicada":
                h.append(f"<p class='alerta'>Mecanismo: {e(json.dumps(ev['dados'], ensure_ascii=False))}</p>")
            elif tp == "acao_proposta":
                h.append(f"<p><b>LLM propôs:</b> <code>{e(ev['dados']['bruto'])}</code> ({ev['dados']['latencia_llm_s']} s)</p>")
            elif tp == "acao_executada":
                h.append(f"<p><b>u:</b> {e(ev['fala'])} → <b>d:</b> {e(ev['resposta'])} · tempo simulado acumulado "
                         f"{ev['dados'].get('tempo_simulado_acumulado_s')} s</p>")
            elif tp in ("acao_rejeitada", "falha_tecnica", "ajuda_solicitada", "erro_capturado", "alerta_exibido"):
                h.append(f"<p class='alerta'>{e(tp)}: {e(json.dumps(ev['dados'], ensure_ascii=False))}</p>")
            elif tp == "avaliacao_externa":
                h.append(f"<h2>Verificador externo</h2><pre>{e(json.dumps(ev['dados'], ensure_ascii=False, indent=1))}</pre>")
        h.append(f"<h2>Estado final</h2><pre>{e(json.dumps(d['estado_final'], ensure_ascii=False, indent=1))}</pre>"
                 "<p><a href='/'>Voltar</a></p></div>")
        return pagina("Replay", "".join(h))


def main(porta=8765):
    print(f"UX-Agent em http://localhost:{porta}")
    ThreadingHTTPServer(("127.0.0.1", porta), Handler).serve_forever()


if __name__ == "__main__":
    main()
