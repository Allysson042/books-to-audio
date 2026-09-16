"""MVP Streamlit: chat + escopo + persona + debug RAG + áudio."""
# TODO S2-S4: Chroma+BM25 RRF, re-rank, 2-pass LLM, Edge-TTS player, modo offline
import streamlit as st
st.title("Books to Audio — Generative Deep Learning")
st.sidebar.selectbox("Escopo", ["Livro todo", "Cap 1", "Cap 2", "Cap 3", "Cap 4"])
st.sidebar.selectbox("Persona", ["tecnico_direto", "iniciante_guiado"])
st.sidebar.toggle("Modo offline (cache demo)", value=False)
q = st.text_input("Pergunte ou peça resumo de capítulo")
if st.button("Gerar áudio (5-8min)"):
    st.info("TODO S4: gerar roteiro Pass2 + Edge-TTS + player")
st.caption("TODO: painel debug com chunks + [Cap X, p. Y] para provar RAG na demo.")
