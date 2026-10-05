"""Renderização híbrida do Pass1: prosa via markdown, matemática via LaTeX.

O parser de markdown do Streamlit mastiga `_ { }` antes do KaTeX ver a equação,
então quebramos o texto em segmentos e renderizamos cada um no componente certo.
Fallback: LaTeX malformado vira bloco de código em vez de erro visível.
"""

from __future__ import annotations

import re

# SÓ blocos display vão p/ st.latex (que sempre renderiza em bloco, com quebra de linha).
# Inline ($...$, \(...\)) fica dentro do st.markdown: o markdown-it não toca em _{...}
# e o KaTeX do frontend renderiza inline sem quebrar linha.
PAT = re.compile(r"(\$\$.+?\$\$|\\\[.+?\\\])", re.DOTALL)


def split_math(text: str) -> list[tuple[str, str]]:
    """Devolve [(kind, conteúdo)] onde kind é 'math' (bloco, sem delimitadores) ou 'text'."""
    out: list[tuple[str, str]] = []
    for part in PAT.split(text):
        if not part:
            continue
        if part.startswith("$$") and part.endswith("$$"):
            out.append(("math", part[2:-2].strip()))
        elif part.startswith("\\[") and part.endswith("\\]"):
            out.append(("math", part[2:-2].strip()))
        else:
            out.append(("text", part))
    return out


def render_mixed(st, text: str) -> None:
    """Renderiza no Streamlit: markdown p/ prosa, st.latex p/ equações."""
    for kind, content in split_math(text):
        if kind == "math":
            try:
                st.latex(content)
            except Exception:
                st.code(content, language="latex")
        else:
            st.markdown(content)
