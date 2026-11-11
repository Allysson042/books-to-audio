# Árvore hierárquica real (L2/L3/L4 do TOC) — plano

Data: 2026-10-09. Origem: teste "explique a seção What Is Generative Modeling (Cap 1)"
retornou só 2 chunks; pelo sumário a seção vai das pp. 4–8 e CONTÉM 3 subseções.

## 1. Causa raiz (2 problemas somados)

- **Árvore achatada**: `tree_index.py` agrupa chunks por `(capítulo, título)` num nível só.
  O TOC tem 3 níveis (L2 capítulo → L3 seção → L4 subseção), mas L3 e L4 viram "irmãos".
  Resultado: "What Is Generative Modeling?" (L3, pp. 4–8) e "Generative Versus..." (L4, p. 5)
  parecem tópicos lado a lado, quando um contém o outro.
- **Ranges truncados**: o range de cada nó é min/max das páginas dos chunks *etiquetados*
  com aquele título. Como a ingestão etiqueta cada página com a seção vigente (a mais
  profunda), as páginas 5–8 foram etiquetadas com as subseções — o nó pai ficou só com
  as pp. 4–5. O tree-search escolheu certo; o mapa de páginas é que estava errado.

## 2. Correção

1. **`tree_index.py`: hierarquia de verdade** — ler o TOC com níveis (`doc.get_toc()`),
   montar L2 → L3 → L4 aninhados. Range de cada nó = `[início_próprio, início_do_próximo_irmão)`
   ( Sherlock: último filho vai até o fim do pai). Não usar mais min/max de chunks p/ ranges.
2. **Mapeamento nó→chunks por página** (já é assim): chunk entra no nó se suas páginas
   intersectam o range — com ranges corrigidos, o pai pp. 4–8 puxa os chunks dos filhos.
3. **Prompt do tree-search**: mostrar indentação (pai/filhos) + regra "selecionar pai inclui
   a subárvore". Cinto + suspensório: `retrieval_tree.py` expande automaticamente os
   descendentes do nó selecionado (respeitando `MAX_CHUNKS`).
4. **Invalidar seleções antigas**: o cache `tree_sel_*` usa hash só de (query, escopo) —
   incluir `TREE_VERSION` (bump v1→v2) ou apagar `cache/tree_sel_*.json` no rebuild,
   senão queries repetidas servem seleção da árvore velha.
5. **Rebuild sem custo**: `python -m src.tree_index` (TOC local, zero LLM).

## 3. Aceite

Status: **implementado** — `TREE_VERSION="2"` e `children` aninhados em `src/tree_index.py`; ver `STATE.md`.

- Mesma query ("seção What Is Generative Modeling, Cap 1") retorna chunks cobrindo pp. 4–8
  (não só ch01_s00/s01).
- `tree_livro.json`: nós L3 com `children` L4; spot-check Cap 1 contra a imagem do sumário.
- AppTest sem exceção nos dois modos; douradas re-rodadas (placar pode mudar — anotar antes/depois).

## 4. Fora de escopo

Resumos por seção (ideia anterior, continua válida e independente); trocar TOC pelo parser
Flash do PageIndex (só se o TOC embutido se mostrar insuficiente em outros caps).
