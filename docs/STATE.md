# STATE.md — Índice e status de `docs/`

> Memória quente desta pasta. Backlog do projeto: `../TASKS.md`; ajustes pequenos/bugs: `../BACKLOG.md`; design travado: `../ARCHITECTURE.md`.
> Este arquivo NÃO duplica o backlog — só indexa as notas e aponta o que ainda está vivo nelas.

## Contexto Atual (2026-11-26)
As 5 notas de design têm contrapartida implementada no código e funcionam como *design rationale*.
`LIMITS.md` é a nota viva: P0 e a trilha vectorless **V0→V3 concluídas**. O vectorless usa store
próprio por seção (271 chunks): **in_scope 99-100%** (era 56%), tree@5 e tree@all 10/10, sem tocar
em Chroma/BM25/árvore. A régua, porém, tem 5 perguntas fáceis — o ganho real do V3 (seleção em
pergunta ambígua) ainda não está medido.

## Status por nota
| Nota | Data | Status | Evidência verificada | Absorvida em |
|---|---|---|---|---|
| `golden-questions.md` | 2026-09-23 | implementado | `scripts/golden.json` (Q1–Q5) + `scripts/eval_retrieval.py` (`hit_in`, `main`, `--no-rerank`) | `../ARCHITECTURE.md` Ramo 5/6; `../TASKS.md` Extras |
| `ui-refactor.md` | 2026-09-23 | implementado | `app.py` toggles cache/re-rank/estratégia/premium; `src/generate.py` `get_pass1`/`get_pass2(use_cache)` | `../TASKS.md` §UI funcional |
| `vectorless-pageindex.md` | 2026-09-23 | implementado | `src/retrieval_tree.py` `TreeStore.search`; `src/tree_index.py` `TREE_VERSION="2"`; default vectorless no `app.py` | `../ARCHITECTURE.md` Ramo 2 + diagrama |
| `tts-openrouter-plan.md` | 2026-10-06 | implementado | `src/tts_provider.py` `synthesize_premium`, `split_slices`, `TTS_MAX_CHARS=15000`; `OPENROUTER_TTS_MODEL` no `.env.example` | `../ARCHITECTURE.md` Ramo 4 |
| `tree-hierarchy-plan.md` | 2026-10-09 | implementado | `src/tree_index.py` `build_tree()` com `children`; `cache/tree_livro.json` version 2 | `../ARCHITECTURE.md` Ramo 2 (`../TASKS.md` só conclusão) |
| `count_tokens.py` | — | parcial/frágil | `ingest.load_chapters`/`clean_page_text` existem, mas `tiktoken` não está em `requirements.txt` | só anotação |
| `LIMITS.md` | 2026-11-26 | P0 + V0→V3 implementados; P1a aberto | auditoria + medições; P0 sem regressão (5/10 re-rank ON, 7/10 híbrido); V0/V1 (ranked 10/10 @5, 63%); V2 (271 chunks por seção, 99%); V2.1 (`tree_fit` com desconto 0.5, 36/36 resgatados); V3 (`TREE_PROMPT=v1\|v2`, v2 = 100%/10/10, prompt 16.819→28.298); vetorial 3/5 inalterado | `../TASKS.md` §P0, §V0/V1, §V2, §V2.1+V3 |
| `image-mindmap-plan.md` | 2026-11-27 | **M0 + tela cheia + M1 implementados** | catálogo/preços; outline JSON → SVG determinístico; `embed` (tamanho natural + rolagem) e `publish` (HTML em viewport com zoom); `src/image_provider.py` (`/api/v1/images`, b64, cache+sidecar, sniff PNG/JPEG/WebP); botão "Estilizar"; régua OCR: **Nano Banana 2 100% (US$ 0,067)** × Recraft 67-92% (US$ 0,007) × gpt-image-1-mini descartado | `../TASKS.md` §M0/M1 |
| `UX/` (README + 01–07 + mockup) | 2026-11-27 | **U0–U5 implementados**; validação humana pendente | auditoria U1–U26 + heurísticas + baseline; wireframes e matriz de estados; design system; roadmap; spec; **guia visual canônico** (`06`); **resultado antes/depois + roteiro de demo** (`07`); mock navegável. **U0:** tema light/dark, `theme/copy`, chips. **U1:** sem abas, CTA "Ouvir", trilha, `mp3_sig`, retry, `↻ Regerar`. **U2:** sem sidebar; header + `⚙ Ajustes`; U25. **U3:** cards de fonte, relevância, trecho/debug em popover. **U4:** `history.py` (turnos, restore sem LLM, export, clear). **U5:** dock, apresentação, foco; **pós-U5:** cards com superfície por tema + player custom (static; reiniciar). AppTest + CSS 1/1 + smoke 200 | `../TASKS.md`, `../ARCHITECTURE.md`, `../README.md` (bloqueados; sincronizar) |

## Decisões já absorvidas (não rediscutir)
- **`finish_reason=length` agora é erro** no `OpenRouterProvider` (2026-11-27): antes o texto truncado voltava como sucesso e podia virar cache envenenado; agora cai no fallback. Junto: `complete(..., extra=)` para payload por provider, com retry sem `extra` em 400/422.
- Mapa mental: **SVG é o default** (fiel, offline, US$ 0); imagem generativa só no botão "Estilizar". `MINDMAP_REASONING=none` porque o DeepSeek queimava todo o `max_tokens` em `reasoning` e devolvia JSON cortado.
- Re-rank default **OFF** (cross-encoder rebaixava chunks didáticos).
- Vectorless é o default da UI; vetorial disponível por toggle.
- TTS premium default **MAI-Voice** (Gemini TTS inventa trechos).
- Cache: toggle OFF pula leitura, mantém escrita; bust por versão (`PROMPT_VERSION`/`TTS_VERSION`/`TREE_VERSION`).
- **Vectorless tem store de chunks próprio** (`storage/tree_chunks.jsonl`, alinhado à seção); Chroma/`bm25.jsonl` continuam exclusivos do ramo vetorial. `TREE_CHUNKS_PATH` com fallback.

## Pendências reais (das seções "Fora de escopo")
- [x] **P0** destravar limites (`LIMITS.md` §10): feito e validado (2026-11-13) — `src/config.py`, `src/token_budget.py`, Gemini com `generation_config`/`system_instruction`, retry/backoff, chaves de cache v6, `split_slices`. Régua sem regressão (5/10 re-rank ON, 7/10 híbrido).
- [ ] **P1a** vector-only (não toca no vectorless): embedding de janela maior (hoje `all-MiniLM-L6-v2` trunca em 256 tok ≈ ⅓ do chunk) + re-rank maior.
- [ ] **P2** BM25 com stemming PT, embeddings normalizados (cosine), orçamento de custo por chamada.
- [x] **Vectorless V0/V1** (medido em `LIMITS.md` §11): régua `--strategy tree` agnóstica a chunking + entrega `TREE_DELIVERY=ranked` (ranking por `in_scope`/`tree_lex` + quota por nó + ordem por score). **10/10 @5 e @all, in_scope 63%**; legacy mantido para A/B.
- [x] **Vectorless V2** (2026-11-26): `scripts/build_tree_chunks.py` → `storage/tree_chunks.jsonl` (271 chunks por seção, 13 grupos fundidos, cobertura 100%); `TreeStore` lê `TREE_CHUNKS_PATH` com fallback para `bm25.jsonl`; Chroma/BM25/árvore intactos. **in_scope 99%** (era 63%), 10/10 @5 e @all, chars/query 10.240.
- [x] **Vectorless V2.1** (2026-11-26): `tree_fit` (sinal de ranking) separado de `in_scope` (métrica); fallback `0.5 × span do nó` resgata 36/36 chunks de abertura. Sem desconto o fallback virava 1.0 e piorava a ordem.
- [x] **Vectorless V3** (2026-11-26): `TREE_PROMPT=v1|v2`; v2 com página impressa consistente + snippet de 80 chars nas folhas (160/202, orçamento 12k). v1 reusa `tree_sel_*` antigo (A/B sem LLM). v2: 100%/10/10, prompt +68% (16.819→28.298).
- [ ] **Medir a seleção de verdade**: a régua (5 perguntas, 9 fáceis) não distingue v1 de v2. Faltam perguntas ambíguas/panorâmicas (ex. "resuma o capítulo", "como se relacionam X e Y") para justificar o custo do prompt maior.
- [ ] S5: `scripts/demo_seed.py` (3 Q&A + 2 MP3) — **não existe**.
- [ ] S5: modo offline real (rastreado como **B1** em `../BACKLOG.md`).
- [ ] Comparação formal vetorial × vectorless nas 5 douradas.
- [ ] Resumos por seção (`tree-hierarchy-plan.md` §4).
- [ ] `pip install pageindex` / TOC via Flash do PageIndex (opcional).
- [x] **Mapa mental M0** (`image-mindmap-plan.md` §8, 2026-11-27): `src/mindmap.py` (outline JSON + SVG determinístico), card no Pass1 com intent `map`, `scripts/eval_mindmap.py`, knobs `MINDMAP_*`. LLM real: 2/2 mapas válidos, SVG 1200×altura dinâmica, todos os rótulos dentro do viewBox. Custo ≈US$ 0,00018/mapa (`reasoning=none`, 4,5× mais barato).
- [x] **Mapa mental — tela cheia** (`image-mindmap-plan.md` §11, 2026-11-27): `src/ui/mindmap_view.py` — `embed()` mantém o SVG no tamanho natural com rolagem no card (rótulos deixam de encolher) e `publish()` gera `static/mind/<hash>.html` ocupando a viewport, com zoom −/+/Ajustar, download e tema herdado; fallback com aviso quando o static serving está off.
- [x] **Mapa mental M1** (`image-mindmap-plan.md` §12, 2026-11-27): `src/image_provider.py` (`POST /api/v1/images`, b64, cache+sidecar com `usage.cost`, retry 429/5xx, 402/403 sem retry, sniff PNG/JPEG/WebP) + botão "🎨 Estilizar" (imagem é adicional; SVG nunca some) + `scripts/eval_images.py` (OCR/recall). Régua: **Nano Banana 2 100%/100%** (US$ 0,067) · Recraft 92%/67% (US$ 0,007) · gpt-image-1-mini 62%/90% (US$ 0,05, 40 s) descartado. `IMAGE_MAX_LABELS=12` elevou o recall sem tocar no SVG. Custo da avaliação ≈US$ 0,40.
- [ ] **Mapa mental M1 — refinamentos**: joelho de `IMAGE_MAX_LABELS` (8/12/16) com mais perguntas; modo híbrido `input_references` (SVG rasterizado como rascunho); pin definitivo no `.env` local (`IMAGE_MODEL=google/gemini-3.1-flash-image`).
- [ ] **UX U0→U5** (`UX/04-roadmap.md`): **U0–U5 implementados em 2026-11-27** (resumo antes/depois em `UX/07-resultado.md`). Tema light/dark; jornada linear com CTA "Ouvir"; sidebar removida; fontes em cards; ☰ Sessão (restore sem LLM, export `.md`); dock com **player custom** (static) e modo apresentação; cards com superfície por tema. Validado: AppTest (normal/apresentação/dock/fallback), CSS, `curl` 200 em `/app/static`, smoke 200. **Falta (humano/S5):** **reiniciar o app** para o static serving, teste do fluxo real LLM/TTS, conferência visual (player/dark/390 px), capturas, pin `streamlit>=1.64,<2`, sincronizar `TASKS.md`/`ARCHITECTURE.md`/`README.md`, `demo_seed.py`/offline.
- [ ] MOS 1–5, clonagem de voz, streaming PCM, SSML (`tts-openrouter-plan.md` §6).

## Resíduos e pendências de doc
- Resolvidos em 2026-11-11: contagem 242→256 em `ARCHITECTURE.md`/`TASKS.md`; aviso de implementado em `golden-questions.md`; typo e "após S5" em `vectorless-pageindex.md`; checkboxes de aceite marcados em `ui-refactor.md`/`tts-openrouter-plan.md`; pasta renomeada `anotations/`→`docs/` e versionada (`.gitignore` limpo).
- `count_tokens.py` depende de `tiktoken`, agora no `requirements.txt` (P0, 2026-11-13); o script segue avulso.
- Aprendizado 2026-11-13: **`python-dotenv` não descarta comentário inline** (`KEY=valor  # nota` vira valor com `#`). No `.env`/`.env.example`, comentário sempre em linha própria — quebrou `LLM_TEMPERATURE` e derrubaria os knobs novos.
- 2026-11-26 (V2): a árvore tem **lacunas de cobertura** (21 páginas de capítulo sem folha), origem dos 36 chunks com `in_scope=0`; `storage/tree_chunks.jsonl` é gerado (não versionado, como Chroma) por `scripts/build_tree_chunks.py`.

## Próximo Passo Imediato
**Medir a seleção de verdade** antes de manter `TREE_PROMPT=v2` como default: a régua atual (5
perguntas, 9 fáceis) empata v1 e v2, mas v2 custa +68% de prompt e quota LLM por query nova.
Adicionar 3-5 perguntas **ambíguas/panorâmicas** em `scripts/golden.json` (ex. "resuma o capítulo 4",
"como se relacionam GANs e diffusion?") e comparar v1 × v2. Se v2 não ganhar, voltar o default para
v1 (grátis via cache). Independentes: **P1a** (embedding de janela maior, só vetorial) e **S5**
(`demo_seed.py` + modo offline).
Miudezas descobertas em sessão (fora de sprint) vão para `../BACKLOG.md`, não para cá.
