# LIMITS.md — Onde o sistema para hoje

> Levantamento de **2026-11-13** (auditoria de código + medição nos artefatos em `storage/`).
> Objetivo: saber o que limita qualidade/custo antes de trocar por modelos pagos de maior capacidade.
> Isto **não** é design travado (ver `../ARCHITECTURE.md`) nem backlog de marcos (ver `../TASKS.md`).
> Valores marcados *medido* vêm de `storage/bm25.jsonl`, `storage/chroma`, `cache/tree_livro.json` e `cache/audio/`.

## TL;DR — os 5 gargalos que realmente importam

1. **Embedding truncado em 256 tokens** (`all-MiniLM-L6-v2`): chunk médio tem ~582 palavras (~750 tok) → **só ~1/3 do texto existe no vetor denso**. Não há flag nem aviso; é silencioso.
2. **`CHUNK_CHARS=4500` < maior chunk real (4864)**: os maiores chunks são cortados antes do LLM (` […]`).
3. **Nenhum orçamento total de contexto**: vectorless monta ~11k tokens de chunks + 3k chars de macro sem validação; não há `tiktoken` no projeto.
4. **`GeminiProvider` ignora `max_tokens`**: `MAX_TOKENS=2500` é decorativo no Gemini; o teto real é o default do modelo. Trocar de modelo pago sem corrigir isso = medir outra coisa.
5. **Zero retry/backoff nos providers LLM** (só TTS tem), com `timeout=120` fixo — roteiro longo em modelo premium estoura e cai para o fallback.

Corolário: **subir a janela do LLM não melhora nada sozinho** — o sistema não preenche o contexto que já tem, e o que impede o recall é o embedding, não o LLM.

---

## 1. Ingestão / chunking (`ingest.py`)

| Onde | Constante | Valor | Efeito prático | Config |
|---|---|---|---|---|
| `ingest.py:38` | `CHUNK_WORDS` | 600 | ~800 tok/chunk | hardcoded |
| `ingest.py:39` | `OVERLAP_WORDS` | 90 | ~120 tok de overlap | hardcoded |
| `ingest.py:132` | `step` | 510 | passo da janela | hardcoded |
| `ingest.py:136` | rabo curto | `< 50 palavras` descartadas | fim de capítulo pode sumir | hardcoded |
| `ingest.py:377` | página vazia | `< 100 chars` descartada | página só de figura nunca entra | hardcoded |
| `ingest.py:41` | `BOOK_PAGE_OFFSET` | 28 | erra → **toda citação `[Cap X, p. Y]` erra** | hardcoded |
| `ingest.py:44` | `MACRO_CHARS` | 12.000 | macro vê só o **início** do capítulo | hardcoded |
| `ingest.py:306` | `max_tokens` macro | 1500 | resumo macro curto por construção | hardcoded |
| `ingest.py:298-314` | retry macro | 3 tentativas, 45s/90s, só 429 | erro 5xx não tem retry | hardcoded |

*Medido*: 196 chunks, 14 capítulos (11/19/17/16/19/10/8/14/14/13/16/12/13/14), chars min 814 / média 3605 / **max 4864**, palavras média 582.

## 2. Indexação — o gargalo silencioso

| Onde | Item | Detalhe | Config |
|---|---|---|---|
| `ingest.py:42` / `src/retrieval.py:27` | `EMBEDDING_MODEL` | `all-MiniLM-L6-v2`, 384 dims, **`max_seq_length=256` tokens** | nome do modelo é CLI no ingest, **hardcoded** no retrieval (divergir = quebra silenciosa) |
| — | truncamento | `.encode()` default corta em 256 tok → ~34% do chunk indexado | implícito, sem aviso |
| `ingest.py:185-186` | batch | 100 | upsert por lote | hardcoded |
| `ingest.py:176` | normalização | `normalize_embeddings=False` → Chroma usa **l2** | default do Chroma |
| `ingest.py:198-212` | BM25 | `text.lower().split()`, **sem stemming/stopwords PT** | query PT casa mal com corpus EN |
| `requirements.txt` | `tiktoken` | **ausente** — contagem é `chars//4` (`src/llm_provider.py:105`) | nenhuma validação real de contexto |

## 3. Retrieval vetorial (`src/retrieval.py`)

| Onde | Constante | Valor | Efeito |
|---|---|---|---|
| `retrieval.py:59` / `:65` | top-k denso / BM25 | 20 / 20 | prefetch do RRF |
| `retrieval.py:29` | `RRF_K` | 60 | suavização da fusão |
| `retrieval.py:84` | `search(top_n)` | 20 | candidatos exibidos/re-rankeados |
| `retrieval.py:117` | `rerank(top_n)` | **5** | é o que vai ao Pass1 |
| `retrieval.py:28` | cross-encoder | `ms-marco-MiniLM-L-6-v2`, **`max_length=512`** | pares query+chunk (~750 tok) também truncados |
| `app.py:48` | re-rank default | **OFF** | régua mostrou CE rebaixando chunks didáticos |
| `app.py:117-118` | 20 / 5 | literais duplicados na UI | `retrieve()` wrapper não é usado |

## 4. Retrieval vectorless (`src/retrieval_tree.py`, `src/tree_index.py`)

| Onde | Constante | Valor | Efeito |
|---|---|---|---|
| `retrieval_tree.py:26` | `MAX_NODES` | 6 | nós que o LLM pode escolher por query |
| `retrieval_tree.py:27` | `MAX_CHUNKS` | **10** | vs 5 no vetorial |
| `retrieval_tree.py:121,129` | `max_tokens` seleção | 1200, **1 retry** | JSON de seleção; falha = `RuntimeError` |
| `retrieval_tree.py:88` | `summary[:200]` | 200 chars | resumo do nó no prompt |
| `retrieval_tree.py:120` | prompt da árvore | **sem teto**; *medido* 16.819 chars (~4,3k tok) livro todo, 1.420 chars no Cap 4 | custo fixo por query |
| `retrieval_tree.py:149-163` | seleção | **sem score, ordem do `bm25.jsonl`**, `break` em 10 | 1º nó pode consumir a cota e os demais serem ignorados |
| `tree_index.py:46` | profundidade | `min(lvl, 4)` | TOC L5+ achatado |
| `tree_index.py:62-63,69` | IDs | 2 dígitos | **teto 99 capítulos / 99 irmãos por nível** |

*Medido*: `cache/tree_livro.json` v2 com 14 capítulos, **256 nós**, profundidade 4.

## 5. Contexto entregue ao LLM (`src/generate.py`)

| Onde | Constante | Valor | Efeito |
|---|---|---|---|
| `generate.py:23` | `CHUNK_CHARS` | 4500 | corta até 364 chars do maior chunk (4864) |
| `generate.py:38-42` | `_clip` | corte em palavra + ` […]` | ok, mas silencioso |
| `generate.py:48` | `macro[:3000]` | 3000 | truncamento do nível 2 |
| `generate.py:24` | `MAX_TOKENS` | 2500 | saída Pass1/Pass2 (**ignorado no Gemini**) |
| `generate.py:22` | `PROMPT_VERSION` | v5 | bust global de cache textual |
| `generate.py:49-52` | orçamento total | **inexistente** | vetorial ≈6k tok; **vectorless ≈11k tok** |
| `generate.py:73` | hash Pass1 | `v|pass1|scope|query|chunk_sig` | **sem persona e sem macro** → trocar persona reusa Pass1 velho |
| `generate.py:85` | hash Pass2 | `v|pass2|persona|scope|query|chunk_sig` | **sem `pass1_text`** → Pass2 pode servir roteiro de resumo antigo |

## 6. LLM provider (`src/llm_provider.py`)

| Onde | Item | Detalhe |
|---|---|---|
| `llm_provider.py:20-22` | **Gemini ignora `max_tokens`** | sem `generation_config`; system+user concatenados numa string (sem `system_instruction`) |
| `llm_provider.py:35` | OpenRouter | `timeout=120`, **sem retry/backoff** |
| `llm_provider.py:40-42` | payload | sem `temperature`/`top_p`/`stop`/`seed` |
| `llm_provider.py:58` | default | `max_tokens=1500` — nenhum caller usa (morto) |
| `llm_provider.py:60` | `opencode` | `shorten(width=12000)` → **truncamento duro ~3k tok** |
| `llm_provider.py:90-114` | fallback | 1 tentativa por provider |
| `llm_provider.py:67-87` | chain | `LLM_PRIMARY` (env, default gemini) → demais com key → `opencode` por último; **Groq key existe sem provider** |

## 7. TTS (`src/tts_provider.py`)

| Onde | Constante | Valor | Efeito |
|---|---|---|---|
| `tts_provider.py:41` | `TTS_MAX_CHARS` | **15.000** | trava só no premium; Edge/Piper sem limite |
| `tts_provider.py:40` | `TTS_SLICE_CHARS` | 2500 | fatia por request |
| `tts_provider.py:52-66` | `split_slices` | **parágrafo > 2500 não é cortado** | fatia pode estourar o request |
| `tts_provider.py:36` | `TTS_VERSION` | v1 | bust do cache de áudio |
| `tts_provider.py:95-109` | premium | 2 tentativas, sleep 5, timeout 300 | única camada com retry |
| `tts_provider.py:149-151` | concat | timeout 600, sem limite de fatias | |
| `tts_provider.py:166-175` | Edge | sem timeout/retry/cap | |
| `cache/audio/` | disco | *medido* 70 MB / 88 arquivos, **sem GC** | cresce indefinidamente |

## 8. UI (`app.py`)

- `app.py:81-83` — `st.chat_input` sem `max_chars`.
- `app.py:137-157` — 5 (vetorial) ou até 10 (vectorless) chunks inteiros + tabela com 20 candidatos, sem paginação.
- `app.py:159` — macro exibido com o mesmo corte de 3000 do prompt (coerente).
- `app.py:218-219` — não avisa quando `len(p2) > TTS_MAX_CHARS`; o erro só aparece no clique de áudio.
- `app.py:237-247` — MP3 inteiro em memória por render (5–10 MB), sem streaming.
- `app.py:45` + `.env:11` — **`OFFLINE_MODE` e o toggle "Modo offline" não são lidos por ninguém** (ver B1).

## 9. Divergências com a documentação

- `ARCHITECTURE.md` promete "~30 termos EN" no glossário; `src/prompts.py:2-3` tem **12**.
- `GROQ_API_KEY` no `.env.example` sem provider correspondente em `build_chain`.
- "Modo offline" anunciado como feature; hoje é cosmético (B1).

---

## 10. Plano de destravamento

### P0 — sem reindexar (destrava e permite medir)
- [x] `GeminiProvider`: respeitar `max_tokens` via `generation_config`, `temperature` configurável e `system_instruction` nativo.
- [x] Knobs por env (defaults idênticos aos atuais): `CHUNK_CHARS`, `MAX_TOKENS`, `TOP_K_*`, `MAX_NODES`, `MAX_CHUNKS`, `TTS_MAX_CHARS`, `TTS_SLICE_CHARS`, `LLM_TIMEOUT`, `LLM_RETRIES`, `LLM_TEMPERATURE`, `MAX_QUERY_CHARS`.
- [x] `tiktoken` + orçamento total de contexto com clipping por prioridade (micro > macro > mapa) e log `[context]`.
- [x] Retry/backoff nos providers LLM (mesmo padrão do TTS).
- [x] Chaves de cache: persona+macro no Pass1, `pass1_text` no Pass2; bump `PROMPT_VERSION`.
- [x] `split_slices`: cortar parágrafo maior que o limite (senão `TTS_MAX_CHARS` é furado).
- [x] UI: aviso quando roteiro excede `TTS_MAX_CHARS`; `max_chars` no input.

### P1 — reindexação (salto de qualidade)

**P1a — vector-only (não toca no vectorless).** Só Chroma + re-rank; `bm25.jsonl` e `tree_livro.json` intactos.
- [ ] Embedding de janela maior (BGE-M3 8k CPU ou API paga), **coleção Chroma nova** (dimensão 384→1024 não permite upsert por cima) e `src/retrieval.py:27` alinhado ao modelo do ingest. Idealmente um fluxo "reembed-only" — `ingest.py` hoje reescreve BM25 junto.
- [ ] Re-rank maior (ex. `bge-reranker-v2-m3`) e reavaliar o default OFF contra as 5 douradas.

**P1b — compartilhado (afeta os dois ramos).** Chunks são lidos por `bm25.jsonl` e a árvore usa ranges de página/posição dos nós.
- [ ] Recalibrar chunking ou ir para chunking estrutural por seção do TOC; exige rebuild de BM25 + árvore (`TREE_VERSION`) e reavaliação da régua **nos dois ramos**.

### P2 — retrieval e escala
- [ ] Vectorless: `MAX_NODES`/`MAX_CHUNKS` via env, score por seção + dedupe, retry > 1.
- [ ] BM25 com stemming/stopwords PT e `argsort` parcial (top-k).
- [ ] Embeddings normalizados (cosine) no Chroma.
- [ ] Orçamento de custo por chamada + contabilização de tokens reais pelo provider.

### P3 — higiene
- [ ] Glossário de 12 → ~30 termos (ou corrigir `ARCHITECTURE.md`).
- [ ] Provider Groq ou remover `GROQ_API_KEY` do `.env.example`.
- [ ] GC/limite de disco em `cache/audio/`.
- [ ] Modo offline real (B1).

---

## 11. Vectorless: chunk ↔ nó (medido 2026-11-13)

O vectorless não usa embeddings: o LLM escolhe nós da árvore e os chunks vêm por **sobreposição de páginas** (`retrieval_tree.py:149-150`). Como o chunk nasce de uma janela de 600 palavras sobre o **capítulo inteiro** (`ingest.py:118-158`), ele atravessa seções.

Medições sobre `bm25.jsonl` (196 chunks) × `tree_livro.json` (202 folhas, ranges disjuntos):

| Métrica | Valor |
|---|---|
| Folhas tocadas por chunk (sobreposição de página) | mediana **2** (min 1, máx 6) |
| Texto do chunk que está **dentro** do nó selecionado | mediana **40%** (129/202 nós ficam <50%) |
| Chunks elegíveis por nó | mediana 2 (máx 4) |
| Redundância de páginas por capítulo | ~**50%** (ex. Cap 2: 36 pp → 62 pp-cobertas) |
| Exemplo | `ch02_s03_t00` (pp.69-73): 13.961 chars, ~4.499 (**32%**) de páginas fora do nó |

**Consequência:** ~metade do contexto que o vectorless entrega ao Pass1 vem de seções vizinhas, e o teto `MAX_CHUNKS=10` é gasto com isso. Chunking estrutural (chunk por seção do TOC) torna o mapeamento 1:1 — a folha tem ~11-20 por capítulo e o livro tem 202 folhas para 196 chunks, então o volume fica praticamente igual.

**O que NÃO é necessário:** rebuild da árvore. `tree_livro.json` deriva do TOC (`tree_index.py`), não dos chunks; ranges e `tree_sel_*` continuam válidos. Rechunkar exige reingestão de **BM25 + Chroma** (mesmo `all-MiniLM-L6-v2`, sem trocar modelo) e invalida o cache textual via `chunk_sig`.

**Ressalvas:** uma seção pode começar no meio da página (o TOC só dá página), então sobra ~1 página de bleed no início de cada seção; seções minúsculas (<50 palavras) precisam de merge com a vizinha; e `MAX_CHUNKS` pode precisar subir (10 → 12-16) quando o LLM escolhe nós pai.

**Pré-requisito de medição:** `scripts/eval_retrieval.py` só avalia denso/híbrido/final. Sem um modo vectorless (`--strategy tree`, usando `tree_sel_*` cacheado), não há como provar ganho — hoje o vectorless só é avaliado "no olho". _(Resolvido no V0: `--strategy {vector,tree,both}`.)_

**Plano sugerido (nesta ordem):**
- [x] **V0** modo vectorless na régua (`--strategy tree`), com acerto **agnóstico a chunking** (cap + sobreposição de páginas contra o `expected_id`, não igualdade de `doc_id`) — sem isso, o V2 troca os IDs e a régua quebra. Baseline + razão de "in-scope". **Feito 2026-11-13**: `scripts/eval_retrieval.py --strategy {vector,tree,both}` — `tree@5` e `tree@all` + `in_scope` médio + chars. Baseline legacy: **8/10 tree@5 = 8/10 tree@all, in_scope médio 56%** (Q4 perdia o Cap 8).
- [x] **V1** (sem reindexar) ranquear chunks do nó por fração de páginas dentro + **quota round-robin por nó** (hoje o 1º nó pode consumir as 10 vagas e os outros 5 voltarem vazios) + `MAX_CHUNKS` por env. Mede. **Feito 2026-11-13**: `rank_and_allocate()` + `TREE_DELIVERY=ranked|legacy` (`src/config.py`). Quota = pertinência, saída reordenada por score = prioridade. Placar ranked: **10/10 tree@5 e 10/10 tree@all, in_scope 63%** (Q4 acerta em `5@2` EN / `5@3` PT; a versão sem a reordenação final fazia 8/10 @5 porque o Cap 8 saía na posição 6). `legacy` reproduz byte-a-byte o comportamento antigo (8/10 e 8/10, in_scope 56%; ids/paths/keys iguais em 10/10).
- [x] **V2** chunks alinhados por seção em **store separado** (`storage/tree_chunks.jsonl`, só leitura pelo `TreeStore`): Chroma/BM25/vetoral **intactos**, árvore intacta, zero reembed. Script próprio reusando a extração do `ingest.py`. Mede. **Feito 2026-11-26**: `scripts/build_tree_chunks.py` → **271 chunks** (14 caps, cobertura 100%; grupos <50 palavras fundidos, janela 600/90 dentro do grupo, `doc_id` `t{cap}_p{ini}-{fim}_{idx}`). `TreeStore` lê `TREE_CHUNKS_PATH` com fallback para `bm25.jsonl`. Medição: `in_scope` por chunk mediana **100%** (86% ≥90%; 37 chunks são páginas de abertura fora dos ranges das folhas), in_scope médio entregue **99%** (63% antes), **tree@5 10/10**, tree@all 10/10, chars médios 10.240 (15.560 antes). A/B com fallback reproduz 63%/10/10; vetorial en segue 3/5.
- [x] **V2.1** (resíduo do V2, sem rebuild) `tree_fit` = `in_scope` quando >0, senão `0.5 ×` a fração coberta pelo span do **próprio nó** — resgata os 36 chunks de abertura de capítulo/seção que caíam em páginas sem folha (`in_scope=0`). **Feito 2026-11-26**: 36/36 resgatáveis. O fator 0.5 é obrigatório: sem desconto o fallback virava `1.0` (span de capítulo cobre 100%) e passava na frente de chunks genuínos — posições no `tree@5` pioravam (soma 6 vs 4) e `in_scope` caía 99→92%. Com desconto: **in_scope 99%, tree@5 10/10, tree@all 10/10**, Q2-pt e Q4 em `5@2`. `in_scope` (métrica) e `tree_fit` (sinal de ranking) são campos distintos.
- [x] **V3** qualidade da *seleção*: páginas impressas consistentes no prompt, snippet por folha e `TREE_PROMPT=v1|v2` para A/B. **Feito 2026-11-26**: v2 usa página impressa em todos os níveis (antes capítulo=`book_page`, L3/L4=`pdf_page` — dois sistemas de numeração no mesmo prompt) + snippet de 80 chars nas folhas (`SNIPPET_BUDGET=12000`; 160/202 nós, 12.012 chars). Chave de cache: `v1` mantém o formato antigo (`tree|v{TREE_VERSION}|{scope}|{query}`) e **reusa `tree_sel_*` de graça**; `v2` usa `p2|` e gasta LLM. Medição: v1 = 99% / 10/10 / 10/10 / 10.240 chars / prompt 16.819; v2 = **100% / 10/10 / 10/10 / 9.575 chars** / prompt **28.298** (+68%). **Ganho marginal na régua de 5 perguntas** (9 delas são casos fáceis) — o alvo real do V3 é seleção em pergunta ambígua, que a régua não mede. Custo: quota LLM por query nova + prompt 68% maior. Risco conhecido: 42 folhas ficam sem snippet (orçamento), criando assimetria de sinal entre folhas.
