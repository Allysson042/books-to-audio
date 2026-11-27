"""V2 — chunks alinhados à seção do TOC em store separado (sem LLM, sem reembed).

Uso:
    venv/bin/python scripts/build_tree_chunks.py
    venv/bin/python scripts/build_tree_chunks.py --chapters 4 --chunk-words 600
    venv/bin/python scripts/build_tree_chunks.py --out storage/tree_chunks.jsonl

Por que existe (`docs/LIMITS.md` §11): o chunking do `ingest.py` é uma janela de
600 palavras sobre o **capítulo inteiro**, então um chunk atravessa 2-6 seções e
metade do contexto entregue pelo vectorless vem de seção vizinha (`in_scope` mediano
40%). Aqui a mesma extração é reaproveitada, mas a janela roda **dentro de cada grupo
de páginas consecutivas da mesma seção do TOC** — o chunk nunca cruza seção.

Regras:
  - Reusa `ingest.load_chapters/build_section_index/section_for_page/clean_page_text/
    classify_chunk/BOOK_PAGE_OFFSET` (mesmo texto, mesmo descarte de páginas <100 chars).
  - Grupo com <50 palavras funde com o **próximo** (o último do capítulo funde com o
    anterior); o label da seção passa a ser o do grupo absorvedor.
  - Janela `--chunk-words`/`--overlap-words` por grupo, rastreando página por palavra.
    O rabo (<50 palavras) é absorvido pelo último chunk do grupo (cobertura total).
  - `doc_id = t{chapter:02d}_p{pdf_start:03d}-{pdf_end:03d}_{idx:03d}` (prefixo `t`
    evita colisão com `bm25.jsonl`).
  - Chroma, `storage/bm25.pkl`/`bm25.jsonl` e `cache/tree_livro.json` **intactos**.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ingest  # noqa: E402  (reuso da extração; PyMuPDF só no main)

MIN_GROUP_WORDS = 50


def build_groups(pages: list[tuple[int, str, str]]) -> tuple[list[dict], int]:
    """Agrupa páginas consecutivas pela mesma seção e funde grupos minúsculos.

    Retorna (grupos, nº de grupos fundidos). Cada grupo:
    {section, pages: [(pdf_page, text)], words}.
    """
    groups: list[dict] = []
    for pdf_page, section, text in pages:
        nwords = len(text.split())
        if groups and groups[-1]["section"] == section:
            groups[-1]["pages"].append((pdf_page, text))
            groups[-1]["words"] += nwords
        else:
            groups.append({"section": section, "pages": [(pdf_page, text)], "words": nwords})

    merged = 0
    i = 0
    while len(groups) > 1 and i < len(groups):
        g = groups[i]
        if g["words"] >= MIN_GROUP_WORDS:
            i += 1
            continue
        if i == len(groups) - 1:  # último do capítulo: funde com o anterior
            prev = groups[i - 1]
            prev["pages"].extend(g["pages"])
            prev["words"] += g["words"]
            del groups[i]
            i = max(0, i - 1)
        else:  # funde com o próximo; label = seção do absorvedor
            nxt = groups[i + 1]
            nxt["pages"] = g["pages"] + nxt["pages"]
            nxt["words"] += g["words"]
            del groups[i]
        merged += 1

    # segurança: absorção pode deixar vizinhos com o mesmo label
    collapsed: list[dict] = []
    for g in groups:
        if collapsed and collapsed[-1]["section"] == g["section"]:
            collapsed[-1]["pages"].extend(g["pages"])
            collapsed[-1]["words"] += g["words"]
            merged += 1
        else:
            collapsed.append(g)
    return collapsed, merged


def chunk_group(chapter: int, group: dict, group_uid: int, idx: int,
                chunk_words: int, overlap_words: int) -> list[tuple[dict, dict]]:
    """Janela deslizante dentro do grupo. Retorna [(chunk, origem_p/ validação)]."""
    items: list[tuple[str, int]] = []  # (palavra, pdf_page)
    for pdf_page, text in group["pages"]:
        for w in text.split():
            items.append((w, pdf_page))
    step = max(1, chunk_words - overlap_words)
    windows: list[tuple[int, int]] = []  # (start, end) no array `items`
    start = 0
    while start < len(items):
        end = min(start + chunk_words, len(items))
        if windows and (end - start) < MIN_GROUP_WORDS and end == len(items):
            windows[-1] = (windows[-1][0], end)  # rabo absorvido: não perde texto
            break
        windows.append((start, end))
        if end >= len(items):
            break
        start += step

    pages = [p for p, _ in group["pages"]]
    origin = {"group_uid": group_uid, "group_min": min(pages), "group_max": max(pages),
              "section": group["section"], "words": len(items)}
    chunks: list[tuple[dict, dict]] = []
    for w_start, w_end in windows:
        win = items[w_start:w_end]
        if not win:
            continue
        span = [p for _, p in win]
        text = " ".join(w for w, _ in win)
        pdf_start, pdf_end = min(span), max(span)
        chunks.append(({
            "doc_id": f"t{chapter:02d}_p{pdf_start:03d}-{pdf_end:03d}_{idx:03d}",
            "text": text,
            "chapter": chapter,
            "section": group["section"],
            "page_start": pdf_start,
            "page_end": pdf_end,
            "book_page_start": pdf_start - ingest.BOOK_PAGE_OFFSET,
            "book_page_end": pdf_end - ingest.BOOK_PAGE_OFFSET,
            "type": ingest.classify_chunk(text),
        }, {**origin, "word_span": (w_start, w_end)}))
        idx += 1
    return chunks


def validate(store: list[tuple[dict, dict]]) -> tuple[bool, list[str], dict[int, dict]]:
    """(a) páginas dentro do grupo; (b) chunk não cruza grupo/seção; (c) cobertura."""
    problems: list[str] = []
    seen: set[str] = set()
    group_words: dict[tuple[int, int], int] = {}
    group_spans: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for chunk, origin in store:
        if chunk["doc_id"] in seen:
            problems.append(f"doc_id duplicado: {chunk['doc_id']}")
        seen.add(chunk["doc_id"])
        if not (origin["group_min"] <= chunk["page_start"] <= chunk["page_end"]
                <= origin["group_max"]):
            problems.append(f"{chunk['doc_id']}: páginas {chunk['page_start']}-"
                            f"{chunk['page_end']} fora do grupo "
                            f"{origin['group_min']}-{origin['group_max']}")
        if chunk["section"] != origin["section"]:
            problems.append(f"{chunk['doc_id']}: seção {chunk['section']!r} != grupo "
                            f"{origin['section']!r}")
        key = (chunk["chapter"], origin["group_uid"])
        group_words[key] = origin["words"]
        group_spans.setdefault(key, []).append(origin["word_span"])

    by_chapter: dict[int, dict] = {}
    chunk_words: dict[int, int] = {}
    for chunk, _origin in store:
        chunk_words[chunk["chapter"]] = chunk_words.get(chunk["chapter"], 0) + \
            len(chunk["text"].split())

    for (chapter, _uid) in group_words:
        info = by_chapter.setdefault(chapter, {"total_n": 0, "covered_n": 0, "words": 0})
    for (chapter, uid), total in group_words.items():
        idxs: set[int] = set()
        for a, b in group_spans[(chapter, uid)]:
            idxs.update(range(a, b))
        info = by_chapter[chapter]
        info["total_n"] += total
        info["covered_n"] += min(len(idxs), total)
    for chapter, info in by_chapter.items():
        info["words"] = chunk_words.get(chapter, 0)
        loss = (info["total_n"] - info["covered_n"]) / info["total_n"] \
            if info["total_n"] else 0.0
        if loss > 0.05:
            problems.append(f"cap {chapter:02d}: cobertura {info['covered_n']}/"
                            f"{info['total_n']} palavras (perda {loss:.1%} > 5%)")
    return (not problems), problems, by_chapter


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V2: chunks por seção do TOC (sem LLM).")
    ap.add_argument("--pdf", default="data/generative-deep-learning.pdf")
    ap.add_argument("--out", default="storage/tree_chunks.jsonl")
    ap.add_argument("--chapters", default="all", help="'all' ou '4' ou '1,2,3'")
    ap.add_argument("--chunk-words", type=int, default=600)
    ap.add_argument("--overlap-words", type=int, default=90)
    args = ap.parse_args(argv)

    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("PyMuPDF ausente: pip install -r requirements.txt", file=sys.stderr)
        return 1
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"PDF não encontrado: {pdf_path}", file=sys.stderr)
        return 1
    if args.chunk_words <= args.overlap_words:
        print("--chunk-words precisa ser maior que --overlap-words", file=sys.stderr)
        return 1

    wanted: set[int] | None = None
    if args.chapters.strip().lower() != "all":
        wanted = {int(x) for x in args.chapters.split(",") if x.strip()}

    doc = fitz.open(str(pdf_path))
    chapters = ingest.load_chapters(doc)
    if wanted:
        chapters = [c for c in chapters if c["chapter"] in wanted]
    if not chapters:
        print("Nenhum capítulo selecionado.", file=sys.stderr)
        return 1
    sec_index = ingest.build_section_index(doc)
    print(f"PDF: {len(doc)} págs | capítulos: {[c['chapter'] for c in chapters]} | "
          f"janela {args.chunk_words}/{args.overlap_words} palavras")

    store: list[tuple[dict, dict]] = []
    for ch in chapters:
        n = ch["chapter"]
        pages: list[tuple[int, str, str]] = []
        for pdf_page in range(ch["pdf_start"], ch["pdf_end"] + 1):
            raw = doc[pdf_page - 1].get_text("text")
            text = ingest.clean_page_text(raw, chapter_num=n, chapter_title=ch["title"])
            if len(text) < 100:  # mesma regra do ingest.main()
                continue
            pages.append((pdf_page, ingest.section_for_page(sec_index, pdf_page, ch["title"]),
                          text))
        if not pages:
            print(f"Cap {n:02d}: nenhuma página de texto.")
            continue
        groups, merged = build_groups(pages)
        idx = 0
        chapter_chunks: list[dict] = []
        for uid, group in enumerate(groups):
            built = chunk_group(n, group, uid, idx, args.chunk_words, args.overlap_words)
            idx += len(built)
            store.extend(built)
            chapter_chunks.extend(c for c, _o in built)
        n_code = sum(1 for c in chapter_chunks if c["type"] == "code")
        print(f"Cap {n:02d} {ch['title'][:40]:40s} pdf pp.{ch['pdf_start']}-{ch['pdf_end']} "
              f"| {len(pages)} págs | {len(groups)} grupos ({merged} fundidos) "
              f"| {len(chapter_chunks)} chunks ({n_code} code)")

    if not store:
        print("Nada extraído.", file=sys.stderr)
        return 1

    store.sort(key=lambda item: (item[0]["chapter"], item[0]["page_start"], item[0]["doc_id"]))
    out_path = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for chunk, _origin in store:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    chunks = [c for c, _ in store]
    print(f"Total: {len(chunks)} chunks -> {out_path} "
          f"({sum(len(c['text'].split()) for c in chunks)} palavras)")

    ok, problems, by_chapter = validate(store)
    for ch in sorted(by_chapter):
        info = by_chapter[ch]
        print(f"  cap {ch}: páginas {info['total_n']} palavras | cobertura "
              f"{info['covered_n']} ({info['covered_n'] / info['total_n']:.1%}) | "
              f"chunks {info['words']} palavras (overlap repetido)")
    if not ok:
        print("FALHOU validação:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 2
    print(f"OK: invariantes válidas (chunk dentro do grupo/seção, cobertura >=95%) — "
          f"{len(chunks)} chunks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
