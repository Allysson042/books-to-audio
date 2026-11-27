"""Histórico de sessão (U4): turnos reabríveis sem tocar em LLM/TTS.

Contrato: `docs/UX/06-guia-visual.md` §5 ("Sessão") e §8. Um turno guarda só
textos e metadados (`top5`/`pass1`/`pass2` já são dicts JSON puros); nada de
objetos de runtime. Reabrir um turno é só restaurar `session_state` — nenhuma
chamada externa (busca, LLM, TTS) é disparada por este módulo.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

import streamlit as st

from src.ui import copy

MAX_TURNS = 8
QUERY_CHARS = 42


# -- derivações puras ---------------------------------------------------------
def turn_key(query, scope, persona, strategy, rerank) -> tuple:
    """Identidade do turno: a mesma combinação é sempre o mesmo turno."""
    return (query or "", scope or "", persona or "", strategy or "", bool(rerank))


def turn_id(key: tuple) -> str:
    """Id estável derivado da `key` (updates mantêm o mesmo id)."""
    raw = "|".join(str(part) for part in key)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def build_turn(*, query: str, scope: str, persona: str, strategy: str, rerank: bool,
               chapter: int | None, ctx: tuple, top5: list[dict] | None,
               pass1: dict | None = None, pass2: dict | None = None,
               mp3: str | None = None, mp3_sig: str | None = None,
               mp3_engine: str | None = None, premium: bool = False,
               ts: str | None = None, id_: str | None = None) -> dict:
    """Monta o turno do estado atual. `ts`/`id` só nascem na criação."""
    key = turn_key(query, scope, persona, strategy, rerank)
    return {
        "id": id_ or turn_id(key),
        "ts": ts or datetime.now().isoformat(timespec="seconds"),
        "key": key,
        "query": query,
        "scope": scope,
        "persona": persona,
        "strategy": strategy,
        "rerank": bool(rerank),
        "chapter": chapter,
        "ctx": tuple(ctx),
        "top5": list(top5 or []),
        # `cands` (top-20) não é guardado: memória. Reabrir usa top5 no debug.
        "cands": None,
        "pass1": pass1,
        "pass2": pass2,
        "mp3": mp3,
        "mp3_sig": mp3_sig,
        "mp3_engine": mp3_engine,
        "premium": bool(premium),
    }


def upsert(turns: list[dict] | None, turn: dict) -> list[dict]:
    """Insere/replace pelo `key`: mais recente primeiro, máximo `MAX_TURNS`.

    Atualizar um turno existente mantém o `id`/`ts` e a posição (cronologia
    preservada); só um turno novo vai para o topo.
    """
    turns = list(turns or [])
    key = tuple(turn.get("key") or ())
    out: list[dict] = []
    merged = dict(turn)
    merged["key"] = key
    replaced = False
    for old in turns:
        if not replaced and tuple(old.get("key") or ()) == key:
            merged["id"] = old.get("id", merged.get("id"))
            merged["ts"] = old.get("ts", merged.get("ts"))
            out.append(merged)
            replaced = True
        else:
            out.append(old)
    if not replaced:
        out.insert(0, merged)
    return out[:MAX_TURNS]


def scope_short(scope: str | None) -> str:
    """`Cap 4 · Variational Autoencoders` → `Cap 4` (label completo no widget)."""
    return (scope or "").split(" · ", 1)[0].strip() or copy.SCOPE_ALL


def short_query(query: str | None, limit: int = QUERY_CHARS) -> str:
    """Pergunta truncada em palavra para o botão do ☰."""
    flat = " ".join((query or "").split())
    if len(flat) <= limit:
        return flat
    cut = flat[: limit - 1].rsplit(" ", 1)[0].rstrip(" .,;:")
    return f"{cut or flat[: limit - 1]}…"


def ts_short(ts: str | None) -> str:
    return (ts or "")[11:16] or "--:--"


def turn_meta(turn: dict) -> str:
    """`Cap 4 · 14:02 · resumo + roteiro + áudio` (só o que existe)."""
    parts = [scope_short(turn.get("scope")), ts_short(turn.get("ts"))]
    have = [copy.TURN_PARTS[k] for k in ("pass1", "pass2", "mp3") if turn.get(k)]
    if have:
        parts.append(" + ".join(have))
    return " · ".join(parts)


def export_markdown(turns: list[dict] | None, now: datetime | None = None) -> str:
    """Sessão em `.md`: ordem cronológica, seções só quando existem."""
    ordered = sorted(turns or [], key=lambda t: t.get("ts") or "")
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    lines = [copy.EXPORT_TITLE, f"_gerado em {stamp}_", ""]
    for i, turn in enumerate(ordered, 1):
        lines.append(f"## {i}. {turn.get('query', '')}")
        meta = [
            scope_short(turn.get("scope")),
            copy.PERSONA_LABELS.get(turn.get("persona"), turn.get("persona") or ""),
            copy.STRATEGY_LABELS.get(turn.get("strategy"), turn.get("strategy") or ""),
        ]
        lines.append(f"_{' · '.join(part for part in meta if part)}_")
        lines.append("")
        sources = turn.get("top5") or []
        if sources:
            lines.append(copy.EXPORT_SOURCES)
            for item in sources:
                section = (item.get("metadata") or {}).get("section", "")
                citation = item.get("citation", "")
                lines.append(f"- {citation} · {section}" if section else f"- {citation}")
            lines.append("")
        p1 = turn.get("pass1") or {}
        if p1.get("text"):
            lines += [copy.EXPORT_RESUMO, p1["text"].strip(), ""]
        p2 = turn.get("pass2") or {}
        if p2.get("text"):
            lines += [copy.EXPORT_ROTEIRO, p2["text"].strip(), ""]
    return "\n".join(lines).rstrip() + "\n"


# -- restauração (só estado; nunca busca/LLM/TTS) -----------------------------
_ARTIFACTS = ("pass1", "pass2", "mp3", "mp3_sig", "mp3_engine",
              "audio_notice", "ui_error")


def restore_state(turn: dict, scope_opts: list[str] | None = None) -> None:
    """Callback de clique no turno: repõe widgets e artefatos, ponto.

    Roda **antes** do script (on_click), então o pipeline encontra `ctx` e
    `ret_ctx` iguais e não rebusca nem regenera nada.
    """
    s = st.session_state
    s["query"] = turn.get("query", "")

    scope = turn.get("scope")
    if scope_opts is not None and scope not in scope_opts:
        scope = copy.SCOPE_ALL
    s["ui_scope"] = scope
    s["ui_persona"] = copy.PERSONA_LABELS_BY_SLUG.get(turn.get("persona"), "Técnico")
    s["ui_strategy"] = copy.STRATEGY_LABELS_BY_SLUG.get(turn.get("strategy"),
                                                        "Sumário navegável")
    s["ui_rerank"] = bool(turn.get("rerank"))
    s["ui_premium"] = bool(turn.get("premium"))
    s["confirm_premium"] = bool(turn.get("premium"))  # turno pago já confirmado

    s["ctx"] = s["ret_ctx"] = tuple(turn.get("ctx") or ())
    s["top5"] = list(turn.get("top5") or [])
    s["cands"] = list(turn.get("cands") or s["top5"])
    s["ret_err"] = None

    for key in _ARTIFACTS:
        value = turn.get(key)
        if value:
            s[key] = value
        else:
            s.pop(key, None)

    s["turn_current"] = turn.get("id")
    s.pop("queued_intent", None)


def clear_artifacts() -> None:
    """Limpa o turno atual (mantém `turns` e os ajustes do header)."""
    s = st.session_state
    for key in _ARTIFACTS + ("top5", "cands", "ret_err", "ctx", "ret_ctx",
                             "turn_current", "queued_intent"):
        s.pop(key, None)
