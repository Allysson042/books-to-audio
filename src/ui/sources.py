"""Cards de fonte (U3): citação, seção, tipo, relevância normalizada e trecho.

Contrato visual: `docs/UX/06-guia-visual.md` §5 (componente "Fontes") e §7
(microcopy). `top5`/`cands` chegam intactos de `RAGStore`/`TreeStore`; nada aqui
toca no pipeline (retrieval, geração, TTS ou cache).

Regra do Streamlit: `st.expander` não pode ser aninhado. O bloco inteiro é **um**
expander; o conteúdo profundo (trecho completo, macro, debug) usa `st.popover`.
"""

from __future__ import annotations

import streamlit as st

from src.ui import copy

SNIPPET_CHARS = 160


# -- derivações puras (testáveis sem Streamlit) -------------------------------
def _meta(item: dict) -> dict:
    return item.get("metadata") or {}


def _pages(meta: dict) -> tuple[int, int] | None:
    """Faixa de páginas impressas; cai para as páginas do PDF quando falta o par."""
    if meta.get("book_page_start") is not None and meta.get("book_page_end") is not None:
        start, end = meta["book_page_start"], meta["book_page_end"]
    else:
        start, end = meta.get("page_start"), meta.get("page_end")
    if start is None or end is None:
        return None
    return int(start), int(end)


def summary(top5: list[dict]) -> str:
    """`Cap 4 · p.96–112`, `Cap 3–4 · p.108–126` ou só `Cap 4` (sem páginas)."""
    metas = [_meta(item) for item in top5]
    chapters = sorted({int(m["chapter"]) for m in metas if m.get("chapter") is not None})
    parts: list[str] = []
    if chapters:
        parts.append(f"Cap {chapters[0]}" if len(chapters) == 1
                     else f"Cap {chapters[0]}–{chapters[-1]}")
    ranges = [p for p in (_pages(m) for m in metas) if p is not None]
    if ranges:
        lo = min(p[0] for p in ranges)
        hi = max(p[1] for p in ranges)
        parts.append(f"p.{lo}" if lo == hi else f"p.{lo}–{hi}")
    return " · ".join(parts)


def _score_key(items: list[dict], strategy: str) -> str | None:
    """Campo de score por estratégia: rerank→rrf (vetorial), tree_fit→in_scope→tree_lex."""
    if strategy == "vectorless":
        keys = ("tree_fit", "in_scope", "tree_lex")
    else:
        keys = ("rerank", "rrf")
    for key in keys:
        if any(item.get(key) is not None for item in items):
            return key
    return None


def normalized_scores(items: list[dict], strategy: str) -> list[int]:
    """Relevância relativa 0–100: `(v-min)/(max-min)`; todos iguais → 100."""
    if not items:
        return []
    key = _score_key(items, strategy)
    if key is None:
        return [100] * len(items)
    values = [float(item.get(key) or 0.0) for item in items]
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [100] * len(items)
    return [round((value - lo) / (hi - lo) * 100) for value in values]


def snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    """Uma linha de até ~`limit` chars, cortada em palavra, com `…`."""
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit].rsplit(" ", 1)[0].rstrip(" .,;:")
    return f"{cut}…"


# -- render -------------------------------------------------------------------
def _bar(pct: int) -> str:
    return (f'<div class="gdl-rel" role="img" aria-label="{pct}%">'
            f'<i style="width:{pct}%"></i></div>')


def _type_label(meta: dict) -> str:
    raw = str(meta.get("type") or "").strip().lower()
    return copy.TYPE_LABELS.get(raw, raw)


def _card(item: dict, pct: int, idx: int) -> None:
    meta = _meta(item)
    with st.container(border=True, key=f"gdl_card_src_{idx}"):
        st.markdown(f"**{item.get('citation', '')}**")
        bits = [meta.get("section", ""), _type_label(meta)]
        line = " · ".join(str(b) for b in bits if b)
        if line:
            st.caption(line)
        st.markdown(_bar(pct), unsafe_allow_html=True)
        st.caption(f"{pct}% · {copy.RELEVANCE_HINT}")
        snip = snippet(item.get("text", ""))
        if snip:
            st.caption(snip)  # sem markdown: chunks têm `_ * ` <` que o md comeria
        with st.popover(copy.SEE_SNIPPET):
            if str(meta.get("type") or "").lower() == "code":
                st.code(item.get("text", ""))
            else:
                st.write(item.get("text", ""))


def _search_details(cands: list[dict], top5: list[dict], strategy: str) -> None:
    with st.popover(copy.SEARCH_DETAILS):
        st.dataframe(
            [{"doc_id": c.get("doc_id", ""), "citação": c.get("citation", ""),
              "rank_denso": str(c.get("dense_rank") or "–"),
              "rank_BM25": str(c.get("sparse_rank") or "–"),
              "RRF": f"{c['rrf']:.5f}" if c.get("rrf") is not None else "–",
              "re-rank": next((f"{t['rerank']:.4f}" for t in top5
                               if t.get("doc_id") == c.get("doc_id")
                               and t.get("rerank") is not None), "–")}
             for c in cands],
            width="stretch")
        thinking = top5[0].get("thinking", "") if (strategy == "vectorless" and top5) else ""
        if thinking:
            with st.expander(copy.THINKING_LABEL):
                st.write(thinking)


def render(container, top5: list[dict], cands: list[dict], strategy: str,
           macro: str | None, chapter: int | None, err: str | None = None,
           on_retry=None) -> None:
    """Bloco "Fontes": 1 linha de resumo (colapsado) + cards + popovers de debug."""
    top5 = top5 or []
    if err:
        with container.container(border=True, key="gdl_card_src_err"):
            st.markdown(f"**{copy.SOURCES_FAILED_TITLE}**")
            st.caption(copy.STAGE_ERROR["fontes"])
            st.button(copy.RETRY, key="retry_search", on_click=on_retry)
            with st.popover(copy.DETAILS):
                st.code(err)
        return
    if not top5:
        with container.container(border=True, key="gdl_card_src_empty"):
            st.warning(copy.NOT_FOUND)
        return

    scores = normalized_scores(top5, strategy)

    # Abertura do capítulo vem antes da lista (o macro é o "resumo da porta de entrada").
    if macro and chapter is not None:
        with container.popover(copy.MACRO_LABEL.format(n=chapter)):
            st.markdown(macro)

    with container.expander(copy.sources_header(len(top5), summary(top5)),
                            expanded=False):
        for i, (item, pct) in enumerate(zip(top5, scores)):
            _card(item, pct, i)
        _search_details(cands or top5, top5, strategy)
