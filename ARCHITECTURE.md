# DECISÕES TRAVADAS (grill-me 2026-09-16)

## Tronco 0 — Restrições
- Prazo: 2-3 meses, poucas h/semana, solo Python. Consequência: monolito Streamlit, sem Docker, sem auth.
- Custo: R$0, open-source pref. LLM via abstração `LLMProvider` (Gemini free primário, Groq/OpenRouter fallback, Ollama local, opencode-subprocess experimental). Embeddings locais CPU. TTS Edge-TTS + Piper.
- Idioma: saída PT-BR, termos técnicos em EN preservados via glossário.
- Fonte: PDF digital com texto (PyMuPDF). Sem OCR no MVP.
- Demo: ao vivo com internet + kit offline obrigatório (cache + 3 perguntas douradas).

## Ramo 1 — Ingestão (micro + macro)
- Hierarquia: Livro > Capítulo > Seção > Chunk (~800 tokens, overlap 120).
- Extrai: texto + blocos de código + legendas + nº página. Ignora pixels das figuras no MVP (VLM futuro).
- Gera 1x: `mapa_livro.json` (título + 2 linhas por cap) + `resumo_macro_{cap}.md` em PT-BR.
- Metadata obrigatória: chapter, section, page_start, page_end, type, doc_id.
- Citação obrigatória `[Cap X, p. Y]`.

## Ramo 2 — Recuperação
- Híbrida desde MVP: Chroma (sentence-transformers, CPU) + BM25 (`rank-bm25`), fusão RRF.
- Contexto 3 níveis sempre: (1) mapa livro, (2) resumo macro cap focado, (3) top-5 micro re-rankeados.
- Filtro escopo: Todos / Cap N (metadata).
- Re-rank local: cross-encoder MiniLM, top-20 -> top-5.
- Vector store: Chroma persistente em `./storage/chroma`.

## Ramo 3 — Geração (rigor vs fluidez + persona)
- 2 passes com cache em `./cache/`:
  - Pass1 `resumo_tecnico`: fiel, denso, com citações.
  - Pass2 `roteiro_audio`: reescrita fluida TTS-friendly, sem colchetes, siglas expandidas na fala, termos do glossário intactos.
- Personas em YAML (`personas/`): `tecnico_direto` (você) e `iniciante_guiado` (parênteses explicativos p/ RAG, LLM, etc.).
- Glossário fixo ~30 termos EN intocáveis, injetado no system prompt.

## Ramo 4 — TTS
- `TTSProvider`: Edge-TTS primário (`pt-BR-FranciscaNeural` / `pt-BR-AntonioNeural`) + Piper fallback offline.
- Template 5-8min: gancho 30s + 3 ideias-chave + analogia + fechamento "leia Cap X p. Y".
- Cache MP3 por hash `(cap+escopo+persona+versão_prompt)` em `./cache/audio/`. Permite demo offline.

## Ramo 5/6 — Stack + UX demo
- `app.py` (Streamlit): sidebar (escopo cap, persona, modo offline), chat, painel debug (chunks + scores + citações — prova visual do RAG), botão "Gerar áudio" + player + download.
- `ingest.py`: one-shot batch. `app.py`: só leitura.
- Kit demo: `scripts/demo_seed.py` pré-gera 3 Q&A + 2 MP3. Ex: "Explique GANs vs Diffusion como se fosse cap 4", "O que é ELBO em VAEs?".
- Anti-demo-effect: se API falhar/quota estourar, modo offline serve cache.

## Evolução pós-grill-me (tudo implementado e validado — ver `TASKS.md`)
- **Ramo 2 — duas estratégias com toggle**: (a) vetorial (RRF + re-rank *desligável*, default OFF após régua mostrar que o cross-encoder rebaixava chunks didáticos); (b) vectorless estilo PageIndex (`src/tree_index.py` + `src/retrieval_tree.py`): árvore L2→L3→L4 do TOC (242 nós, ranges por irmão) + LLM escolhe seções via JSON (parser tolerante + retry), sem vetores, sem re-rank. Tradução de query p/ EN só faz sentido no ramo vetorial (no vectorless o LLM já casa PT→EN).
- **Ramo 1/3 — fidelidade de contexto**: Pass1 recebe chunks ~inteiros (`CHUNK_CHARS=4500`, corte em palavra; regra: UI mostra = LLM recebe); Pass1 permite LaTeX com render híbrido (`src/markdown_math.py`: inline no markdown, bloco no `st.latex`); teto de saída `MAX_TOKENS=2500`.
- **Ramo 3 — providers**: chain configurável (`LLM_PRIMARY`, `GEMINI_MODEL`, `OPENROUTER_MODEL`); regra **só-`content`** (pensamento de reasoning nunca vaza; `reasoning.exclude` quebra DeepSeek — não usar); log `[llm-call]` (provider/modelo/tamanhos/tempo) no terminal.
- **Ramo 4 — TTS premium opcional**: `synthesize_premium()` via OpenRouter (`OPENROUTER_TTS_MODEL`, default `microsoft/mai-voice-2.1` com vozes PT-BR por persona) + fatiamento (~2500ch, cache por fatia) + concat ffmpeg + trava `TTS_MAX_CHARS` + toggle sidebar (OFF = Edge grátis, zero gasto). Achado: Gemini 3.8 Flash TTS **inventa trechos** (provado via transcrição+diff) — MAI é o default premium por fidelidade literal.
- **Ramo 5/6 — UI e régua**: chunks em expander colapsado, abas Pass1/Pass2 independentes (auto-encadeiam), toggles de cache / re-rank / estratégia / voz premium, logs `[llm-call]`/`[tts-call]`; `scripts/` com `golden.json` (5 douradas PT+EN) + `eval_retrieval.py` (hit-rate por estágio) + `fix_summaries.py`.
- **Cache (regra geral)**: tudo cacheia (texto, seleção da árvore, fatias de áudio); versões (`PROMPT_VERSION`, `TTS_VERSION`, `TREE_VERSION`) invalidam; toggle OFF pula leitura, mantém escrita.

## Diagrama (atual: 2 estratégias, TTS premium opcional)
```
[PDF] --PyMuPDF--> [chunks + metadata + resumos macro + árvore TOC]
                          |
              +-----------+-----------+
              |                       |
     [Chroma + BM25]           [tree_livro.json]
              |                       |
[query + escopo + persona] -> [RRF top20 -> re-rank top5]  (vetorial, re-rank toggável)
[query + escopo + persona] -> [LLM escolhe seções na árvore]  (vectorless)
                          |
        [mapa + macro + micro + glossário + persona] -> [LLM pass1] -> [LLM pass2 roteiro]
                          |
     [Edge-TTS / Piper / OpenRouter-TTS premium] -> [MP3 cache] -> [Streamlit player]
```

## Backlog (sprints 2h/semana)
- S0 (2h): setup env, `.env`, ingest skeleton, 1 cap teste. **[x]**
- S1 (2x2h): ingest completo + mapa + macros + Chroma + BM25. **[x]**
- S2 (2h): retrieval + re-rank + filtro escopo + painel debug. **[x]**
- S3 (2x2h): LLMProvider (Gemini) + 2-pass + personas YAML + glossário + citações. **[x]**
- S4 (2h): TTSProvider + cache MP3 + player Streamlit. **[x]**
- S5 (2h): kit demo + modo offline + polish seminário (diagrama + métricas). **[ ]**
- Extras feitos pós-S4: régua dourada + toggle re-rank + tradução-EN planejada (só vetorial) + vectorless + TTS premium + observabilidade.
- Futuro: VLM p/ figuras, Qdrant, editor persona, avaliação RAGAS, chunking estrutural, MOS de áudio.
