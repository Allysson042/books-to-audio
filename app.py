"""MVP Streamlit: chat + escopo + persona + debug RAG + áudio."""
import json
import logging
from pathlib import Path

# Silencia o file-watcher fuçando submódulos de visão do `transformers`
# (ModuleNotFoundError: torchvision — ruído inofensivo, nosso pipeline é só texto).
logging.getLogger("streamlit.watcher.local_sources_watcher").setLevel(logging.CRITICAL)

import streamlit as st

from src.generate import chunk_sig_of, get_pass1, get_pass2, load_persona
from src.markdown_math import render_mixed
from src.retrieval import RAGStore, Reranker
from src.retrieval_tree import TreeStore
from src.tts_provider import synthesize, synthesize_premium

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
use_rerank = st.sidebar.toggle("Re-rank (cross-encoder)", value=False,
                               help="OFF = usa o top-5 direto do RRF. Compare os dois modos.")
strategy = st.sidebar.selectbox("Estratégia", ["vectorless", "vetorial" ],
                                help="vectorless = LLM navega no sumário (árvore), sem vetores.")
premium_voice = st.sidebar.toggle("Voz premium (OpenRouter TTS)", value=False,
                                  help="ON = sintetiza via OpenRouter (pago, ~$0,06/áudio). OFF = Edge-TTS grátis.")
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


@st.cache_resource
def _treestore() -> TreeStore:
    return TreeStore()


# -- busca --------------------------------------------------------------------
# `chat_input` só devolve texto no rerun do submit (trocar de aba do navegador ou
# perder o foco não comita texto parcial). Precisa ficar no corpo principal:
# dentro de tabs/columns/expander ele quebra o layout (fixa no rodapé do container).
submitted = st.chat_input(
    placeholder="Pergunte ou peça resumo de capítulo — ex: O que é ELBO em VAEs?",
    key="q_input")
if submitted and submitted.strip():
    st.session_state["query"] = submitted.strip()

# query efetiva = última submetida (nunca o texto em edição no widget)
query = st.session_state.get("query", "")

# resultados de outro contexto (query/escopo/persona/rerank/estratégia) não valem mais
ctx = (query, scope, persona, use_rerank, strategy)
if st.session_state.get("ctx") != ctx:
    for k in ("pass1", "pass2", "mp3"):
        st.session_state.pop(k, None)
    st.session_state["ctx"] = ctx

if not query:
    st.info("Digite uma pergunta no campo abaixo — ex: **O que é ELBO em VAEs?** · "
            "**Explique GANs vs Diffusion** · **Resuma o Cap 4**")

if query:
    q = query  # alias curto: mesma string de antes, chaves de cache de `src.generate` intactas

    # busca memoizada por contexto: os `st.rerun()` dos botões não rebuscam (nem gastam LLM)
    if st.session_state.get("ret_ctx") != ctx:
        err = None
        if strategy == "vectorless":
            with st.spinner("Navegando na árvore (LLM escolhe as seções)..."):
                try:
                    top5 = _treestore().search(q, chapter=chapter, use_cache=use_cache)
                    cands = top5
                except (RuntimeError, ValueError) as e:
                    err = str(e)
                    top5, cands = [], []
        else:
            with st.spinner("Recuperando chunks (Chroma + BM25 → RRF → re-rank)..."):
                cands = _store().search(q, chapter=chapter, top_n=20)
                top5 = _reranker().rerank(q, cands, top_n=5) if (cands and use_rerank) else cands[:5]
        st.session_state["ret_ctx"] = ctx
        st.session_state["top5"] = top5
        st.session_state["cands"] = cands
        st.session_state["ret_err"] = err

    top5 = st.session_state["top5"]
    cands = st.session_state.get("cands", top5)
    if st.session_state.get("ret_err"):
        st.error(st.session_state["ret_err"])

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
                extra = (f"caminho `{r['tree_path']}`" if strategy == "vectorless"
                         else f"re-rank `{f'{r['rerank']:.4f}' if r.get('rerank') is not None else '–'}`")
                st.markdown(f"**{i}. {r['citation']}** · {m['section']} · `{m['type']}` · {extra}")
            if strategy == "vectorless" and top5 and st.checkbox("Raciocínio da navegação"):
                st.write(top5[0].get("thinking", ""))
            pick = st.selectbox("Ver texto do chunk:",
                                [f"{i}. {r['doc_id']}" for i, r in enumerate(top5, 1)])
            st.write(top5[int(pick.split(".")[0]) - 1]["text"])
            if st.checkbox("Debug RAG (tabela RRF top-20 → re-rank top-5)"):
                st.dataframe(
                    [{"doc_id": c["doc_id"], "citação": c["citation"],
                      "rank_denso": str(c.get("dense_rank") or "–"),
                      "rank_BM25": str(c.get("sparse_rank") or "–"),
                      "RRF": f"{c['rrf']:.5f}" if c.get("rrf") is not None else "–",
                  "re-rank": next((f"{t['rerank']:.4f}" for t in top5
                                   if t["doc_id"] == c["doc_id"] and t.get("rerank") is not None), "–")}
                     for c in cands],
                    width="stretch")
            if macro and st.checkbox(f"Resumo macro Cap {chapter} (nível 2)"):
                st.markdown(macro[:3000] + ("…" if len(macro) > 3000 else ""))
            st.caption(f"Query: {q!r} · escopo: {scope} · persona: {persona} · "
                       f"estratégia: {strategy}"
                       + (f" · re-rank: {'on' if use_rerank else 'off'}" if strategy == "vetorial" else "") + " · "
                       f"offline: {offline} · cache: {'on' if use_cache else 'off'}")

        t1, t2 = st.tabs(["Pass1 · resumo técnico", "Pass2 · roteiro TTS"])
        with t1:
            p1 = st.session_state.get("pass1")
            if p1:
                st.caption(_badge(p1["provider"], p1["cached"]))
                render_mixed(st, p1["text"])
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
                import os as _os
                _override = _os.getenv("OPENROUTER_TTS_VOICE", "")
                pvoice = (_override if premium_voice and _override
                          else (load_persona(persona).get("tts_voice_openrouter", voice)
                                if premium_voice else voice))
                st.caption(f"Roteiro pronto ({len(p2['text'])} chars · voz `{pvoice}`"
                           + (" · premium" if premium_voice else "") + ")")
                if st.button("Gerar áudio (5-8min)"):
                    try:
                        with st.spinner(f"Sintetizando com {pvoice}..."):
                            if premium_voice:
                                try:
                                    mp3, engine, n = synthesize_premium(
                                        p2["text"], pvoice, use_cache=use_cache)
                                    engine = f"{engine} ({n} fatia(s))"
                                except RuntimeError as e:
                                    st.warning(f"Premium indisponível ({str(e)[:120]}…) — "
                                               f"caindo p/ Edge-TTS grátis.")
                                    mp3, engine = synthesize(p2["text"], voice, use_cache)
                            else:
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
