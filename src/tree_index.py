"""Índice em árvore (estilo PageIndex, sem vetores) a partir do TOC + macros.

Gera 1x `cache/tree_livro.json`:
  livro -> capítulos (título, range de páginas, summary do mapa) -> seções (título, range).
Nenhum LLM aqui: estrutura vem do TOC embutido (grátis), resumos já existem (macros S1).
Uso: python -m src.tree_index  (ou importado por src/retrieval_tree.py, que gera se ausente)
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
TREE_PATH = CACHE / "tree_livro.json"


def build_tree() -> dict:
    mapa = json.loads((CACHE / "mapa_livro.json").read_text(encoding="utf-8"))
    chunks = [json.loads(line) for line in
              (ROOT / "storage" / "bm25.jsonl").read_text(encoding="utf-8").splitlines()]
    by_chapter: dict[int, OrderedDict[str, dict]] = {}
    for c in chunks:
        ch = c["chapter"]
        sec = by_chapter.setdefault(ch, OrderedDict()).setdefault(
            c["section"], {"pdf_start": 10**9, "pdf_end": -1})
        sec["pdf_start"] = min(sec["pdf_start"], c["page_start"])
        sec["pdf_end"] = max(sec["pdf_end"], c["page_end"])

    nodes = []
    for ch in mapa["chapters"]:
        n = ch["chapter"]
        children = [{"node_id": f"ch{n:02d}_s{i:02d}", "title": title, **span}
                    for i, (title, span) in enumerate(by_chapter.get(n, {}).items())]
        nodes.append({"node_id": f"ch{n:02d}", "chapter": n, "title": ch["title"],
                      "pdf_start": ch["pdf_start"], "pdf_end": ch["pdf_end"],
                      "book_start": ch["book_start"], "book_end": ch["book_end"],
                      "summary": ch.get("summary_2lines", ""), "children": children})
    tree = {"title": mapa.get("title", "Generative Deep Learning"), "nodes": nodes}
    TREE_PATH.write_text(json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")
    return tree


def load_tree() -> dict:
    if not TREE_PATH.exists():
        return build_tree()
    return json.loads(TREE_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    tree = build_tree()
    n_sec = sum(len(n["children"]) for n in tree["nodes"])
    print(f"Árvore: {len(tree['nodes'])} capítulos, {n_sec} seções -> {TREE_PATH}")
