"""Régua A/B do M1: Pass1 → outline → prompt → imagem generativa → OCR/recall.

Uso:
    venv/bin/python scripts/eval_images.py                     # 2 douradas, 3 modelos
    venv/bin/python scripts/eval_images.py --limit 5 --budget-usd 0.40
    venv/bin/python scripts/eval_images.py --models recraft/recraft-v4.1-flash-v2
    venv/bin/python scripts/eval_images.py --no-ocr --json out.json

Mede o que o mapa estilizado precisa entregar: **texto legível**. Cada imagem gerada
é transcrita por um VLM (`VISION_MODEL`, default `google/gemini-3.1-flash`) e o texto
é comparado com os rótulos do outline (título + ramos + filhos) por **recall** após
normalização (minúsculas, sem acentos, espaços colapsados).

Guarda de orçamento: estima o custo pelo catálogo (`_PRICE_EST`) e **nunca** inicia uma
geração que passaria de `--budget-usd`; o total real gasto é somado de `meta["cost"]`.
Cache do `image_provider` é reaproveitado (custo 0 e `cached=True` não consome teto).

Sem chave/store/PDF/golden → skip gracioso, exit 0. Nunca imprime a chave.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import image_provider  # noqa: E402
from src.config import (IMAGE_MAX_LABELS, MINDMAP_LABEL_CHARS,  # noqa: E402
                        RETRIEVAL_TOP_N)
from src.generate import get_pass1, load_persona  # noqa: E402
from src.mindmap import build_outline, outline_to_prompt  # noqa: E402
from src.retrieval import RAGStore  # noqa: E402

CACHE = ROOT / "cache"

DEFAULT_MODELS = "recraft/recraft-v4.1-flash-v2,openai/gpt-image-1-mini,google/gemini-3.1-flash-image"
# `google/gemini-3.1-flash` (nome do plano) não existe no catálogo: a variante
# visível mais próxima é a `-lite`. Sobrescreva com `VISION_MODEL` no `.env`.
DEFAULT_VISION = "google/gemini-3.1-flash-lite"
# Estimativa por imagem (catálogo em docs/image-mindmap-plan.md §2); o custo real vem
# de `usage.cost`, isto só evita INICIAR uma geração que estouraria o teto.
_PRICE_EST = {
    "recraft/recraft-v4.1-flash-v2": 0.007,
    "recraft/recraft-v4.1-flash": 0.007,
    "openai/gpt-image-1-mini": 0.05,  # medido na régua (0,0502 com res=1K/quality=medium)
    "openai/gpt-image-1-mini:low": 0.002,
    "google/gemini-3.1-flash-image": 0.08,
    "google/gemini-2.5-flash-image": 0.039,
    "google/gemini-3.1-flash-lite-image": 0.039,
}
_DEFAULT_EST = 0.08
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


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


def _norm(text: str) -> str:
    """Minúsculas, sem acentos, espaços colapsados — denominador comum do OCR."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"[–—]", "-", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _labels(outline: dict, prompt: str) -> list[str]:
    """Rótulos esperados (título + ramos + filhos) que de fato entraram no prompt.

    `outline_to_prompt` omite os últimos nós quando o outline passa do teto de chars;
    cobrar no OCR um rótulo que nunca foi pedido mediria o script, não o modelo.
    """
    ramos = outline.get("ramos") or []
    out: list[str] = []
    for label in ([outline.get("titulo", "")]
                  + [b.get("rotulo", "") for b in ramos]
                  + [k for b in ramos for k in (b.get("filhos") or [])]):
        label = " ".join(str(label).split())
        if label and len(label) <= MINDMAP_LABEL_CHARS and _norm(label) in _norm(prompt):
            out.append(label)
    return list(dict.fromkeys(out))


def _recall(labels: list[str], ocr_text: str) -> tuple[float | None, list[str]]:
    if not labels:
        return None, []
    hay = _norm(ocr_text)
    missing = [lbl for lbl in labels if _norm(lbl) not in hay]
    return (len(labels) - len(missing)) / len(labels), missing


def _ocr(path: Path, media_type: str, api_key: str, model: str) -> str:
    """Transcrição literal da imagem. 1 retry em 429/5xx; erro vira RuntimeError curto."""
    import httpx

    raw = path.read_bytes()
    mime = media_type or "image/png"
    b64 = base64.b64encode(raw).decode()
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",
                 "text": "Liste TODO o texto visível na imagem, um por linha, copiando "
                         "exatamente. Não traduza."},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        "max_tokens": 400,
        "temperature": 0,
        "reasoning": {"effort": "none"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
               "HTTP-Referer": "https://github.com/books-to-audio",
               "X-Title": "Books to Audio (eval images)"}
    last = ""
    for attempt in range(2):
        try:
            r = httpx.post(OPENROUTER_CHAT_URL, headers=headers, json=payload, timeout=120)
        except Exception as exc:  # noqa: BLE001 - timeout/conexão viram erro curto
            last = f"{type(exc).__name__}"
            if attempt == 0:
                time.sleep(2)
                continue
            raise RuntimeError(f"OCR transporte: {last}") from None
        if r.status_code == 200:
            try:
                data = r.json()
            except ValueError:
                raise RuntimeError("OCR resposta não-JSON") from None
            choices = data.get("choices") or [{}]
            content = ((choices[0] or {}).get("message") or {}).get("content")
            return str(content or "")
        last = f"HTTP {r.status_code}: {(r.text or '')[:120]}"
        if (r.status_code == 429 or r.status_code >= 500) and attempt == 0:
            time.sleep(2)
            continue
        raise RuntimeError(f"OCR falhou ({last})")
    raise RuntimeError(f"OCR falhou ({last})")


def _fmt(value: float | None, spec: str, default: str = "-") -> str:
    return format(value, spec) if isinstance(value, (int, float)) else default


def main() -> int:
    ap = argparse.ArgumentParser(description="Régua A/B M1 — imagem generativa.")
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--models", default=DEFAULT_MODELS,
                    help=f"lista separada por vírgula (default: {DEFAULT_MODELS})")
    ap.add_argument("--scope", default="")
    ap.add_argument("--budget-usd", type=float, default=0.30)
    ap.add_argument("--no-ocr", action="store_true", help="pula a legibilidade (só gera)")
    ap.add_argument("--vision-model", default=os.getenv("VISION_MODEL") or DEFAULT_VISION)
    ap.add_argument("--max-labels", type=int, default=IMAGE_MAX_LABELS,
                    help="teto de nós no prompt da imagem, título incluído "
                         f"(default: IMAGE_MAX_LABELS={IMAGE_MAX_LABELS}; 0 = sem teto)")
    ap.add_argument("--golden", default=str(ROOT / "scripts" / "golden.json"))
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    try:
        golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"SKIP: golden.json indisponível ({type(exc).__name__}: {exc})")
        return 0

    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not api_key:
        print("SKIP: OPENROUTER_API_KEY ausente no .env (custo R$ 0, nada gerado)")
        return 0
    if not models:
        print("SKIP: nenhum modelo em --models")
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
    budget = max(0.0, float(args.budget_usd))
    spent = 0.0
    skipped_budget: list[str] = []
    rows: list[dict] = []

    print(f"Modelos: {', '.join(models)}")
    print(f"Teto de orçamento: US$ {budget:.2f} · OCR: "
          f"{'off' if args.no_ocr else args.vision_model}")
    print(f"IMAGE_MAX_LABELS={args.max_labels} · prompt ≤ 1200 chars · "
          f"MINDMAP_LABEL_CHARS={MINDMAP_LABEL_CHARS}\n")

    for q in golden[: max(0, args.limit)]:
        query = q.get("pt") or q.get("en")
        if not query:
            continue
        qid = q.get("id")
        try:
            chunks = store.search(query, chapter=chapter, top_n=RETRIEVAL_TOP_N)
            if not chunks:
                print(f"{qid}: SKIP sem chunks neste escopo")
                continue
            text1, _, _ = get_pass1(query, scope, chunks, macro, addendum, True)
            outline, _, _ = build_outline(text1, query, scope, use_cache=True)
        except Exception as exc:  # chave/rede/store: skip gracioso
            print(f"{qid}: SKIP ({type(exc).__name__}: {str(exc)[:120]})")
            continue

        prompt = outline_to_prompt(outline, max_labels=args.max_labels)
        expected = _labels(outline, prompt)
        print(f"{qid}: {query} — {len(expected)} rótulos no prompt")

        for model in models:
            est = _PRICE_EST.get(model, _DEFAULT_EST)
            if spent + est > budget + 1e-9:
                skipped_budget.append(f"{qid}/{model} (≈${est:.3f})")
                rows.append({"id": qid, "model": model, "ok": False,
                             "error": "BUDGET", "cost": None, "seconds": None,
                             "recall": None, "missing": []})
                continue
            t0 = time.time()
            try:
                path, meta = image_provider.generate(prompt, model=model)
            except Exception as exc:  # 402/400/rede: registra e segue a régua
                reason = str(exc).split("\n")[0][:110]
                print(f"  {model:<38} ERRO: {reason}")
                rows.append({"id": qid, "model": model, "ok": False,
                             "error": reason, "cost": None,
                             "seconds": round(time.time() - t0, 2),
                             "recall": None, "missing": []})
                continue

            cost = meta.get("cost")
            # Cache hit não cobra de novo: o custo do sidecar é histórico.
            if isinstance(cost, (int, float)) and not meta.get("cached"):
                spent += float(cost)
            seconds = meta.get("seconds") if meta.get("seconds") is not None else time.time() - t0
            if meta.get("cached"):
                # Cache hit não mede geração; o sidecar guarda o tempo real da 1ª chamada.
                try:
                    side = json.loads(Path(path).with_suffix(".json").read_text(encoding="utf-8"))
                    if isinstance(side.get("seconds"), (int, float)):
                        seconds = float(side["seconds"])
                except (OSError, ValueError):
                    pass
            recall = missing = None
            ocr_error = None
            ocr_text = ""
            if not args.no_ocr and expected:
                try:
                    ocr_text = _ocr(Path(path), meta.get("media_type", "image/png"),
                                    api_key, args.vision_model)
                    recall, missing = _recall(expected, ocr_text)
                except Exception as exc:  # OCR não derruba a régua de imagem
                    ocr_error = str(exc)[:120]
            rows.append({"id": qid, "model": model, "ok": True,
                         "error": ocr_error, "cost": cost,
                         "seconds": round(float(seconds or 0), 2),
                         "recall": recall, "missing": missing or [],
                         "path": str(path), "prompt": prompt, "ocr": ocr_text,
                         "labels": expected})
            cost_s = f"${cost:.4f}" if isinstance(cost, (int, float)) else "$?"
            rec_s = f"{recall:.0%}" if recall is not None else "-"
            miss_s = ", ".join((missing or [])[:3])
            extra = f" ERRO OCR: {ocr_error}" if ocr_error else ""
            cached_s = " (cache)" if meta.get("cached") else ""
            print(f"  {model:<38} ok=True {cost_s:>8} {float(seconds or 0):5.1f}s "
                  f"recall={rec_s:>4} missing={miss_s or '-'}{cached_s}{extra}")

    executed = [r for r in rows if r["ok"]]
    if not executed:
        print("\nSKIP: nenhuma imagem gerada (chave/store/PDF/modelo indisponível)")
        if skipped_budget:
            print("Fora do teto: " + "; ".join(skipped_budget))
        return 0

    print("\n== Agregado por modelo ==")
    print(f"{'model':<38} {'imgs':>4} {'custo':>9} {'recall':>7} {'s':>6}")
    agg: list[dict] = []
    for model in models:
        got = [r for r in rows if r["model"] == model and r["ok"]]
        if not got:
            continue
        total_cost = sum(r["cost"] for r in got if isinstance(r["cost"], (int, float)))
        priced = [r["cost"] for r in got if isinstance(r["cost"], (int, float))]
        recalls = [r["recall"] for r in got if r["recall"] is not None]
        seconds = [r["seconds"] for r in got if isinstance(r["seconds"], (int, float))]
        avg_recall = sum(recalls) / len(recalls) if recalls else None
        avg_s = sum(seconds) / len(seconds) if seconds else None
        per_img = total_cost / len(priced) if priced else None
        agg.append({"model": model, "images": len(got), "total_cost": total_cost,
                    "cost_per_image": per_img, "avg_recall": avg_recall,
                    "avg_seconds": avg_s})
        print(f"{model:<38} {len(got):>4} ${total_cost:>7.4f} "
              f"{_fmt(avg_recall, '>6.0%')} {_fmt(avg_s, '>6.1f')}")

    scored = [a for a in agg if a["avg_recall"] is not None and a["cost_per_image"]]
    if scored:
        best = max(scored, key=lambda a: a["avg_recall"] / max(a["cost_per_image"], 1e-9))
        print(f"\nRecomendação: {best['model']} — melhor recall por dólar "
              f"(recall médio {best['avg_recall']:.0%} a ${best['cost_per_image']:.4f}/img)")
    elif agg:
        print("\nRecomendação: sem OCR (--no-ocr) — decidir pelo custo/legibilidade manual")

    print(f"\nCusto real da régua: US$ {spent:.4f} (teto US$ {budget:.2f})")
    if skipped_budget:
        print("Fora do teto: " + "; ".join(skipped_budget))

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"rows": rows, "aggregate": agg, "spent_usd": spent,
                                   "budget_usd": budget,
                                   "skipped_budget": skipped_budget},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON: {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
