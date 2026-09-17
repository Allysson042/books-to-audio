"""S2 — Recuperação híbrida: Chroma (denso) + BM25 (esparso), fusão RRF, re-rank local.

Uso:
    from src.retrieval import RAGStore, Reranker, retrieve, citation

    store = RAGStore()                      # abre Chroma + BM25 do disco (só leitura)
    cands = store.search("What is ELBO?", chapter=None, top_n=20)
    top5 = Reranker().rerank("What is ELBO?", cands, top_n=5)
    # ou em 1 chamada:
    top5 = retrieve("What is ELBO?", chapter=3)

Convenções (ver ARCHITECTURE.md Ramo 2):
  - Filtro escopo: chapter=None (livro todo) ou nº do capítulo (metadata `chapter`).
  - Fusão RRF k=60 sobre top-20 denso + top-20 esparso; re-rank cross-encoder top-20 -> top-5.
  - Citação usa páginas impressas: [Cap X, p. Y] (metadata `book_page_*`).
  - `app.py` importa daqui; `ingest.py` continua sendo o único escritor do storage.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = ROOT / "storage" / "chroma"
BM25_PATH = ROOT / "storage" / "bm25.pkl"
COLLECTION = "books"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RRF_K = 60


def citation(meta: dict) -> str:
    """`[Cap X, p. Y]` (ou `p. Y-Z`) a partir da metadata do chunk."""
    start, end = meta["book_page_start"], meta["book_page_end"]
    pages = f"{start}" if start == end else f"{start}-{end}"
    return f"[Cap {meta['chapter']}, p. {pages}]"


class RAGStore:
    """Acesso só-leitura ao índice S1 (Chroma + BM25 + docstore)."""

    def __init__(self, chroma_dir: Path = CHROMA_DIR, bm25_path: Path = BM25_PATH):
        import pickle

        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        ef = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL, device="cpu")
        self.col = chromadb.PersistentClient(path=str(chroma_dir)).get_collection(
            COLLECTION, embedding_function=ef)
        with open(bm25_path, "rb") as f:
            dump = pickle.load(f)
        self.doc_ids: list[str] = dump["doc_ids"]
        self.bm25 = dump["bm25"]
        self.meta_by_id: dict[str, dict] = {m["doc_id"]: m for m in dump["metadatas"]}
        self._pos = {doc_id: i for i, doc_id in enumerate(self.doc_ids)}

    # -- etapa 1: busca densa -------------------------------------------------
    def dense_search(self, query: str, chapter: int | None = None, k: int = 20) -> list[str]:
        where = {"chapter": chapter} if chapter is not None else None
        res = self.col.query(query_texts=[query], n_results=k, where=where, include=["documents"])
        return res["ids"][0]

    # -- etapa 2: busca esparsa -----------------------------------------------
    def sparse_search(self, query: str, chapter: int | None = None, k: int = 20) -> list[str]:
        import numpy as np

        scores = np.asarray(self.bm25.get_scores(query.lower().split()), dtype=float)
        if chapter is not None:
            mask = np.array([self.meta_by_id[i]["chapter"] == chapter for i in self.doc_ids])
            scores = np.where(mask, scores, -np.inf)
        top = np.argsort(scores)[::-1][:k]
        return [self.doc_ids[i] for i in top if np.isfinite(scores[i])]

    # -- etapa 3: fusão RRF ----------------------------------------------------
    @staticmethod
    def rrf_fuse(ranked_lists: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
        fused: dict[str, float] = {}
        for ranked in ranked_lists:
            for rank, doc_id in enumerate(ranked, start=1):
                fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
        return sorted(fused.items(), key=lambda kv: kv[1], reverse=True)

    def search(self, query: str, chapter: int | None = None, top_n: int = 20) -> list[dict]:
        """Top-N candidatos com texto + metadata + scores de cada estágio."""
        dense = self.dense_search(query, chapter, k=top_n)
        sparse = self.sparse_search(query, chapter, k=top_n)
        dense_rank = {d: i + 1 for i, d in enumerate(dense)}
        sparse_rank = {d: i + 1 for i, d in enumerate(sparse)}
        fused = self.rrf_fuse([dense, sparse])[:top_n]
        docs = self.col.get(ids=[d for d, _ in fused], include=["documents"])
        text_by_id = dict(zip(docs["ids"], docs["documents"]))
        return [{
            "doc_id": doc_id,
            "text": text_by_id[doc_id],
            "metadata": self.meta_by_id[doc_id],
            "citation": citation(self.meta_by_id[doc_id]),
            "dense_rank": dense_rank.get(doc_id),
            "sparse_rank": sparse_rank.get(doc_id),
            "rrf": round(score, 5),
        } for doc_id, score in fused]


class Reranker:
    """Cross-encoder local (CPU) top-20 -> top-N. Lazy-load: ~80MB na 1ª chamada."""

    def __init__(self, model: str = RERANK_MODEL):
        self.model_name = model
        self._ce = None

    def _load(self):
        if self._ce is None:
            from sentence_transformers import CrossEncoder
            self._ce = CrossEncoder(self.model_name, device="cpu")
        return self._ce

    def rerank(self, query: str, candidates: list[dict], top_n: int = 5) -> list[dict]:
        ce = self._load()
        scores = ce.predict([(query, c["text"]) for c in candidates])
        ranked = sorted(zip(candidates, scores), key=lambda cs: cs[1], reverse=True)[:top_n]
        out = []
        for cand, s in ranked:
            cand = dict(cand)
            cand["rerank"] = round(float(s), 4)
            out.append(cand)
        return out


def retrieve(query: str, chapter: int | None = None,
             prefetch: int = 20, top_n: int = 5,
             store: RAGStore | None = None,
             reranker: Reranker | None = None) -> list[dict]:
    """Pipeline S2 completo: híbrida + RRF + re-rank."""
    store = store or RAGStore()
    reranker = reranker or Reranker()
    return reranker.rerank(query, store.search(query, chapter, top_n=prefetch), top_n=top_n)
