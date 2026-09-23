"""Régua do retrieval: hit-rate top-5 por pergunta dourada (PT e EN), por estágio.

Uso:
    venv/bin/python scripts/eval_retrieval.py            # tudo
    venv/bin/python scripts/eval_retrieval.py --lang en  # só inglês
    venv/bin/python scripts/eval_retrieval.py --no-rerank  # pula cross-encoder (rápido)

Serve para comparar estratégias (chunking, tradução de query, vectorless):
rode antes/depois e compare o placar. Não chama LLM de geração (só embeddings locais).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval import RAGStore, Reranker  # noqa: E402


def hit_in(ids: list[str], q: dict, metas: dict) -> tuple[bool, int]:
    """(acertou?, posição do 1º acerto 1-indexed ou -1)."""
    if "expected_chapters" in q:
        need = set(q["expected_chapters"])
        for i, doc_id in enumerate(ids, 1):
            need.discard(metas[doc_id]["chapter"])
            if not need:
                return True, i
        return False, -1
    for i, doc_id in enumerate(ids, 1):
        if doc_id in q["expected_ids"]:
            return True, i
    return False, -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["en", "pt", "all"], default="all")
    ap.add_argument("--no-rerank", action="store_true")
    args = ap.parse_args()

    golden = json.loads((ROOT / "scripts" / "golden.json").read_text(encoding="utf-8"))
    store = RAGStore()
    reranker = None if args.no_rerank else Reranker()
    metas = store.meta_by_id
    langs = ["en", "pt"] if args.lang == "all" else [args.lang]

    total = hits = 0
    print(f"{'qid':4} {'lang':4} {'denso':>8} {'híbrido':>8} {'final':>8}  1º_acerto")
    for q in golden:
        for lang in langs:
            query = q[lang]
            dense = store.dense_search(query, k=20)
            cands = store.search(query, top_n=20)
            hybrid = [c["doc_id"] for c in cands]
            if reranker:
                final = [c["doc_id"] for c in reranker.rerank(query, cands, top_n=5)]
            else:
                final = hybrid[:5]
            hd, pd = hit_in(dense, q, metas)
            hh, ph = hit_in(hybrid, q, metas)
            hf, pf = hit_in(final, q, metas)
            total += 1
            hits += hf
            flag = lambda h: "HIT" if h else "miss"
            print(f"{q['id']:4} {lang:4} {flag(hd):>8} {flag(hh):>8} {flag(hf):>8}  "
                  f"denso@{pd} híbrido@{ph} final@{pf}")
    print(f"\nPlacar top-5: {hits}/{total} ({hits/total:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
