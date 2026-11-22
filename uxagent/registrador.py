"""Registrador de eventos em JSON (um arquivo por execução)."""
import json
from datetime import datetime, timezone
from pathlib import Path

TIPOS = {
    "sessao_iniciada", "observacao_exposta", "observacao_transformada", "restricao_aplicada",
    "acao_proposta", "acao_rejeitada", "acao_executada", "ajuda_solicitada", "erro_capturado",
    "alerta_exibido", "estado_interface", "encerrada", "interrompida", "falha_tecnica",
    "avaliacao_externa",
}


class Registrador:
    def __init__(self, meta, pasta):
        self.meta = meta
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.eventos = []
        self.passo = 0

    def evento(self, tipo, cena=None, fala=None, resposta=None, **dados):
        assert tipo in TIPOS, tipo
        self.eventos.append({
            "execucao_id": self.meta["execucao_id"],
            "persona_id": self.meta["persona_id"],
            "tarefa_id": self.meta["tarefa_id"],
            "conjunto": self.meta["conjunto"],
            "condicao": self.meta["condicao"],
            "config_id": self.meta["config_id"],
            "semente": self.meta["semente"],
            "passo": self.passo,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "tipo": tipo,
            "cena": cena,
            "fala": fala,
            "resposta": resposta,
            "dados": dados,
            "origem": self.meta["origem"],
            "modelo": self.meta["modelo"],
        })

    def salvar(self, estado_final):
        arq = self.pasta / f"{self.meta['execucao_id']}.json"
        arq.write_text(json.dumps({"meta": self.meta, "eventos": self.eventos,
                                   "estado_final": estado_final}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        return arq
