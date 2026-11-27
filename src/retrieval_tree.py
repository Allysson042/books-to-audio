"""Estratégia vectorless (estilo PageIndex): LLM raciocina sobre a árvore e escolhe nós.

Uso:
    from src.retrieval_tree import TreeStore
    cands = TreeStore().search("What is ELBO?", chapter=None)  # final, ordenado

Retorna o MESMO formato de `RAGStore.search` (doc_id/text/metadata/citation) com
`tree_path` + `thinking` no lugar de ranks — downstream (Pass1/Pass2/TTS) reusado sem tocar.
Sem re-rank aqui: a seleção do LLM já é o ranking (comparação A/B pura contra o vetorial).
Seleção cacheada por (query, escopo) em cache/tree_sel_*.json (1 chamada LLM por query nova).

Entrega dos chunks (`TREE_DELIVERY`, `docs/LIMITS.md` §11 V1/V2.1):
- `ranked` (default): ranqueia por `tree_fit` + `tree_lex` (tokens da query no texto)
  e distribui por quota entre os nós. `tree_fit` = `in_scope` (fração das páginas do
  chunk dentro de UMA folha — métrica de *bleed*) quando > 0; se `in_scope == 0` (chunk
  de abertura de capítulo/seção em páginas sem folha), usa a fração coberta pelo span do
  próprio nó selecionado **multiplicada por `FALLBACK_FIT_DISCOUNT` (0.5)** — o fallback
  nunca deve superar um match genuíno de folha. `in_scope` permanece com o significado
  original (régua).
- `legacy`: comportamento antigo (ordem do arquivo, 1º nó consome as vagas).
A seleção de nós não muda em nenhum dos dois — `tree_sel_*` continua válido.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ingest import BOOK_PAGE_OFFSET  # mesmo import que tree_index.py (páginas impressas)
from src.config import (MAX_CHUNKS, MAX_NODES, TREE_CHUNKS_PATH, TREE_DELIVERY,
                        TREE_PROMPT)
from src.llm_provider import complete_with_fallback
from src.retrieval import citation
from src.tree_index import TREE_VERSION, load_tree

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"

# V3: snippet por folha no prompt de seleção (`TREE_PROMPT=v2`).
SNIPPET_CHARS = 80        # tamanho alvo do trecho por folha (corte em palavra)
SNIPPET_BUDGET = 12000    # teto total de chars de snippet no prompt (~160 folhas)

# Desconto aplicado ao fallback de `tree_fit` (V2.1). O span do nó costuma cobrir 100%
# dos chunks de abertura de capítulo/seção, o que faria o fallback empatar em 1.0 e passar
# na frente de um match genuíno de folha. Regra: fallback nunca supera um `in_scope` > 0.
FALLBACK_FIT_DISCOUNT = 0.5

SEARCH_SYSTEM = """Você navega no sumário em árvore de um livro técnico (títulos + resumos + páginas).
Dada a pergunta, escolha os nós (seções; só use capítulo se a pergunta for panorâmica)
que provavelmente contêm a resposta. Escolher um nó pai cobre automaticamente os filhos —
prefira o pai quando a pergunta abranger a seção inteira. Comece sua resposta DIRETAMENTE com {, sem nenhum texto antes.
Responda com UMA ÚNICA linha JSON: {"thinking": "<raciocínio curto>", "node_ids": ["id", ...]}."""


def _parse_selection(raw: str, valid_ids: set[str]) -> dict | None:
    """Extrai {thinking, node_ids} de respostas rebeldes (preâmbulo, blocos, aspas)."""
    try:
        sel = json.loads(raw)
        if isinstance(sel.get("node_ids"), list):
            return sel
    except (json.JSONDecodeError, AttributeError):
        pass
    for pat in (r"\{[^{}]*\"node_ids\"\s*:\s*\[[^\]]*\][^{}]*\}", r"\{.*\}"):
        m = re.search(pat, raw, re.DOTALL)
        if m:
            try:
                sel = json.loads(m.group(0))
                if isinstance(sel.get("node_ids"), list):
                    return sel
            except json.JSONDecodeError:
                continue
    m = re.search(r"\"node_ids\"\s*:\s*\[(.*?)\]", raw, re.DOTALL)
    if m:
        ids = re.findall(r"\"([^\"]+)\"", m.group(1))
        if ids:
            return {"thinking": "", "node_ids": ids}
    # Último recurso: o raciocínio citou IDs de nós (ex. ch04_s02) — usa os citados.
    cited = [i for i in re.findall(r"\b(ch\d{2}(?:_s\d{2})?)\b", raw) if i in valid_ids]
    if cited:
        return {"thinking": raw[:300], "thinking_fallback": True, "node_ids": cited}
    return None


# -- V1: entrega de chunks por ranking/quota (puro, sem LLM) ------------------

def _page_overlap(chunk: dict, span: tuple[int, int]) -> int:
    """Páginas em comum (ranges inclusivos) entre um chunk e um span da árvore."""
    return max(0, min(chunk["page_end"], span[1]) - max(chunk["page_start"], span[0]) + 1)


def query_tokens(query: str) -> set[str]:
    """Tokens úteis da query: lowercase, >=3 chars (dígitos sempre entram)."""
    return {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) >= 3 or t.isdigit()}


def _tree_lex(text: str, tokens: set[str]) -> float:
    """Fração dos tokens da query presentes no texto (0..1)."""
    if not tokens:
        return 0.0
    return len(tokens & set(re.findall(r"[a-z0-9]+", text.lower()))) / len(tokens)


def _chunk_sort_key(chunk: dict) -> tuple:
    """Ordena por `tree_fit` (fallback `in_scope` p/ dicts antigos/legacy)."""
    fit = chunk.get("tree_fit", chunk.get("in_scope", 0.0))
    return (-float(fit), -float(chunk.get("tree_lex", 0.0)),
            chunk["metadata"]["page_start"], chunk["doc_id"])


def rank_and_allocate(node_pools: list[tuple[str, list[dict]]],
                      max_chunks: int) -> list[dict]:
    """Entrega justa por nó: quota round-robin + preenchimento global do resto.

    Puro (sem LLM/IO) para ser testável. Cada chunk já traz:
    - `in_scope`: fração das páginas do chunk dentro de UMA folha do nó (métrica de
      *bleed* contra folhas — mede se o chunk pertence ao nível fino da subárvore);
    - `tree_fit`: sinal de ranking = `in_scope` quando > 0, senão a fração coberta pelo
      span do próprio nó selecionado **vezes `FALLBACK_FIT_DISCOUNT` (0.5)** (V2.1 —
      resgata chunks de abertura de capítulo/seção que caem em páginas sem folha, sem
      mudar `in_scope` e sem o fallback passar na frente de um match genuíno de folha);
    - `tree_lex`: fração dos tokens da query no texto.
    Ordenação interna: (-tree_fit, -tree_lex, page_start, doc_id); dicts sem `tree_fit`
    (legacy) caem para `in_scope`. Rodada 1: até `per_node` por nó **na ordem de
    seleção**. Rodada 2: vagas restantes saem do merge global dos pools. Dedupe por
    `doc_id`; nunca passa de `max_chunks`. A quota decide **pertinência** (quem entra);
    a saída é reordenada por score, então a **prioridade** (`tree@5`) é sempre o melhor
    chunk disponível.
    """
    if max_chunks <= 0 or not node_pools:
        return []
    ranked = [(nid, sorted(pool, key=_chunk_sort_key)) for nid, pool in node_pools]
    per_node = max(1, max_chunks // len(ranked))
    out: list[dict] = []
    seen: set[str] = set()

    for _nid, pool in ranked:  # rodada 1: quota por nó
        taken = 0
        for chunk in pool:
            if taken >= per_node or len(out) >= max_chunks:
                break
            if chunk["doc_id"] in seen:
                continue
            seen.add(chunk["doc_id"])
            out.append(chunk)
            taken += 1

    if len(out) < max_chunks:  # rodada 2: sobras pelo ranking global
        merged = sorted((c for _nid, pool in ranked for c in pool), key=_chunk_sort_key)
        for chunk in merged:
            if len(out) >= max_chunks:
                break
            if chunk["doc_id"] in seen:
                continue
            seen.add(chunk["doc_id"])
            out.append(chunk)

    return sorted(out, key=_chunk_sort_key)  # pertinência = quota; prioridade = score


def _clean_snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    """Trecho de uma linha: sem bullets, espaços duplos/quebras, corte em palavra."""
    text = text.replace("•", " ")
    text = re.sub(r"^\s*[-*–—]\s*", " ", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:.-–—")


class TreeStore:
    def __init__(self):
        self.tree = load_tree()
        self.chunks, self.chunks_source = self._load_chunks()
        self.chunks_count = len(self.chunks)
        self.by_id: dict[str, tuple[dict, dict]] = {}

        def walk(ch, node, trail):
            self.by_id[node["node_id"]] = (ch, node, trail)
            for kid in node.get("children", []):
                walk(ch, kid, trail + [kid["title"]])

        for ch in self.tree["nodes"]:
            walk(ch, ch, [ch["title"]])

    @staticmethod
    def _load_chunks() -> tuple[list[dict], str]:
        """`TREE_CHUNKS_PATH` (V2, alinhado à seção) se válido; senão `bm25.jsonl`.

        Arquivo ausente, vazio ou corrompido nunca derruba o app: avisa e cai no
        docstore antigo. Imprime UMA linha `[tree] chunks: <path> (N)`.
        """
        fallback = ROOT / "storage" / "bm25.jsonl"
        path = Path(TREE_CHUNKS_PATH or "storage/tree_chunks.jsonl")
        if not path.is_absolute():
            path = ROOT / path
        chunks: list[dict] = []
        if path.exists():
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
                chunks = [json.loads(line) for line in lines if line.strip()]
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[tree] aviso: {path} ilegível ({type(exc).__name__}: {exc}) — "
                      f"usando {fallback}", flush=True)
                chunks = []
        if not chunks and path != fallback:
            print(f"[tree] aviso: {path} vazio/ausente — usando {fallback}", flush=True)
        if not chunks:
            path = fallback
            chunks = [json.loads(line) for line in
                      path.read_text(encoding="utf-8").splitlines() if line.strip()]
        try:
            shown = path.relative_to(ROOT)
        except ValueError:
            shown = path
        print(f"[tree] chunks: {shown} ({len(chunks)})", flush=True)
        return chunks, str(shown)

    def _prompt_tree(self, chapter: int | None) -> str:
        """Prompt de seleção. `TREE_PROMPT=v1` = formato antigo exato (cache antigo)."""
        prompt = (self._prompt_tree_v1(chapter) if TREE_PROMPT == "v1"
                  else self._prompt_tree_v2(chapter))
        print(f"[tree] prompt={TREE_PROMPT} chars={len(prompt)}", flush=True)
        return prompt

    def _prompt_tree_v1(self, chapter: int | None) -> str:
        """Prompt antigo byte-a-byte: capítulo em páginas impressas, L3/L4 em páginas do PDF."""
        lines = []

        def show(node, depth):
            pad = "  " * depth
            if depth == 0:
                lines.append(f"{pad}- {node['node_id']} [Cap {node['chapter']}, "
                             f"pp. {node['book_start']}-{node['book_end']}] "
                             f"{node['title']}: {node['summary'][:200]}")
            else:
                lines.append(f"{pad}- {node['node_id']} [pdf pp. {node['pdf_start']}-{node['pdf_end']}] "
                             f"{node['title']}")
            for kid in node.get("children", []):
                show(kid, depth + 1)

        for ch in self.tree["nodes"]:
            if chapter is not None and ch["chapter"] != chapter:
                continue
            show(ch, 0)
        return "\n".join(lines)

    def _node_snippet(self, chapter: int, pdf_start: int, pdf_end: int) -> str:
        """Trecho do 1º chunk do nó (páginas dentro do range; senão sobreposição)."""
        inside, overlap = [], []
        for c in self.chunks:
            if c["chapter"] != chapter:
                continue
            if c["page_start"] >= pdf_start and c["page_end"] <= pdf_end:
                inside.append(c)
            elif not (c["page_end"] < pdf_start or c["page_start"] > pdf_end):
                overlap.append(c)
        pool = inside or overlap
        if not pool:
            return ""
        first = min(pool, key=lambda c: (c["page_start"], c["doc_id"]))
        return _clean_snippet(first["text"])

    def _prompt_tree_v2(self, chapter: int | None) -> str:
        """V3: tudo em página impressa (`pdf - BOOK_PAGE_OFFSET`) + snippet por folha.

        Guarda de orçamento: para de acrescentar snippets quando o total passa de
        `SNIPPET_BUDGET` (o excedente fica sem snippet, sem quebrar o prompt).
        """
        lines = []
        stats = {"leaves": 0, "with_snippet": 0, "chars": 0}
        budget_hit = False

        def show(node, depth, ch_num):
            nonlocal budget_hit
            pad = "  " * depth
            bs = node["pdf_start"] - BOOK_PAGE_OFFSET
            be = node["pdf_end"] - BOOK_PAGE_OFFSET
            if depth == 0:
                lines.append(f"{pad}- {node['node_id']} [Cap {node['chapter']}, "
                             f"pp. {bs}-{be}] {node['title']}: {node['summary'][:200]}")
            else:
                line = (f"{pad}- {node['node_id']} [pp. {bs}-{be}] {node['title']}")
                kids = node.get("children", [])
                if not kids:
                    stats["leaves"] += 1
                    if not budget_hit:
                        snippet = self._node_snippet(ch_num, node["pdf_start"],
                                                     node["pdf_end"])
                        if snippet:
                            stats["with_snippet"] += 1
                            stats["chars"] += len(snippet)
                            line += " — " + snippet
                            if stats["chars"] > SNIPPET_BUDGET:
                                budget_hit = True
                lines.append(line)
            for kid in node.get("children", []):
                show(kid, depth + 1, ch_num)

        for ch in self.tree["nodes"]:
            if chapter is not None and ch["chapter"] != chapter:
                continue
            show(ch, 0, ch["chapter"])
        print(f"[tree] snippets: {stats['with_snippet']}/{stats['leaves']} nós, "
              f"~{stats['chars']} chars", flush=True)
        return "\n".join(lines)

    def _subtree_spans(self, node_id: str) -> list[tuple[int, tuple[int, int], str, bool]]:
        """(chapter, (pdf_start, pdf_end), path, is_leaf) do nó + todos os descendentes."""
        ch, node, trail = self.by_id[node_id]
        spans = [(ch["chapter"], (node["pdf_start"], node["pdf_end"]), " > ".join(trail),
                  not node.get("children"))]
        stack = list(node.get("children", []))
        while stack:
            kid = stack.pop(0)
            spans.append((ch["chapter"], (kid["pdf_start"], kid["pdf_end"]),
                          " > ".join(trail + [kid["title"]]), not kid.get("children")))
            stack.extend(kid.get("children", []))
        return spans

    @staticmethod
    def _leaves(spans: list[tuple[int, tuple[int, int], str, bool]]) -> list[tuple[int, int]]:
        """Spans das folhas da subárvore (fallback: a própria span do nó)."""
        return [s[1] for s in spans if s[3]] or [spans[0][1]]

    @staticmethod
    def _in_scope(chunk: dict, leaves: list[tuple[int, int]]) -> float:
        """Fração das páginas do chunk dentro de UMA única folha (0..1)."""
        pages = max(1, chunk["page_end"] - chunk["page_start"] + 1)
        return round(max(_page_overlap(chunk, leaf) for leaf in leaves) / pages, 4)

    def _select_nodes(self, query: str, chapter: int | None, use_cache: bool) -> tuple[list[str], str]:
        scope = str(chapter) if chapter is not None else "all"
        # v1 mantém o formato antigo (reusa `cache/tree_sel_*`); v2 ganha sufixo `p2`.
        tag = "" if TREE_PROMPT == "v1" else "p2|"
        key = hashlib.sha256(f"tree|v{TREE_VERSION}|{tag}{scope}|{query}".encode()).hexdigest()[:16]
        sel_path = CACHE / f"tree_sel_{key}.json"
        if use_cache and sel_path.exists():
            sel = json.loads(sel_path.read_text(encoding="utf-8"))
            return sel["node_ids"], sel["thinking"]
        user = f"Pergunta: {query}\n\nÁrvore do documento:\n{self._prompt_tree(chapter)}"
        raw, _ = complete_with_fallback(SEARCH_SYSTEM, user, max_tokens=1200)
        sel = _parse_selection(raw, set(self.by_id))
        if sel is None:  # 1 retry com ordem mais severa (reenviando a árvore) antes de desistir
            raw, _ = complete_with_fallback(
                "Você responde APENAS com uma única linha JSON válida, sem nenhum outro texto, "
                "sem explicações, sem markdown. Formato exato: "
                "{\"thinking\": \"...\", \"node_ids\": [\"...\"]}",
                f"A resposta anterior foi inválida por conter texto fora do JSON. Tente de novo.\n\n{user}",
                max_tokens=1200)
            sel = _parse_selection(raw, set(self.by_id))
        if sel is None:
            raise RuntimeError(
                "Tree-search não devolveu JSON válido após 2 tentativas. "
                "Troque a Estratégia p/ 'vetorial' na sidebar ou tente de novo. "
                f"Amostra: {raw[:200]}")
        node_ids = [i for i in sel.get("node_ids", []) if i in self.by_id][:MAX_NODES]
        if not node_ids:
            raise RuntimeError(f"Tree-search não selecionou nós válidos: {raw[:200]}")
        sel_path.write_text(json.dumps({"node_ids": node_ids, "thinking": sel.get("thinking", "")},
                                       ensure_ascii=False), encoding="utf-8")
        return node_ids, sel.get("thinking", "")

    def search(self, query: str, chapter: int | None = None, use_cache: bool = True) -> list[dict]:
        node_ids, thinking = self._select_nodes(query, chapter, use_cache)
        if TREE_DELIVERY == "legacy":
            out = self._search_legacy(node_ids, thinking)
        else:
            out = self._search_ranked(node_ids, thinking, query)
        if not out:
            raise ValueError("Tree-search selecionou nós sem chunks — tente o modo vetorial.")
        return out

    def _search_legacy(self, node_ids: list[str], thinking: str) -> list[dict]:
        """Comportamento original (`TREE_DELIVERY=legacy`): ordem do arquivo + break."""
        out, seen = [], set()
        for nid in node_ids:
            # Selecionar um pai puxa a subárvore inteira (respeitando MAX_CHUNKS).
            spans = self._subtree_spans(nid)
            leaves = self._leaves(spans)
            for ch_num, span, path, _leaf in spans:
                for c in self.chunks:
                    if (c["doc_id"] not in seen and c["chapter"] == ch_num
                            and not (c["page_end"] < span[0] or c["page_start"] > span[1])):
                        seen.add(c["doc_id"])
                        out.append({
                            "doc_id": c["doc_id"], "text": c["text"], "metadata": c,
                            "citation": citation(c), "dense_rank": None, "sparse_rank": None,
                            "rrf": None, "tree_path": f"Cap {ch_num} > {path}",
                            "thinking": thinking, "in_scope": self._in_scope(c, leaves)})
                    if len(out) >= MAX_CHUNKS:
                        break
                if len(out) >= MAX_CHUNKS:
                    break
            if len(out) >= MAX_CHUNKS:
                break
        return out

    def _search_ranked(self, node_ids: list[str], thinking: str, query: str) -> list[dict]:
        """V1/V2.1: ranqueia por `tree_fit`/`tree_lex` e distribui por quota entre os nós.

        `tree_fit` = `in_scope` se > 0, senão a fração das páginas do chunk cobertas
        pelo span do **próprio nó selecionado** vezes `FALLBACK_FIT_DISCOUNT` (0.5) (V2.1).
        O desconto impede que o fallback (span de capítulo cobre 100% da abertura) supere
        um match genuíno de folha. Mantém `in_scope` intacto para a régua.
        """
        tokens = query_tokens(query)
        lex_cache: dict[str, float] = {}
        pools: list[tuple[str, list[dict]]] = []
        for nid in node_ids:
            spans = self._subtree_spans(nid)
            leaves = self._leaves(spans)
            node_span = [spans[0][1]]  # span do próprio nó (1º item de _subtree_spans)
            pool: list[dict] = []
            for c in self.chunks:
                best_ov, best_path = 0, None
                for ch_num, span, path, _leaf in spans:  # elegibilidade = regra antiga
                    if c["chapter"] != ch_num:
                        continue
                    ov = _page_overlap(c, span)
                    if ov > best_ov:
                        best_ov, best_path = ov, path
                if best_path is None:
                    continue
                if c["doc_id"] not in lex_cache:
                    lex_cache[c["doc_id"]] = round(_tree_lex(c["text"], tokens), 4)
                leaf_scope = self._in_scope(c, leaves)
                tree_fit = (leaf_scope if leaf_scope > 0
                            else FALLBACK_FIT_DISCOUNT * self._in_scope(c, node_span))
                pool.append({
                    "doc_id": c["doc_id"], "text": c["text"], "metadata": c,
                    "citation": citation(c), "dense_rank": None, "sparse_rank": None,
                    "rrf": None, "tree_path": f"Cap {c['chapter']} > {best_path}",
                    "thinking": thinking, "in_scope": leaf_scope,
                    "tree_fit": tree_fit, "tree_lex": lex_cache[c["doc_id"]]})
            pools.append((nid, pool))
        return rank_and_allocate(pools, MAX_CHUNKS)
