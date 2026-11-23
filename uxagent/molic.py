"""Diagrama MoLIC como máquina de estados (Barbosa e de Paula, 2003).

Cada cena tem falas do usuário (u:) que definem o espaço de ações do agente
naquele estado. As falas do preposto (d:) são as respostas do sistema que mudam
a imagem observável. O caderno E1 desenha este mesmo diagrama; os ids abaixo
são os que aparecem no log (campo `fala`).
"""

# Cenas
CONVERSA = "conversa"          # cena principal: cartão, histórico, campos
AJUDA = "ajuda"                # suspensão para ajuda (CTT |>)
CONFIRMACAO = "confirmacao"    # prevenção ativa antes de encerrar com campo vazio
ENCERRADA = "encerrada"        # ponto de saída

# Falas do usuário (u:). rotulo = texto do botão na tela humana.
FALAS_U = {
    "enviar": {"cena": CONVERSA, "rotulo": "Enviar", "args": ["campo", "texto"],
               "descricao": "enviar um texto para um dos campos de resposta"},
    "rolar_historico": {"cena": CONVERSA, "rotulo": "Rolar histórico",
                        "descricao": "rolar o histórico para ver o restante da mensagem"},
    "reformular": {"cena": CONVERSA, "rotulo": "Explicar/reformular",
                   "descricao": "pedir que a última mensagem seja explicada em lista"},
    "nova_pergunta": {"cena": CONVERSA, "rotulo": "Perguntar de novo",
                      "descricao": "perguntar de novo ao chat"},
    "ajuda_como_fazer": {"cena": CONVERSA, "rotulo": "Ajuda: como faço?",
                         "descricao": "abrir a ajuda sobre como usar esta tela"},
    "ajuda_corrigir": {"cena": CONVERSA, "rotulo": "Ajuda: como corrijo?",
                       "descricao": "abrir a ajuda sobre como corrigir um campo"},
    "encerrar": {"cena": CONVERSA, "rotulo": "Encerrar",
                 "descricao": "encerrar a tarefa"},
    "voltar": {"cena": AJUDA, "rotulo": "Voltar ao chat",
               "descricao": "fechar a ajuda e voltar ao chat"},
    "confirmar_encerrar": {"cena": CONFIRMACAO, "rotulo": "Encerrar mesmo assim",
                           "descricao": "confirmar o encerramento com campo vazio"},
    "cancelar_encerrar": {"cena": CONFIRMACAO, "rotulo": "Voltar e completar",
                          "descricao": "cancelar o encerramento e voltar ao chat"},
}

# Ajuda sob demanda estratificada por tipo de dúvida (Shneiderman e Plaisant).
# significado -> reformular; procedimento -> ajuda_como_fazer; recuperacao -> ajuda_corrigir.
TIPO_AJUDA = {"reformular": "significado", "ajuda_como_fazer": "procedimento",
              "ajuda_corrigir": "recuperacao"}

TEXTO_AJUDA = {
    "ajuda_como_fazer": ("Leia o cartão da tarefa. As respostas vão nos campos indicados no cartão: "
                         "use Enviar com o nome do campo e o texto. Se a mensagem do chat estiver "
                         "cortada, use Rolar histórico. Explicar/reformular mostra a última mensagem "
                         "em lista. Quando os campos estiverem como você quer, use Encerrar."),
    "ajuda_corrigir": ("Para corrigir um campo, envie um novo texto para o mesmo campo. O valor "
                       "anterior é substituído e a troca aparece no histórico."),
}

# Falas do preposto (d:) — ids usados no log, campo `resposta`.
FALAS_D = {
    "d_mostra_cartao": "exibe cartão, campos vazios e primeira mensagem",
    "d_revela_bloco": "exibe o restante da mensagem (bloco B)",
    "d_reformulacao": "exibe a mensagem em lista literal",
    "d_fala_neutra": "responde que não há outra informação",
    "d_campo_preenchido": "mostra o campo com o texto enviado",
    "d_campo_substituido": "mostra o novo valor e o valor anterior (recuperação apoiada)",
    "d_texto_vazio_recusado": "recusa texto vazio sem alterar o campo (captura de erro)",
    "d_campo_inexistente": "informa que o campo não existe nesta tarefa (captura de erro)",
    "d_abre_ajuda": "abre a ajuda do tipo pedido",
    "d_fecha_ajuda": "volta ao chat no mesmo estado (retomada da suspensão)",
    "d_pede_confirmacao": "avisa que há campo vazio e pede confirmação (prevenção ativa)",
    "d_alerta_acoes": "alerta que restam poucas ações (prevenção apoiada)",
    "d_encerra": "encerra a tarefa e bloqueia novas ações",
    "d_interrompe": "encerra por limite de ações ou falha técnica",
}


def falas_habilitadas(estado):
    """Lista de u: habilitadas no estado atual (antes dos mecanismos)."""
    if estado.cena == ENCERRADA:
        return []
    if estado.cena == AJUDA:
        return ["voltar"]
    if estado.cena == CONFIRMACAO:
        return ["confirmar_encerrar", "cancelar_encerrar"]
    falas = ["enviar"]
    if estado.tem_bloco_oculto():
        falas.append("rolar_historico")   # prevenção passiva: só aparece se há o que rolar
    falas += ["reformular", "nova_pergunta", "ajuda_como_fazer", "ajuda_corrigir", "encerrar"]
    return falas
