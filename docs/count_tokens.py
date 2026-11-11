"""Estimativa de tokens do livro (análise local, artefato de pesquisa em docs/).

Conta com tiktoken cl100k_base (referência GPT; Gemini usa outra tokenização,
mas a ordem de grandeza é a mesma) sobre o texto extraído via PyMuPDF,
e compara com janelas de contexto longas (estratégia tipo NotebookLM).

Requer tiktoken (NÃO está no requirements.txt; instale avulso: pip install tiktoken).
Uso: venv/bin/python docs/count_tokens.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz
import tiktoken

import ingest

PDF = Path("data/generative-deep-learning.pdf")
enc = tiktoken.get_encoding("cl100k_base")

doc = fitz.open(str(PDF))
chapters = ingest.load_chapters(doc)
print(f"{'cap':>4} {'págs':>6} {'chars':>10} {'tokens':>10}  título")
total = 0
for ch in chapters:
    texts = []
    for p in range(ch["pdf_start"], ch["pdf_end"] + 1):
        t = ingest.clean_page_text(doc[p - 1].get_text("text"))
        if len(t) >= 100:
            texts.append(t)
    toks = len(enc.encode(" ".join(texts)))
    total += toks
    print(f"{ch['chapter']:>4} {ch['pdf_end']-ch['pdf_start']+1:>6} "
          f"{sum(map(len, texts)):>10} {toks:>10}  {ch['title'][:40]}")

print(f"\nTotal livro (14 caps): ~{total:,} tokens")
for ctx, nome in [(128_000, "GPT-4o (128k)"), (1_000_000, "Gemini 1M"),
                  (2_000_000, "NotebookLM-like 2M")]:
    cabe = "SIM " if total < ctx else "NÃO "
    print(f"Cabe em {nome}? {cabe} ({total/ctx:.0%} da janela)")
print("\nNota: RAG segue valendo — janela grande custa por query e o livro cresce; "
      "aqui o livro inteiro (~ordem de centenas de k tokens) ainda é confortável p/ 1M+.")
