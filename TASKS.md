# TASKS.md — Plano de ação persistente (fonte de progresso entre sessões)

> Agentes OpenCode: leiam este arquivo + `ARCHITECTURE.md` + `AGENTS.md` no início de cada sessão.
> Atualizem os checkboxes ao concluir. `TodoWrite` é volátil — isto aqui é permanente.

## Estado atual (2026-09-16)
- Grill-me concluído. Scaffold inicial criado. Pronto para S0.

## S0 — Setup [ ]
- [ ] Criar `.venv`, instalar `requirements.txt`, copiar `.env.example` → `.env` com `GEMINI_API_KEY`
- [ ] Colocar PDF em `data/generative-deep-learning.pdf`
- [ ] Teste: `python ingest.py --help` + `streamlit run app.py` abre sem erro

## S1 — Ingestão hierárquica [ ]
- [ ] `ingest.py`: PyMuPDF por capítulo/seção, chunks ~800 tok overlap 120, metadata (chapter/section/page/type)
- [ ] Extrair texto + código + legendas, ignorar pixels (VLM fica p/ futuro)
- [ ] Gerar `mapa_livro.json` + `resumo_macro_{cap}.md` (1x via LLM)
- [ ] Persistir Chroma em `storage/chroma/` + dump BM25

## S2 — Recuperação [ ]
- [ ] Híbrida Chroma + BM25 com fusão RRF
- [ ] Filtro escopo Todos/Cap N
- [ ] Re-rank cross-encoder MiniLM top-20 → top-5
- [ ] Painel debug no Streamlit (chunks + scores + citações)

## S3 — Geração 2-pass + personas [ ]
- [ ] `LLMProvider`: Gemini primário + fallback + opencode-subprocess experimental
- [ ] Pass1 técnico com `[Cap X, p. Y]` + Pass2 roteiro TTS (limpo, siglas expandidas)
- [ ] `personas/*.yaml` + glossário EN injetado
- [ ] Cache em `cache/` por hash

## S4 — TTS + player [ ]
- [ ] `TTSProvider`: Edge-TTS primário + Piper fallback
- [ ] Template 5-8min, cache `cache/audio/`, player + download no Streamlit

## S5 — Kit demo seminário [ ]
- [ ] `scripts/demo_seed.py`: 3 Q&A douradas + 2 MP3 pré-gerados
- [ ] Modo offline (serve cache se API falhar)
- [ ] Polish: diagrama + métricas + vídeo backup

## Futuro (pós-seminário)
- [ ] VLM para descrever figuras
- [ ] Avaliação RAGAS, editor de persona, Qdrant

## Log de decisões
- 2026-09-16: grill-me travou hierárquico + híbrida + 2-pass + Edge+Piper + Streamlit monolito. Ver `ARCHITECTURE.md`.
