# Vectorless RAG (PageIndex) — relatório de viabilidade

Data: 2026-09-23. Origem: pedido do Allysson + repo https://github.com/VectifyAI/PageIndex (35k+ stars, MIT).
Clone de referência lido em `/tmp/opencode/PageIndex` (não commitado).

## 1. O conceito em 30s

Vectorless RAG troca **similaridade de embeddings** por **raciocínio do LLM sobre a estrutura do documento**:

1. **Index**: gera uma árvore hierárquica (capítulo → seção → páginas) com título + resumo por nó, salva em JSON puro. Sem vetores, sem chunking arbitrário, sem vector DB.
2. **Retrieve**: diante da query, o LLM lê a árvore (só títulos/resumos/páginas, sem o texto) e decide *quais nós* ler — como um humano que consulta o sumário. Só então o texto dos nós escolhidos vai ao prompt de resposta.

Tese central: *similarity ≠ relevance* — busca vetorial retorna o que é parecido, não o que é relevante; relevância exige raciocínio.

## 2. Como o PageIndex implementa (verificado no código)

- `pageindex/flash/` — **Flash indexing** (default): extrai a estrutura do **layout do PDF** (parser próprio via `pypdfium2`, char-level, detecção de títulos) **sem LLM**; o LLM entra só p/ resumos dos nós + passada de otimização da árvore. Segundos a poucos minutos p/ 1000 págs.
- `pageindex/local_api.py` (`LocalAPI`) + `local_chat.py` — modo local: indexa, recupera e conversa na própria máquina com **sua própria key** (via `litellm`, logo aceita qualquer provider OpenAI-compatible — Gemini/OpenRouter servem, sem precisar de OpenAI).
- API relevante: `submit_document()` → `get_tree()` / `submit_query()` / `chat()`; índice em `local_store.py` (diretório local, JSON).
- Custos declarados: index ~US$0,001/pág (modelo pago básico; 456 págs ≈ US$0,50, **uma vez**); query lê só os nós alcançados (2,1×–16,6× mais barato que jogar o PDF inteiro no contexto). Benchmark próprio: 98,7% no FinanceBench vs 50% do RAG vetorial (benchmark de lookup factual; ler com ceticismo saudável).
- Deps: `litellm`, `openai`, `pypdfium2`, `mcp`, `openai-agents` — pesadas p/ nosso venv CPU enxuto, mas nada com torch.

## 3. Fit com este projeto (por que é quase sob medida)

- Nosso caso é o sweet spot deles: **livro-texto longo, único, bem estruturado** ("academic textbooks" está na lista de casos ideais).
- **Já temos 80% da árvore de graça**: `ingest.py` extrai TOC (capítulos L2, seções L3/L4) + `resumo_macro` por capítulo = nós + resumos. O Flash deles é melhor (layout real vs TOC embutido), mas nosso atalho custa R$0 e zero deps.
- Citações `[Cap X, p. Y]` continuam triviais: nós têm page ranges; é só mapear nó → `book_page_*`.
- Restrição R$0 mantida: indexação via TOC (sem LLM) + resumos/macro já pagos na quota free; tree-search por query usa o chain atual (Gemini/OpenRouter free).

## 4. Proposta: estratégia dual com toggle (sem substituir nada)

```
sidebar: [Estratégia: vetorial | vectorless]
                │                    │
   RAGStore+RRF+re-rank     TOC-tree + LLM tree-search
   (src/retrieval.py)        (NOVO src/retrieval_tree.py)
                └──────┬───────┘
              mesmos top-N → Pass1 → Pass2 → TTS
```

- **Novo módulo** `src/retrieval_tree.py`: carrega `cache/tree_livro.json` (gerado 1x a partir do TOC + macros), monta prompt de tree-search ("dada a query, devolva `node_ids` relevantes em JSON"), mapeia nós → textos (chunks existentes cujas páginas caem no range, ou texto cru das páginas), retorna **mesmo formato** `{doc_id, text, metadata, citation, scores}` p/ reuso total do downstream.
- **Comparação justa**: mesmas perguntas douradas nas duas estratégias; debug mostra lado a lado (ranks RRF vs caminho na árvore + `thinking` do LLM); métricas = hit-rate top-N, citação correta, custo/latência por query.
- **Evolução opcional** (só se o experimento provar valor): trocar nosso TOC-tree pelo `pip install pageindex` (Flash real) mantendo a mesma interface.

## 5. Riscos / custos honestos

- **Cada query vectorless = +1 chamada LLM** (tree-search) antes do Pass1 — latência maior e gasto de quota (free router tem limite diário). O vetorial atual é local, grátis e instantâneo no retrieval.
- Tree-search precisa de modelo razoável p/ JSON confiável; `openrouter/free` aleatório pode variar — fixar `OPENROUTER_MODEL` vira pré-requisito.
- `pip install pageindex` (se adotado depois) puxa `litellm` + `pypdfium2` — ok, mas engorda o venv; nada nativo pesado.
- Benchmarks deles são marketing-adjacentes (dataset próprio, lookup factual); nossa comparação local nas douradas vale mais.

## 6. Recomendação

**Viável e de baixo custo — implementado (ver `STATE.md` para evidências), antes do S5.** Passos executados: (1) perguntas douradas + hit-rate do vetorial (régua); (2) `tree_livro.json` a partir do TOC+macros (quase de graça); (3) `retrieval_tree.py` + toggle na sidebar. O passo (4) — comparação formal — segue pendente. Não mexe em ingestão, Chroma, prompts 2-pass nem TTS.

Pendências opcionais: comparação formal vetorial × vectorless nas 5 douradas; troca pelo Flash real do PageIndex só se a árvore do TOC se mostrar insuficiente em outros capítulos.
