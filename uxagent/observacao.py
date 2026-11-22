"""Tradutor de observação o_t (paridade de signos).

Cada signo da tela humana (estático, dinâmico e metalinguístico) vira uma
linha de texto. Nada além do que a tela mostra entra aqui: nem HTA, nem
chave, nem rótulo de figura. O único desvio permitido é o do mecanismo R1,
que troca o texto de um bloco pelo superficial e é registrado no log.
"""
from . import molic


def traduzir(tela, falas, campos_tarefa, controlador=None):
    """Retorna (texto_o_t, transformacoes)."""
    transf = []
    linhas = [f"TELA: {tela['titulo']}"]
    if tela["cena"] == molic.AJUDA:
        linhas.append("JANELA DE AJUDA ABERTA:")
        linhas.append(f"  {tela['texto_ajuda']}")
    linhas.append(f"CARTÃO DA TAREFA: {tela['cartao']}")
    campos = " | ".join(f"{c}: " + (f"\"{v}\"" if v else "(vazio)") for c, v in tela["campos"].items())
    linhas.append(f"CAMPOS DE RESPOSTA: {campos}")
    linhas.append("HISTÓRICO DO CHAT:")
    for e in tela["historico"]:
        texto = e["texto"]
        if controlador is not None and e["autor"] == "chat" and e.get("bloco") in ("A", "B"):
            texto, filtrado = controlador.texto_observado(e["bloco"], texto)
            if filtrado:
                transf.append({"mecanismo": "filtro_leitura", "bloco": e["bloco"]})
        autor = {"chat": "Chat", "sistema": "Sistema", "voce": "Você"}[e["autor"]]
        linhas.append(f"  [{autor}] {texto}")
    if tela["continua"]:
        linhas.append("  (A mensagem continua abaixo. Use \"Rolar histórico\" para ver o restante.)")
    if tela["mensagem_sistema"]:
        linhas.append(f"AVISO DO SISTEMA: {tela['mensagem_sistema']}")
    linhas.append(f"AÇÕES RESTANTES: {tela['acoes_restantes']} de 12"
                  + (" (atenção: restam poucas ações)" if tela["alerta_acoes"] else ""))
    linhas.append("AÇÕES DISPONÍVEIS AGORA:")
    for f in falas:
        d = molic.FALAS_U[f]
        extra = f" (escolha o campo entre: {', '.join(campos_tarefa)}; escreva o texto)" if f == "enviar" else ""
        linhas.append(f"  - {f}: botão \"{d['rotulo']}\" — {d['descricao']}{extra}")
    return "\n".join(linhas), transf
