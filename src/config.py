"""Configuração central por env — P0 de `docs/LIMITS.md`.

Todos os defaults são **idênticos aos valores hardcoded anteriores**: importar este
módulo não muda comportamento nenhum. Só o `.env` / ambiente muda algo.

Uso:
    from src import config
    config.CHUNK_CHARS

Escopo: apenas leitura de ambiente (sem torch/chromadb — import leve).
O `.env` da raiz é carregado no import (best-effort) para que os valores valham
tanto no `streamlit run` quanto em scripts.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:  # .env antes de ler qualquer variável (python-dotenv já é dependência)
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover - dotenv é obrigatório no requirements
    pass


def env_str(name: str, default: str | None = None) -> str | None:
    """String do ambiente (``""`` e ausente contam como default)."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def env_int(name: str, default: int) -> int:
    """Inteiro do ambiente; valor inválido cai no default (com aviso)."""
    raw = env_str(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[config] {name}={raw!r} não é inteiro — usando default {default}", flush=True)
        return default


def env_float(name: str, default: float | None = None) -> float | None:
    """Float do ambiente; default pode ser ``None`` (variável "não setada")."""
    raw = env_str(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"[config] {name}={raw!r} não é número — usando default {default}", flush=True)
        return default


def env_bool(name: str, default: bool) -> bool:
    """Booleano do ambiente: 1/true/yes/on (case-insensitive); resto = default."""
    raw = env_str(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


# -- contexto / geração -------------------------------------------------------
CHUNK_CHARS = env_int("CHUNK_CHARS", 4500)          # corte por chunk no prompt (Pass1)
MAX_TOKENS = env_int("MAX_TOKENS", 2500)            # teto de saída Pass1/Pass2
CONTEXT_TOKENS_BUDGET = env_int("CONTEXT_TOKENS_BUDGET", 24000)  # 0 = desliga o clipping
MAX_QUERY_CHARS = env_int("MAX_QUERY_CHARS", 2000)  # limite do input na UI

# -- retrieval vetorial -------------------------------------------------------
RETRIEVAL_PREFETCH = env_int("RETRIEVAL_PREFETCH", 20)  # top-k denso/BM25/candidatos RRF
RETRIEVAL_TOP_N = env_int("RETRIEVAL_TOP_N", 5)         # final do vetorial (pós re-rank)

# -- retrieval vectorless -----------------------------------------------------
MAX_NODES = env_int("MAX_NODES", 6)   # nós que o LLM pode escolher por query
MAX_CHUNKS = env_int("MAX_CHUNKS", 10)  # chunks finais da árvore


def _tree_delivery() -> str:
    """`ranked` (default) ou `legacy`; valor inválido cai em `ranked` com aviso."""
    raw = env_str("TREE_DELIVERY", "ranked")
    if raw not in ("ranked", "legacy"):
        print(f"[config] TREE_DELIVERY={raw!r} inválido (use ranked|legacy) — usando 'ranked'",
              flush=True)
        return "ranked"
    return raw


TREE_DELIVERY = _tree_delivery()  # ranked = in_scope + quota por nó; legacy = comportamento antigo
# V2: store de chunks alinhados à seção do TOC (só o TreeStore lê; fallback = bm25.jsonl)
TREE_CHUNKS_PATH = env_str("TREE_CHUNKS_PATH", "storage/tree_chunks.jsonl")


def _tree_prompt() -> str:
    """`v2` (default, páginas impressas + snippets) ou `v1` (prompt antigo, cache antigo)."""
    raw = env_str("TREE_PROMPT", "v2")
    if raw not in ("v1", "v2"):
        print(f"[config] TREE_PROMPT={raw!r} inválido (use v1|v2) — usando 'v2'", flush=True)
        return "v2"
    return raw


TREE_PROMPT = _tree_prompt()  # v1 = prompt antigo exato (A/B com cache tree_sel antigo)

# -- TTS ----------------------------------------------------------------------
TTS_MAX_CHARS = env_int("TTS_MAX_CHARS", 15000)   # trava de custo do premium
TTS_SLICE_CHARS = env_int("TTS_SLICE_CHARS", 2500)  # alvo por request/fatia

# -- mapa mental (M0: outline JSON + SVG determinístico, US$ 0) ----------------
MINDMAP_ENABLED = env_bool("MINDMAP_ENABLED", True)   # card + botão na UI
MINDMAP_MAX_BRANCHES = env_int("MINDMAP_MAX_BRANCHES", 5)  # nós de 1º nível
MINDMAP_MAX_DEPTH = env_int("MINDMAP_MAX_DEPTH", 2)  # 2 = título → ramo → filho
MINDMAP_LABEL_CHARS = env_int("MINDMAP_LABEL_CHARS", 40)  # corte de rótulo
MINDMAP_VERSION = env_str("MINDMAP_VERSION", "v1")   # bust do outline em cache


def _mindmap_reasoning() -> str:
    """`reasoning.effort` do outline: default `none`; `""`/`off` = não enviar.

    Lê o ambiente cru de propósito: aqui `""` significa "desligado", não "default".
    """
    raw = os.getenv("MINDMAP_REASONING")
    return "none" if raw is None else raw.strip()


MINDMAP_REASONING = _mindmap_reasoning()  # ex. none|minimal|low|medium|high|off

# -- mapa mental M1: render generativo (OpenRouter Images) --------------------
# `IMAGE_MODEL` vazio = renderer desligado (R$ 0 preservado; botão "Estilizar" some).
IMAGE_MODEL = env_str("IMAGE_MODEL", "")
IMAGE_QUALITY = env_str("IMAGE_QUALITY", "medium")      # só p/ modelos com o knob
IMAGE_ASPECT = env_str("IMAGE_ASPECT", "4:3")
IMAGE_RESOLUTION = env_str("IMAGE_RESOLUTION", "1K")    # vazio = não enviar
IMAGE_MAX_LABELS = env_int("IMAGE_MAX_LABELS", 12)      # nós no prompt (título conta; 0 = sem teto)
IMAGE_TIMEOUT = env_int("IMAGE_TIMEOUT", 180)           # timeout por request (s)
IMAGE_RETRIES = env_int("IMAGE_RETRIES", 1)             # tentativas EXTRAS (429/5xx/timeout)
IMAGE_VERSION = env_str("IMAGE_VERSION", "v1")          # bust do cache de imagens

# -- LLM ----------------------------------------------------------------------
LLM_TIMEOUT = env_int("LLM_TIMEOUT", 120)   # timeout por request (s)
LLM_RETRIES = env_int("LLM_RETRIES", 1)     # tentativas EXTRAS após a 1ª falha
LLM_PROMPT_CHARS = env_int("LLM_PROMPT_CHARS", 12000)  # width do opencode-subprocess
# None = não enviado ao provider (comportamento antigo preservado)
LLM_TEMPERATURE = env_float("LLM_TEMPERATURE", None)
