"""M0 — mapa mental: outline JSON (LLM de texto) + SVG determinístico (US$ 0).

O mapa é montado em duas etapas separadas de propósito:

1. `build_outline`: deriva do **Pass1** um JSON curto (título, 3–5 ramos, filhos,
   citações). Uma chamada barata de LLM de texto, cacheada em `cache/mind_*.json`.
   Sem chave/API/erro, cai num outline heurístico — nunca levanta exceção.
2. `outline_to_svg`: desenha o outline como SVG standalone, sem rede e sem
   dependência nova. Mesma entrada → mesmo SVG byte-a-byte.

Texto 100% fiel: os rótulos vêm do outline (nunca de um modelo de imagem) e são
escapados antes de entrar no XML. Custo no default: US$ 0.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from xml.sax.saxutils import escape

from src.config import (IMAGE_MAX_LABELS, MINDMAP_LABEL_CHARS,
                        MINDMAP_MAX_BRANCHES, MINDMAP_MAX_DEPTH,
                        MINDMAP_REASONING, MINDMAP_VERSION)

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"

MAX_TOKENS = 2000         # curto, mas com folga p/ o "thinking" dos modelos 3.x
MIN_BRANCHES = 3
MAX_CHILDREN = 3
MAX_CITATIONS = 5
MAX_LINES = 2
LINE_CHARS = 22
PASS1_PROMPT_CHARS = 6000  # resumo enviado ao LLM (Pass1 costuma ser menor)

_TAG_RE = re.compile(r"<[^>]+>")
_MD_RE = re.compile(r"[*_`#>]+")
_BRACKETS_RE = re.compile(r"\[[^\]]*\]")
_WS_RE = re.compile(r"\s+")
_CITE_RE = re.compile(r"\[?\s*Cap\s*\d+\s*,\s*p\.?\s*\d+\s*\]?", re.IGNORECASE)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?")


# -- saneamento de texto ------------------------------------------------------
def _clean_label(text, limit: int | None = None) -> str:
    """Tira markdown/colchetes/quebras, colapsa espaços e corta em palavra."""
    limit = MINDMAP_LABEL_CHARS if limit is None else limit
    s = str(text or "")
    s = _TAG_RE.sub(" ", s)
    s = _BRACKETS_RE.sub(" ", s)          # citações nunca entram no rótulo
    s = _MD_RE.sub(" ", s)
    s = s.replace("\r", " ").replace("\n", " ")
    s = _WS_RE.sub(" ", s).strip(" -–—:;,.|")
    if not s:
        return ""
    if len(s) > limit:
        cut = s[: max(1, limit - 1)]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        s = cut.rstrip(" -–—:;,.") + "…"
    return s


def _clean_citation(text) -> str:
    s = _WS_RE.sub(" ", str(text or "")).strip().strip("[]").strip()
    m = _CITE_RE.search(s)
    if m:
        s = m.group(0).strip().strip("[]").strip()
    return _WS_RE.sub(" ", s)[:60]


def _citations_from(text: str) -> list[str]:
    out: list[str] = []
    for m in _CITE_RE.finditer(text or ""):
        c = _clean_citation(m.group(0))
        if c and c.lower() not in {x.lower() for x in out}:
            out.append(c)
    return out[:MAX_CITATIONS]


# -- parser tolerante ---------------------------------------------------------
def _extract_json(raw: str) -> dict:
    """Aceita cerca ```json, texto antes/depois e vírgula final."""
    if not raw or not str(raw).strip():
        raise ValueError("resposta vazia")
    s = str(raw).strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s.strip())
    candidates: list[str] = []
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        candidates.append(s[start:end + 1])
    candidates.append(s)
    for cand in candidates:
        for cleaned in (cand, re.sub(r",\s*([}\]])", r"\1", cand)):
            try:
                data = json.loads(cleaned)
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict):
                return data
    raise ValueError("nenhum objeto JSON encontrado")


# -- outline heurístico (sem LLM) --------------------------------------------
def _heuristic_outline(pass1_text: str, query: str) -> dict:
    title = _clean_label(query) or "Mapa mental"
    text = pass1_text or ""
    branches: list[dict] = []
    seen: set[str] = set()

    for m in _HEADING_RE.finditer(text):
        label = _clean_label(m.group(1))
        if label and label.lower() not in seen:
            seen.add(label.lower())
            branches.append({"rotulo": label, "filhos": []})
        if len(branches) >= MINDMAP_MAX_BRANCHES:
            break

    if len(branches) < MIN_BRANCHES:
        for m in _SENTENCE_RE.finditer(text):
            label = _clean_label(m.group(0))
            if len(label) >= 8 and label.lower() not in seen:
                seen.add(label.lower())
                branches.append({"rotulo": label, "filhos": []})
            if len(branches) >= MIN_BRANCHES:
                break

    while len(branches) < MIN_BRANCHES:
        label = f"Ponto {len(branches) + 1}"
        if label.lower() in seen:
            label = f"Ponto {len(branches) + 1}·"
        seen.add(label.lower())
        branches.append({"rotulo": label, "filhos": []})

    return {"titulo": title, "ramos": branches[:MINDMAP_MAX_BRANCHES],
            "citacoes": _citations_from(text)}


# -- validação do contrato ----------------------------------------------------
def _normalize_outline(raw, query: str, pass1_text: str) -> dict:
    """Valida/sanitiza o JSON do LLM; nunca confia no formato recebido."""
    if not isinstance(raw, dict):
        raw = {}
    title = _clean_label(raw.get("titulo")) or _clean_label(query) or "Mapa mental"

    branches: list[dict] = []
    seen: set[str] = set()
    for item in raw.get("ramos") or []:
        if isinstance(item, dict):
            label = _clean_label(item.get("rotulo") or item.get("label")
                                 or item.get("titulo"))
            kids_raw = item.get("filhos") or item.get("children") or []
        else:
            label = _clean_label(item)
            kids_raw = []
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        kids: list[str] = []
        if MINDMAP_MAX_DEPTH >= 2 and isinstance(kids_raw, (list, tuple)):
            for kid in kids_raw:
                k = _clean_label(kid)
                if k and k.lower() not in {x.lower() for x in kids}:
                    kids.append(k)
                if len(kids) >= MAX_CHILDREN:
                    break
        branches.append({"rotulo": label, "filhos": kids})
        if len(branches) >= MINDMAP_MAX_BRANCHES:
            break

    # completa até o mínimo usando o que o Pass1 realmente oferece
    if len(branches) < MIN_BRANCHES:
        for b in _heuristic_outline(pass1_text, query)["ramos"]:
            if len(branches) >= MIN_BRANCHES:
                break
            if b["rotulo"].lower() not in seen:
                seen.add(b["rotulo"].lower())
                branches.append(b)
    while len(branches) < MIN_BRANCHES:
        label = f"Ponto {len(branches) + 1}"
        seen.add(label.lower())
        branches.append({"rotulo": label, "filhos": []})

    cites_raw = raw.get("citacoes") or raw.get("citations") or []
    if isinstance(cites_raw, str):
        cites_raw = [cites_raw]
    citations: list[str] = []
    for c in cites_raw if isinstance(cites_raw, (list, tuple)) else []:
        cc = _clean_citation(c)
        if cc and cc.lower() not in {x.lower() for x in citations}:
            citations.append(cc)
    for c in _citations_from(pass1_text):
        if len(citations) >= MAX_CITATIONS:
            break
        if c.lower() not in {x.lower() for x in citations}:
            citations.append(c)

    return {"titulo": title, "ramos": branches[:MINDMAP_MAX_BRANCHES],
            "citacoes": citations[:MAX_CITATIONS]}


# -- LLM ----------------------------------------------------------------------
def _system_prompt() -> str:
    from src.prompts import GLOSSARIO
    return (
        "Você organiza um mapa mental a partir de um resumo técnico.\n"
        "Responda SOMENTE com um objeto JSON válido: sem markdown, sem cercas, "
        "sem comentários.\n"
        "Derive todos os conceitos EXCLUSIVAMENTE do resumo fornecido; é proibido "
        "inventar.\n"
        f"Regras: {MIN_BRANCHES} a {MINDMAP_MAX_BRANCHES} ramos; no máximo "
        f"{MAX_CHILDREN} filhos por ramo; rótulos com até {MINDMAP_LABEL_CHARS} "
        "caracteres; sem markdown e sem [colchetes]; citações apenas na lista "
        '"citacoes".\n'
        "Preserve intactos os termos do glossário em inglês: "
        f"{', '.join(GLOSSARIO)}.\n"
        'Formato exato:\n'
        '{"titulo": "tema curto", "ramos": [{"rotulo": "...", '
        '"filhos": ["...", "..."]}], "citacoes": ["Cap 3, p. 71"]}'
    )


def _user_prompt(pass1_text: str, query: str) -> str:
    return (f"Pergunta: {query}\n\n"
            f"Resumo técnico (única fonte permitida):\n"
            f"{(pass1_text or '')[:PASS1_PROMPT_CHARS]}")


def _reasoning_extra() -> dict | None:
    """Payload opcional de reasoning (`MINDMAP_REASONING`); vazio/`off` = não envia.

    Sem isso, modelos reasoning (ex. DeepSeek) queimam os 2000 tokens pensando e
    devolvem `finish_reason=length` — JSON vazio ou cortado no meio.
    """
    effort = str(MINDMAP_REASONING or "").strip()
    if not effort or effort.lower() in {"off", "none_off"}:
        return None
    return {"reasoning": {"effort": effort}}


def _call_llm(llm_fn, system: str, user: str) -> tuple[str, str]:
    """`llm_fn(system, user)` pode devolver str ou (str, provider)."""
    if llm_fn is None:
        from src.llm_provider import build_chain, complete_with_fallback
        chain = build_chain()
        if not chain:
            raise RuntimeError("nenhum provider configurado")
        text, provider = complete_with_fallback(system, user, MAX_TOKENS, chain,
                                                extra=_reasoning_extra())
        return text, provider
    res = llm_fn(system, user)
    if isinstance(res, tuple) and len(res) == 2:
        return str(res[0]), str(res[1])
    return str(res), "llm"


# -- cache --------------------------------------------------------------------
def _sig8(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:8]


def _cache_path(scope: str, query: str, pass1_text: str) -> Path:
    raw = f"{MINDMAP_VERSION}|{scope}|{query}|{_sig8(pass1_text)}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return CACHE / f"mind_{h}.json"


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# -- API pública --------------------------------------------------------------
def build_outline(pass1_text: str, query: str, scope: str = "",
                  use_cache: bool = True, llm_fn=None) -> tuple[dict, str, bool]:
    """Outline (dict validado), provider e `cached`.

    Cache hit devolve sem chamar LLM. `use_cache=False` pula a leitura mas escreve
    o resultado quando veio de LLM. Falha de LLM → outline heurístico (provider
    `heuristic`, nunca cacheado), sem levantar exceção.
    """
    path = _cache_path(scope, query, pass1_text)
    if use_cache and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            outline = data.get("outline")
            # Heurístico não é cache válido: resultado degradado nunca vira "hit".
            if data.get("provider") == "heuristic":
                path.unlink(missing_ok=True)
                outline = None
            if isinstance(outline, dict):
                norm = _normalize_outline(outline, query, pass1_text)
                provider = str(data.get("provider") or "cache")
                print(f"[mind-call] provider={provider} in=0ch out=0ch 0.0s cached=True",
                      flush=True)
                return norm, provider, True
        except (OSError, ValueError):
            pass

    t0 = time.time()
    outline: dict | None = None
    provider = "heuristic"
    system, user = _system_prompt(), _user_prompt(pass1_text, query)
    in_chars = len(system) + len(user)
    try:
        raw_text, provider = _call_llm(llm_fn, system, user)
        try:
            outline = _normalize_outline(_extract_json(raw_text), query, pass1_text)
        except (ValueError, TypeError):
            retry_user = (user + "\n\nSua resposta anterior não era JSON válido. "
                          "Responda APENAS o objeto JSON, sem texto extra.")
            raw_text, provider = _call_llm(llm_fn, system, retry_user)
            outline = _normalize_outline(_extract_json(raw_text), query, pass1_text)
        print(f"[mind-call] provider={provider} in={in_chars}ch "
              f"out={len(raw_text)}ch {time.time() - t0:.1f}s cached=False", flush=True)
    except Exception as exc:  # chain vazia, timeout, JSON inválido após retry...
        print(f"[mind-call] provider=heuristic erro={str(exc)[-150:]} "
              f"{time.time() - t0:.1f}s", flush=True)
        outline = None

    if outline is None:
        outline = _heuristic_outline(pass1_text, query)
        provider = "heuristic"

    # Só cacheia resultado de LLM; heurístico deve ser reavaliado na próxima chamada.
    if provider != "heuristic":
        _atomic_write(path, {"outline": outline, "provider": provider,
                             "version": MINDMAP_VERSION})
    return outline, provider, False


def _wrap(text: str, max_chars: int = LINE_CHARS,
          max_lines: int = MAX_LINES) -> list[str]:
    """Quebra em até `max_lines`; o excedente é fundido na última (texto fiel)."""
    words = str(text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for word in words:
        candidate = f"{cur} {word}".strip()
        if cur and len(candidate) > max_chars:
            lines.append(cur)
            cur = word
        else:
            cur = candidate
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    return lines or [""]


def _box(lines: list[str], font: float, pad_x: float, pad_y: float,
         line_gap: float = 4.0) -> tuple[float, float]:
    max_len = max((len(line) for line in lines), default=1)
    width = max(60.0, max_len * font * 0.55 + pad_x * 2)
    height = len(lines) * (font + line_gap) + pad_y * 2 - line_gap
    return width, height


def _esc(text) -> str:
    """Escapa TODO texto (inclui aspas) antes de entrar no XML."""
    return escape(str(text or ""), {'"': "&quot;", "'": "&apos;"})


def _bezier(x1: float, y1: float, x2: float, y2: float) -> str:
    mx = (x1 + x2) / 2
    return (f'<path d="M {x1:.1f} {y1:.1f} C {mx:.1f} {y1:.1f}, '
            f'{mx:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}"/>')


def _box_xml(x: float, y: float, w: float, h: float, lines: list[str],
             font: float, accent: bool = False) -> str:
    if accent:
        rect = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'rx="12" fill="currentColor" fill-opacity="0.10" '
                f'stroke="#6366f1" stroke-width="2.5"/>')
        pad_x, pad_y = 18.0, 14.0
    else:
        rect = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'rx="10" fill="currentColor" fill-opacity="0.05" '
                f'stroke="currentColor" stroke-opacity="0.28" stroke-width="1.5"/>')
        pad_x, pad_y = (14.0, 10.0) if font >= 16 else (12.0, 8.0)
    out = [rect]
    line_gap = 4.0
    start_y = y + pad_y + font
    for i, line in enumerate(lines):
        ty = start_y + i * (font + line_gap)
        out.append(f'<text x="{x + pad_x:.1f}" y="{ty:.1f}" font-size="{font:g}" '
                   f'fill="currentColor">{_esc(line)}</text>')
    return "".join(out)


def outline_to_svg(outline: dict) -> str:
    """SVG horizontal determinístico (mesma entrada → mesmos bytes)."""
    outline = outline if isinstance(outline, dict) else {}
    title = str(outline.get("titulo") or "Mapa mental")
    branches = outline.get("ramos") or []
    citations = [str(c) for c in (outline.get("citacoes") or [])][:MAX_CITATIONS]

    W, M = 1200.0, 40.0
    accent = "#6366f1"
    root_font, branch_font, child_font = 22.0, 16.0, 13.0

    root_lines = _wrap(title)
    root_w, root_h = _box(root_lines, root_font, 18.0, 14.0)
    root_x = M
    branch_x = root_x + root_w + 150.0

    entries: list[dict] = []
    for raw in branches:
        if not isinstance(raw, dict):
            raw = {"rotulo": str(raw), "filhos": []}
        blines = _wrap(str(raw.get("rotulo") or ""))
        bw, bh = _box(blines, branch_font, 14.0, 10.0)
        children: list[dict] = []
        for kid in (raw.get("filhos") or []):
            klines = _wrap(str(kid))
            cw, ch = _box(klines, child_font, 12.0, 8.0)
            children.append({"lines": klines, "w": cw, "h": ch})
        entries.append({"lines": blines, "w": bw, "h": bh, "children": children})

    max_bw = max((e["w"] for e in entries), default=120.0)
    child_x = branch_x + max_bw + 130.0
    child_gap, branch_gap = 18.0, 34.0

    for entry in entries:
        kids_h = (sum(c["h"] for c in entry["children"])
                  + child_gap * max(0, len(entry["children"]) - 1))
        entry["subtree_h"] = max(entry["h"], kids_h)

    total = (sum(e["subtree_h"] for e in entries)
             + branch_gap * max(0, len(entries) - 1))
    # Cresce a altura quando o conteúdo não cabe em 900 px (5 ramos × 3 filhos).
    # O rodapé de citações fica em H-26; reserva evita sobrepor o último nó.
    reserve_footer = (34.0 + 20.0 * len(citations)) if citations else 0.0
    H = max(900.0, total + 2 * M + reserve_footer)
    y = max(M, (H - total) / 2)

    for entry in entries:
        top = y
        entry["y"] = top + (entry["subtree_h"] - entry["h"]) / 2
        entry["cy"] = top + entry["subtree_h"] / 2
        kids_h = (sum(c["h"] for c in entry["children"])
                  + child_gap * max(0, len(entry["children"]) - 1))
        cy = top + (entry["subtree_h"] - kids_h) / 2
        for c in entry["children"]:
            c["y"] = cy
            c["cy"] = cy + c["h"] / 2
            cy += c["h"] + child_gap
        y += entry["subtree_h"] + branch_gap

    root_cy = H / 2
    if entries:
        root_cy = min(max(root_cy, M + root_h / 2), H - M - root_h / 2)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(W)} {int(H)}" '
        f'width="100%" preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="{_esc(title)}">',
        '<g fill="none" stroke="currentColor" stroke-opacity="0.45" stroke-width="2">',
    ]
    for entry in entries:
        parts.append(_bezier(root_x + root_w, root_cy, branch_x, entry["cy"]))
        for c in entry["children"]:
            parts.append(_bezier(branch_x + entry["w"], entry["cy"],
                                 child_x, c["cy"]))
    parts.append("</g>")
    parts.append('<g font-family="ui-sans-serif, system-ui, sans-serif">')
    parts.append(_box_xml(root_x, root_cy - root_h / 2, root_w, root_h,
                          root_lines, root_font, accent=True))
    for entry in entries:
        parts.append(_box_xml(branch_x, entry["y"], entry["w"], entry["h"],
                              entry["lines"], branch_font))
        for c in entry["children"]:
            parts.append(_box_xml(child_x, c["y"], c["w"], c["h"],
                                  c["lines"], child_font))
    parts.append("</g>")
    if citations:
        label = " · ".join(citations)
        parts.append(
            f'<text x="{M:.1f}" y="{H - 26:.1f}" '
            f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="12" '
            f'fill="currentColor" fill-opacity="0.55">{_esc(label)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# -- M1: prompt do renderer generativo (OpenRouter Images) --------------------
IMAGE_PROMPT_MAX_CHARS = 1200  # template curto: prompt grande é custo desnecessário

_PROMPT_HEAD = "Clean flat-vector mind map infographic, plain white background, {aspect}."
_PROMPT_TAIL = (
    "Render EXACTLY these labels, in Brazilian Portuguese, preserving accents. "
    "No other words, no watermark, no signature, no decorative letters. "
    "Palette: 2 colors + neutral, high contrast, generous spacing, legible at 1K."
)


def _prompt_branches(outline: dict) -> list[dict]:
    """Ramos do outline já saneados (sem [colchetes]/markdown), sem tocar no original."""
    raw = outline.get("ramos") if isinstance(outline, dict) else None
    branches: list[dict] = []
    for item in raw or []:
        if isinstance(item, dict):
            label = _clean_label(item.get("rotulo") or item.get("label"))
            kids_raw = item.get("filhos") or item.get("children") or []
        else:
            label = _clean_label(item)
            kids_raw = []
        if not label:
            continue
        kids = [k for k in (_clean_label(x) for x in kids_raw) if k]
        branches.append({"rotulo": label, "filhos": kids})
    return branches


def _compose_prompt(aspect: str, title: str, branches: list[dict]) -> str:
    lines = [
        _PROMPT_HEAD.format(aspect=aspect),
        f'Center node: "{title}". {len(branches)} '
        f'{"branch" if len(branches) == 1 else "branches"} connected by smooth arrows:',
    ]
    for b in branches:
        if b["filhos"]:
            lines.append(f'- branch "{b["rotulo"]}" with children: '
                         f'{"; ".join(b["filhos"])}.')
        else:
            lines.append(f'- branch "{b["rotulo"]}".')
    lines.append(_PROMPT_TAIL)
    return "\n".join(lines)


def _fit_label_budget(branches: list[dict], max_labels: int) -> list[dict]:
    """Prioriza título → todos os ramos → filhos (ordem do outline) até o teto.

    Devolve cópias: o outline original e o do SVG nunca são tocados. `max_labels`
    conta o título; `<= 0` desliga o teto. Ramos que já estouram o teto são
    cortados a partir do fim, na ordem do outline.
    """
    if max_labels <= 0:
        return [{"rotulo": b["rotulo"], "filhos": list(b["filhos"])} for b in branches]
    budget = max_labels - 1                      # o título ocupa 1 nó
    if budget <= 0:
        return []
    selected = [{"rotulo": b["rotulo"], "filhos": []} for b in branches[:budget]]
    budget -= len(selected)
    for src, dst in zip(branches, selected):
        if budget <= 0:
            break
        take = src["filhos"][:budget]
        dst["filhos"] = list(take)
        budget -= len(take)
    return selected


def outline_to_prompt(outline: dict, aspect: str = "4:3",
                      max_labels: int | None = None) -> str:
    """Prompt curto (≤1200 chars) p/ um modelo de imagem redesenhar o outline.

    Determinístico e sem markdown/colchetes. `max_labels` (default
    `IMAGE_MAX_LABELS`) limita os nós enviados: primeiro o título, depois todos os
    ramos e por fim os filhos, na ordem do outline. Se ainda não couber no teto de
    caracteres, os ÚLTIMOS filhos (e depois os últimos ramos) saem do prompt — o
    SVG continua com tudo; preferimos omitir um nó a truncar um rótulo.
    """
    outline = outline if isinstance(outline, dict) else {}
    aspect = str(aspect or "").strip() or "4:3"
    max_labels = IMAGE_MAX_LABELS if max_labels is None else int(max_labels)
    title = _clean_label(outline.get("titulo") or "Mapa mental")
    branches = _prompt_branches(outline)
    if branches:
        branches = _fit_label_budget(branches, max_labels)
    else:
        branches = [{"rotulo": "Visão geral", "filhos": []}]

    while True:
        prompt = _compose_prompt(aspect, title, branches)
        if len(prompt) <= IMAGE_PROMPT_MAX_CHARS:
            return prompt
        for b in reversed(branches):  # remove o último filho disponível
            if b["filhos"]:
                b["filhos"].pop()
                break
        else:
            if len(branches) > 1:
                branches.pop()
                continue
            # Último ramo sem filhos e ainda grande: encurta os rótulos.
            title = _clean_label(title, 24)
            branches[0]["rotulo"] = _clean_label(branches[0]["rotulo"], 24)
            prompt = _compose_prompt(aspect, title, branches)
            return prompt[:IMAGE_PROMPT_MAX_CHARS].rstrip()


# -- self-test offline --------------------------------------------------------
def _selftest() -> int:
    import xml.etree.ElementTree as ET

    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        print(("OK   " if cond else "FAIL ") + msg)
        ok = ok and cond

    fake = {
        "titulo": "VAEs e o ELBO",
        "ramos": [
            {"rotulo": "Objetivo", "filhos": ["latent space", "reconstrução"]},
            {"rotulo": "Trade-off", "filhos": ["fidelidade", "regularização"]},
            {"rotulo": "Loss", "filhos": ["ELBO", "divergência KL"]},
        ],
        "citacoes": ["Cap 3, p. 71", "Cap 3, p. 74"],
    }
    svg = outline_to_svg(fake)
    try:
        root = ET.fromstring(svg)
        check(True, "SVG é XML bem formado")
    except ET.ParseError as exc:
        root = None
        check(False, f"SVG XML inválido: {exc}")

    texts = ""
    if root is not None:
        texts = " ".join((t.text or "") for t in root.iter() if t.tag.endswith("text"))
    joined = _WS_RE.sub(" ", texts)
    labels = ([fake["titulo"]] + [b["rotulo"] for b in fake["ramos"]]
              + [k for b in fake["ramos"] for k in b["filhos"]])
    for label in labels:
        check(_WS_RE.sub(" ", label) in joined, f"rótulo presente: {label}")
    for cite in fake["citacoes"]:
        check(cite in joined, f"citação presente: {cite}")
    check(outline_to_svg(fake) == svg, "determinismo byte-a-byte")

    # M1: prompt do renderer generativo (curto, fiel, sem markdown/colchetes).
    prompt = outline_to_prompt(fake, aspect="16:9")
    check(len(prompt) <= IMAGE_PROMPT_MAX_CHARS,
          f"prompt ≤ {IMAGE_PROMPT_MAX_CHARS} chars ({len(prompt)})")
    check("16:9" in prompt, "aspecto do prompt respeitado")
    for label in labels:
        check(_WS_RE.sub(" ", label) in _WS_RE.sub(" ", prompt),
              f"rótulo no prompt: {label}")
    check(not any(ch in prompt for ch in "[]*#`"),
          "prompt sem markdown/colchetes")
    check("Brazilian Portuguese" in prompt and "preserving accents" in prompt,
          "prompt exige PT-BR com acentos")
    check(outline_to_prompt(fake) == outline_to_prompt(fake),
          "prompt determinístico")

    # 5 ramos × 3 filhos com rótulos longos: nada pode sair do viewBox.
    big = {
        "titulo": "Título bem comprido para forçar a altura do mapa",
        "ramos": [
            {"rotulo": f"Ramo {i} com um rótulo razoavelmente comprido",
             "filhos": [f"Filho {i}.{j} também comprido" for j in range(1, 4)]}
            for i in range(1, 6)
        ],
        "citacoes": ["Cap 3, p. 71", "Cap 3, p. 74", "Cap 4, p. 100"],
    }
    big_svg = outline_to_svg(big)
    try:
        big_root = ET.fromstring(big_svg)
        vb = [float(v) for v in big_root.get("viewBox", "").split()]
        view_h = vb[3]
        bad = []
        for el in big_root.iter():
            tag = el.tag.split("}")[-1]
            if tag in ("rect", "text"):
                ey = float(el.get("y", 0))
                eh = float(el.get("height", 0))
                if ey + eh > view_h + 0.01:
                    bad.append((tag, ey, eh))
        check(not bad, f"5 ramos × 3 filhos cabem no viewBox (H={view_h:.0f})")
    except (ET.ParseError, IndexError, ValueError) as exc:
        check(False, f"SVG grande inválido: {exc}")
    big_prompt = outline_to_prompt(big)
    check(len(big_prompt) <= IMAGE_PROMPT_MAX_CHARS,
          f"prompt do outline grande cabe no teto ({len(big_prompt)} chars)")

    # M1: teto de nós no prompt (título conta). O SVG continua completo.
    def _prompt_nodes(text: str) -> int:
        n_ramos = len(re.findall(r'- branch "', text))
        n_filhos = sum(len([x for x in m.group(1).split(";") if x.strip()])
                       for m in re.finditer(r"with children: (.+?)\.", text))
        return 1 + n_ramos + n_filhos

    big_nodes = _prompt_nodes(big_prompt)
    check(big_nodes <= IMAGE_MAX_LABELS,
          f"prompt respeita IMAGE_MAX_LABELS={IMAGE_MAX_LABELS} ({big_nodes} nós)")
    big_joined = _WS_RE.sub(" ", " ".join(
        (t.text or "") for t in big_root.iter() if t.tag.split("}")[-1] == "text"))
    check(all(_WS_RE.sub(" ", lbl) in big_joined
              for lbl in ([big["titulo"]] + [b["rotulo"] for b in big["ramos"]]
                          + [k for b in big["ramos"] for k in b["filhos"]])),
          "SVG do outline grande mantém TODOS os rótulos")
    first_only = outline_to_prompt(big, max_labels=1)
    check(_prompt_nodes(first_only) <= 1,
          f"max_labels=1 deixa só o título ({_prompt_nodes(first_only)} nó)")

    # Ramos pequenos + rótulos longos: o teto de caracteres continua valendo.
    long_labels = {
        "titulo": "Um título deliberadamente muito comprido para estourar o limite",
        "ramos": [{"rotulo": "Ramo com rótulo longo " * 2,
                   "filhos": [f"Filho {i}.{j} com descrição longa " * 2
                              for j in range(1, 4)]} for i in range(1, 3)],
    }
    long_prompt = outline_to_prompt(long_labels, max_labels=MINDMAP_MAX_BRANCHES)
    check(len(long_prompt) <= IMAGE_PROMPT_MAX_CHARS,
          f"MINDMAP_MAX_BRANCHES={MINDMAP_MAX_BRANCHES} + rótulos longos ≤ "
          f"{IMAGE_PROMPT_MAX_CHARS} chars ({len(long_prompt)})")
    check(not any(ch in long_prompt for ch in "[]*#`"),
          "prompt longo sem markdown/colchetes")

    out = Path("/tmp/mind_selftest.svg")
    out.write_text(svg, encoding="utf-8")
    print(f"SVG gravado em {out} ({len(svg)} chars)")

    # cache + parser sujo (cerca ```json + texto antes + vírgula final)
    calls = {"n": 0}

    def stub(system: str, user: str) -> str:
        calls["n"] += 1
        return ('Aqui está:\n```json\n{"titulo": "Teste", "ramos": ['
                '{"rotulo": "A", "filhos": ["x"]}, {"rotulo": "B", "filhos": []}, '
                '{"rotulo": "C", "filhos": []}], "citacoes": ["Cap 1, p. 2"],}\n```')

    query = "__selftest_cache__"
    p1 = "Trecho [Cap 1, p. 2]."
    o1, _, c1 = build_outline(p1, query, "selftest", use_cache=False, llm_fn=stub)
    check(calls["n"] == 1 and not c1, "1ª chamada usa LLM (1 call)")
    o2, _, c2 = build_outline(p1, query, "selftest", use_cache=True, llm_fn=stub)
    check(calls["n"] == 1 and c2, "2ª chamada vem do cache (sem LLM)")
    check(o1["titulo"] == "Teste" and o1 == o2,
          "JSON sujo (cerca + vírgula final) parseado")
    _cache_path("selftest", query, p1).unlink(missing_ok=True)

    def boom(system: str, user: str) -> str:
        raise RuntimeError("sem api")

    q2 = "Resumo do capítulo"
    p2 = "## Objetivo\nTexto.\n## Loss [Cap 2, p. 5]\nMais."
    path2 = _cache_path("selftest2", q2, p2)
    path2.unlink(missing_ok=True)
    o3, prov3, c3 = build_outline(p2, q2, "selftest2", use_cache=False, llm_fn=boom)
    check(prov3 == "heuristic" and not c3, "erro de LLM cai no heurístico")
    check(len(o3["ramos"]) >= 3 and bool(o3["citacoes"]),
          "heurístico tem 3+ ramos e citação")
    check(not path2.exists(), "heurístico NÃO grava cache")
    o4, prov4, c4 = build_outline(p2, q2, "selftest2", use_cache=True, llm_fn=boom)
    check(prov4 == "heuristic" and not c4, "2ª chamada heurística não é cache hit")
    check(not path2.exists(), "cache continua ausente após 2ª chamada")

    # cache legado com provider=heuristic precisa ser ignorado (e sobrescrito por LLM)
    path2.parent.mkdir(parents=True, exist_ok=True)
    path2.write_text(json.dumps({"outline": o3, "provider": "heuristic",
                                 "version": MINDMAP_VERSION}), encoding="utf-8")
    o5, prov5, c5 = build_outline(p2, q2, "selftest2", use_cache=True, llm_fn=stub)
    check(not c5 and prov5 != "heuristic", "cache heurístico legado é ignorado")
    check(path2.exists()
          and json.loads(path2.read_text(encoding="utf-8")).get("provider") != "heuristic",
          "cache legado é sobrescrito por resultado de LLM")
    path2.unlink(missing_ok=True)

    # -- regressão: finish_reason=length e retry sem `extra` (httpx.post fake) ----
    import httpx
    from src.llm_provider import OpenRouterProvider, complete_with_fallback

    def resp(status: int, data: dict) -> httpx.Response:
        req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        return httpx.Response(status, json=data, request=req)

    provider = OpenRouterProvider("fake-key", "deepseek/fake")
    real_post = httpx.post
    try:
        # (1) content não-vazio, mas cortado: precisa estourar RuntimeError.
        truncated = {"choices": [{"finish_reason": "length",
                                  "message": {"content": '{"titulo": "cort'}}]}
        httpx.post = lambda *a, **k: resp(200, truncated)
        try:
            provider.complete("s", "u", extra={"reasoning": {"effort": "none"}})
            check(False, "finish_reason=length levanta RuntimeError")
        except RuntimeError as exc:
            check("finish_reason=length" in str(exc),
                  "finish_reason=length levanta RuntimeError")
        except Exception as exc:  # noqa: BLE001
            check(False, f"finish_reason=length: exceção errada ({type(exc).__name__})")

        # (2) 400 no 1º POST (com extra) e 200 no 2º (sem extra): devolve texto.
        seen: list[dict] = []

        def fake_post(url, **kwargs):
            payload = kwargs.get("json") or {}
            seen.append(payload)
            if len(seen) == 1:
                return resp(400, {"error": {"message": "reasoning not supported"}})
            return resp(200, {"choices": [{"finish_reason": "stop",
                                           "message": {"content": "texto ok"}}]})

        httpx.post = fake_post
        got = provider.complete("s", "u", extra={"reasoning": {"effort": "none"}})
        check(got == "texto ok", "400 com `extra` repete sem extra e devolve texto")
        check(len(seen) == 2 and "reasoning" in seen[0] and "reasoning" not in seen[1],
              "retry sem extra manda 2 POSTs (1º com reasoning, 2º sem)")

        # (3) complete_with_fallback repassa `extra` ao provider.
        class _Stub:
            name = "stub"
            model_name = "stub-1"

            def __init__(self):
                self.got = None

            def complete(self, system, user, max_tokens=1500, extra=None):
                self.got = extra
                return "stub text"

        stub = _Stub()
        text, name = complete_with_fallback("s", "u", 100, [stub],
                                            extra={"reasoning": {"effort": "none"}})
        check(text == "stub text" and name == "stub"
              and stub.got == {"reasoning": {"effort": "none"}},
              "complete_with_fallback repassa extra")
    finally:
        httpx.post = real_post

    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
