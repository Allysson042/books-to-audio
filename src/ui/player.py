"""Player dock (U5 opção B): iframe sem CDN servido por `static/`, com fallback nativo.

Contrato visual: `docs/UX/06-guia-visual.md` §5 (PlayerDock) e §6 (dark).
O áudio em si (roteiro/voz/cache) não muda aqui: recebemos um MP3 já válido do
`app.py` e só o apresentamos. Sem static serving (ou sem arquivo), cai no
`st.audio` + download nativos — nunca levanta exceção.
"""

from __future__ import annotations

import hashlib
import html
import shutil
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src.ui import copy, theme

STATIC_DIR = Path("static")
URL_PREFIX = "/app/static"
KEEP_FILES = 10
HEIGHT = 68


def enabled() -> bool:
    """`server.enableStaticServing` ligado? (config exige restart do app)."""
    try:
        return bool(st.get_option("server.enableStaticServing"))
    except Exception:  # noqa: BLE001 — sem contexto/config, usa o fallback nativo
        return False


def prune(keep: int = KEEP_FILES) -> None:
    """Mantém só os `keep` arquivos mais recentes por mtime (evita lixo em `static/`)."""
    files = [p for p in STATIC_DIR.glob("*") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def stage(mp3: str | Path, sig: str | None = None) -> str:
    """Copia o MP3 para `static/` e devolve a URL pública com cache-bust.

    Nome preservado (o cache de TTS já é hash de conteúdo). Só copia o que falta;
    a URL leva `?v=` (sig recebida ou mtime+tamanho) para o browser não servir
    áudio velho depois de um `↻ Regerar`.
    """
    src = Path(mp3)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    dst = STATIC_DIR / src.name
    if not dst.exists():
        shutil.copyfile(src, dst)
    # O prune poda por mtime: sem tocar, um arquivo já existente (mas antigo)
    # poderia ser removido logo depois de gerarmos a URL dele.
    dst.touch()
    prune()
    if sig:
        stamp = str(sig)[:12]
    else:
        stat = dst.stat()
        stamp = hashlib.sha1(f"{int(stat.st_mtime)}|{stat.st_size}".encode()).hexdigest()[:8]
    return f"{URL_PREFIX}/{dst.name}?v={stamp}"


def _tokens_css() -> str:
    """Tokens do iframe (não herda CSS da página). Defaults light + dark explícito."""
    light = TOKENS_BY_THEME["light"]
    dark = TOKENS_BY_THEME["dark"]

    def block(prefix: str, values: dict[str, str]) -> str:
        return prefix + " { " + " ".join(f"--{k}:{v};" for k, v in values.items()) + " }"

    return "\n  ".join([
        block("body", light),
        block('body[data-theme="dark"]', dark),
        "@media (prefers-color-scheme: dark) { "
        + block("body:not([data-theme])", dark) + " }",
    ])


TOKENS_BY_THEME = {
    "light": {
        "text": theme.TOKENS["text"]["light"],
        "muted": theme.TOKENS["muted"]["light"],
        "accent": theme.TOKENS["accent"]["light"],
        "on-accent": theme.TOKENS["on-accent"]["light"],
        "border": theme.TOKENS["border"]["light"],
        "warning": theme.TOKENS["warning"]["light"],
    },
    "dark": {
        "text": theme.TOKENS["text"]["dark"],
        "muted": theme.TOKENS["muted"]["dark"],
        "accent": theme.TOKENS["accent"]["dark"],
        "on-accent": theme.TOKENS["on-accent"]["dark"],
        "border": theme.TOKENS["border"]["dark"],
        "warning": theme.TOKENS["warning"]["dark"],
    },
}


_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; background: transparent; overflow: hidden; }
  __TOKENS__
  body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         color: var(--text); }
  .dock { display: flex; align-items: center; gap: 12px; height: __HEIGHT__px; }
  .play { width: 38px; height: 38px; flex: none; border: none; border-radius: 50%;
          background: var(--accent); color: var(--on-accent); font-size: 12px;
          display: grid; place-items: center; cursor: pointer; }
  .play:disabled { opacity: .5; cursor: default; }
  .info { min-width: 0; flex: none; max-width: 220px; }
  .info b { display: block; font-size: 12.5px; font-weight: 600;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .info span { font-size: 11px; color: var(--muted); }
  .mid { flex: 1; min-width: 0; display: flex; align-items: center; gap: 10px; }
  input[type="range"] { flex: 1; min-width: 0; margin: 0; height: 4px;
                        accent-color: var(--accent); cursor: pointer; }
  .time { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums;
          white-space: nowrap; }
  .dl { flex: none; font-size: 13px; line-height: 1; text-decoration: none;
        color: var(--muted); border: 1px solid var(--border); border-radius: 8px;
        padding: 7px 9px; }
  .dl:hover { color: var(--text); border-color: var(--text); }
  .err { font-size: 12px; color: var(--warning); margin-top: 2px; }
</style>
</head>
<body__BODY_ATTR__>
<audio id="a" src="__URL__" preload="metadata" style="display:none"></audio>
<div class="dock">
  <button class="play" id="p" type="button" aria-label="Reproduzir">&#9654;</button>
  <div class="info"><b>__TITLE__</b><span>__META__</span></div>
  <div class="mid">
    <input type="range" id="seek" min="0" max="1000" value="0"
           aria-label="Progresso" disabled>
    <span class="time" id="t">0:00 / 0:00</span>
  </div>
  <a class="dl" id="dl" href="__URL__" download="__DL__"
     aria-label="Baixar áudio">&#10515;</a>
</div>
<div class="err" id="err" hidden>__ERR__</div>
<script>
(function () {
  var a = document.getElementById("a"), p = document.getElementById("p"),
      s = document.getElementById("seek"), t = document.getElementById("t"),
      e = document.getElementById("err");
  function fmt(n) {
    if (!isFinite(n) || n < 0) { n = 0; }
    var m = Math.floor(n / 60), sec = Math.floor(n % 60);
    return m + ":" + (sec < 10 ? "0" : "") + sec;
  }
  function paint() {
    var d = isFinite(a.duration) ? a.duration : 0;
    t.textContent = fmt(a.currentTime) + " / " + fmt(d);
    if (d > 0) {
      s.value = String(Math.round(a.currentTime / d * 1000));
      s.disabled = false;
    }
  }
  function fail() { e.hidden = false; p.disabled = true; s.disabled = true; }
  p.addEventListener("click", function () {
    if (a.paused) {
      var r = a.play();
      if (r && r.catch) { r.catch(fail); }
    } else { a.pause(); }
  });
  a.addEventListener("play", function () {
    p.innerHTML = "&#10074;&#10074;"; p.setAttribute("aria-label", "Pausar");
  });
  a.addEventListener("pause", function () {
    p.innerHTML = "&#9654;"; p.setAttribute("aria-label", "Reproduzir");
  });
  a.addEventListener("ended", function () {
    p.innerHTML = "&#9654;"; p.setAttribute("aria-label", "Reproduzir");
  });
  a.addEventListener("timeupdate", paint);
  a.addEventListener("loadedmetadata", paint);
  a.addEventListener("error", fail);
  s.addEventListener("input", function () {
    if (isFinite(a.duration) && a.duration > 0) {
      a.currentTime = a.duration * (Number(s.value) / 1000);
    }
  });
  paint();
})();
</script>
</body>
</html>
"""


def _iframe_html(url: str, title: str, meta: str, download_name: str,
                 theme_type: str | None) -> str:
    body_attr = f' data-theme="{theme_type}"' if theme_type in ("light", "dark") else ""
    return (_HTML
            .replace("__TOKENS__", _tokens_css())
            .replace("__HEIGHT__", str(HEIGHT))
            .replace("__BODY_ATTR__", body_attr)
            .replace("__URL__", html.escape(url, quote=True))
            .replace("__TITLE__", html.escape(title))
            .replace("__META__", html.escape(meta))
            .replace("__DL__", html.escape(download_name, quote=True))
            .replace("__ERR__", html.escape(copy.AUDIO_UNAVAILABLE)))


def _native(mp3: Path, download_name: str) -> None:
    """Fallback: player + download nativos, no mesmo dock compacto."""
    fmt = theme.audio_mime(mp3) or "audio/mpeg"
    col_a, col_d = st.columns([4, 1], vertical_alignment="center")
    with col_a:
        st.audio(str(mp3), format=fmt)
    with col_d:
        st.download_button(copy.AUDIO_DOWNLOAD, data=mp3.read_bytes(),
                           file_name=download_name, mime=fmt, key="dl_audio")


def render(mp3: str | Path, title: str, meta: str,
           download_name: str = "gdl-audio.mp3", sig: str | None = None) -> bool:
    """Renderiza o player custom (True) ou cai no nativo (False).

    Nunca levanta: static serving desligado, arquivo ausente ou falha de cópia
    viram fallback nativo.
    """
    path = Path(mp3)
    if enabled() and path.exists():
        try:
            url = stage(path, sig)
        except OSError:
            url = ""
        if url:
            frame = _iframe_html(url, title, meta, download_name,
                                 theme.theme_type_of(st))
            if hasattr(st, "iframe"):  # 1.64+: components.v1.html está depreciado
                st.iframe(frame, height=HEIGHT)
            else:  # compat com streamlit>=1.36
                components.html(frame, height=HEIGHT, scrolling=False)
            return True
    if path.exists():
        _native(path, download_name)
    else:
        st.caption(copy.AUDIO_UNAVAILABLE)
    return False
