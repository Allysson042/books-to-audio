# docs/ — Notas de design e investigações

**Escopo:** histórico datado de decisões, planos e experimentos já executados.
**NÃO mora aqui:** backlog, design atual nem convenções do projeto.
- Fonte de verdade do design: `../ARCHITECTURE.md`
- Fonte de verdade do progresso: `../TASKS.md`
- Status/índice desta pasta: `STATE.md`
- Pasta versionada no git: as notas são histórico durável (não descartável).

## Stack (só contexto; detalhes no `../README.md`)
Python + Streamlit; RAG dual: Chroma + BM25 (vetorial) e árvore L2→L3→L4 (vectorless);
sentence-transformers CPU; LLM via `src/llm_provider.py` (Gemini/OpenRouter/…);
TTS Edge-TTS + Piper + OpenRouter premium (`src/tts_provider.py`). Custo default R$0.

## Comandos úteis
```bash
streamlit run app.py                                       # UI
python ingest.py --pdf data/generative-deep-learning.pdf   # ingestão one-shot
python -m src.tree_index                                   # rebuild da árvore (grátis)
python scripts/eval_retrieval.py [--lang en|pt|all] [--no-rerank]
python scripts/fix_summaries.py
python docs/count_tokens.py                          # requer tiktoken (fora do requirements)
```
Não há suíte pytest; validação é manual/AppTest (ver `../TASKS.md`).

## Índice (Memória Fria)
| Arquivo | Tema | Status |
|---|---|---|
| `golden-questions.md` | Régua dourada Q1–Q5 (PT+EN) | implementado |
| `ui-refactor.md` | Pass1/Pass2 independentes, chunks, toggles | implementado |
| `vectorless-pageindex.md` | Estratégia vectorless + toggle | implementado |
| `tts-openrouter-plan.md` | TTS premium (MAI-Voice) + fatiamento | implementado |
| `tree-hierarchy-plan.md` | Árvore L2→L3→L4 com ranges por irmão | implementado |
| `count_tokens.py` | Script avulso de contagem de tokens | parcial/frágil |

## Regras para agentes
- Notas são **histórico imutável**: decisão nova = nota nova + atualizar `STATE.md` e `../ARCHITECTURE.md`.
- Seções "Fora de escopo"/"Futuro" de cada nota são as ideias ainda não feitas.
- Não crie `AGENTS.md`/`STATE.md` fora desta pasta por causa destas notas.
- Não edite `../ARCHITECTURE.md`/`../TASKS.md` a partir daqui sem pedido explícito.
