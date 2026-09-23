"""MVP Streamlit: chat + escopo + persona + debug RAG + áudio."""
import json
from pathlib import Path

import streamlit as st

from src.generate import chunk_sig_of, get_pass1, get_pass2, load_persona
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


def _badge(provider: str, cached: bool) -> str:
    return f"via `{provider}`" + (" · do cache" if cached else " · recém-gerado")


# -- sidebar ------------------------------------------------------------------
scope_opts = ["Livro todo"] + [f"Cap {c['chapter']}: {c['title']}" for c in MAPA["chapters"]]
scope = st.sidebar.selectbox("Escopo", scope_opts or ["Livro todo"])
persona = st.sidebar.selectbox("Persona", ["tecnico_direto", "iniciante_guiado"])
offline = st.sidebar.toggle("Modo offline (cache demo)", value=False)
use_cache = st.sidebar.toggle("Usar cache (texto+áudio)", value=True,
                              help="OFF = ignora a leitura do cache e gera de novo (escrita continua).")
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

# resultados de outro contexto (query/escopo/persona) não valem mais
ctx = (q, scope, persona)
if st.session_state.get("ctx") != ctx:
    for k in ("pass1", "pass2", "mp3"):
        st.session_state.pop(k, None)
    st.session_state["ctx"] = ctx

if q:
    with st.spinner("Recuperando chunks (Chroma + BM25 → RRF → re-rank)..."):
        cands = _store().search(q, chapter=chapter, top_n=20)
        top5 = _reranker().rerank(q, cands, top_n=5) if cands else []

    if not top5:
        st.warning("Nada encontrado neste escopo. Tente 'Livro todo'.")
    else:
        macro = _macro(chapter) if chapter is not None else None
        sig = chunk_sig_of(top5)
        addendum = load_persona(persona).get("system_addendum", "")
        voice = load_persona(persona).get("tts_voice", "pt-BR-FranciscaNeural")

        with st.expander(f"Chunks recuperados ({len(top5)}) — ver fontes", expanded=False):
            for i, r in enumerate(top5, 1):
                m = r["metadata"]
                st.markdown(f"**{i}. {r['citation']}** · {m['section']} · `{m['type']}` · "
                            f"re-rank `{r['rerank']}`")
            pick = st.selectbox("Ver texto do chunk:",
                                [f"{i}. {r['doc_id']}" for i, r in enumerate(top5, 1)])
            st.write(top5[int(pick.split(".")[0]) - 1]["text"])
            if st.checkbox("Debug RAG (tabela RRF top-20 → re-rank top-5)"):
                st.dataframe(
                    [{"doc_id": c["doc_id"], "citação": c["citation"],
                      "rank_denso": str(c["dense_rank"] or "–"),
                      "rank_BM25": str(c["sparse_rank"] or "–"),
                      "RRF": f"{c['rrf']:.5f}",
                      "re-rank": next((f"{t['rerank']:.4f}" for t in top5
                                       if t["doc_id"] == c["doc_id"]), "–")}
                     for c in cands],
                    width="stretch")
            if macro and st.checkbox(f"Resumo macro Cap {chapter} (nível 2)"):
                st.markdown(macro[:3000] + ("…" if len(macro) > 3000 else ""))
            st.caption(f"Query: {q!r} · escopo: {scope} · persona: {persona} · "
                       f"offline: {offline} · cache: {'on' if use_cache else 'off'}")

        t1, t2 = st.tabs(["Pass1 · resumo técnico", "Pass2 · roteiro TTS"])
        with t1:
            p1 = st.session_state.get("pass1")
            if p1:
                st.caption(_badge(p1["provider"], p1["cached"]))
                st.markdown(p1["text"])
            else:
                st.info("Nada gerado ainda.")
            if st.button("Gerar resumo", type="primary"):
                try:
                    with st.spinner("Gerando Pass1 técnico..."):
                        text, prov, cached = get_pass1(q, str(chapter) if chapter else "all",
                                                       top5, macro, addendum, use_cache)
                    st.session_state["pass1"] = {"text": text, "provider": prov,
                                                 "cached": cached, "chunk_sig": sig}
                    st.rerun()
                except (RuntimeError, ValueError) as e:
                    st.error(str(e))

        with t2:
            p2 = st.session_state.get("pass2")
            if p2:
                st.caption(_badge(p2["provider"], p2["cached"]))
                st.markdown(p2["text"])
            else:
                st.info("Nada gerado ainda.")
            if st.button("Gerar roteiro", type="primary"):
                try:
                    with st.spinner("Gerando roteiro..."):
                        p1 = st.session_state.get("pass1")
                        if not p1:  # auto-encadeia o Pass1 em silêncio
                            text1, _, _ = get_pass1(q, str(chapter) if chapter else "all",
                                                    top5, macro, addendum, use_cache)
                            p1 = st.session_state["pass1"] = {
                                "text": text1, "provider": "encadeado",
                                "cached": False, "chunk_sig": sig}
                        text, prov, cached = get_pass2(
                            q, str(chapter) if chapter else "all", persona,
                            p1["text"], p1["chunk_sig"], use_cache)
                    st.session_state["pass2"] = {"text": text, "provider": prov,
                                                 "cached": cached}
                    st.rerun()
                except (RuntimeError, ValueError) as e:
                    st.error(str(e))

            st.divider()
            p2 = st.session_state.get("pass2")
            if p2:
                st.caption(f"Roteiro pronto ({len(p2['text'])} chars · voz `{voice}`)")
                if st.button("Gerar áudio (5-8min)"):
                    try:
                        with st.spinner(f"Sintetizando com {voice}..."):
                            mp3, engine = synthesize(p2["text"], voice, use_cache)
                        st.session_state["mp3"] = str(mp3)
                        st.caption(f"via `{engine}`"
                                   + (" · do cache" if engine == "cache" else ""))
                        st.audio(str(mp3))
                        st.download_button("Baixar MP3", data=mp3.read_bytes(),
                                           file_name=mp3.name, mime="audio/mpeg")
                    except RuntimeError as e:
                        st.error(str(e))
                elif st.session_state.get("mp3"):
                    mp3 = Path(st.session_state["mp3"])
                    if mp3.exists():
                        st.audio(str(mp3))
                        st.download_button("Baixar MP3", data=mp3.read_bytes(),
                                           file_name=mp3.name, mime="audio/mpeg")
            else:
                st.button("Gerar áudio (5-8min)", disabled=True,
                          help="Gere o roteiro primeiro")
