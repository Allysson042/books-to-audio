"""Estratégia vectorless (estilo PageIndex): LLM raciocina sobre a árvore e escolhe nós.

Uso:
    from src.retrieval_tree import TreeStore
    cands = TreeStore().search("What is ELBO?", chapter=None)  # final, ordenado

Retorna o MESMO formato de `RAGStore.search` (doc_id/text/metadata/citation) com
`tree_path` + `thinking` no lugar de ranks — downstream (Pass1/Pass2/TTS) reusado sem tocar.
Sem re-rank aqui: a seleção do LLM já é o ranking (comparação A/B pura contra o vetorial).
Seleção cacheada por (query, escopo) em cache/tree_sel_*.json (1 chamada LLM por query nova).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from src.llm_provider import complete_with_fallback
from src.retrieval import citation
from src.tree_index import TREE_VERSION, load_tree

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
MAX_NODES = 6       # nós por query
MAX_CHUNKS = 10      # chunks finais (paridade aprox. com o top-5 vetorial)

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


class TreeStore:
    def __init__(self):
        self.tree = load_tree()
        self.chunks = [json.loads(line) for line in
                       (ROOT / "storage" / "bm25.jsonl").read_text(encoding="utf-8").splitlines()]
        self.by_id: dict[str, tuple[dict, dict]] = {}

        def walk(ch, node, trail):
            self.by_id[node["node_id"]] = (ch, node, trail)
            for kid in node.get("children", []):
                walk(ch, kid, trail + [kid["title"]])

        for ch in self.tree["nodes"]:
            walk(ch, ch, [ch["title"]])

    def _prompt_tree(self, chapter: int | None) -> str:
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

    def _subtree_spans(self, node_id: str) -> list[tuple[int, tuple[int, int], str]]:
        """(chapter, (pdf_start, pdf_end), path) do nó + todos os descendentes."""
        ch, node, trail = self.by_id[node_id]
        spans = [(ch["chapter"], (node["pdf_start"], node["pdf_end"]), " > ".join(trail))]
        stack = list(node.get("children", []))
        while stack:
            kid = stack.pop(0)
            spans.append((ch["chapter"], (kid["pdf_start"], kid["pdf_end"]),
                          " > ".join(trail + [kid["title"]])))
            stack.extend(kid.get("children", []))
        return spans

    def _select_nodes(self, query: str, chapter: int | None, use_cache: bool) -> tuple[list[str], str]:
        scope = str(chapter) if chapter is not None else "all"
        key = hashlib.sha256(f"tree|v{TREE_VERSION}|{scope}|{query}".encode()).hexdigest()[:16]
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
        out, seen = [], set()
        for nid in node_ids:
            # Selecionar um pai puxa a subárvore inteira (respeitando MAX_CHUNKS).
            for ch_num, span, path in self._subtree_spans(nid):
                for c in self.chunks:
                    if (c["doc_id"] not in seen and c["chapter"] == ch_num
                            and not (c["page_end"] < span[0] or c["page_start"] > span[1])):
                        seen.add(c["doc_id"])
                        out.append({
                            "doc_id": c["doc_id"], "text": c["text"], "metadata": c,
                            "citation": citation(c), "dense_rank": None, "sparse_rank": None,
                            "rrf": None, "tree_path": f"Cap {ch_num} > {path}",
                            "thinking": thinking})
                    if len(out) >= MAX_CHUNKS:
                        break
                if len(out) >= MAX_CHUNKS:
                    break
            if len(out) >= MAX_CHUNKS:
                break
        if not out:
            raise ValueError("Tree-search selecionou nós sem chunks — tente o modo vetorial.")
        return out
