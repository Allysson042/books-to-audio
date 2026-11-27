"""Trilha dos 5 estágios (Pergunta → Fontes → Resumo → Roteiro → Áudio).

Não é navegável e não tem clique: é só o estado da história, derivado do
`session_state`. Estado nunca é só cor (§2 do guia), por isso cada estágio
carrega símbolo + nome.
"""

from __future__ import annotations

import streamlit as st

from src.ui import copy

DONE = ":green[●]"
ACTIVE = "◐"
EMPTY = "○"
ERROR = ":red[✕]"

_SYMBOL = {"done": DONE, "active": ACTIVE, "empty": EMPTY, "error": ERROR}


def derive(query: str, top5, pass1, pass2, audio, err: str | None = None) -> dict:
    """Estados por estágio. O primeiro estágio pendente fica `active` (◐)."""
    has_sources = bool(top5)
    states = {
        "pergunta": "done" if query else "active",
        "fontes": "error" if err else ("done" if has_sources else ("active" if query else "empty")),
        "resumo": "done" if pass1 else "empty",
        "roteiro": "done" if pass2 else "empty",
        "audio": "done" if audio else "empty",
    }
    if not err and has_sources:
        for key in ("resumo", "roteiro", "audio"):
            if states[key] != "done":
                states[key] = "active"
                break
    return states


def rail(query: str, top5, pass1, pass2, audio, err: str | None = None, *,
         target=None) -> None:
    """Uma linha: `● Pergunta · ● Fontes · ◐ Resumo · ○ Roteiro · ○ Áudio`."""
    states = derive(query, top5, pass1, pass2, audio, err)
    line = " · ".join(f"{_SYMBOL[states[key]]} {label}"
                      for key, label in zip(("pergunta", "fontes", "resumo",
                                             "roteiro", "audio"), copy.STAGES))
    (target or st).markdown(line)
