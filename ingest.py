"""Ingestão one-shot S1: PDF -> chunks hierárquicos + Chroma + BM25 + macros.

Uso:
    python ingest.py --pdf data/generative-deep-learning.pdf
    python ingest.py --pdf data/generative-deep-learning.pdf --chapters 4   # só Cap 4 (teste rápido)
    python ingest.py --chapters 1,2 --skip-llm                              # sem gastar quota Gemini
    python ingest.py --force                                                # reingere tudo do zero

Pipeline (Ramo 1 do ARCHITECTURE.md):
  [PDF] --PyMuPDF--> [chunks (Livro > Capítulo > Seção > Chunk) + metadata]
      --> [Chroma persistente ./storage/chroma + dump BM25 ./storage/bm25.pkl]
      --> [mapa_livro.json + resumo_macro_{cap}.md em ./cache (1x via LLM, com cache)]

Convenções:
  - Chunks ~800 tokens com overlap 120. Aproximação CPU sem tokenizer externo:
    1 token ~= 1.3 palavra  =>  CHUNK_WORDS=600 (~800 tok), OVERLAP_WORDS=90 (~120 tok).
  - Metadata obrigatória: chapter, section, page_start, page_end, type, doc_id.
    page_* = nº da página do PDF (1-indexed, estável p/ reabrir o arquivo);
    book_page_* = nº impresso no livro (pdf - BOOK_PAGE_OFFSET), usado nas citações [Cap X, p. Y].
  - Extrai texto + blocos de código ("Example N-M") + legendas ("Figure/Table N-M" vêm no
    fluxo de texto). Pixels das figuras são ignorados no MVP (VLM fica p/ futuro).
  - 2-pass com cache: nunca chama o LLM se o .md do capítulo já existir (a menos que --force).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import re
import sys
from collections import Counter
from pathlib import Path

# ~800 tokens / overlap 120 (ver docstring p/ conversão palavra->token)
CHUNK_WORDS = 600
OVERLAP_WORDS = 90
# Nº impresso = nº do PDF - offset (verificado: PDF p31 = livro p3, p51 = p23, ...)
BOOK_PAGE_OFFSET = 28
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHROMA_COLLECTION = "books"
MACRO_CHARS = 12_000  # quanto do início do capítulo vai ao prompt do resumo macro

RE_CHAPTER = re.compile(r"Chapter\s+(\d+)\s*\.\s*(.+)", re.DOTALL)
RE_CODE_MARK = re.compile(r"Example\s+\d+\s*-\s*\d+", re.IGNORECASE)
RE_CODE_HINT = re.compile(r"(^\s*(import|from|def |class |for |if |return|bash )|\blayers\.|\(\)|=>|```)", re.MULTILINE)
RE_CAPTION = re.compile(r"^(Figure|Table)\s+\d+\s*-\s*\d+\.", re.MULTILINE)


# ---------------------------------------------------------------- TOC / capítulos

def load_chapters(doc) -> list[dict]:
    """Limites de capítulos a partir do TOC embutido: [{chapter, title, pdf_start, pdf_end}]."""
    toc = doc.get_toc()  # [(level, title, pageno1), ...] pageno 1-indexed == nº PDF
    starts: list[tuple[int, str, int]] = []
    for level, title, pageno in toc:
        if level == 2:
            m = RE_CHAPTER.match(" ".join(title.split()))
            if m:
                starts.append((int(m.group(1)), " ".join(m.group(2).split()), pageno))
    starts.sort(key=lambda c: c[2])
    # fim do último capítulo = página anterior ao Índice (ou fim do PDF)
    index_start = next((p for lvl, t, p in toc if lvl == 1 and t.strip() == "Index"), len(doc) + 1)
    chapters = []
    for i, (num, title, start) in enumerate(starts):
        end = (starts[i + 1][2] - 1) if i + 1 < len(starts) else (index_start - 1)
        chapters.append({"chapter": num, "title": title, "pdf_start": start, "pdf_end": end})
    return chapters


def build_section_index(doc) -> list[tuple[int, str]]:
    """Índice ordenado (pdf_pageno, section_title) com entradas L3/L4 do TOC."""
    idx: list[tuple[int, str]] = []
    for level, title, pageno in doc.get_toc():
        if level >= 3:
            clean = " ".join(title.split())
            if clean:
                idx.append((pageno, clean))
    idx.sort()
    return idx


def section_for_page(sec_index: list[tuple[int, str]], pdf_page: int, fallback: str) -> str:
    current = fallback
    for pageno, title in sec_index:
        if pageno <= pdf_page:
            current = title
        else:
            break
    return current


# ---------------------------------------------------------------- extração / limpeza

def clean_page_text(raw: str, chapter_num: int | None = None,
                      chapter_title: str | None = None) -> str:
    """Des-hifeniza quebras de linha e normaliza espaços; mantém Example/Figure/Table no fluxo."""
    text = raw.replace("\u00ad", "")  # soft hyphen
    if chapter_num and chapter_title:
        # cabeçalho corrente O'Reilly no meio da frase ("...generative 4 | Chapter 1: Generative Modeling model...")
        text = re.sub(rf"\s*\d{{1,3}}\s*\|\s*Chapter\s+{chapter_num}\s*:\s*{re.escape(chapter_title)}\s*",
                      " ", text)
    text = re.sub(r"[‐‑‒–—-]\n", "", text)  # hifenização de fim de linha ("gov‐\nern" -> "govern")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+(\d{1,3})\s*$", "", text)  # nº de página impresso no rodapé
    return text


def classify_chunk(text: str) -> str:
    if RE_CODE_MARK.search(text) and RE_CODE_HINT.search(text):
        return "code"
    return "text"


def chunk_chapter(chapter: int, pages: list[tuple[int, str, str]]) -> list[dict]:
    """Janela deslizante sobre palavras com rastreio de página.

    pages: [(pdf_page, section, clean_text)]. Retorna chunks com metadata completa.
    """
    words: list[str] = []
    word_pages: list[int] = []
    word_sections: list[str] = []
    for pdf_page, section, text in pages:
        for w in text.split():
            words.append(w)
            word_pages.append(pdf_page)
            word_sections.append(section)
    chunks: list[dict] = []
    step = CHUNK_WORDS - OVERLAP_WORDS
    idx = 0
    for start in range(0, len(words), step):
        window = words[start:start + CHUNK_WORDS]
        if len(window) < 50:  # rabo insignificante
            break
        span_pages = word_pages[start:start + len(window)]
        span_sections = word_sections[start:start + len(window)]
        pdf_start, pdf_end = min(span_pages), max(span_pages)
        section = Counter(span_sections).most_common(1)[0][0]
        text = " ".join(window)
        doc_id = f"ch{chapter:02d}_p{pdf_start:03d}-{pdf_end:03d}_{idx:04d}"
        chunks.append({
            "doc_id": doc_id,
            "text": text,
            "chapter": chapter,
            "section": section,
            "page_start": pdf_start,
            "page_end": pdf_end,
            "book_page_start": pdf_start - BOOK_PAGE_OFFSET,
            "book_page_end": pdf_end - BOOK_PAGE_OFFSET,
            "type": classify_chunk(text),
        })
        idx += 1
        if start + CHUNK_WORDS >= len(words):
            break
    return chunks


# ---------------------------------------------------------------- Chroma + BM25

def persist_chroma(chunks: list[dict], storage_dir: Path, embedding_model: str,
                   force: bool = False) -> int:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    storage_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(storage_dir))
    if force:
        try:
            client.delete_collection(CHROMA_COLLECTION)
        except Exception:
            pass
    ef = SentenceTransformerEmbeddingFunction(model_name=embedding_model, device="cpu")
    col = client.get_or_create_collection(name=CHROMA_COLLECTION, embedding_function=ef)
    existing: set[str] = set()
    try:
        existing = set(col.get(include=[])["ids"])
    except Exception:
        pass
    fresh = [c for c in chunks if c["doc_id"] not in existing]
    if not fresh:
        return 0
    batch = 100
    for i in range(0, len(fresh), batch):
        part = fresh[i:i + batch]
        col.upsert(
            ids=[c["doc_id"] for c in part],
            documents=[c["text"] for c in part],
            metadatas=[{k: c[k] for k in
                        ("chapter", "section", "page_start", "page_end",
                         "book_page_start", "book_page_end", "type", "doc_id")} for c in part],
        )
    return len(fresh)


def dump_bm25(chunks: list[dict], out_path: Path) -> None:
    from rank_bm25 import BM25Okapi

    tokenized = [c["text"].lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        pickle.dump({
            "doc_ids": [c["doc_id"] for c in chunks],
            "tokens": tokenized,
            "metadatas": [{k: c[k] for k in
                           ("chapter", "section", "page_start", "page_end",
                            "book_page_start", "book_page_end", "type", "doc_id")} for c in chunks],
            "bm25": bm25,  # rank-bm25 é picklável; S2 pode reusar sem retokenizar
        }, f)
    # docstore legível p/ debug e p/ S2 (painel Streamlit)
    with open(out_path.with_suffix(".jsonl"), "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- macros via LLM (1x, com cache)

MACRO_SYSTEM = (
    "Você é tutor de mestrado sobre o livro Generative Deep Learning. "
    "Responda em PT-BR, preserve termos técnicos em EN (GAN, VAE, diffusion model, "
    "ELBO, latent space, Transformer, token, training loop, checkpoint). "
    "Cite fontes como [Cap X, p. Y] usando as páginas do livro informadas."
)

MACRO_USER_TPL = (
    "Capítulo {chapter} — {title} (livro pp. {bstart}-{bend}). "
    "Abaixo o início do capítulo (amostra, pode estar truncado):\n\n{sample}\n\n"
    "Tarefa em PT-BR:\n"
    "1) RESUMO2LINHAS: exatamente 2 linhas descrevendo o capítulo (p/ o mapa do livro).\n"
    "2) MACRO: resumo estruturado em markdown com: ## Ideias-chave (3-5 bullets), "
    "## Conceitos, ## Exemplos de código/figuras mencionados, ## Pré-requisitos. "
    "Fiel ao texto, denso, com citações [Cap {chapter}, p. Y]."
)


def parse_macro_output(raw: str) -> tuple[str, str]:
    """Separa RESUMO2LINHAS do MACRO; tolera marcadores markdown (**..**, ###, com/sem ':')."""
    text = re.sub(r"(?m)^\s*(#{1,4}\s*)?\*{0,2}\s*RESUMO\s*2\s*LINHAS\s*\*{0,2}\s*:?\s*$",
                  "RESUMO2LINHAS:", text := raw.strip(), count=1)
    text = re.sub(r"(?m)^\s*(#{1,4}\s*)?\*{0,2}\s*MACRO\s*\*{0,2}\s*:?\s*$", "---MACRO---", text)
    m = re.search(r"RESUMO2LINHAS\s*:\s*(.+?)(?:\n\s*\n|---MACRO---)", text, re.DOTALL | re.IGNORECASE)
    if m:
        two = " ".join(m.group(1).split())
        macro = text[m.end():].replace("---MACRO---", "").strip() or text.strip()
        return two[:400], macro
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " ".join(lines[:2])[:400], text


def heuristic_macro(chapter: int, title: str, full_text: str) -> tuple[str, str]:
    sents = re.split(r"(?<=[.!?])\s+", full_text.strip())
    intro = " ".join(sents[:4])[:900]
    two = f"{title}: {intro[:300]}{'...' if len(intro) > 300 else ''}"
    macro = (
        f"# Cap {chapter} — {title} (rascunho extrativo — LLM indisponível)\n\n"
        f"> Gerado sem LLM (--skip-llm ou falha de API). Re rode sem a flag p/ o resumo fiel.\n\n"
        f"## Amostra do início\n\n{intro}\n"
    )
    return two, macro


def ensure_macros(chapters: list[dict], chapter_texts: dict[int, str],
                  cache_dir: Path, skip_llm: bool, force: bool,
                  model: str) -> dict[int, dict]:
    """Gera (ou reusa do cache) resumo_macro por capítulo. Retorna info p/ o mapa."""
    from dotenv import load_dotenv
    load_dotenv()
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Chain com fallback (Gemini -> OpenRouter -> ...): macros não dependem de 1 provider.
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    try:
        from llm_provider import build_chain  # type: ignore
        chain = build_chain()
        if not chain:
            print("[macros] Nenhum provider com key no .env; usando heurística.", file=sys.stderr)
            chain = None
    except Exception as e:
        print(f"[macros] Chain indisponível ({e}); usando heurística.", file=sys.stderr)
        chain = None
    infos: dict[int, dict] = {}

    for ch in chapters:
        n = ch["chapter"]
        md_path = cache_dir / f"resumo_macro_cap{n:02d}.md"
        if md_path.exists() and not force:
            macro = md_path.read_text(encoding="utf-8")
            two = macro.splitlines()[0][:400] if macro else ch["title"]
            infos[n] = {"summary_2lines": two, "macro_file": md_path.name}
            continue
        full = chapter_texts.get(n, "")
        if chain and not skip_llm and full.strip():
            from llm_provider import complete_with_fallback  # type: ignore
            sample = full[:MACRO_CHARS]
            raw = None
            for attempt in range(1, 4):
                try:
                    raw, _prov = complete_with_fallback(
                        MACRO_SYSTEM,
                        MACRO_USER_TPL.format(chapter=n, title=ch["title"],
                                              bstart=ch["pdf_start"] - BOOK_PAGE_OFFSET,
                                              bend=ch["pdf_end"] - BOOK_PAGE_OFFSET,
                                              sample=sample),
                        max_tokens=1500, chain=chain)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < 3:
                        wait = 45 * attempt
                        print(f"[macros] Cap {n}: quota (429), retry em {wait}s "
                              f"(tentativa {attempt}/3)...", file=sys.stderr)
                        import time
                        time.sleep(wait)
                    else:
                        print(f"[macros] Cap {n}: LLM falhou ({str(e)[-200:]}); heurística.",
                              file=sys.stderr)
                        break
            if raw is not None:
                two, macro = parse_macro_output(raw)
            else:
                two, macro = heuristic_macro(n, ch["title"], full)
        else:
            two, macro = heuristic_macro(n, ch["title"], full)
        md_path.write_text(macro, encoding="utf-8")
        infos[n] = {"summary_2lines": two, "macro_file": md_path.name}
    return infos


# ---------------------------------------------------------------- main

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Ingestão S1: PDF -> Chroma + BM25 + macros.")
    p.add_argument("--pdf", default="data/generative-deep-learning.pdf")
    p.add_argument("--chapters", default="all",
                   help="'all' ou lista como '4' ou '1,2,3' (padrão: all)")
    p.add_argument("--storage", default="storage/chroma")
    p.add_argument("--bm25", default="storage/bm25.pkl")
    p.add_argument("--cache", default="cache")
    p.add_argument("--embedding-model", default=EMBEDDING_MODEL)
    p.add_argument("--llm-model", default=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"))
    p.add_argument("--skip-llm", action="store_true", help="não chama Gemini; macros heurísticas")
    p.add_argument("--force", action="store_true", help="reingere e regenera macros mesmo com cache")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    import fitz  # PyMuPDF (import tardio p/ --help funcionar sem deps)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"PDF não encontrado: {pdf_path}", file=sys.stderr)
        return 1
    wanted: set[int] | None = None
    if args.chapters.strip().lower() != "all":
        wanted = {int(x) for x in args.chapters.split(",") if x.strip()}

    doc = fitz.open(str(pdf_path))
    chapters = load_chapters(doc)
    if wanted:
        chapters = [c for c in chapters if c["chapter"] in wanted]
    if not chapters:
        print("Nenhum capítulo selecionado.", file=sys.stderr)
        return 1
    sec_index = build_section_index(doc)
    print(f"PDF: {len(doc)} págs | capítulos: {[c['chapter'] for c in chapters]}")

    all_chunks: list[dict] = []
    chapter_texts: dict[int, str] = {}
    for ch in chapters:
        n = ch["chapter"]
        pages: list[tuple[int, str, str]] = []
        for pdf_page in range(ch["pdf_start"], ch["pdf_end"] + 1):
            raw = doc[pdf_page - 1].get_text("text")
            text = clean_page_text(raw, chapter_num=n, chapter_title=ch["title"])
            if len(text) < 100:  # página de figura/título sem texto — pixels ignorados (MVP)
                continue
            pages.append((pdf_page, section_for_page(sec_index, pdf_page, ch["title"]), text))
        full = " ".join(t for _, _, t in pages)
        chapter_texts[n] = full
        chunks = chunk_chapter(n, pages)
        all_chunks.extend(chunks)
        n_code = sum(1 for c in chunks if c["type"] == "code")
        print(f"Cap {n:02d} {ch['title'][:45]:45s} pdf pp.{ch['pdf_start']}-{ch['pdf_end']} "
              f"| {len(pages)} págs texto | {len(chunks)} chunks ({n_code} code)")

    if not all_chunks:
        print("Nada extraído.", file=sys.stderr)
        return 1

    added = persist_chroma(all_chunks, Path(args.storage), args.embedding_model,
                           force=args.force)
    print(f"Chroma: +{added} novos ({len(all_chunks)} chunks processados) -> {args.storage}")
    dump_bm25(all_chunks, Path(args.bm25))
    print(f"BM25: dump -> {args.bm25} (+ .jsonl docstore)")

    infos = ensure_macros(chapters, chapter_texts, Path(args.cache),
                          skip_llm=args.skip_llm, force=args.force, model=args.llm_model)
    mapa = {
        "title": "Generative Deep Learning",
        "source_pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "book_page_offset": BOOK_PAGE_OFFSET,
        "chunking": {"words": CHUNK_WORDS, "overlap_words": OVERLAP_WORDS,
                     "approx": "~800 tokens / overlap 120"},
        "embedding_model": args.embedding_model,
        "chapters": [{**ch,
                      "book_start": ch["pdf_start"] - BOOK_PAGE_OFFSET,
                      "book_end": ch["pdf_end"] - BOOK_PAGE_OFFSET,
                      **infos[ch["chapter"]]} for ch in chapters],
    }
    mapa_path = Path(args.cache) / "mapa_livro.json"
    # merge com mapa existente (ingestões parciais por --chapters)
    if mapa_path.exists() and not args.force:
        try:
            prev = json.loads(mapa_path.read_text(encoding="utf-8"))
            by_ch = {c["chapter"]: c for c in prev.get("chapters", [])}
            for c in mapa["chapters"]:
                by_ch[c["chapter"]] = c
            mapa["chapters"] = [by_ch[k] for k in sorted(by_ch)]
        except Exception:
            pass
    mapa_path.write_text(json.dumps(mapa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Macros: {len(infos)} cap(s) -> {args.cache}/resumo_macro_capNN.md + mapa_livro.json")
    print(f"OK: {len(all_chunks)} chunks | {len(chapters)} capítulo(s). Próximo: S2 retrieval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
