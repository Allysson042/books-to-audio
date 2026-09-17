"""MVP Streamlit: chat + escopo + persona + debug RAG + áudio."""
import json
from pathlib import Path

import streamlit as st

from src.generate import answer, load_persona
from src.retrieval import RAGStore, Reranker
from src.tts_provider import synthesize
st.set_page_config(page_title="Books to Audio — GDL", layout="wide")
st.title("Books to Audio — Generative Deep Learning")

# -- contexto hierárquico (nível 1: mapa; nível 2: macro do cap em foco) ------
CACHE = Path("cache")
try:
    MAPA = json.loads((CACHE / "mapa_livro.json").read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError):
    MAPA = {"chapters": []}


def _macro(chapter: int) -> str | None:
    for c in MAPA["chapters"]:
        if c["chapter"] == chapter:
            p = CACHE / c["macro_file"]
            return p.read_text(encoding="utf-8") if p.exists() else None
    return None


# -- sidebar ------------------------------------------------------------------
scope_opts = ["Livro todo"] + [f"Cap {c['chapter']}: {c['title']}" for c in MAPA["chapters"]]
scope = st.sidebar.selectbox("Escopo", scope_opts or ["Livro todo"])
persona = st.sidebar.selectbox("Persona", ["tecnico_direto", "iniciante_guiado"])
offline = st.sidebar.toggle("Modo offline (cache demo)", value=False)
chapter = int(scope.split(":")[0].replace("Cap", "")) if scope != "Livro todo" else None

with st.sidebar.expander("Mapa do livro (nível 1)"):
    for c in MAPA["chapters"]:
        st.markdown(f"**Cap {c['chapter']}** — {c['title']}")
        st.caption(c.get("summary_2lines", ""))

# -- recursos (cache) ----------------------------------------------------------
@st.cache_resource
def _store() -> RAGStore:
    return RAGStore()


@st.cache_resource
def _reranker() -> Reranker:
    return Reranker()


# -- busca --------------------------------------------------------------------
q = st.text_input("Pergunte ou peça resumo de capítulo",
                  placeholder="Ex: O que é ELBO em VAEs? | Explique GANs vs Diffusion")
if q:
    with st.spinner("Recuperando chunks (Chroma + BM25 → RRF → re-rank)..."):
        cands = _store().search(q, chapter=chapter, top_n=20)
        top5 = _reranker().rerank(q, cands, top_n=5) if cands else []

    if chapter is not None and (macro := _macro(chapter)):
        with st.expander(f"Resumo macro Cap {chapter} (nível 2 — PT-BR, gerado 1x na ingestão)"):
            st.markdown(macro[:3000] + ("…" if len(macro) > 3000 else ""))

    if not top5:
        st.warning("Nada encontrado neste escopo. Tente 'Livro todo'.")
    else:
        st.subheader(f"Top-{len(top5)} chunks (nível 3 — micro)")
        for i, r in enumerate(top5, 1):
            m = r["metadata"]
            st.markdown(f"**{i}. {r['citation']}** · {m['section']} · `{m['type']}` · "
                        f"re-rank `{r['rerank']}`")
            with st.expander("ver texto"):
                st.write(r["text"])

        with st.expander("Debug RAG (prova visual: RRF top-20 → re-rank top-5)"):
            st.dataframe(
                [{"doc_id": c["doc_id"], "citação": c["citation"],
                  "rank_denso": str(c["dense_rank"] or "–"),
                  "rank_BM25": str(c["sparse_rank"] or "–"),
                  "RRF": f"{c['rrf']:.5f}",
                  "re-rank": next((f"{t['rerank']:.4f}" for t in top5
                                   if t["doc_id"] == c["doc_id"]), "–")}
                 for c in cands],
                width="stretch")
            st.caption(f"Query: {q!r} · escopo: {scope} · persona p/ S3: {persona} · "
                       f"modo offline: {offline}")

        if st.button("Gerar resumo + roteiro (2-pass)", type="primary"):
            try:
                with st.spinner("Gerando Pass1 técnico → Pass2 roteiro..."):
                    res = answer(q, chapter, persona,
                                 store=_store(), reranker=_reranker(),
                                 macro=_macro(chapter) if chapter else None)
                st.caption(f"via `{res['provider']}`"
                           + (" · do cache" if res["cached"] else " · recém-gerado"))
                st.session_state["roteiro"] = {"pass2": res["pass2"], "persona": persona,
                                               "query": q, "scope": scope}
                t1, t2 = st.tabs(["Pass1 · resumo técnico", "Pass2 · roteiro TTS"])
                with t1:
                    st.markdown(res["pass1"])
                with t2:
                    st.markdown(res["pass2"])
            except (RuntimeError, ValueError) as e:
                st.error(str(e))

st.divider()
if "roteiro" in st.session_state:
    r = st.session_state["roteiro"]
    voice = load_persona(r["persona"]).get("tts_voice", "pt-BR-FranciscaNeural")
    st.caption(f"Roteiro pronto ({len(r['pass2'])} chars · voz `{voice}`) — "
               f"query: {r['query']!r} · escopo: {r['scope']}")
    if st.button("Gerar áudio (5-8min)", type="primary"):
        try:
            with st.spinner(f"Sintetizando com {voice}..."):
                mp3, engine = synthesize(r["pass2"], voice)
            st.caption(f"via `{engine}`" + (" · do cache" if engine == "cache" else ""))
            st.audio(str(mp3))
            st.download_button("Baixar MP3", data=mp3.read_bytes(),
                               file_name=mp3.name, mime="audio/mpeg")
        except RuntimeError as e:
            st.error(str(e))
else:
    st.button("Gerar áudio (5-8min)", disabled=True,
              help="Gere o resumo + roteiro (2-pass) primeiro")
    st.caption("O áudio é sintetizado a partir do roteiro Pass2.")
