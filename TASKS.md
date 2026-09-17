# TASKS.md — Plano de ação persistente (fonte de progresso entre sessões)

> Agentes OpenCode: leiam este arquivo + `ARCHITECTURE.md` + `AGENTS.md` no início de cada sessão.
> Atualizem os checkboxes ao concluir. `TodoWrite` é volátil — isto aqui é permanente.

## Estado atual (2026-09-16)
- Grill-me concluído. Scaffold inicial criado. S0 concluído. **S1 concluído** (196 chunks, 14 caps). **S2 concluído**. **S3 implementado** (live E2E OK via OpenRouter). **S4 concluído**. Pronto para S5.

## S0 — Setup [x]
- [x] Criar `.venv`, instalar `requirements.txt`, copiar `.env.example` → `.env` com `GEMINI_API_KEY`
- [x] Colocar PDF em `data/generative-deep-learning.pdf`
- [x] Teste: `python ingest.py --help` + `streamlit run app.py` abre sem erro

## S1 — Ingestão hierárquica [x]
- [x] `ingest.py`: PyMuPDF por capítulo/seção, chunks ~800 tok overlap 120, metadata (chapter/section/page/type)
- [x] Extrair texto + código + legendas, ignorar pixels (VLM fica p/ futuro)
- [x] Gerar `mapa_livro.json` + `resumo_macro_{cap}.md` (1x via LLM)
- [x] Persistir Chroma em `storage/chroma/` + dump BM25

## S2 — Recuperação [x]
- [x] Híbrida Chroma + BM25 com fusão RRF
- [x] Filtro escopo Todos/Cap N
- [x] Re-rank cross-encoder MiniLM top-20 → top-5
- [x] Painel debug no Streamlit (chunks + scores + citações)

## S3 — Geração 2-pass + personas [x]
- [x] `LLMProvider`: Gemini primário + fallback + opencode-subprocess experimental
- [x] Pass1 técnico com `[Cap X, p. Y]` + Pass2 roteiro TTS (limpo, siglas expandidas)
- [x] `personas/*.yaml` + glossário EN injetado
- [x] Cache em `cache/` por hash

## S4 — TTS + player [x]
- [x] `TTSProvider`: Edge-TTS primário + Piper fallback
- [x] Template 5-8min, cache `cache/audio/`, player + download no Streamlit

## S5 — Kit demo seminário [ ]
- [ ] `scripts/demo_seed.py`: 3 Q&A douradas + 2 MP3 pré-gerados
- [ ] Modo offline (serve cache se API falhar)
- [ ] Polish: diagrama + métricas + vídeo backup

## Futuro (pós-seminário)
- [ ] VLM para descrever figuras
- [ ] Avaliação RAGAS, editor de persona, Qdrant

## Notas p/ futuras sessões (aprendizados 16/09 — não repetir erros)
- **Query EN > PT no retrieval** (corpus e MiniLM são EN; resposta sai PT-BR de todo jeito). Otimização futura: traduzir query p/ EN antes de buscar. **Medir antes de mexer**: montar 3-5 perguntas douradas (pergunta + cap/pág esperados) e checar hit-rate top-5 em PT vs EN antes de rechunkar (rechunk = reembedar tudo).
- **Gemini**: chave nova só aceita família 3.x (`gemini-3.6-flash` ok). Quota diária reseta 00:00 Pacific = 04:00 BRT. Caps 12-14 seguem em macro heurística (ver comando no log S1).
- **OpenRouter**: key em `OPENROUTER_API_KEY` no `.env`; default `openrouter/free` (aleatório — fixar via `OPENROUTER_MODEL` p/ qualidade estável em PT-BR). Headers HTTP do httpx devem ser **ASCII puro** (X-Title com `á` quebrou).
- **`opencode-subprocess` é fallback experimental e perigoso em testes**: invoca sessão aninhada; nunca disparar em AppTest/CI (validar só chain, com stub).
- **Streamlit**: `st.dataframe` exige colunas de tipo homogêneo (pyarrow); usar strings + `width="stretch"`. Ruído `torchvision` no log = file-watcher fuçando o `transformers`, ignorar. AppTest desta versão **não tem `.audio`** (checar player via `download_button`).
- **Cache**: texto `cache/pass1_*.md` / `pass2_*` (bust via `PROMPT_VERSION`); áudio `cache/audio/` (bust via `TTS_VERSION`). Repetir query = instantâneo, sem gastar quota.
- **BM25**: `ingest.py --chapters N` **sobrescreve** `storage/bm25.pkl` só com o subset — após ingest parcial, rodar full p/ restaurar os 196 docs.

## Log de decisões
- 2026-09-16: grill-me travou hierárquico + híbrida + 2-pass + Edge+Piper + Streamlit monolito. Ver `ARCHITECTURE.md`.
- 2026-09-16 (S1): 196 chunks (600 palavras ~800 tok, overlap 90 ~120 tok) via TOC embutido; capítulos = TOC L2, seções = L3/L4 por página. Cabeçalhos `N | Chapter X: Título` removidos via regex (poluíam 100% dos chunks). `page_*` = nº PDF, `book_page_*` = impresso (offset 28) p/ citações `[Cap X, p. Y]`. Chroma `books` (all-MiniLM-L6-v2 CPU) + `storage/bm25.pkl` + `storage/bm25.jsonl`. Macros 11/14 via Gemini; modelo padrão `gemini-2.0-flash` → `gemini-3.6-flash` (2.0/2.5 indisponíveis p/ chave nova). Caps 12-14 em rascunho heurístico (quota 429): regenerar com `rm cache/resumo_macro_cap1[234].md && python ingest.py --chapters 12,13,14`.
- 2026-09-16 (S2): `src/retrieval.py` — `RAGStore` (denso Chroma + esparso BM25, RRF k=60, `where chapter` nos dois lados) + `Reranker` (cross-encoder ms-marco-MiniLM-L-6-v2 CPU, lazy) + `retrieve()` top-20→top-5. `app.py`: escopo dinâmico via `mapa_livro.json`, macro do cap em foco (nível 2), top-5 com `[Cap X, p. Y]` + tipo + score, tabela debug com ranks denso/BM25/RRF/re-rank. `streamlit run` healthy (200). Bugfix pós-teste: colunas do debug como string homogênea (pyarrow quebrava com int+`–` misturados) + `width="stretch"` (deprecation do `use_container_width`).
- 2026-09-16 (S3): `OpenRouterProvider` (`openrouter/free` default, via httpx, sem nova dep) + `build_chain()` (só providers com key; ordem `LLM_PRIMARY`, opencode-subprocess por último) + `complete_with_fallback()` (retorna texto+provider, erro agregado). `src/generate.py`: `answer()` retrieve→Pass1→Pass2, personas via YAML (`system_addendum`), glossário injetado, cache `pass1_{h}.md`/`pass2_{persona}_{h}.md` (hash `PROMPT_VERSION|persona|escopo|query|chunk_ids`). `app.py`: botão 2-pass + abas Pass1/Pass2 + badge provider/cache. Validado com stub (geração→cache→cache-hit) + AppTest sem exceção. **Live E2E OK via OpenRouter** (query ELBO → Pass1 com `[Cap X, p. Y]` + Pass2 roteiro). Bugfix: header `X-Title` com `á` quebrava httpx (ASCII) — removido acento. Gemini segue 429 até ~04:00 BRT 17/09.
- 2026-09-16 (S4): `src/tts_provider.py` — `synthesize()` sync (Edge-TTS + fallback Piper, retorna `(mp3, engine)`), `clean_for_speech()` (tira `#/**/`` `/bullets/`[MARCADORES]` do roteiro antes da fala), cache `cache/audio/{sha}.mp3` + sidecar `.json`. Voz por persona (`tts_voice` no YAML: Francisca=iniciante, Antonio=técnico). `app.py`: roteiro em `session_state`, botão áudio habilitado após 2-pass + player + download. Validado: 1358 chars → 591KB via edge-tts, cache-hit na 2ª, AppTest sem exceção. Piper: código pronto, binário não instalado (erro claro se Edge falhar offline).
