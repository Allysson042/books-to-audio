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

# -- LLM ----------------------------------------------------------------------
LLM_TIMEOUT = env_int("LLM_TIMEOUT", 120)   # timeout por request (s)
LLM_RETRIES = env_int("LLM_RETRIES", 1)     # tentativas EXTRAS após a 1ª falha
LLM_PROMPT_CHARS = env_int("LLM_PROMPT_CHARS", 12000)  # width do opencode-subprocess
# None = não enviado ao provider (comportamento antigo preservado)
LLM_TEMPERATURE = env_float("LLM_TEMPERATURE", None)
