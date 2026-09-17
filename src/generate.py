"""S3 — Geração 2-pass com personas + glossário + cache por hash.

Pass1 `resumo_tecnico`: fiel, denso, com citações [Cap X, p. Y].
Pass2 `roteiro_audio`: reescrita fluida TTS-friendly (S4 consome este texto).
Cache em ./cache/: nada regenera se o hash existir (R$0 + anti-demo-effect).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from src.llm_provider import complete_with_fallback
from src.prompts import GLOSSARIO, PASS1, PASS2_INICIANTE, PASS2_TECNICO
from src.retrieval import RAGStore, Reranker

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
PERSONAS = ROOT / "personas"
PROMPT_VERSION = "v1"  # bump p/ invalidar todo o cache textual
CHUNK_CHARS = 1500    # truncagem por chunk no prompt (5 chunks ~= 7.5k chars)


def load_persona(name: str) -> dict:
    with open(PERSONAS / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def pass1_system(persona_addendum: str) -> str:
    return (PASS1
            + f"\nGlossário — termos a preservar em EN, nunca traduzir: {', '.join(GLOSSARIO)}."
            + f"\nPerfil do leitor: {persona_addendum}")


def pass1_user(query: str, chunks: list[dict], macro: str | None) -> str:
    parts = [f"Pergunta: {query}"]
    if macro:
        parts.append(f"Resumo macro do capítulo em foco (contexto, PT-BR):\n{macro[:3000]}")
    parts.append("Chunks recuperados (fontes — cite como [Cap X, p. Y]):")
    for c in chunks:
        m = c["metadata"]
        parts.append(f"- {c['citation']} {m['section']} [{m['type']}]: {c['text'][:CHUNK_CHARS]}")
    parts.append("Responda em PT-BR. Se os chunks não contiverem a resposta, diga que não encontrou.")
    return "\n\n".join(parts)


def pass2_prompt(pass1_text: str, persona: str) -> tuple[str, str]:
    system = (PASS2_INICIANTE if persona == "iniciante_guiado" else PASS2_TECNICO)
    return system, f"Resumo técnico de base:\n\n{pass1_text}"


def _key(*bits: str) -> str:
    return hashlib.sha256("|".join(bits).encode()).hexdigest()[:16]


def answer(query: str, chapter: int | None, persona: str = "tecnico_direto",
           store: RAGStore | None = None, reranker: Reranker | None = None,
           macro: str | None = None) -> dict:
    """Pipeline S3: retrieve top-5 -> Pass1 (cache) -> Pass2 (cache)."""
    store = store or RAGStore()
    reranker = reranker or Reranker()
    chunks = reranker.rerank(query, store.search(query, chapter, top_n=20), top_n=5)
    if not chunks:
        raise ValueError("Nada recuperado neste escopo — tente 'Livro todo'.")

    CACHE.mkdir(parents=True, exist_ok=True)
    chunk_sig = ",".join(sorted(c["doc_id"] for c in chunks))
    scope = str(chapter) if chapter is not None else "all"
    h1 = _key(PROMPT_VERSION, "pass1", scope, query, chunk_sig)
    h2 = _key(PROMPT_VERSION, "pass2", persona, scope, query, chunk_sig)
    p1_path, p2_path = CACHE / f"pass1_{h1}.md", CACHE / f"pass2_{persona}_{h2}.md"

    addendum = load_persona(persona).get("system_addendum", "")
    provider = "cache"
    if p1_path.exists() and p2_path.exists():
        return {"pass1": p1_path.read_text(encoding="utf-8"),
                "pass2": p2_path.read_text(encoding="utf-8"),
                "chunks": chunks, "provider": provider, "cached": True}

    if not p1_path.exists():
        text1, provider = complete_with_fallback(
            pass1_system(addendum), pass1_user(query, chunks, macro))
        p1_path.write_text(text1, encoding="utf-8")
    else:
        text1 = p1_path.read_text(encoding="utf-8")
    if not p2_path.exists():
        system2, user2 = pass2_prompt(text1, persona)
        text2, provider = complete_with_fallback(system2, user2)
        p2_path.write_text(text2, encoding="utf-8")
    else:
        text2 = p2_path.read_text(encoding="utf-8")
    return {"pass1": text1, "pass2": text2, "chunks": chunks,
            "provider": provider, "cached": False}
