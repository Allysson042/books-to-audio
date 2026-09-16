# Books to Audio — RAG + TTS para estudo (Generative Deep Learning)

Case prático de IA Generativa: LLM para texto + TTS para áudio, com RAG hierárquico sobre um único livro.

## Quickstart (MVP grátis, CPU 8-16GB)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # colocar GEMINI_API_KEY (free tier)
# 1. colocar o PDF em data/generative-deep-learning.pdf
python ingest.py --pdf data/generative-deep-learning.pdf
streamlit run app.py
```

## Fluxo

`PDF (PyMuPDF) -> chunks hierárquicos + resumos macro -> Chroma (vetor local) + BM25 -> fusão RRF -> re-rank MiniLM -> 2-pass LLM (técnico -> roteiro TTS) -> Edge-TTS / Piper -> MP3 cacheado`

Ver `ARCHITECTURE.md` para blueprint completo travado no grill-me.
