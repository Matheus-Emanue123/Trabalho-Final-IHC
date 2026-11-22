# Dicionário de eventos do UX-Agent

Cada execução gera `dados/piloto/<tarefa>_<condicao>_s<semente>.json` com três chaves:

- `meta`: identificação da execução (ver abaixo), prompt de sistema e instrução do protocolo efetivamente usados.
- `eventos`: lista ordenada de eventos.
- `estado_final`: estado da interface ao fim (`status`, `campos`, `acoes`, `cena`, `tempo_simulado_s`), única entrada do verificador.

## Campos comuns a todo evento

| Campo | Tipo | Descrição |
|---|---|---|
| `execucao_id` | texto | `<tarefa>_<condicao>_s<semente>` |
| `persona_id` | texto | `E` (agente) ou `humano` |
| `tarefa_id` | texto | `C1`, `C2` (V1, V2 bloqueadas no piloto) |
| `conjunto` | texto | `calibracao` ou `validacao` |
| `condicao` | texto | `perfil` (mecanismos ligados), `comparador` (desligados), `controle` (executor de regra) ou `humano` |
| `config_id` | texto | hash de theta, prompt, versão do roteiro e modelo |
| `semente` | inteiro | semente do controlador e da API |
| `passo` | inteiro | passo da sessão (0 = início) |
| `timestamp` | texto | ISO 8601 UTC, relógio de parede; só para ordenar e auditar |
| `tipo` | texto | tipo do evento (tabela abaixo) |
| `cena` | texto | cena MoLIC: `conversa`, `ajuda`, `confirmacao`, `encerrada` |
| `fala` | texto | fala `u:` envolvida (id), quando houver |
| `resposta` | texto | fala `d:` do preposto (id), quando houver |
| `dados` | objeto | conteúdo específico do tipo |
| `origem` | texto | `sintetica`, `humana` ou `verificador` |
| `modelo` | texto | `openai:gpt-4o-mini`, `ollama:<modelo>` ou `regra:<tipo>` |

## Tipos de evento e conteúdo de `dados`

| Tipo | Quando | `dados` |
|---|---|---|
| `sessao_iniciada` | início | `amostra` (h, p_lit, p_explore, p_sup, p_accept, hesitação média, k de desistência), `filtro_leitura` (bloco → disparou?) |
| `observacao_exposta` | todo passo | `texto` da tela integral; `falas_habilitadas` pela MoLIC |
| `restricao_aplicada` | quando um mecanismo age | `mecanismo`, `removidas` ou `bloco`, `p` ou `k` |
| `observacao_transformada` | todo passo | `texto` = o_t efetivamente enviado ao LLM; `falas_permitidas` |
| `acao_proposta` | resposta do LLM | `proposta`, `bruto`, `mensagens` (prompt completo enviado), `modelo_devolvido`, `latencia_llm_s`, `uso` (tokens), `system_fingerprint` |
| `acao_rejeitada` | proposta fora da lista | `proposta`, `consecutivas` |
| `acao_executada` | fala aceita | `campo`, `texto`, `campos_antes`, `campos_depois`, `operadores_klm`, `tempo_operadores_s`, `hesitacao_s`, `tempo_simulado_acumulado_s`, `acoes` |
| `ajuda_solicitada` | `reformular`, `ajuda_como_fazer`, `ajuda_corrigir` | `tipo_ajuda`: `significado`, `procedimento`, `recuperacao` |
| `erro_capturado` | texto vazio ou campo inexistente | `motivo` |
| `alerta_exibido` | restam 3 ações ou menos | `acoes_restantes` |
| `estado_interface` | após cada ação | `status`, `campos`, `revelados` |
| `encerrada` / `interrompida` | fim | `motivo` (interrompida) |
| `falha_tecnica` | erro de API ou 3 propostas inválidas | `erro`, `consecutivas` |
| `avaliacao_externa` | escrito só pelo verificador | `sucesso`, `status`, `campos_ok` |

## Tempo

- `tempo_operadores_s`: operadores KLM da fala (`M P B` para botão; `M P B H K^n H P B` para envio).
- `hesitacao_s`: sorteada pelo controlador (lognormal; +1,35 s na primeira exposição a bloco com figura).
- `latencia_llm_s`: tempo da API; nunca somado ao tempo simulado.
