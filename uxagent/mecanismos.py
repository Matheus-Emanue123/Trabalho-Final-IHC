"""Amostrador de parâmetros e controlador de mecanismos (fora do prompt).

O comportamento da persona não é pedido ao LLM: ele resulta de sorteios com
semente registrada que (a) trocam o texto integral pelo superficial na
observação (R1/R5), (b) retiram falas u: da lista por um passo (R2, R3, R4,
limite de tentativas) e (c) somam tempo de hesitação simulado. O LLM só vê a
observação já transformada e a lista já filtrada.
"""
import math
import random

PERFIL = "perfil"
COMPARADOR = "comparador"


class Amostra:
    """Valores sorteados no início de uma execução (gravados no log)."""

    def __init__(self, theta, condicao, rng):
        mp = theta["mecanismos_perfil"]
        mc = theta["mecanismos_comuns"]
        u = lambda par: rng.uniform(par[0], par[1])
        self.condicao = condicao
        self.h = "alta" if rng.random() < mp["capacidade_linguagem"]["P_alta"] else "media"
        tabela = mp["filtro_leitura"]["p_lit"][self.h]
        self.p_lit = {tipo: u(faixa) for tipo, faixa in tabela.items()}
        self.p_explore = u(mp["injetor_exploracao"]["p_explore"])
        self.p_sup = u(mp["limiar_suporte"]["p_sup"])
        self.p_accept = u(mp["aceite_prematuro"]["p_accept"])
        if condicao != PERFIL:   # comparador sintético: mecanismos de perfil desligados
            self.p_lit = {k: 0.0 for k in self.p_lit}
            self.p_explore = self.p_sup = self.p_accept = 0.0
        self.hesitacao_media = u(mc["hesitacao"]["media_s"])
        self.hesitacao_sigma = mc["hesitacao"]["sigma_log"]
        self.M_extra_figura = mc["hesitacao"]["M_extra_figura"]
        lo, hi = mc["limite_tentativas"]["acoes_sem_progresso"]
        self.k_desistencia = rng.randint(lo, hi)

    def como_dict(self):
        return {"condicao": self.condicao, "h": self.h,
                "p_lit": {k: round(v, 4) for k, v in self.p_lit.items()},
                "p_explore": round(self.p_explore, 4), "p_sup": round(self.p_sup, 4),
                "p_accept": round(self.p_accept, 4),
                "hesitacao_media_s": round(self.hesitacao_media, 3),
                "k_desistencia": self.k_desistencia}


class Controlador:
    def __init__(self, theta, item, condicao, semente):
        self.rng = random.Random(semente)
        self.semente = semente
        self.item = item
        self.amostra = Amostra(theta, condicao, self.rng)
        # R1 (+R5): decide por figura, uma vez, se a leitura será superficial
        self.filtro = {}
        for b in item["blocos"]:
            if b.get("figura"):
                p = self.amostra.p_lit[b["figura"]]
                self.filtro[b["id"]] = self.rng.random() < p
        self.suporte_usado = False
        self.r2_avaliado = False
        self.r3_avaliado = False
        self.r4_avaliado = False
        self.sem_progresso = 0
        self.ja_enviou = False
        self.figuras_vistas = set()

    # ---------- R1: transformação da observação ----------
    def texto_observado(self, bloco_id, texto_integral):
        b = next((x for x in self.item["blocos"] if x["id"] == bloco_id), None)
        if b is not None and self.filtro.get(bloco_id) and b.get("superficial"):
            return b["superficial"], True
        return texto_integral, False

    # ---------- R2, R3, R4, limite de tentativas: filtro de affordance ----------
    def restringir(self, estado, falas):
        """Recebe as u: habilitadas pela MoLIC e devolve (falas_filtradas, restricoes)."""
        restricoes = []
        remover = set()
        if estado.cena == "conversa":
            figura_visivel = any(self.item_bloco(bid).get("figura") for bid in estado.revelados
                                 if self.item_bloco(bid) is not None)
            # R3 limiar de suporte: diante de figura, botão vira a ação mais provável
            if figura_visivel and not self.suporte_usado and not self.r3_avaliado:
                self.r3_avaliado = True
                if self.rng.random() < self.amostra.p_sup:
                    remover |= {"enviar", "encerrar"}
                    restricoes.append({"mecanismo": "limiar_suporte", "removidas": ["enviar", "encerrar"],
                                       "p": round(self.amostra.p_sup, 4)})
            # R2 injetor de exploração: uma vez por tarefa com distratores, antes do 1º envio
            if self.item.get("distratores", 0) > 0 and not self.ja_enviou and not self.r2_avaliado:
                self.r2_avaliado = True
                if self.rng.random() < self.amostra.p_explore:
                    remover |= {"enviar", "encerrar"}
                    restricoes.append({"mecanismo": "injetor_exploracao", "removidas": ["enviar", "encerrar"],
                                       "p": round(self.amostra.p_explore, 4)})
            # R4 aceite prematuro: resposta incompleta (campo vazio) e suporte não usado
            preenchidos = len(estado.campos) - len(estado.campos_vazios())
            if (0 < preenchidos < len(estado.campos)) and not self.suporte_usado and not self.r4_avaliado:
                self.r4_avaliado = True
                if self.rng.random() < self.amostra.p_accept:
                    rem = {"reformular", "nova_pergunta", "ajuda_como_fazer", "ajuda_corrigir"}
                    remover |= rem
                    restricoes.append({"mecanismo": "aceite_prematuro", "removidas": sorted(rem),
                                       "p": round(self.amostra.p_accept, 4)})
        # Limite de tentativas (comum às duas condições): desistência
        if self.sem_progresso >= self.amostra.k_desistencia and estado.cena != "encerrada":
            manter = {"conversa": "encerrar", "ajuda": "voltar", "confirmacao": "confirmar_encerrar"}[estado.cena]
            rem = set(falas) - {manter}
            remover |= rem
            restricoes.append({"mecanismo": "limite_tentativas", "removidas": sorted(rem),
                               "k": self.amostra.k_desistencia})
        filtradas = [f for f in falas if f not in remover] or falas[:1]
        return filtradas, restricoes

    def item_bloco(self, bid):
        return next((x for x in self.item["blocos"] if x["id"] == bid), None)

    # ---------- atualização após cada ação ----------
    def registrar_acao(self, fala, resultado):
        if fala in ("reformular", "ajuda_como_fazer", "ajuda_corrigir"):
            self.suporte_usado = True
        if fala == "enviar":
            self.ja_enviou = True
        self.sem_progresso = 0 if resultado.get("campos_mudaram") else self.sem_progresso + 1

    # ---------- tempo de hesitação simulado ----------
    def hesitacao(self, estado):
        m, s = self.amostra.hesitacao_media, self.amostra.hesitacao_sigma
        t = self.rng.lognormvariate(math.log(m) - s * s / 2, s)
        novas = {bid for bid in estado.revelados
                 if self.item_bloco(bid) is not None and self.item_bloco(bid).get("figura")} - self.figuras_vistas
        if novas:
            t += self.amostra.M_extra_figura
            self.figuras_vistas |= novas
        return round(t, 3)
