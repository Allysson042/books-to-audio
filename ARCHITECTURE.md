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

## Diagrama
```
[PDF] --PyMuPDF--> [chunks + metadata + resumos macro]
                          |
                     [Chroma + BM25]
                          |
[query + escopo + persona] -> [RRF top20 -> re-rank top5]
                          |
        [mapa + macro + micro + glossário + persona] -> [LLM pass1] -> [LLM pass2 roteiro]
                          |
              [Edge-TTS / Piper] -> [MP3 cache] -> [Streamlit player]
```

## Backlog (sprints 2h/semana)
- S0 (2h): setup env, `.env`, ingest skeleton, 1 cap teste.
- S1 (2x2h): ingest completo + mapa + macros + Chroma + BM25.
- S2 (2h): retrieval + re-rank + filtro escopo + painel debug.
- S3 (2x2h): LLMProvider (Gemini) + 2-pass + personas YAML + glossário + citações.
- S4 (2h): TTSProvider + cache MP3 + player Streamlit.
- S5 (2h): kit demo + modo offline + polish seminário (diagrama + métricas).
- Futuro: VLM p/ figuras, Qdrant, editor persona, avaliação RAGAS.
