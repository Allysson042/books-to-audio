"""Orçamento de contexto em tokens — P0 de `docs/LIMITS.md` (§10).

Funções puras e import leve (sem torch/chromadb) para poderem ser usadas em
`src/generate.py` e em testes rápidos.

- `count_tokens`: tiktoken (`cl100k_base`) em singleton lazy; sem tiktoken,
  cai para `len(text)//4` com aviso único.
- `fit_chunks_to_budget`: descarta chunks do FIM até caber no orçamento,
  preservando a ordem e os primeiros (micro > macro > mapa).
"""

from __future__ import annotations

from src.config import CONTEXT_TOKENS_BUDGET

_ENC = None
_ENC_TRIED = False
_WARNED = False


def _encoding():
    global _ENC, _ENC_TRIED, _WARNED
    if _ENC is None and not _ENC_TRIED:
        _ENC_TRIED = True
        try:
            import tiktoken

            _ENC = tiktoken.get_encoding("cl100k_base")
        except Exception as e:  # ImportError, rede (primeiro uso baixa o BPE), etc.
            if not _WARNED:
                _WARNED = True
                print(f"[context] tiktoken indisponível ({str(e)[:120]}) — "
                      f"contando tokens como len(text)//4 (aproximado).", flush=True)
    return _ENC


def count_tokens(text: str) -> int:
    """Tokens de `text` (cl100k_base) ou estimativa `len//4` sem tiktoken."""
    global _WARNED
    if not text:
        return 0
    enc = _encoding()
    if enc is None:
        if not _WARNED:
            _WARNED = True
            print("[context] tiktoken indisponível — contando tokens como len(text)//4.",
                  flush=True)
        return len(text) // 4
    return len(enc.encode(text, disallowed_special=()))


def _truncate_to_tokens(text: str, room: int) -> str:
    """Corta `text` (por caracteres, em fronteira de palavra) até caber em `room` tokens."""
    if room <= 0:
        return ""
    total = count_tokens(text)
    if total <= room:
        return text
    # proporção chars/token do próprio texto, com folga de 2% contra arredondamento
    cut = int(len(text) * room / total * 0.98)
    cut = max(0, min(cut, len(text)))
    while cut > 0 and count_tokens(text[:cut]) > room:
        cut = int(cut * 0.95)
    if cut <= 0:
        return ""
    head = text[:cut]
    if cut < len(text):
        head = head.rsplit(" ", 1)[0] if " " in head else head
        head = head + " […]"
    return head


def fit_chunks_to_budget(chunks: list[str], fixed_text: str,
                         budget: int = CONTEXT_TOKENS_BUDGET) -> list[str]:
    """Garante `count_tokens(fixed_text) + count_tokens(chunks) <= budget`.

    - `budget <= 0` desliga o clipping (retorna `chunks` intactos).
    - Descarta do FIM preservando a ordem e os primeiros chunks.
    - Nunca corta todos: se o 1º chunk sozinho estourar, ele é truncado por caracteres.
    """
    if budget <= 0 or not chunks:
        return list(chunks)

    counts = [count_tokens(c) for c in chunks]
    fixed = count_tokens(fixed_text)
    total = fixed + sum(counts)
    if total <= budget:
        return list(chunks)

    n = len(chunks)
    while n > 1 and total > budget:
        n -= 1
        total -= counts[n]

    kept = list(chunks[:n])
    if n == 1 and total > budget:  # o 1º sozinho estoura: trunca em vez de zerar
        room = budget - fixed
        kept[0] = _truncate_to_tokens(chunks[0], room)
        total = fixed + count_tokens(kept[0])

    print(f"[context] kept {len(kept)}/{len(chunks)} chunks (~{total}tok, "
          f"budget={budget}, fixed~{fixed}tok)", flush=True)
    return kept
