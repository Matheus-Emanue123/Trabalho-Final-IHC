# E3 — Pacote de dados do piloto

- `piloto/`: 120 logs JSON, um por execução: C1 e C2 × condições `perfil` e `comparador` × 30 sementes (20261026 a 20261055). Modelo: `gpt-4o-mini-2024-07-18`, temperatura 0. Execução em 22/11/2026.
- `controles/`: execuções dos executores de regra (`controle_sucesso`, `controle_falha`) usados só para conferir o verificador.
- `resultados/metricas.json`: métricas por tarefa e condição (S, R_e, A, uso de ajuda, tempo simulado × KLM, MAC, PP/PA/AL/RA/CE, mecanismos disparados, tokens) e por sessão.
- `dicionario_eventos.md`: dicionário dos campos dos eventos.

## Onde estão os prompts e contextos enviados ao LLM

- `meta.prompt_sistema` e `meta.instrucao_protocolo`: texto fixo de cada execução (hash em `meta.hash_prompt`).
- Cada evento `acao_proposta` traz em `dados.mensagens` a lista completa de mensagens enviada à API naquele passo (sistema + usuário com a observação o_t e o histórico das próprias ações), além de `dados.bruto` (resposta), `dados.modelo_devolvido`, `dados.uso` (tokens) e `dados.latencia_llm_s`.
- O texto da observação enviada também está em `observacao_transformada.dados.texto`; a tela integral, em `observacao_exposta.dados.texto`.

## Respostas, tempos, ajuda e resultado

- Ações: eventos `acao_executada` (campo, texto, campos antes/depois, operadores KLM, hesitação, tempo simulado acumulado).
- Ajuda: eventos `ajuda_solicitada` com `tipo_ajuda`.
- Resultado: evento `avaliacao_externa`, escrito pelo verificador (`origem = verificador`), e `estado_final`.

Reproduzir: `python -m uxagent.executar --tarefas C1 C2 --condicoes perfil comparador --n 30 --agente openai`, depois `python -m analista.verificador dados/piloto` e `python -m analista.analisar dados/piloto`.
