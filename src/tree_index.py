"""Índice em árvore (estilo PageIndex, sem vetores) a partir do TOC + macros.

Hierarquia REAL do TOC embutido: L2 capítulo -> L3 seção -> L4 subseção (aninhados).
Range de cada nó = [início próprio, início do próximo irmão) — o pai cobre os filhos.
Gera 1x `cache/tree_livro.json`. Nenhum LLM aqui (TOC local + macros S1 existentes).
Uso: python -m src.tree_index  (ou importado por src/retrieval_tree.py, que gera se ausente)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ingest import BOOK_PAGE_OFFSET, load_chapters  # noqa: E402

CACHE = ROOT / "cache"
TREE_PATH = CACHE / "tree_livro.json"
TREE_VERSION = "2"  # bump quando a estrutura mudar (invalida tree_sel_* — ver retrieval_tree)


def _clean(title: str) -> str:
    return " ".join(title.split())


def build_tree() -> dict:
    import fitz
    pdf_path = next((ROOT / "data").glob("*.pdf"))
    doc = fitz.open(str(pdf_path))
    toc = [(lvl, _clean(t), p) for lvl, t, p in doc.get_toc() if _clean(t)]
    chapters = load_chapters(doc)
    summaries = {c["chapter"]: c.get("summary_2lines", "") for c in
                 json.loads((CACHE / "mapa_livro.json").read_text(encoding="utf-8"))["chapters"]}

    nodes = []
    # Entradas L3/L4 agrupadas por capítulo (pelo range de páginas do cap).
    for ch in chapters:
        n = ch["chapter"]
        fam = [(lvl, t, p) for lvl, t, p in toc
               if lvl >= 3 and ch["pdf_start"] <= p <= ch["pdf_end"]]
        fam.append((3, "__END__", ch["pdf_end"] + 1))  # sentinela p/ fechar o último
        l3_list, stack = [], []
        for lvl, title, page in fam:
            lvl = min(lvl, 4)
            node = {"title": title, "pdf_start": page, "pdf_end": page}
            while stack and stack[-1][0] >= lvl:
                closed_lvl, closed = stack.pop()
                closed["pdf_end"] = page - 1
                if stack:
                    stack[-1][1].setdefault("children", []).append(closed)
                else:
                    l3_list.append(closed)
            stack.append((lvl, node))
        # A sentinela nunca entra na árvore (só fechou ranges); L3 relativos ao cap:
        l3_rel = [c for c in l3_list if c["title"] != "__END__"]

        def finalize(items, idx_prefix):
            out = []
            for i, it in enumerate(items):
                nid = f"{idx_prefix}{i:02d}"
                kids = finalize(it.pop("children", []), f"{nid}_t")
                out.append({"node_id": nid, "title": it["title"],
                            "pdf_start": it["pdf_start"], "pdf_end": it["pdf_end"],
                            "children": kids})
            return out

        children = finalize(l3_rel, f"ch{n:02d}_s")
        nodes.append({"node_id": f"ch{n:02d}", "chapter": n, "title": ch["title"],
                      "pdf_start": ch["pdf_start"], "pdf_end": ch["pdf_end"],
                      "book_start": ch["pdf_start"] - BOOK_PAGE_OFFSET,
                      "book_end": ch["pdf_end"] - BOOK_PAGE_OFFSET,
                      "summary": summaries.get(n, ""),
                      "children": children})
    tree = {"version": TREE_VERSION,
            "title": "Generative Deep Learning", "nodes": nodes}
    TREE_PATH.write_text(json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")
    return tree


def load_tree() -> dict:
    if not TREE_PATH.exists():
        return build_tree()
    return json.loads(TREE_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    tree = build_tree()
    def count(ns):
        return sum(1 + count(n.get("children", [])) for n in ns)
    print(f"Árvore v{TREE_VERSION}: {len(tree['nodes'])} capítulos, "
          f"{count(tree['nodes']) - len(tree['nodes'])} seções/subseções -> {TREE_PATH}")
