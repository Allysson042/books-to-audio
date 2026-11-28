"""MVP Streamlit: pergunta → fontes → resumo → roteiro → áudio (U1)."""
import hashlib
import json
import logging
import os
import time
from pathlib import Path

# Silencia o file-watcher fuçando submódulos de visão do `transformers`
# (ModuleNotFoundError: torchvision — ruído inofensivo, nosso pipeline é só texto).
logging.getLogger("streamlit.watcher.local_sources_watcher").setLevel(logging.CRITICAL)

import streamlit as st

from src import config, image_provider
from src.generate import chunk_sig_of, get_pass1, get_pass2, load_persona
from src.markdown_math import render_mixed
from src.mindmap import build_outline, outline_to_prompt, outline_to_svg
from src.retrieval import RAGStore, Reranker
from src.retrieval_tree import TreeStore
from src.tts_provider import clean_for_speech, synthesize, synthesize_premium
from src.ui import actions, copy, history, mindmap_view, player, sources, stages, theme

st.set_page_config(page_title=copy.PAGE_TITLE, page_icon=copy.PAGE_ICON, layout="wide")
theme.inject(st)

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


# -- header (U2): título + escopo + persona + sessão + ajustes, sem sidebar ---
scope_opts = ([copy.SCOPE_ALL]
              + [f"Cap {c['chapter']} · {c['title']}" for c in MAPA["chapters"]])
SCOPE_TO_CHAPTER = {f"Cap {c['chapter']} · {c['title']}": c["chapter"]
                    for c in MAPA["chapters"]}

head_l, head_c, head_p, head_s, head_g = st.columns([4.7, 2.1, 1.6, 1.1, 1.3],
                                                    vertical_alignment="bottom")
with head_l:
    st.title(copy.TITLE)
    st.caption(copy.SUBTITLE)
    if not MAPA["chapters"]:
        st.warning(copy.MAPA_MISSING)
with head_c:
    scope = st.selectbox(copy.SCOPE_LABEL, scope_opts or [copy.SCOPE_ALL],
                         label_visibility="collapsed", key="ui_scope")
with head_p:
    persona_label = st.selectbox(copy.PERSONA_LABEL, list(copy.PERSONA_OPTIONS),
                                 label_visibility="collapsed", key="ui_persona")
with head_s:
    ph_sess = st.empty()  # ☰ Sessão: preenchido no fim (já com o turno do run)
with head_g:
    with st.popover(copy.ADVANCED_LABEL):
        strategy_label = st.selectbox(copy.STRATEGY_LABEL, list(copy.STRATEGY_OPTIONS),
                                      key="ui_strategy")
        strategy = copy.STRATEGY_OPTIONS[strategy_label]
        use_rerank = False
        if strategy == "vetorial":
            use_rerank = st.checkbox(copy.RERANK_LABEL, value=False,
                                     help=copy.RERANK_HELP, key="ui_rerank")
        ignore_cache = st.toggle(copy.IGNORE_CACHE_LABEL, value=False,
                                 help=copy.IGNORE_CACHE_HELP, key="ui_ignore_cache")
        has_premium_key = bool(os.getenv("OPENROUTER_API_KEY"))
        premium_voice = st.toggle(copy.PREMIUM_LABEL, value=False,
                                  disabled=not has_premium_key, key="ui_premium")
        if not has_premium_key:
            st.caption(copy.PREMIUM_NO_KEY)
            premium_voice = False
        present = st.toggle(copy.PRESENT_LABEL, value=False, key="ui_present")
        st.divider()
        with st.expander(copy.MAP_LABEL.format(n=len(MAPA["chapters"]))):
            with st.container(height=260):
                for c in MAPA["chapters"]:
                    st.markdown(f"**Cap {c['chapter']}** — {c['title']}")
                    st.caption(c.get("summary_2lines", ""))

use_cache = not ignore_cache
persona = copy.PERSONA_OPTIONS[persona_label]
chapter = SCOPE_TO_CHAPTER.get(scope)

# U5: modo apresentação (toggle em ⚙ Ajustes). O tema dark não é forçado por
# sessão (o Streamlit não permite); é escolha do SO ou do menu do app.
present = st.session_state.get("ui_present", False)
if present:
    theme.inject_present(st)


def _exit_present() -> None:
    """Callback: desliga o modo antes do rerun (widget já instanciado)."""
    st.session_state["ui_present"] = False

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


# -- voz e assinatura do áudio (U6) --------------------------------------------
def _voice_for(persona_name: str, premium: bool) -> str:
    meta = load_persona(persona_name)
    base = meta.get("tts_voice", "pt-BR-FranciscaNeural")
    if not premium:
        return base
    return os.getenv("OPENROUTER_TTS_VOICE", "") or meta.get("tts_voice_openrouter", base)


def _audio_sig(text: str, voice: str) -> str:
    """sha1(voz + tamanho + início + fim): troca de roteiro/voz invalida o player."""
    raw = f"{voice}|{len(text)}|{text[:200]}|{text[-200:]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _valid_audio(text: str | None, voice: str) -> Path | None:
    """Só devolve o MP3 quando é do roteiro+voz atuais e existe no disco."""
    stored = st.session_state.get("mp3")
    if not (text and stored):
        return None
    path = Path(stored)
    if not path.exists():
        return None
    if st.session_state.get("mp3_sig") != _audio_sig(text, voice):
        return None
    return path


# migração de sessão antiga (mp3 sem assinatura = órfão)
if "mp3" in st.session_state and "mp3_sig" not in st.session_state:
    st.session_state.pop("mp3", None)

# -- busca --------------------------------------------------------------------
# `chat_input` só devolve texto no rerun do submit (trocar de aba do navegador ou
# perder o foco não comita texto parcial). Precisa ficar no corpo principal:
# dentro de tabs/columns/expander ele quebra o layout (fixa no rodapé do container).
submitted = st.chat_input(
    placeholder=copy.ASK_PLACEHOLDER,
    max_chars=config.MAX_QUERY_CHARS, key="q_input")
if submitted and submitted.strip():
    st.session_state["query"] = submitted.strip()

# query efetiva = última submetida (nunca o texto em edição no widget)
query = st.session_state.get("query", "")

# resultados de outro contexto (query/escopo/persona/rerank/estratégia) não valem mais
# (re-rank só entra no ctx no vetorial: alterná-lo no vectorless não rebusca)
ctx = (query, scope, persona, use_rerank if strategy == "vetorial" else None, strategy)
if st.session_state.get("ctx") != ctx:
    for k in ("pass1", "pass2", "mind", "mind_img", "mp3", "mp3_sig", "mp3_engine",
              "ui_error", "audio_notice", "top5", "cands", "ret_err"):
        st.session_state.pop(k, None)
    st.session_state["ctx"] = ctx

# -- sessão (U4): ☰ no header; reabrir turno = só restaurar estado ------------
def _restore_turn(turn: dict) -> None:
    history.restore_state(turn, scope_opts)


def _new_question() -> None:
    history.clear_artifacts()
    st.session_state["query"] = ""


def _clear_session() -> None:
    st.session_state["turns"] = []
    history.clear_artifacts()
    st.session_state["query"] = ""


def _render_session() -> None:
    """Painel ☰: turnos (mais recente primeiro) + novas ações. Sem chamada externa."""
    turns = st.session_state.get("turns") or []
    current = st.session_state.get("turn_current")
    with ph_sess:
        with st.popover(copy.SESSION_LABEL):
            if not turns:
                st.caption(copy.SESSION_EMPTY)
            for turn in turns:
                label = history.short_query(turn.get("query"))
                if turn.get("id") == current:
                    label = f"{copy.SESSION_CURRENT} {label}"
                st.button(label, key=f"turn_{turn.get('id')}", width="stretch",
                          on_click=_restore_turn, args=(turn,))
                st.caption(history.turn_meta(turn))
            st.divider()
            st.button(copy.SESSION_NEW, key="session_new", width="stretch",
                      on_click=_new_question)
            st.download_button(copy.SESSION_EXPORT,
                               data=history.export_markdown(turns),
                               file_name=copy.SESSION_EXPORT_NAME,
                               mime="text/markdown", key="session_export",
                               disabled=not turns)
            confirmed = st.checkbox(copy.SESSION_CONFIRM, key="session_confirm")
            st.button(copy.SESSION_CLEAR, key="session_clear", width="stretch",
                      disabled=not confirmed, on_click=_clear_session)


if not query:
    _render_session()
    with st.container(key="gdl_hero"):
        st.subheader(copy.EMPTY_TITLE)
        st.caption(copy.EMPTY_HELP)
    with st.container(key="gdl_chips", horizontal=True, gap="small"):
        for i, chip in enumerate(copy.EMPTY_CHIPS):
            if st.button(chip, key=f"empty_chip_{i}", width="stretch"):
                st.session_state["query"] = chip
                st.rerun()
    st.stop()

# -- U5: linha de apresentação (chips de exemplo + saída), só no modo --------
if present:
    st.caption(copy.PRESENT_HINT)
    with st.container(horizontal=True, gap="small"):
        for i, chip in enumerate(copy.EMPTY_CHIPS):
            if st.button(chip, key=f"present_chip_{i}"):
                st.session_state["query"] = chip
                st.rerun()
        st.button(copy.PRESENT_EXIT, key="present_exit", on_click=_exit_present)

q = query  # alias curto: mesma string de antes, chaves de cache de `src.generate` intactas
macro = _macro(chapter) if chapter is not None else None
scope_str = str(chapter) if chapter else "all"
addendum = load_persona(persona).get("system_addendum", "")
edge_voice = load_persona(persona).get("tts_voice", "pt-BR-FranciscaNeural")
voice_out = _voice_for(persona, premium_voice)

# -- trilha (placeholder acima das colunas; preenchido após a busca) -----------
ph_stages = st.empty()

# -- layout: coluna de leitura e rail de ações (U5: coluna única no modo
# apresentação — sem rail; a intenção vem dos cards) ---------------------------
if present:
    ph_run = st.empty()  # status inline, acima dos cards
    left = st.container()
    ph_rail = None
else:
    left, right = st.columns([2, 1], gap="medium")
    with right:
        with st.container(key="gdl_actions"):
            ph_rail = st.empty()
            ph_run = st.empty()
with left:
    with st.container(key="gdl_read"):
        ph_status = st.empty()
        ph_q = st.empty()
        ph_src = st.empty()
        ph_p1 = st.empty()
        ph_map = st.empty()
        ph_p2 = st.empty()
        ph_audio = st.empty()


# -- trilha imediata (não espera a busca; re-renderizada depois) --------------
stages.rail(q, st.session_state.get("top5") or [], st.session_state.get("pass1"),
            st.session_state.get("pass2"),
            _valid_audio((st.session_state.get("pass2") or {}).get("text"), voice_out),
            err=st.session_state.get("ret_err"), target=ph_stages)

# -- busca memoizada por contexto (nunca rebusca; nunca gasta LLM) -------------
if st.session_state.get("ret_ctx") != ctx:
    ret_err = None
    t_search = time.monotonic()
    with ph_status.container():
        label = (copy.SEARCH_RUNNING_TREE if strategy == "vectorless"
                 else copy.SEARCH_RUNNING_VECTOR)
        with st.status(label, expanded=False) as box:
            if strategy == "vectorless":
                try:
                    top5 = _treestore().search(q, chapter=chapter, use_cache=use_cache)
                    cands = top5
                except (RuntimeError, ValueError) as e:
                    ret_err = str(e)
                    top5, cands = [], []
            else:
                cands = _store().search(q, chapter=chapter, top_n=config.RETRIEVAL_PREFETCH)
                top5 = (_reranker().rerank(q, cands, top_n=config.RETRIEVAL_TOP_N)
                        if (cands and use_rerank) else cands[:config.RETRIEVAL_TOP_N])
            box.update(state="error" if ret_err else "complete",
                       label=copy.SEARCH_FAILED if ret_err else copy.SEARCH_DONE)
    ph_status.empty()
    st.session_state["ret_ctx"] = ctx
    st.session_state["top5"] = top5
    st.session_state["cands"] = cands
    st.session_state["ret_err"] = ret_err
    st.session_state["ret_elapsed"] = time.monotonic() - t_search

top5 = st.session_state.get("top5", [])
cands = st.session_state.get("cands", top5)
ret_err = st.session_state.get("ret_err")
has_sources = not ret_err and bool(top5)


# -- pipeline (mesmas chamadas de antes, agora sem rerun cego) ------------------
def _synth(text: str, force: bool = False) -> tuple[Path, str]:
    """Premium com queda para Edge (mesma política de antes); nunca engole erro de Edge.

    `force=True` (↻ Regerar áudio) ignora o cache de áudio daquela voz.
    """
    read_cache = use_cache and not force
    if premium_voice:
        try:
            mp3, engine, n = synthesize_premium(text, voice_out, use_cache=read_cache)
            return Path(mp3), f"{engine} ({n} fatia(s))"
        except RuntimeError:
            st.session_state["audio_notice"] = copy.AUDIO_NOTICE_PREMIUM
    mp3, engine = synthesize(text, edge_voice, read_cache)
    return Path(mp3), engine


def _run(intent: str, box, force: bool = False) -> None:
    """Executa a intenção e grava em session_state. Falha vira card com ação.

    `force=True` (botão ↻ Regerar) ignora o cache **daquele** estágio e invalida
    o que depende dele (novo resumo derruba roteiro+áudio; novo roteiro derruba
    o áudio), para nunca servir conteúdo baseado em texto velho.
    """
    s = st.session_state
    s.pop("ui_error", None)
    s.pop("audio_notice", None)
    p1 = s.get("pass1")
    stage = "resumo"

    def _drop(*keys: str) -> None:
        for k in keys:
            s.pop(k, None)

    try:
        if intent in ("listen", "pass1", "pass2", "map"):
            fresh_p1 = force and intent == "pass1"
            if fresh_p1 or not p1:
                if box:
                    box.update(label=copy.STEP_RESUMO)
                text, prov, cached = get_pass1(q, scope_str, top5, macro, addendum,
                                               use_cache and not fresh_p1)
                p1 = s["pass1"] = {"text": text, "provider": prov, "cached": cached,
                                   "chained": intent in ("listen", "pass2", "map"),
                                   "chunk_sig": chunk_sig_of(top5), "persona": persona}
                # resumo (re)gerado: roteiro, áudio, mapa e imagem antigos não valem mais
                _drop("pass2", "mind", "mind_img", "mp3", "mp3_sig", "mp3_engine",
                      "audio_notice")
        stage = "roteiro"
        fresh_p2 = force and intent == "pass2"
        if intent in ("listen", "pass2") and (fresh_p2 or not s.get("pass2")):
            if box:
                box.update(label=copy.STEP_ROTEIRO)
            text, prov, cached = get_pass2(q, scope_str, persona, p1["text"],
                                           p1["chunk_sig"], use_cache and not fresh_p2)
            s["pass2"] = {"text": text, "provider": prov, "cached": cached,
                          "chars": len(clean_for_speech(text)), "voice": voice_out}
            # roteiro novo: o áudio antigo deixa de corresponder
            _drop("mp3", "mp3_sig", "mp3_engine", "audio_notice")
        stage = "audio"
        if intent in ("listen", "audio") and s.get("pass2"):
            if premium_voice and not s.get("confirm_premium", False):
                s["ui_error"] = {"stage": "audio", "msg": copy.PREMIUM_GATE,
                                 "hint": copy.PREMIUM_GATE}
                return
            if box:
                box.update(label=copy.STEP_AUDIO)
            mp3, engine = _synth(s["pass2"]["text"], force)
            s["mp3"] = str(mp3)
            s["mp3_sig"] = _audio_sig(s["pass2"]["text"], voice_out)
            s["mp3_engine"] = engine
        stage = "mapa"
        if intent == "map" and p1:
            if box:
                box.update(label=copy.STEP_MAPA)
            outline, prov, cached = build_outline(
                p1["text"], q, scope_str, use_cache and not force)
            s["mind"] = {"svg": outline_to_svg(outline),
                         "provider": prov, "cached": cached, "outline": outline}
            # mapa novo: a imagem ilustrada do mapa antigo não corresponde mais
            s.pop("mind_img", None)
        stage = "imagem"
        if intent == "image":
            mind = s.get("mind") or {}
            if not mind.get("outline"):
                raise RuntimeError("Gere o mapa mental antes de estilizar a imagem.")
            if box:
                box.update(label=copy.STEP_IMAGEM)
            png, meta = image_provider.generate(
                outline_to_prompt(mind["outline"]), use_cache=use_cache and not force)
            s["mind_img"] = {"path": str(png), "model": meta.get("model"),
                             "cost": meta.get("cost"),
                             "cached": bool(meta.get("cached"))}
    except (RuntimeError, ValueError) as e:
        s["ui_error"] = {"stage": stage, "msg": str(e)}


def _queue(intent: str, force: bool = False) -> None:
    """Callback: o clique vira intenção no próximo run, antes de renderizar os cards."""
    st.session_state["queued_intent"] = {"intent": intent, "force": force}


def _retry(stage: str) -> None:
    st.session_state.pop("ui_error", None)
    st.session_state["queued_intent"] = {"intent": copy.STAGE_RETRY.get(stage, "pass1"),
                                         "force": False}


def _retry_search() -> None:
    st.session_state.pop("ret_ctx", None)


# -- rail de ações → intenção (rail ou clique num card do run anterior) --------
p2_now = st.session_state.get("pass2")
intent = None
if ph_rail is not None:
    with ph_rail.container():
        intent = actions.rail(has_sources=has_sources,
                              script_chars=(p2_now or {}).get("chars"),
                              premium=premium_voice,
                              has_p1=bool(st.session_state.get("pass1")),
                              has_p2=bool(p2_now))
queued = st.session_state.pop("queued_intent", None)
if isinstance(queued, str):  # compat: fila antiga era só a string do intent
    queued = {"intent": queued, "force": False}
force = False
if queued:
    intent = intent or queued.get("intent")
    force = bool(queued.get("force")) and intent == queued.get("intent")

if intent:
    with ph_run.status(copy.RUN_LABEL.get(intent, copy.RUN_LABEL["listen"]),
                       expanded=True) as box:
        t0 = time.monotonic()
        _run(intent, box, force)
        elapsed = time.monotonic() - t0
        failed = bool(st.session_state.get("ui_error"))
        box.update(state="error" if failed else "complete",
                   label=(copy.RUN_FAILED if failed
                          else f"{copy.RUN_DONE} · {elapsed:.0f} s"),
                   expanded=failed)

# trilha de estágios (preenchida depois da execução: mesmo run, sem piscar)
stages.rail(q, top5, st.session_state.get("pass1"), st.session_state.get("pass2"),
            _valid_audio((st.session_state.get("pass2") or {}).get("text"), voice_out),
            err=ret_err, target=ph_stages)

# -- leitura: pergunta, fontes, resumo, roteiro, áudio ------------------------
with ph_q.container(border=True, key="gdl_card_q"):
    st.markdown(f"**{q}**")
    st.caption(copy.context_line(len(top5), persona, strategy, use_rerank))
    st.button(copy.NEW_QUESTION, key="new_question", on_click=_new_question)


def _render_sources() -> None:
    sources.render(ph_src, top5, cands, strategy, macro, chapter,
                   err=ret_err, on_retry=_retry_search)

_render_sources()


def _error_card(stage: str) -> bool:
    err = st.session_state.get("ui_error") or {}
    if err.get("stage") != stage:
        return False
    st.error(err.get("hint") or copy.STAGE_ERROR[stage])
    st.button(copy.RETRY, key=f"retry_{stage}", on_click=_retry, args=(stage,))
    if not err.get("hint"):
        with st.expander(copy.DETAILS):
            st.write(err.get("msg", ""))
    return True


def _regen_button(key: str, intent: str) -> None:
    """↻ Regerar: refaz só este estágio ignorando o cache (não toca no áudio)."""
    st.caption(copy.REGERAR_HINT)
    st.button(copy.REGERAR, key=key, on_click=_queue, args=(intent, True))


# resumo técnico
p1 = st.session_state.get("pass1")
with ph_p1.container(border=True, key="gdl_card_p1"):
    st.markdown(f"**{copy.PASS1_TITLE}**")
    if not _error_card("resumo"):
        if p1:
            st.caption(copy.provenance(p1["provider"], p1["cached"],
                                       p1.get("chained", False)))
            render_mixed(st, p1["text"])
            _regen_button("regen_p1", "pass1")
        else:
            st.caption(copy.P1_EMPTY)
            st.button(copy.BTN_GEN_P1, width="stretch", key="gen_p1",
                      disabled=not has_sources, on_click=_queue, args=("pass1",))

# mapa mental (M0: SVG determinístico, US$ 0)
mind = st.session_state.get("mind")
if config.MINDMAP_ENABLED:
    with ph_map.container(border=True, key="gdl_card_map"):
        st.markdown(f"**{copy.MINDMAP_TITLE}**")
        if not _error_card("mapa"):
            if mind:
                st.caption(copy.provenance(mind["provider"], mind["cached"]))
                st.markdown(mindmap_view.embed(mind["svg"]), unsafe_allow_html=True)
                url = mindmap_view.publish(mind["svg"], q)
                if url:
                    st.link_button(copy.MINDMAP_FULLSCREEN, url, width="stretch")
                    st.caption(copy.MINDMAP_ZOOM_HINT)
                else:
                    st.caption(copy.MINDMAP_STATIC_OFF)
                mindmap_view.download(mind["svg"])
                # M1: imagem ilustrada é ADICIONAL — o SVG acima nunca some
                if not _error_card("imagem"):
                    img = st.session_state.get("mind_img")
                    if img and not Path(img.get("path", "")).exists():
                        img = None
                    if img:
                        st.image(img["path"], width="stretch")
                        cost = img.get("cost")
                        cost_txt = (f"US$ {cost:.4f}"
                                    if isinstance(cost, (int, float))
                                    else "custo não informado")
                        caption = f"{img.get('model') or ''} · {cost_txt}"
                        if img.get("cached"):
                            caption += " · cache"
                        st.caption(caption)
                        st.button(copy.MINDMAP_IMAGE_REGEN, key="regen_img",
                                  width="stretch", on_click=_queue,
                                  args=("image", True))
                    elif image_provider.enabled():
                        st.button(copy.MINDMAP_STYLE_BTN, key="style_img",
                                  width="stretch", on_click=_queue, args=("image",),
                                  help=copy.MINDMAP_STYLE_HELP.format(
                                      model=config.IMAGE_MODEL))
                    else:
                        st.caption(copy.MINDMAP_IMAGE_OFF)
                if mind.get("provider") == "heuristic":
                    st.warning(copy.MINDMAP_HEURISTIC)
                _regen_button("regen_map", "map")
            else:
                st.caption(copy.MINDMAP_SUBTITLE)
                st.button(copy.MINDMAP_BTN, width="stretch", key="gen_map",
                          disabled=not has_sources, on_click=_queue, args=("map",))

# roteiro falado
p2 = st.session_state.get("pass2")
with ph_p2.container(border=True, key="gdl_card_p2"):
    st.markdown(f"**{copy.PASS2_TITLE}**")
    if not _error_card("roteiro"):
        if p2:
            st.caption(f"{copy.provenance(p2['provider'], p2['cached'])} · "
                       f"≈{copy.audio_minutes(p2['chars']):g} min")
            st.markdown(p2["text"])
            if p2["chars"] > config.TTS_MAX_CHARS:
                st.warning(f"Roteiro com {p2['chars']} chars limpos excede o limite de "
                           f"TTS_MAX_CHARS={config.TTS_MAX_CHARS}. Encurte o roteiro "
                           f"(ou aumente o limite no `.env`) antes de gerar áudio.")
            _regen_button("regen_p2", "pass2")
        else:
            st.caption(copy.P2_EMPTY)
            st.button(copy.BTN_GEN_P2, width="stretch", key="gen_p2",
                      disabled=not has_sources, on_click=_queue, args=("pass2",))

# áudio
mp3 = _valid_audio((p2 or {}).get("text"), voice_out)
audio_allowed = (not premium_voice) or bool(st.session_state.get("confirm_premium", False))
with ph_audio.container(border=True, key="gdl_card_audio"):
    st.markdown(f"**{copy.AUDIO_TITLE}**")
    if not _error_card("audio"):
        if st.session_state.get("audio_notice"):
            st.info(st.session_state["audio_notice"])
        if not p2:
            st.caption(copy.AUDIO_EMPTY)
        elif mp3:
            st.caption(copy.AUDIO_IN_DOCK)
            st.button(copy.BTN_AUDIO_REGEN, width="stretch", key="gen_audio",
                      disabled=not audio_allowed,
                      on_click=_queue, args=("audio", True))
        elif st.session_state.get("mp3"):
            st.info(copy.AUDIO_ORPHAN)
            st.button(copy.BTN_AUDIO_REGEN, width="stretch", key="gen_audio",
                      disabled=not audio_allowed,
                      on_click=_queue, args=("audio",))
        else:
            st.caption(copy.audio_label(p2["chars"]))
            st.button(copy.BTN_GEN_AUDIO, width="stretch", key="gen_audio",
                      disabled=not audio_allowed,
                      on_click=_queue, args=("audio",))
        if p2 and not audio_allowed:
            st.caption(copy.PREMIUM_GATE)

# -- U5: player dock fixo (só com áudio válido do roteiro/voz atuais) ----------
if mp3:
    with st.container(key="gdl_dock"):
        player.render(
            mp3,
            title=history.short_query(q, copy.DOCK_QUERY_CHARS),
            meta=copy.dock_meta(p2["chars"], voice_out,
                                st.session_state.get("mp3_engine", "")),
            download_name=f"gdl-audio{mp3.suffix}",
            sig=st.session_state.get("mp3_sig"),
        )

# -- sessão (U4): salva o turno atual e preenche o ☰ (já com o áudio de agora) --
top5_now = st.session_state.get("top5") or []
if query and top5_now:
    p1_now = st.session_state.get("pass1")
    p2_now = st.session_state.get("pass2")
    mp3_now = _valid_audio((p2_now or {}).get("text"), voice_out)
    turn = history.build_turn(
        query=query, scope=scope, persona=persona, strategy=strategy,
        rerank=bool(use_rerank) if strategy == "vetorial" else False,
        chapter=chapter, ctx=ctx, top5=top5_now, pass1=p1_now, pass2=p2_now,
        mp3=str(mp3_now) if mp3_now else None,
        mp3_sig=st.session_state.get("mp3_sig") if mp3_now else None,
        mp3_engine=st.session_state.get("mp3_engine") if mp3_now else None,
        premium=premium_voice)
    turns = history.upsert(st.session_state.get("turns") or [], turn)
    st.session_state["turns"] = turns
    saved = next((t for t in turns if tuple(t.get("key") or ()) == turn["key"]), turn)
    st.session_state["turn_current"] = saved["id"]

_render_session()
