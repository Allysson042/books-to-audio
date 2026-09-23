# Books to Audio — RAG + TTS para estudo

Case de seminário: **LLM para texto + TTS para áudio**, com RAG hierárquico sobre o livro
*Generative Deep Learning* (David Foster, O'Reilly). Você pergunta, o sistema recupera os
trechos do livro, gera um resumo técnico + um roteiro de áudio em **PT-BR** — e narra o
roteiro para você ouvir (5–8 min). Tudo com **custo R$0** (APIs free tier + modelos locais CPU).

## Como funciona

```
[PDF] --PyMuPDF--> [chunks (~800 tok) + resumos macro por capítulo]
                          |
                     [Chroma (vetor local) + BM25]
                          |
[pergunta + escopo + persona] --> [RRF top-20 -> re-rank MiniLM top-5]
                          |
[macro + micro + glossário + persona] --> [LLM Pass1 técnico] --> [LLM Pass2 roteiro]
                          |
                  [Edge-TTS / Piper] --> [MP3] --> [player Streamlit]
```

- **Retrieval híbrido**: busca densa (Chroma + MiniLM, CPU) + esparsa (BM25), fusão RRF,
  re-rank com cross-encoder local. Filtro por capítulo ou livro todo.
- **Geração 2-pass**: Pass1 fiel e denso com citações `[Cap X, p. Y]`; Pass2 reescrito para
  fala (sem colchetes, siglas expandidas, termos técnicos em EN preservados).
- **Personas**: `tecnico_direto` (voz Antonio) e `iniciante_guiado` (voz Francisca, com
  parênteses explicativos) — ver `personas/*.yaml`.
- **Cache agressivo**: texto em `cache/pass*.md`, áudio em `cache/audio/`. Repetir pergunta =
  instantâneo, sem gastar quota. Base do futuro modo offline.
- **Fallback de LLM**: Gemini (primário) → OpenRouter (modelos grátis) → erro legível.

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

Uso na interface: digite a pergunta → expanda **"Chunks recuperados"** para ver as fontes →
abas **Pass1 / Pass2** para gerar resumo e roteiro (botões independentes) → **Gerar áudio**
dentro da aba Pass2 (player + download MP3). Perguntas em **inglês** recuperam melhor
(o livro é em EN); a resposta sai em PT-BR de qualquer forma. Exemplos:
*What is ELBO in VAEs?* · *Explain GANs vs diffusion models* · *How does the diffusion schedule work?*

## Configuração (`.env`)

| Variável | Para quê | Default |
|---|---|---|
| `GEMINI_API_KEY` | LLM primário (free tier) | — |
| `GEMINI_MODEL` | Modelo Gemini (chaves novas: família 3.x) | `gemini-3.6-flash` |
| `OPENROUTER_API_KEY` | Fallback + testes sem quota Gemini | — |
| `OPENROUTER_MODEL` | Fixa um modelo grátis (ex. `qwen/...:free`); vazio = roteador `openrouter/free` | `openrouter/free` |
| `LLM_PRIMARY` | Qual provider tenta primeiro (`gemini`/`openrouter`) | `gemini` |

Toggle **"Usar cache"** na sidebar: OFF ignora a leitura do cache (gera de novo via LLM/TTS)
para testes; a escrita continua para manter o cache aquecido.

## Estrutura

```
app.py             # UI Streamlit (só leitura: busca, 2-pass, player)
ingest.py          # ingestão one-shot: PDF -> Chroma + BM25 + macros (--help p/ opções)
src/retrieval.py   # RAGStore (híbrida+RRF), Reranker, retrieve()
src/generate.py    # Pass1/Pass2, personas, cache por hash
src/llm_provider.py# Gemini / OpenRouter / opencode-subprocess + fallback chain
src/tts_provider.py# Edge-TTS + Piper fallback, cache MP3
src/prompts.py     # prompts 2-pass + glossário EN
personas/          # tecnico_direto.yaml, iniciante_guiado.yaml (tom + voz TTS)
storage/           # Chroma + BM25 (gerado, não commitar)
cache/             # macros, pass1/pass2, MP3s (gerado, não commitar)
anotations/        # notas locais de pesquisa (ignorado no git)
ARCHITECTURE.md    # decisões de design travadas | TASKS.md # progresso por sprint
```

## Custos e quotas (R$0)

Embeddings, re-rank e BM25 rodam locais (CPU). Gasto de API só em: macros da ingestão
(14 chamadas, 1x), Pass1/Pass2 por pergunta nova e TTS (Edge, grátis). Quota diária do
Gemini free reseta 00:00 Pacific (04:00 BRT); se estourar, o sistema cai sozinho para o
OpenRouter. Ruído `torchvision` no log do Streamlit é inofensivo (file-watcher); pode ignorar.

## Roadmap

S5 (kit demo: perguntas douradas + MP3s pré-gerados + modo offline), otimização do retrieval
(tradução da query p/ EN, medição de hit-rate) e 2ª estratégia vectorless estilo PageIndex
(ver `anotations/`).
