"""Reparo one-off: summary_2lines do mapa estavam com lixo (marcadores/---/thinking).

O LLM não seguiu o template "1) RESUMO2LINHAS / 2) MACRO" — escreveu só marcadores
("2) MACRO:", "---") ou preâmbulo thinking-aloud, e o fallback do parser pegou essas
linhas. Os corpos das macros estão bons; então re-extraímos o resumo do corpo,
sem gastar quota. Também reconstrói a árvore (que usa os summaries).
Uso: venv/bin/python scripts/fix_summaries.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JUNK = re.compile(
    r"^(\s*(#{1,4}\s*)?(\*{1,2}\s*)?(RESUMO\s*2?\s*LINHAS|MACRO)\b.*"
    r"|\s*[*_\-]{3,}\s*$"
    r"|\s*\d+\)\s*(RESUMO.*|MACRO:?)\s*$"
    r"|\s*(Vou|Preparando|Claro|Perfeito|Entendido)\b.*)$",
    re.IGNORECASE)


def extract_summary(markdown: str, limit: int = 400) -> str:
    """Primeiras frases de conteúdo real, pulando marcadores/headers/preâmbulo.
    Junta linhas antes de cortar (PDF quebra frases no meio da linha)."""
    clean = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or JUNK.match(line) or line.startswith("#"):
            continue
        line = re.sub(r"^[*\-•]\s+", "", line)          # bullets
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)     # negrito
        line = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", line)  # itálico
        line = re.sub(r"`(.+?)`", r"\1", line)
        line = re.sub(r"\[Cap \d+, pp?\.[\d\-,\s]+\]", "", line)  # citações poluem o resumo curto
        if line.endswith(":"):  # lead-in: mantém só frases completas da linha
            line = " ".join(p for p in re.split(r"(?<=[.!?])\s+", line) if re.search(r"[.!?]$", p))
            if not line:
                continue
        clean.append(line)
    full = " ".join(clean)
    sents = [m.group(0).strip() for m in re.finditer(r".+?[.!?](?=\s|$)", full)]
    if not sents and full:  # sem pontuação: bullets soltos — junta o início
        return full[:limit]
    text = ""
    for s in sents:
        text = (text + " " + s).strip()
        if len(text) >= 120 or s == sents[-1]:
            break
    return text[:limit] if len(text) >= 60 else ""


def main() -> int:
    mapa_path = ROOT / "cache" / "mapa_livro.json"
    mapa = json.loads(mapa_path.read_text(encoding="utf-8"))
    for ch in mapa["chapters"]:
        md = ROOT / "cache" / ch["macro_file"]
        summary = extract_summary(md.read_text(encoding="utf-8")) if md.exists() else ""
        ch["summary_2lines"] = summary or ch["title"]
        print(f"Cap{ch['chapter']:02d}: {summary[:100]}")
    mapa_path.write_text(json.dumps(mapa, ensure_ascii=False, indent=2), encoding="utf-8")
    from src.tree_index import build_tree
    tree = build_tree()
    print(f"mapa + árvore reconstruídos ({len(tree['nodes'])} caps).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
