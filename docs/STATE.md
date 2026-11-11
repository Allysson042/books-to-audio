# STATE.md — Índice e status de `docs/`

> Memória quente desta pasta. Backlog do projeto: `../TASKS.md`; design travado: `../ARCHITECTURE.md`.
> Este arquivo NÃO duplica o backlog — só indexa as notas e aponta o que ainda está vivo nelas.

## Contexto Atual (2026-11-11)
As 5 notas `.md` têm contrapartida implementada no código e funcionam como *design rationale*.
O que resta de vivo são as seções "Fora de escopo"/"Futuro" e alguns resíduos textuais abaixo.

## Status por nota
| Nota | Data | Status | Evidência verificada | Absorvida em |
|---|---|---|---|---|
| `golden-questions.md` | 2026-09-23 | implementado | `scripts/golden.json` (Q1–Q5) + `scripts/eval_retrieval.py` (`hit_in`, `main`, `--no-rerank`) | `../ARCHITECTURE.md` Ramo 5/6; `../TASKS.md` Extras |
| `ui-refactor.md` | 2026-09-23 | implementado | `app.py` toggles cache/re-rank/estratégia/premium; `src/generate.py` `get_pass1`/`get_pass2(use_cache)` | `../TASKS.md` §UI funcional |
| `vectorless-pageindex.md` | 2026-09-23 | implementado | `src/retrieval_tree.py` `TreeStore.search`; `src/tree_index.py` `TREE_VERSION="2"`; default vectorless no `app.py` | `../ARCHITECTURE.md` Ramo 2 + diagrama |
| `tts-openrouter-plan.md` | 2026-10-06 | implementado | `src/tts_provider.py` `synthesize_premium`, `split_slices`, `TTS_MAX_CHARS=15000`; `OPENROUTER_TTS_MODEL` no `.env.example` | `../ARCHITECTURE.md` Ramo 4 |
| `tree-hierarchy-plan.md` | 2026-10-09 | implementado | `src/tree_index.py` `build_tree()` com `children`; `cache/tree_livro.json` version 2 | `../ARCHITECTURE.md` Ramo 2 (`../TASKS.md` só conclusão) |
| `count_tokens.py` | — | parcial/frágil | `ingest.load_chapters`/`clean_page_text` existem, mas `tiktoken` não está em `requirements.txt` | só anotação |

## Decisões já absorvidas (não rediscutir)
- Re-rank default **OFF** (cross-encoder rebaixava chunks didáticos).
- Vectorless é o default da UI; vetorial disponível por toggle.
- TTS premium default **MAI-Voice** (Gemini TTS inventa trechos).
- Cache: toggle OFF pula leitura, mantém escrita; bust por versão (`PROMPT_VERSION`/`TTS_VERSION`/`TREE_VERSION`).

## Pendências reais (das seções "Fora de escopo")
- [ ] S5: `scripts/demo_seed.py` (3 Q&A + 2 MP3) — **não existe**.
- [ ] Comparação formal vetorial × vectorless nas 5 douradas.
- [ ] Resumos por seção (`tree-hierarchy-plan.md` §4).
- [ ] `pip install pageindex` / TOC via Flash do PageIndex (opcional).
- [ ] Estética da UI: CSS, cores, responsivo, landing (`ui-refactor.md` §5).
- [ ] MOS 1–5, clonagem de voz, streaming PCM, SSML (`tts-openrouter-plan.md` §6).

## Resíduos e pendências de doc
- Resolvidos em 2026-11-11: contagem 242→256 em `ARCHITECTURE.md`/`TASKS.md`; aviso de implementado em `golden-questions.md`; typo e "após S5" em `vectorless-pageindex.md`; checkboxes de aceite marcados em `ui-refactor.md`/`tts-openrouter-plan.md`; pasta renomeada `anotations/`→`docs/` e versionada (`.gitignore` limpo).
- `count_tokens.py` depende de `tiktoken` ausente do `requirements.txt` (documentado no docstring).

## Próximo Passo Imediato
Atacar S5 (`scripts/demo_seed.py` + 2 MP3 pré-gerados + modo offline); depois a comparação formal vetorial × vectorless nas 5 douradas.
