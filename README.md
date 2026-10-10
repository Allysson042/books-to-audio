# Books to Audio — RAG + TTS para estudo

Case de seminário: **LLM para texto + TTS para áudio**, com RAG sobre o livro
*Generative Deep Learning* (David Foster, O'Reilly). Você pergunta, o sistema recupera os
trechos do livro, gera um resumo técnico + um roteiro de áudio em **PT-BR** — e narra o
roteiro para você ouvir (5–8 min). Roda **grátis** (APIs free tier + modelos locais CPU),
com upgrade opcional para vozes premium pagas (centavos por áudio).

## Como funciona

```
[PDF] --PyMuPDF--> [chunks (~800 tok) + resumos macro + árvore TOC]
                          |
              +-----------+-----------+
              |                       |
     [Chroma (vetor local) + BM25]  [tree_livro.json]
              |                       |
[pergunta + escopo + persona] --> [RRF top-20 -> re-rank top-5]  (vetorial)
[pergunta + escopo + persona] --> [LLM escolhe seções na árvore]  (vectorless)
                          |
[macro + micro + glossário + persona] --> [LLM Pass1 técnico] --> [LLM Pass2 roteiro]
                          |
            [Edge-TTS / Piper / OpenRouter-TTS] --> [MP3] --> [player Streamlit]
```

- **Duas estratégias de retrieval (toggle na sidebar)**: vetorial híbrida — densa (Chroma +
  MiniLM, CPU) + esparsa (BM25), fusão RRF, re-rank desligável — ou vectorless, onde o LLM
  navega no sumário em árvore. Filtro por capítulo ou livro todo.
- **Geração 2-pass**: Pass1 fiel e denso com citações `[Cap X, p. Y]` (aceita LaTeX, render
  híbrido); Pass2 reescrito para fala (sem colchetes, siglas expandidas, termos EN preservados).
- **Personas**: `tecnico_direto` (voz Pedro/Antonio) e `iniciante_guiado` (voz Luana/Francisca,
  com parênteses explicativos) — ver `personas/*.yaml`.
- **TTS**: Edge-TTS grátis por padrão; toggle de voz premium via OpenRouter (MAI-Voice PT-BR,
  fatiamento + cache por fatia). Piper como fallback offline.
- **Cache agressivo**: texto em `cache/pass*.md`, seleções da árvore, áudio em `cache/audio/`.
  Repetir pergunta = instantâneo, sem gastar quota. Base do futuro modo offline.
- **Fallback de LLM**: chain configurável (Gemini → OpenRouter → erro legível); log `[llm-call]`
  e `[tts-call]` no terminal mostra provider, modelo e tamanhos de cada chamada.

## Quickstart

```bash
# 1. Ambiente
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Chaves (R$0: free tiers)
cp .env.example .env
# edite .env: GEMINI_API_KEY e/ou OPENROUTER_API_KEY (https://openrouter.ai/keys)

# 3. Coloque o PDF em data/generative-deep-learning.pdf e ingira (uma vez)
python ingest.py --pdf data/generative-deep-learning.pdf

# 4. Rode
streamlit run app.py
```

Uso na interface: escolha a **estratégia** (vetorial/vectorless) e digite a pergunta →
expanda **"Chunks recuperados"** para ver as fontes → abas **Pass1 / Pass2** para gerar
resumo e roteiro (botões independentes) → **Gerar áudio** na aba Pass2 (player + download
MP3; toggle de voz premium p/ MAI-Voice). No modo vetorial, perguntas em **inglês**
recuperam melhor (o livro é em EN; no vectorless o PT funciona); a resposta sai em PT-BR
de qualquer forma. Exemplos:
*What is ELBO in VAEs?* · *Explain GANs vs diffusion models* · *How does the diffusion schedule work?*

## Configuração (`.env`)

| Variável | Para quê | Default |
|---|---|---|
| `GEMINI_API_KEY` | LLM (free tier) | — |
| `GEMINI_MODEL` | Modelo Gemini (chaves novas: família 3.x) | `gemini-3.6-flash` |
| `OPENROUTER_API_KEY` | Fallback + testes sem quota Gemini (+ TTS premium) | — |
| `OPENROUTER_MODEL` | Modelo de texto (ex. `deepseek/...`, `qwen/...:free`) | `openrouter/free` |
| `OPENROUTER_TTS_MODEL` | Voz premium (ex. `microsoft/mai-voice-2.1`) | `microsoft/mai-voice-2.1` |
| `OPENROUTER_TTS_VOICE` | Sobrescreve a voz das personas (testes) | — (usa o YAML) |
| `LLM_PRIMARY` | Qual provider tenta primeiro (`gemini`/`openrouter`) | `gemini` |

Toggle **"Usar cache"** na sidebar: OFF ignora a leitura do cache (gera de novo via LLM/TTS)
para testes; a escrita continua para manter o cache aquecido.

## Estrutura

```
app.py             # UI Streamlit (só leitura: busca, 2-pass, player)
ingest.py          # ingestão one-shot: PDF -> Chroma + BM25 + macros (--help p/ opções)
src/retrieval.py   # RAGStore vetorial (híbrida+RRF), Reranker, retrieve()
src/retrieval_tree.py # TreeStore vectorless (LLM navega na árvore) — mesmo formato de saída
src/tree_index.py  # gera cache/tree_livro.json (L2→L3→L4 do TOC)
src/generate.py    # Pass1/Pass2, personas, cache por hash
src/llm_provider.py# Gemini / OpenRouter / opencode-subprocess + fallback chain
src/tts_provider.py# Edge-TTS + Piper + OpenRouter-TTS premium (fatiamento), cache MP3
src/prompts.py     # prompts 2-pass + glossário EN
src/markdown_math.py # render híbrido LaTeX (inline no markdown, bloco no st.latex)
personas/          # tecnico_direto.yaml, iniciante_guiado.yaml (tom + vozes Edge/premium)
scripts/           # golden.json (5 douradas) + eval_retrieval.py + fix_summaries.py
storage/           # Chroma + BM25 (gerado, não commitar)
cache/             # macros, árvore, pass1/pass2, seleções, MP3s (gerado, não commitar)
anotations/        # planos e notas locais de pesquisa (ignorado no git)
ARCHITECTURE.md    # decisões de design travadas | TASKS.md # progresso por sprint
```

## Custos e quotas

Base grátis: embeddings, re-rank e BM25 locais (CPU); Edge-TTS grátis. Gasto de API só em:
macros da ingestão (14 chamadas, 1x), Pass1/Pass2 + tree-search por pergunta nova. Quota
diária do Gemini free reseta 00:00 Pacific (04:00 BRT); se estourar, cai sozinho para o
OpenRouter. Com créditos OpenRouter (~centavos/áudio e frações de centavo/texto), dá para
fixar modelos pagos (`OPENROUTER_MODEL`, `OPENROUTER_TTS_MODEL`) e voz premium. Ruído
`torchvision` no log foi silenciado no `app.py`; pode ignorar.

## Roadmap

S5 (kit demo: perguntas douradas + MP3s pré-gerados + modo offline — base pronta:
`golden.json`, `eval_retrieval.py`, cache total), tradução da query p/ EN (só ramo vetorial),
chunking estrutural, MOS de áudio, VLM p/ figuras.
