"""Rail de ações (coluna direita, sticky).

Um único CTA primário (`▶ Ouvir`) encadeia resumo → roteiro → áudio; os dois
secundários geram só uma etapa. Custo e estimativa ficam visíveis no rail
(nunca só no `help`). Devolve a intenção clicada, sem executar nada.
"""

from __future__ import annotations

import streamlit as st

from src.ui import copy


def rail(has_sources: bool, script_chars: int | None, premium: bool,
         has_p1: bool = False, has_p2: bool = False) -> str | None:
    """Retorna `"listen" | "pass1" | "pass2" | None` (clique deste run).

    Os secundários só existem enquanto o artefato não existe: com conteúdo na
    tela, regenerar é papel do `↻ Regerar` do card (nunca de no-op).
    """
    intent = None

    confirmed = True
    if premium:
        confirmed = st.checkbox(copy.PREMIUM_CONFIRM, key="confirm_premium")

    blocked = (not has_sources) or (premium and not confirmed)
    if st.button(copy.BTN_LISTEN, type="primary", width="stretch",
                 disabled=blocked, key="act_listen"):
        intent = "listen"
    if not has_p1 and st.button(copy.BTN_PASS1, width="stretch",
                                disabled=not has_sources, key="act_pass1"):
        intent = intent or "pass1"
    if not has_p2 and st.button(copy.BTN_PASS2, width="stretch",
                                disabled=not has_sources, key="act_pass2"):
        intent = intent or "pass2"

    cost = copy.PREMIUM_COST if premium else copy.FREE_COST
    if script_chars:
        st.caption(f"≈{copy.audio_minutes(script_chars):g} min · {cost}")
    else:
        st.caption(f"{copy.CHAIN_HINT} · {cost}")
    if not has_sources:
        st.caption(copy.RAIL_NEEDS_QUERY)
    elif premium and not confirmed:
        st.caption(copy.PREMIUM_CONFIRM)
    return intent
