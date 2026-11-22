"""Política do agente proxy: LLM restrito às falas u: habilitadas.

Fronteira de informação: este módulo NÃO importa nada de `analista/`.
O contexto enviado ao LLM é: prompt de sistema fixo, instrução do protocolo,
observação o_t e o histórico das próprias ações nesta tarefa. A resposta é
forçada por esquema JSON com `enum` das falas permitidas no estado atual.
"""
import json
import os
import time
import urllib.error
import urllib.request

PROMPT_SISTEMA = ("Você opera um chat de estudo. Complete o objetivo do cartão. Escolha uma ação "
                  "da lista recebida. Se a ação for enviar, escreva o campo e o texto. Não invente "
                  "ação fora da lista. Responda apenas com o JSON pedido.")

INSTRUCAO_PROTOCOLO = ("Use o chat para completar uma tarefa acadêmica curta. Leia o cartão. Use "
                       "Enviar, Explicar/reformular, Nova pergunta e Encerrar. O limite é de 12 ações.")


def carregar_env(caminho=".env"):
    """Lê KEY=VALOR de um .env local sem dependências externas."""
    if not os.path.exists(caminho):
        return
    for linha in open(caminho, encoding="utf-8"):
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def esquema(falas, campos):
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["acao", "campo", "texto"],
        "properties": {
            "acao": {"type": "string", "enum": list(falas)},
            "campo": {"anyOf": [{"type": "string", "enum": list(campos)}, {"type": "null"}]},
            "texto": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
    }


def montar_mensagens(o_t, memoria):
    passos = "\n".join(memoria) if memoria else "(nenhuma ação ainda)"
    usuario = (f"{INSTRUCAO_PROTOCOLO}\n\nSUAS AÇÕES ANTERIORES NESTA TAREFA:\n{passos}\n\n"
               f"TELA ATUAL:\n{o_t}\n\nEscolha a próxima ação. Responda em JSON com as chaves "
               "acao, campo e texto (use null em campo e texto quando a ação não for enviar).")
    return [{"role": "system", "content": PROMPT_SISTEMA}, {"role": "user", "content": usuario}]


class AgenteLLM:
    def __init__(self, provedor="openai", modelo=None, semente=20261026, temperatura=0.0):
        self.provedor = provedor
        self.semente = semente
        self.temperatura = temperatura
        if provedor == "openai":
            carregar_env()
            self.modelo = modelo or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            self.chave = os.environ.get("OPENAI_API_KEY")
            if not self.chave:
                raise RuntimeError("OPENAI_API_KEY ausente. Crie o arquivo .env a partir de .env.example.")
        elif provedor == "ollama":
            self.modelo = modelo or os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
            self.url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        else:
            raise ValueError(provedor)
        self.nome = f"{provedor}:{self.modelo}"

    def propor(self, o_t, falas, campos, memoria):
        """Retorna dict com proposta, mensagens enviadas, resposta bruta, modelo e latência."""
        msgs = montar_mensagens(o_t, memoria)
        sch = esquema(falas, campos)
        t0 = time.time()
        if self.provedor == "openai":
            corpo = {"model": self.modelo, "messages": msgs, "temperature": self.temperatura,
                     "seed": self.semente,
                     "response_format": {"type": "json_schema",
                                         "json_schema": {"name": "acao", "strict": True, "schema": sch}}}
            req = urllib.request.Request("https://api.openai.com/v1/chat/completions",
                                         data=json.dumps(corpo).encode(), method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": f"Bearer {self.chave}"})
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read())
            bruto = resp["choices"][0]["message"]["content"]
            modelo_devolvido = resp.get("model")
            extra = {"system_fingerprint": resp.get("system_fingerprint"), "uso": resp.get("usage")}
        else:
            corpo = {"model": self.modelo, "messages": msgs, "stream": False, "format": sch,
                     "options": {"temperature": self.temperatura, "seed": self.semente}}
            req = urllib.request.Request(f"{self.url}/api/chat", data=json.dumps(corpo).encode(),
                                         method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                resp = json.loads(r.read())
            bruto = resp["message"]["content"]
            modelo_devolvido = resp.get("model")
            extra = {}
        latencia = round(time.time() - t0, 3)
        try:
            proposta = json.loads(bruto)
        except json.JSONDecodeError:
            proposta = None
        return {"proposta": proposta, "mensagens": msgs, "bruto": bruto,
                "modelo_devolvido": modelo_devolvido, "latencia_llm_s": latencia, **extra}


class AgenteControle:
    """Executores de regra usados só para conferir o verificador (não são dados do piloto).

    'controle_sucesso' copia a resposta canônica do analista; 'controle_falha' copia o
    texto superficial. Ficam marcados condicao=controle no log.
    """

    def __init__(self, tipo, gabarito_tarefa):
        self.tipo = tipo
        self.gab = gabarito_tarefa
        self.nome = f"regra:{tipo}"
        self.fila = None

    def propor(self, o_t, falas, campos, memoria):
        if self.fila is None:
            self.fila = []
            if "rolar_historico" in falas:
                self.fila.append({"acao": "rolar_historico", "campo": None, "texto": None})
            for c in campos:
                txt = self.gab["resposta_canonica"][c] if self.tipo == "controle_sucesso" else "segunda"
                self.fila.append({"acao": "enviar", "campo": c, "texto": txt})
            self.fila.append({"acao": "encerrar", "campo": None, "texto": None})
        prop = self.fila.pop(0) if self.fila else {"acao": falas[0], "campo": None, "texto": None}
        if prop["acao"] not in falas:
            prop = {"acao": "confirmar_encerrar" if "confirmar_encerrar" in falas else falas[0],
                    "campo": None, "texto": None}
        return {"proposta": prop, "mensagens": None, "bruto": json.dumps(prop),
                "modelo_devolvido": self.nome, "latencia_llm_s": 0.0}
