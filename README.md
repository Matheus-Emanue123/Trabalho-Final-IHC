# UX-Agent — chat de estudo instrumentado (IHC, CEFET-MG Divinópolis)

Agente proxy baseado em LLM que opera um chat de estudo no lugar da persona E. (estudante universitária adulta autista, CID-11 6A02.0, fictícia) e gera registros sintéticos de uso, auditáveis e comparáveis à linha de base KLM. Projeto da disciplina de Interação Humano-Computador.

Autores: Matheus Emanuel da Silva, João Francisco Teles da Silva, Eduardo Almeida.

## O que garante a auditabilidade

| Regra do enunciado | Onde está no código |
|---|---|
| O agente só vê o que a persona veria (paridade de signos) | `uxagent/observacao.py` traduz `EstadoInterface.tela()`, a mesma função usada pela tela humana (`uxagent/web.py`) |
| HTA, CTT, KLM e gabarito ficam com o analista | `analista/` (nunca importado por `uxagent/agente.py`) |
| Navegação dirigida pela MoLIC | `uxagent/molic.py`: `falas_habilitadas(estado)` vira o `enum` do esquema JSON da resposta |
| Comportamento da persona fora do prompt | `uxagent/mecanismos.py` + `config/theta.json`: sorteios com semente que filtram a observação e a lista de falas |
| Ajuda só sob demanda registrada | falas `reformular`, `ajuda_como_fazer`, `ajuda_corrigir` → evento `ajuda_solicitada` |
| Rupturas detectadas só por assinatura no log | `analista/analisar.py` |
| Sucesso verificado fora do agente | `analista/verificador.py` lê só `estado_final` |
| Validação intocada | `roteiros/validacao.json` só abre com `--validacao-congelada`; o piloto usa C1 e C2 |

## Instalação

Requer apenas Python 3.10+ (biblioteca padrão; sem `pip install`).

```bash
git clone <url-do-repositorio> && cd uxagent
cp .env.example .env      # coloque OPENAI_API_KEY no .env
```

Sem chave, use o Ollama local (`ollama pull qwen2.5:3b`) e a opção `--agente ollama`.

## Execução

```bash
# Piloto de calibração: C1 e C2, persona (mecanismos ligados) e comparador neutro (mecanismos desligados)
python -m uxagent.executar --tarefas C1 C2 --condicoes perfil comparador --n 10 --agente openai

# Verificação externa de sucesso (acrescenta avaliacao_externa a cada log)
python -m analista.verificador dados/piloto

# Métricas S, R_e, A, uso de ajuda, MAC e comparação com KLM
python -m analista.analisar dados/piloto

# Linha de base KLM de especialista
python -m analista.klm

# Tela humana e reprodução passo a passo das sessões (demonstração)
python -m uxagent.web      # http://localhost:8765
```

Controles sem LLM, usados para conferir o verificador (não são dados do piloto):

```bash
python -m uxagent.executar --tarefas C1 C2 --n 1 --agente controle_sucesso --saida dados/controles
python -m uxagent.executar --tarefas C1 C2 --n 1 --agente controle_falha   --saida dados/controles
```

## Parâmetros e sementes

- `config/theta.json`: distribuições dos mecanismos (R1 filtro de leitura, R2 injetor de exploração, R3 limiar de suporte, R4 aceite prematuro, R5 capacidade de linguagem), hesitação, limite de tentativas, limite de 12 ações e operadores KLM.
- Semente da execução *i*: `--semente-base + i` (padrão 20261026). A mesma semente alimenta o controlador e o campo `seed` da API.
- Agente neutro de comparação: `--condicoes comparador` (mesmo agente, mecanismos de perfil com probabilidade zero).
- Modelo: `gpt-4o-mini`, temperatura 0; o identificador devolvido pela API é gravado em cada `acao_proposta`.

## Estrutura

```
config/theta.json          parâmetros (versão theta-0.2)
roteiros/                  falas exibidas na tela (calibração e validação congelada)
uxagent/                   aplicação, MoLIC, tradutor o_t, mecanismos, agente, registrador, web
analista/                  gabaritos, verificador, KLM, análise de rupturas e métricas
dados/piloto/              logs JSON do piloto (um arquivo por execução)
dados/resultados/          métricas agregadas
docs/                      caderno de design (E1), artigo (E4), dicionário de eventos
```

O dicionário de campos dos eventos está em `docs/dicionario_eventos.md`.
