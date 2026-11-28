"""Visualização ampliada do mapa mental M0: HTML standalone em `static/mind/`.

O SVG continua sendo gerado por `src/mindmap.py` (não tocamos em outline, SVG,
LLM ou cache). Aqui só publicamos uma cópia navegável, com tema e legibilidade
própria, para abrir em nova aba sem depender do iframe pequeno do Streamlit.

Sem static serving (`player.enabled()` falso) não publicamos nada: o app cai no
download do SVG — nunca levanta exceção.
"""

from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path

import streamlit as st

from src.ui import copy, player, theme

MIND_DIR = player.STATIC_DIR / "mind"
URL_PREFIX = f"{player.URL_PREFIX}/mind"
KEEP_FILES = 20

_VIEWBOX = re.compile(
    r'viewBox="\s*-?[\d.]+\s*[, ]\s*-?[\d.]+\s*[, ]\s*([\d.]+)\s*[, ]\s*([\d.]+)\s*"'
)
_WIDTH = re.compile(r'\swidth="[^"]*"')
_HEIGHT = re.compile(r'\sheight="[^"]*"')

# `__BODY_ATTR__` = `data-theme="light|dark"` quando o Streamlit conhece o tema;
# vazio deixa a media query `prefers-color-scheme` decidir.
_HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Mapa mental — __TITLE__</title>
<style>
  html,body{margin:0;background:#FBFAF7;color:#1B1A17}
  body[data-theme="dark"]{background:#12110F;color:#EDEAE3}
  @media (prefers-color-scheme: dark){body:not([data-theme]){background:#12110F;color:#EDEAE3}}
  body{margin:0;font:13px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;overflow:hidden}
  .bar{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:8px 16px;border-bottom:1px solid rgba(128,128,128,.25)}
  .bar .title{font-weight:600;opacity:.8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .bar .tools{display:flex;gap:8px;align-items:center;flex:none}
  .bar button{font:inherit;line-height:1;padding:6px 10px;border-radius:8px;cursor:pointer;border:1px solid rgba(128,128,128,.4);background:transparent;color:inherit}
  .bar button:hover{border-color:rgba(128,128,128,.8)}
  .bar a{color:inherit;font-size:12px;opacity:.8;text-decoration:none}
  .bar a:hover{opacity:1;text-decoration:underline}
  .wrap{height:calc(100vh - 48px);overflow:auto;display:flex;align-items:center;justify-content:center}
  .stage{width:100%;transform-origin:center top;transition:transform .12s ease}
  .stage svg{width:100%;height:calc(100vh - 96px);display:block}
  @media (max-width:1280px){
    body{overflow:auto}
    .wrap{display:block;height:auto;overflow:auto}
    .stage{width:auto}
    .stage svg{min-width:1200px;width:1200px;height:auto}
  }
</style></head><body __BODY_ATTR__>
<div class="bar"><span class="title">Mapa mental · __TITLE__</span>
<div class="tools">
<button type="button" onclick="zoom(-0.15)" title="Menos zoom" aria-label="Menos zoom">−</button>
<button type="button" onclick="zoom(0.15)" title="Mais zoom" aria-label="Mais zoom">+</button>
<button type="button" onclick="fit()">Ajustar</button>
<a href="__HASH__.svg" download="mapa-mental.svg">Baixar SVG</a>
<a href="__HASH__.svg" target="_blank" rel="noopener">Abrir original</a>
</div></div>
<div class="wrap"><div class="stage">__SVG__</div></div>
<script>
var z = 1, stage = document.querySelector('.stage');
function apply() { stage.style.transform = 'scale(' + z + ')'; }
function zoom(d) { z = Math.min(2.5, Math.max(0.6, z + d)); apply(); }
function fit() { z = 1; apply(); }
</script>
</body></html>
"""


def _body_attr() -> str:
    theme_type = theme.theme_type_of(st)
    return f'data-theme="{theme_type}"' if theme_type in ("light", "dark") else ""


def _num(value: str) -> str:
    """`1200.0` → `1200`; `1180.5` → `1180.5` (atributos de SVG previsíveis)."""
    try:
        number = float(value)
    except ValueError:
        return value
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _natural_size(svg: str) -> tuple[str, str]:
    match = _VIEWBOX.search(svg)
    return (_num(match.group(1)), _num(match.group(2))) if match else ("1200", "900")


def embed(svg: str) -> str:
    """HTML do card: SVG no tamanho natural dentro de uma moldura rolável.

    Em coluna estreita o mapa rola na horizontal em vez de encolher até os
    rótulos ficarem ilegíveis. Determinístico, sem dependências.
    """
    width, height = _natural_size(svg)
    end = svg.find(">")
    if end < 0:
        return f'<div class="gdl-mind-scroll" style="overflow:auto;max-height:70vh;border-radius:12px">{svg}</div>'
    opening = svg[:end + 1]
    opening = _WIDTH.sub(f' width="{width}"', opening, count=1)
    if _HEIGHT.search(opening):
        opening = _HEIGHT.sub(f' height="{height}"', opening, count=1)
    elif opening.endswith("/>"):
        opening = opening[:-2] + f' height="{height}"/>'
    else:
        opening = opening[:-1] + f' height="{height}">'
    body = opening + svg[end + 1:]
    return ('<div class="gdl-mind-scroll" '
            'style="overflow:auto;max-height:70vh;border-radius:12px">'
            f'{body}</div>')


def _prune(keep: int = KEEP_FILES) -> None:
    """Mantém os `keep` arquivos mais recentes (html/svg) em `static/mind/`."""
    files = [p for p in MIND_DIR.glob("*") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def publish(svg: str, title: str) -> str | None:
    """Grava `<hash>.html` + `<hash>.svg` e devolve a URL pública (ou None).

    Sem static serving, devolve `None` (o app mostra aviso + download). Escreve
    só o que falta e poda o diretório para não acumular mapas antigos.
    """
    if not player.enabled():
        return None
    body_attr = _body_attr()
    digest = hashlib.sha1(f"{svg}{title}{body_attr}".encode("utf-8")).hexdigest()[:12]
    MIND_DIR.mkdir(parents=True, exist_ok=True)
    svg_path = MIND_DIR / f"{digest}.svg"
    html_path = MIND_DIR / f"{digest}.html"
    if not svg_path.exists():
        svg_path.write_text(svg, encoding="utf-8")
    if not html_path.exists():
        html_path.write_text(
            _HTML
            .replace("__TITLE__", html.escape(title))
            .replace("__BODY_ATTR__", body_attr)
            .replace("__HASH__", digest)
            .replace("__SVG__", svg),
            encoding="utf-8",
        )
    # O prune poda por mtime: sem tocar, um arquivo já existente (mas antigo)
    # poderia ser removido logo depois de devolvermos a URL dele.
    svg_path.touch()
    html_path.touch()
    _prune()
    return f"{URL_PREFIX}/{html_path.name}"


def download(svg: str) -> None:
    """Botão de download do SVG (funciona mesmo sem static serving)."""
    st.download_button(copy.MINDMAP_DOWNLOAD, data=svg,
                       file_name="mapa-mental.svg", mime="image/svg+xml",
                       width="stretch", key="dl_mindmap")