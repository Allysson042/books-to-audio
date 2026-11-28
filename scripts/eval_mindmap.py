"""Régua do mapa mental M0: Pass1 → outline JSON → SVG (sem imagem, US$ 0).

Uso:
    venv/bin/python scripts/eval_mindmap.py              # 2 primeiras douradas
    venv/bin/python scripts/eval_mindmap.py --limit 5    # todas
    venv/bin/python scripts/eval_mindmap.py --scope 4    # capítulo fixo

Valida schema (3–5 ramos, rótulos ≤ limite, citações), XML do SVG e fidelidade
(todo rótulo do outline precisa aparecer no texto do SVG). Sem store/chave/PDF,
pula a pergunta e sai 0 — nunca quebra CI. Nunca imprime chaves.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import MINDMAP_LABEL_CHARS, RETRIEVAL_TOP_N  # noqa: E402
from src.generate import get_pass1, load_persona  # noqa: E402
from src.mindmap import build_outline, outline_to_svg  # noqa: E402
from src.retrieval import RAGStore  # noqa: E402

CACHE = ROOT / "cache"


def _macro(chapter: int | None) -> str | None:
    try:
        mapa = json.loads((CACHE / "mapa_livro.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for c in mapa.get("chapters", []):
        if c.get("chapter") == chapter:
            path = CACHE / c.get("macro_file", "")
            return path.read_text(encoding="utf-8") if path.exists() else None
    return None


def _svg_text(svg: str) -> str:
    """Junta o texto dos nós `<text>` com espaço (quebra de linha não perde palavra)."""
    root = ET.fromstring(svg)
    parts = [" ".join((t.text or "").split()) for t in root.iter()
             if t.tag.endswith("text")]
    return " ".join(p for p in parts if p)


def _validate(outline: dict, svg: str) -> list[str]:
    problems: list[str] = []
    try:
        json.loads(json.dumps(outline, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        problems.append(f"json: {exc}")

    ramos = outline.get("ramos") or []
    if not (3 <= len(ramos) <= 5):
        problems.append(f"ramos={len(ramos)}")
    for branch in ramos:
        label = str(branch.get("rotulo") or "")
        if len(label) > MINDMAP_LABEL_CHARS:
            problems.append(f"rotulo>{MINDMAP_LABEL_CHARS}: {label!r}")
        for kid in branch.get("filhos") or []:
            if len(str(kid)) > MINDMAP_LABEL_CHARS:
                problems.append(f"filho>{MINDMAP_LABEL_CHARS}: {kid!r}")
    if not outline.get("citacoes"):
        problems.append("sem citacoes")

    try:
        text = _svg_text(svg)
    except ET.ParseError as exc:
        problems.append(f"svg xml: {exc}")
        text = ""
    labels = ([outline.get("titulo", "")]
              + [b.get("rotulo", "") for b in ramos]
              + [k for b in ramos for k in (b.get("filhos") or [])])
    for label in labels:
        norm = " ".join(str(label).split())
        if norm and norm not in text:
            problems.append(f"svg sem rótulo: {label!r}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--scope", default="")
    ap.add_argument("--golden", default=str(ROOT / "scripts" / "golden.json"))
    args = ap.parse_args()

    try:
        golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"SKIP: golden.json indisponível ({type(exc).__name__}: {exc})")
        return 0

    chapter = int(args.scope) if args.scope.strip().isdigit() else None
    scope = str(chapter) if chapter is not None else "all"

    try:
        store = RAGStore()
        addendum = load_persona("tecnico_direto").get("system_addendum", "")
    except Exception as exc:  # store sem Chroma/PDF, persona ausente...
        print(f"SKIP: store/persona indisponível ({type(exc).__name__}: {str(exc)[:120]})")
        return 0

    macro = _macro(chapter)
    failures = executed = 0
    for q in golden[: max(0, args.limit)]:
        query = q.get("pt") or q.get("en")
        if not query:
            continue
        try:
            chunks = store.search(query, chapter=chapter, top_n=RETRIEVAL_TOP_N)
            if not chunks:
                print(f"{q.get('id')}: SKIP sem chunks neste escopo")
                continue
            t0 = time.time()
            text1, prov1, cached1 = get_pass1(query, scope, chunks, macro, addendum, True)
            outline, prov, cached = build_outline(text1, query, scope, use_cache=True)
            svg = outline_to_svg(outline)
            elapsed = time.time() - t0
        except Exception as exc:  # chave/rede/store: skip gracioso, sem vazar detalhes
            print(f"{q.get('id')}: SKIP ({type(exc).__name__}: {str(exc)[:120]})")
            continue
        problems = _validate(outline, svg)
        executed += 1
        failures += bool(problems)
        status = "OK" if not problems else "FAIL " + "; ".join(problems[:4])
        print(f"{q.get('id')}: {status} | provider={prov} cached={cached} "
              f"pass1={prov1}/{cached1} {elapsed:.1f}s svg={len(svg)}ch "
              f"ramos={len(outline.get('ramos') or [])}")
        if problems:
            print("  outline:", json.dumps(outline, ensure_ascii=False)[:400])

    if not executed:
        print("SKIP: nenhuma pergunta executada (store/chave/PDF ausente)")
        return 0
    print(f"\n{executed - failures}/{executed} mapas válidos")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
