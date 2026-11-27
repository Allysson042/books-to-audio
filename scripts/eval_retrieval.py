"""Régua do retrieval: hit-rate top-5 por pergunta dourada (PT e EN), por estágio.

Uso:
    venv/bin/python scripts/eval_retrieval.py             # vetorial (tabela de sempre)
    venv/bin/python scripts/eval_retrieval.py --lang en   # só inglês
    venv/bin/python scripts/eval_retrieval.py --no-rerank # pula cross-encoder (só vetorial)
    venv/bin/python scripts/eval_retrieval.py --strategy tree   # vectorless (V0)
    venv/bin/python scripts/eval_retrieval.py --strategy both   # os dois, para A/B

Serve para comparar estratégias (chunking, tradução de query, vectorless):
rode antes/depois e compare o placar. Não chama LLM de geração (só embeddings locais);
no modo `tree` usa a seleção cacheada (`cache/tree_sel_*`) e só chama o LLM em cache miss.

Acerto no `tree` é **agnóstico a chunking** (V0): deriva os ranges esperados dos
`expected_ids` (chapter + páginas) e aceita qualquer chunk que caia neles — se o
chunking mudar (V2), a régua continua válida. `tree@5` usa os 5 primeiros do retorno;
`tree@all` usa tudo o que a árvore devolveu (até `MAX_CHUNKS`). `in_scope` e `chars`
medem o bleed: quanto do contexto entregue realmente pertence às seções escolhidas.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import MAX_CHUNKS, TREE_DELIVERY, TREE_PROMPT  # noqa: E402
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


def expected_ranges(q: dict, metas: dict) -> list[tuple[int, int, int]]:
    """(chapter, page_start, page_end) de cada `expected_id` (agnóstico a chunking)."""
    out = []
    for doc_id in q.get("expected_ids", []):
        meta = metas.get(doc_id)
        if meta:
            out.append((meta["chapter"], meta["page_start"], meta["page_end"]))
    return out


def tree_hit(chunks: list[dict], q: dict, metas: dict) -> tuple[bool, int]:
    """HIT = mesmo chapter + sobreposição de páginas com QUALQUER range esperado."""
    if "expected_chapters" in q:  # Q4: ≥1 chunk de cada capítulo exigido
        need = set(q["expected_chapters"])
        for i, chunk in enumerate(chunks, 1):
            need.discard(chunk["metadata"]["chapter"])
            if not need:
                return True, i
        return False, -1
    ranges = expected_ranges(q, metas)
    for i, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        for chapter, start, end in ranges:
            if (meta["chapter"] == chapter
                    and not (meta["page_end"] < start or meta["page_start"] > end)):
                return True, i
    return False, -1


def run_vector(args, golden: list[dict], langs: list[str], store: RAGStore) -> None:
    reranker = None if args.no_rerank else Reranker()
    metas = store.meta_by_id

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


def run_tree(args, golden: list[dict], langs: list[str], store: RAGStore) -> None:
    from src.retrieval_tree import TreeStore  # tardio: só carrega se a estratégia pedir

    metas = store.meta_by_id
    tree = TreeStore()
    print(f"(tree) TREE_DELIVERY={TREE_DELIVERY}  TREE_PROMPT={TREE_PROMPT}  "
          f"MAX_CHUNKS={MAX_CHUNKS}  chunks={tree.chunks_source} ({tree.chunks_count})")
    print(f"{'qid':4} {'lang':4} {'tree@5':>8} {'tree@all':>8} {'in_scope':>9} "
          f"{'chars':>7}  1º_acerto")

    total = hits5 = hits_all = errors = 0
    scope_sum, chars_sum, n_chunks = 0.0, 0, 0
    for q in golden:
        for lang in langs:
            query = q[lang]
            try:
                res = tree.search(query, chapter=None, use_cache=True)
            except Exception as exc:  # seleção sem cache + provider fora do ar
                errors += 1
                print(f"{q['id']:4} {lang:4} {'ERRO':>8} {type(exc).__name__}: "
                      f"{str(exc)[:110]}")
                continue
            h5, p5 = tree_hit(res[:5], q, metas)
            hall, pall = tree_hit(res, q, metas)
            total += 1
            hits5 += h5
            hits_all += hall
            scopes = [float(c.get("in_scope", 0.0)) for c in res]
            scopes_avg = sum(scopes) / len(scopes) if scopes else 0.0
            chars = sum(len(c["text"]) for c in res)
            scope_sum += scopes_avg
            chars_sum += chars
            n_chunks += len(res)
            flag = lambda h: "HIT" if h else "miss"
            print(f"{q['id']:4} {lang:4} {flag(h5):>8} {flag(hall):>8} {scopes_avg:>8.0%} "
                  f"{chars:>7}  5@{p5} all@{pall} ({len(res)} chunks)")
    if total:
        print(f"\nPlacar tree@5: {hits5}/{total} ({hits5/total:.0%})   "
              f"tree@all: {hits_all}/{total} ({hits_all/total:.0%})   "
              f"in_scope médio: {scope_sum/total:.0%}   "
              f"chars médios: {chars_sum/total:.0f} ({n_chunks//total} chunks/query)")
    if errors:
        print(f"ERROS tree: {errors} pergunta(s) — seleção sem cache e provider indisponível.")
    if args.no_rerank:
        print("(nota: --no-rerank só afeta o vetorial; ignorado no tree)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["en", "pt", "all"], default="all")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--strategy", choices=["vector", "tree", "both"], default="vector",
                    help="vector = Chroma+BM25+re-rank (default); tree = vectorless; both = A/B")
    args = ap.parse_args()

    golden = json.loads((ROOT / "scripts" / "golden.json").read_text(encoding="utf-8"))
    langs = ["en", "pt"] if args.lang == "all" else [args.lang]

    store = RAGStore()
    if args.strategy in ("vector", "both"):
        run_vector(args, golden, langs, store)
    if args.strategy in ("tree", "both"):
        try:
            run_tree(args, golden, langs, store)
        except Exception as exc:  # árvore/índice ausente: não derruba o vetorial
            print(f"ERRO ao avaliar a estratégia tree: {type(exc).__name__}: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
