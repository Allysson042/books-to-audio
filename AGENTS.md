# Books to Audio — AGENTS.md (escopo: só este projeto)

Este arquivo é lido automaticamente pelo OpenCode em toda sessão aberta neste diretório.
Nada aqui afeta `~/.config/opencode/` (global). Tudo é local ao projeto.

## O que é
RAG hierárquico + TTS sobre o livro "Generative Deep Learning" (PDF único).
Case de seminário: LLM para texto + TTS para áudio. Saída em PT-BR, termos EN preservados.
Stack: Python + Streamlit + Chroma local + sentence-transformers CPU + BM25 + Edge-TTS/Piper.
Custo R$0. Ver `ARCHITECTURE.md` para decisões travadas (fonte de verdade de design).

## Estrutura
- `app.py` — UI Streamlit (chat + escopo + persona + player). Só leitura.
- `ingest.py` — ingestão one-shot do PDF → Chroma + BM25 + macros.
- `src/llm_provider.py` — abstração LLM (Gemini free primário, fallback Groq/OpenRouter/Ollama, opencode-subprocess experimental).
- `src/tts_provider.py` — Edge-TTS primário + Piper fallback, cache em `cache/audio/`.
- `src/prompts.py` — prompts 2-pass + glossário.
- `personas/*.yaml` — `tecnico_direto`, `iniciante_guiado`.
- `ARCHITECTURE.md` — design travado. `TASKS.md` — progresso (atualizar sempre).
- `data/` — PDF de entrada (não commitar). `storage/chroma/` — vetores. `cache/` — resumos + MP3.

## Comandos
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python ingest.py --pdf data/generative-deep-learning.pdf
streamlit run app.py
```

## Convenções para agentes
- Ler `ARCHITECTURE.md` + `TASKS.md` no início de toda sessão.
- Nunca tocar em `~/.config/opencode/`. Só arquivos deste repo.
- Manter R$0 / CPU 8-16GB: sem dependência paga, sem Docker obrigatório.
- Todo resumo/roteiro deve citar `[Cap X, p. Y]` no texto; roteiro TTS remove colchetes na fala.
- Preservar termos do glossário em EN (`src/prompts.py`).
- 2-pass com cache: não regenerar LLM/TTS se cache existir.
- Ao terminar uma etapa, marcar `[x]` em `TASKS.md` e sugerir próximo passo S0→S5.
- Não commitar `.env`, `*.pdf`, `storage/`, `cache/`, `venv/`.
