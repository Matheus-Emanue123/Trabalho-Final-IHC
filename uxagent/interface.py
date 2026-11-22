"""Aplicação interativa: chat de estudo roteirizado (roteiro-0.2).

O estado integral (`EstadoInterface`) é a única fonte da tela humana e da
observação do agente. O verificador externo lê só `estado_final()`.
"""
import copy
import json
from pathlib import Path

from . import molic

RAIZ = Path(__file__).resolve().parent.parent


def carregar_tarefa(tarefa_id, permitir_validacao=False):
    """Carrega o roteiro de uma tarefa. Validação exige permissão explícita."""
    if tarefa_id.startswith("V"):
        if not permitir_validacao:
            raise PermissionError(
                f"{tarefa_id} é tarefa de validação congelada; o piloto usa só C1 e C2. "
                "Use --validacao-congelada somente depois de congelar theta e prompt.")
        arquivo = RAIZ / "roteiros" / "validacao.json"
    else:
        arquivo = RAIZ / "roteiros" / "calibracao.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    item = copy.deepcopy(dados["tarefas"][tarefa_id])
    item["id"] = tarefa_id
    item["versao_roteiro"] = dados["versao"]
    return item


class EstadoInterface:
    def __init__(self, item, limite_acoes=12, alerta_restantes=3):
        self.item = item
        self.limite_acoes = limite_acoes
        self.alerta_restantes = alerta_restantes
        self.cena = molic.CONVERSA
        self.status = "em_andamento"          # em_andamento | encerrada | interrompida
        self.campos = {c: "" for c in item["campos"]}
        self.revelados = {b["id"] for b in item["blocos"] if not b["oculto"]}
        self.historico = []                    # entradas exibidas no histórico
        self.acoes = 0
        self.texto_ajuda = None
        self.ultima_resposta = "d_mostra_cartao"
        self.ultima_mensagem_sistema = None
        for b in item["blocos"]:
            if not b["oculto"]:
                self.historico.append({"autor": "chat", "bloco": b["id"], "texto": b["texto"]})

    # ---------- consultas ----------
    def tem_bloco_oculto(self):
        return any(b["id"] not in self.revelados for b in self.item["blocos"])

    def campos_vazios(self):
        return [c for c, v in self.campos.items() if not v.strip()]

    def acoes_restantes(self):
        return self.limite_acoes - self.acoes

    def bloco(self, bid):
        return next(b for b in self.item["blocos"] if b["id"] == bid)

    def tela(self):
        """Signos da tela, na ordem em que aparecem. Fonte única para humano e agente."""
        return {
            "titulo": "Chat de estudo",
            "cena": self.cena,
            "cartao": self.item["cartao"],
            "historico": list(self.historico),
            "continua": self.tem_bloco_oculto(),
            "campos": dict(self.campos),
            "acoes_restantes": self.acoes_restantes(),
            "alerta_acoes": self.acoes_restantes() <= self.alerta_restantes,
            "texto_ajuda": self.texto_ajuda,
            "mensagem_sistema": self.ultima_mensagem_sistema,
            "status": self.status,
        }

    def estado_final(self):
        return {"tarefa_id": self.item["id"], "status": self.status, "campos": dict(self.campos),
                "acoes": self.acoes, "cena": self.cena}

    # ---------- transições (u: -> d:) ----------
    def executar(self, fala, campo=None, texto=None):
        """Executa uma fala u: habilitada. Retorna dict com a fala d: e efeitos."""
        if fala not in molic.falas_habilitadas(self):
            raise ValueError(f"fala {fala} não habilitada na cena {self.cena}")
        antes = copy.deepcopy(self.campos)
        self.acoes += 1
        self.ultima_mensagem_sistema = None
        resp, extra = self._transicao(fala, campo, texto)
        self.ultima_resposta = resp
        mudou = self.campos != antes
        if self.status == "em_andamento" and self.acoes >= self.limite_acoes:
            self.status = "interrompida"
            self.cena = molic.ENCERRADA
            resp = "d_interrompe"
            self.ultima_mensagem_sistema = "Limite de 12 ações atingido. A tarefa foi encerrada."
        elif self.status == "em_andamento" and self.acoes_restantes() <= self.alerta_restantes:
            extra["alerta"] = "d_alerta_acoes"
        return {"resposta": resp, "campos_mudaram": mudou, **extra}

    def _transicao(self, fala, campo, texto):
        it = self.item
        if fala == "enviar":
            texto = (texto or "").strip()
            if campo not in self.campos:
                self.ultima_mensagem_sistema = f"O campo '{campo}' não existe nesta tarefa. Campos: {', '.join(self.campos)}."
                return "d_campo_inexistente", {"erro_capturado": "campo_inexistente"}
            if not texto:
                self.ultima_mensagem_sistema = "Texto vazio: nada foi enviado."
                return "d_texto_vazio_recusado", {"erro_capturado": "texto_vazio"}
            anterior = self.campos[campo]
            self.campos[campo] = texto
            if anterior:
                self.historico.append({"autor": "sistema", "bloco": None,
                                       "texto": f"Campo {campo} atualizado para \"{texto}\" (antes: \"{anterior}\")."})
                return "d_campo_substituido", {"valor_anterior": anterior}
            self.historico.append({"autor": "sistema", "bloco": None,
                                   "texto": f"Campo {campo} preenchido: \"{texto}\"."})
            return "d_campo_preenchido", {}
        if fala == "rolar_historico":
            for b in it["blocos"]:
                if b["id"] not in self.revelados:
                    self.revelados.add(b["id"])
                    self.historico.append({"autor": "chat", "bloco": b["id"], "texto": b["texto"]})
                    break
            return "d_revela_bloco", {}
        if fala == "reformular":
            self.historico.append({"autor": "chat", "bloco": "reformulacao", "texto": it["reformulacao"]})
            return "d_reformulacao", {"tipo_ajuda": "significado"}
        if fala == "nova_pergunta":
            self.historico.append({"autor": "chat", "bloco": None, "texto": it["nova_pergunta"]})
            return "d_fala_neutra", {}
        if fala in ("ajuda_como_fazer", "ajuda_corrigir"):
            self.cena = molic.AJUDA
            self.texto_ajuda = molic.TEXTO_AJUDA[fala]
            return "d_abre_ajuda", {"tipo_ajuda": molic.TIPO_AJUDA[fala]}
        if fala == "voltar":
            self.cena = molic.CONVERSA
            self.texto_ajuda = None
            return "d_fecha_ajuda", {}
        if fala == "encerrar":
            vazios = self.campos_vazios()
            if vazios:
                self.cena = molic.CONFIRMACAO
                self.ultima_mensagem_sistema = (f"O campo {', '.join(vazios)} está vazio. "
                                                "Encerrar mesmo assim?")
                return "d_pede_confirmacao", {"campos_vazios": vazios}
            return self._encerrar()
        if fala == "confirmar_encerrar":
            return self._encerrar()
        if fala == "cancelar_encerrar":
            self.cena = molic.CONVERSA
            return "d_fecha_ajuda", {}
        raise ValueError(fala)

    def _encerrar(self):
        self.cena = molic.ENCERRADA
        self.status = "encerrada"
        self.ultima_mensagem_sistema = "Tarefa encerrada."
        return "d_encerra", {}

    def interromper(self, motivo):
        self.status = "interrompida"
        self.cena = molic.ENCERRADA
        self.ultima_mensagem_sistema = f"Sessão interrompida: {motivo}."
