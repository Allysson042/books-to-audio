"""Tema do produto: tokens (light/dark), CSS mínimo e utilidades de mídia.

Contrato visual: `docs/UX/06-guia-visual.md` §3 (tokens), §4 (medidas) e §6 (dark).
O grosso do tema vem de `.streamlit/config.toml`; aqui só há o que o Streamlit não
expressa em config (largura de página, respiro do título, utilitários de layout).
"""

from __future__ import annotations

from pathlib import Path

# Pares light/dark canônicos (§3). O dark é explícito, nunca inversão automática.
TOKENS: dict[str, dict[str, str]] = {
    "bg": {"light": "#FBFAF7", "dark": "#12110F"},
    "surface": {"light": "#FFFFFF", "dark": "#1A1917"},
    "alt": {"light": "#F2EFE9", "dark": "#24221F"},
    "border": {"light": "#E4DFD5", "dark": "#33302B"},
    "text": {"light": "#1B1A17", "dark": "#EDEAE3"},
    "muted": {"light": "#5C574E", "dark": "#A8A29A"},
    "primary": {"light": "#0E6F63", "dark": "#4FD1BD"},
    "primary-weak": {"light": "#E3F1EE", "dark": "#14332F"},
    "on-primary": {"light": "#FFFFFF", "dark": "#06231F"},
    "accent": {"light": "#6D28D9", "dark": "#A78BFA"},
    "on-accent": {"light": "#FFFFFF", "dark": "#1B1030"},
    "accent-weak": {"light": "#EDE7FD", "dark": "#241B3F"},
    "success": {"light": "#157F3D", "dark": "#4ADE80"},
    "warning": {"light": "#A15C07", "dark": "#FBBF24"},
    "error": {"light": "#B3261E", "dark": "#F87171"},
    "error-weak": {"light": "#FBEAE8", "dark": "#2A1615"},
}

# Só geometria/respiro + utilitários. Cores sempre via vars do Streamlit para
# acompanhar o tema escolhido (claro/escuro). Nada de reset global ou chrome.
CSS = """
<style>
[data-testid="stAppViewContainer"] .block-container {
  max-width: 1120px;
  padding-top: 2.4rem;
  /* U5: respiro para o player dock (sticky) + input não cobrirem o fim. */
  padding-bottom: 13rem;
}
/* Superfície dos cards: `st.container(border=True)` só desenha a borda; sem
   background o card herda o `bg` e some no dark. Tokens por tema abaixo. */
:root {
  __GDL_SURFACE__
}
[class*="st-key-gdl_card"] {
  background: var(--secondary-background-color);
  background: var(--gdl-surface);
  border-color: var(--gdl-border);
  border-radius: 12px;
  color: var(--gdl-text);
}
[data-testid="stAppViewContainer"] h1 {
  font-size: 1.625rem;
  line-height: 2.125rem;
  font-weight: 700;
  margin: 0 0 0.25rem;
}
[data-testid="stAppViewContainer"] h1 + [data-testid="stCaptionContainer"] {
  margin-top: 0;
  margin-bottom: 1.5rem;
}
.gdl-hero,
.st-key-gdl_hero {
  margin: 1.5rem 0 0.25rem;
}
.gdl-chips,
.st-key-gdl_chips {
  gap: 0.5rem;
  margin: 0.5rem 0 1rem;
}
.gdl-chips .stButton > button,
.st-key-gdl_chips .stButton > button {
  background: var(--secondary-background-color);
  color: var(--text-color);
  border: 1px solid var(--secondary-background-color);
  border-radius: 999px;
  padding: 0.4rem 0.8rem;
  font-size: 0.8125rem;
  white-space: nowrap;
}
.gdl-chips .stButton > button:hover,
.st-key-gdl_chips .stButton > button:hover {
  border-color: var(--primary-color);
  color: var(--text-color);
}
/* U1: coluna de leitura com medida controlada; rail de ações sticky. */
.st-key-gdl_read {
  max-width: 95ch;
}
.st-key-gdl_actions {
  position: sticky;
  top: 1rem;
  align-self: start;
}
.st-key-gdl_stages {
  margin: 0 0 1rem;
  font-size: 0.781rem;
  letter-spacing: 0.01em;
}
.st-key-gdl_stages {
  margin: 0 0 1rem;
  font-size: 0.781rem;
  letter-spacing: 0.01em;
}
/* U3: barra de relevância das fontes (78×5, §5 do guia). */
.gdl-rel {
  width: 78px;
  height: 5px;
  margin: 0.2rem 0 0.1rem;
  border-radius: 999px;
  background: var(--secondary-background-color);
  overflow: hidden;
}
.gdl-rel > i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--primary-color);
}
/* U5: player dock — barra fixa logo acima do input (§5 do guia).
   `fixed` (não sticky): fica no rodapé mesmo quando a página não rola. */
.st-key-gdl_dock {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 8rem;
  z-index: 100;
  background: var(--secondary-background-color);
  background: var(--gdl-surface);
  border-top: 1px solid var(--gdl-border);
  border-radius: 0;
  padding: 0.35rem max(1rem, calc((100vw - 1120px) / 2)) 0.45rem;
}
/* U5: foco visível (§10) — não depende de cor como único sinal. */
:where(button, a, input, [role="tab"]):focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}
</style>
"""

# U5: modo apresentação — leitura em coluna única, tipografia maior (§5, U5).
# Emitido só quando o modo está ligado; reemitir a cada run (mesma regra do CSS).
PRESENT_CSS = """
<style>
.st-key-gdl_read { max-width: 760px; }
.st-key-gdl_read p,
.st-key-gdl_read li { font-size: 1.05rem; line-height: 1.8; }
</style>
"""

def _surface_tokens(st) -> str:
    """Tokens da superfície dos cards/dock (§3 + §6).

    `st.context.theme.type` é a fonte principal; `None` (primeiro load/AppTest)
    cai em `color-mix` sobre as vars do Streamlit (nunca só media query).
    """
    theme_type = theme_type_of(st)
    if theme_type in ("light", "dark"):
        return (f"--gdl-surface:{TOKENS['surface'][theme_type]};"
                f"--gdl-border:{TOKENS['border'][theme_type]};"
                f"--gdl-text:{TOKENS['text'][theme_type]};")
    return ("--gdl-surface:color-mix(in srgb, var(--background-color) 94%, "
            "var(--text-color) 6%);"
            "--gdl-border:color-mix(in srgb, var(--text-color) 12%, transparent);"
            "--gdl-text:var(--text-color);")


def theme_type_of(st) -> str | None:
    """`"light" | "dark" | None` — tolerante a contextos sem browser/AppTest."""
    try:
        return getattr(st.context.theme, "type", None) or None
    except Exception:  # noqa: BLE001 — tema nunca derruba o app
        return None


def inject(st) -> None:
    """Emite o CSS a cada rerun (o Streamlit reconstrói a árvore de elementos;
    sem reemitir, o `<style>` desaparece). Elemento leve, sem estado."""
    css = CSS.replace("__GDL_SURFACE__", _surface_tokens(st))
    st.markdown(css, unsafe_allow_html=True)


def inject_present(st) -> None:
    """CSS do modo apresentação (U5); também reemitido a cada run."""
    st.markdown(PRESENT_CSS, unsafe_allow_html=True)


def audio_mime(path: str | Path) -> str | None:
    """MIME pelo sufixo real do arquivo (Piper pode devolver `.wav`)."""
    suffix = Path(path).suffix.lower()
    return {".mp3": "audio/mpeg", ".wav": "audio/wav"}.get(suffix)