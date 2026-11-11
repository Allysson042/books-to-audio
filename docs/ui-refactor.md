# Refatoração da interface (Streamlit) — plano funcional

Data: 2026-09-23. Escopo: **só funcionalidade/layout** (cores, fontes, textos ficam p/ depois).
Sidebar atual está OK e não muda (escopo, persona, offline + novo toggle de cache).

## 1. Problemas de hoje (o que muda e por quê)

| # | Hoje | Proposto |
|---|------|----------|
| 1 | Top-5 chunks ocupa a tela toda após cada busca | Tudo de retrieval dentro de **1 expander colapsado** ("Chunks recuperados (N)") |
| 2 | Botão único gera Pass1+Pass2 juntos | **Botão por seção**: "Gerar resumo" no Pass1, "Gerar roteiro" no Pass2 |
| 3 | Seções Pass1/Pass2 só aparecem após gerar | **Duas colunas sempre visíveis** com empty-state ("nada gerado ainda") |
| 4 | Sem controle de cache (sempre lê `cache/`) | **Toggle "Usar cache"** na sidebar p/ testes com/sem |
| 5 | Botão de áudio global no fim da página | Áudio mora **dentro da coluna Pass2** (fluxo: roteiro → áudio) |

## 2. Layout proposto (wireframe texto)

```
[sidebar: Escopo | Persona | Modo offline | Usar cache (ON)]   <- inalterada + 1 toggle

# Título (inalterado)

[ input da pergunta ........................................ ]

[Expander colapsado: "Chunks recuperados (5) — ver fontes" ]
   -> dentro: cards compactos c/ citação+seção+tipo+score (expander por chunk p/ texto)
   -> dentro: sub-expander "Debug RAG" (tabela RRF/re-rank, como hoje)
   -> dentro (se escopo=cap): sub-expander "Resumo macro" (nível 2, como hoje)

[col Pass1 · resumo técnico        | col Pass2 · roteiro TTS        ]
 [badge: cache/fresco/provider]     [badge: cache/fresco/provider]
 [empty-state OU markdown]          [empty-state OU markdown]
 [btn "Gerar resumo"]               [btn "Gerar roteiro"]
                                    [--- áudio ---]
                                    [btn "Gerar áudio" (desabilitado sem roteiro)]
                                    [player + download]
```

Regras:
- Colunas sempre renderizadas; antes de gerar, placeholder `st.info("...")` discreto.
- "Gerar roteiro" sem Pass1 existente → gera Pass1 silenciosamente antes (spinner único), não erro.
- Regenerar (botão de novo com cache OFF, ou botão "↻" dedicado — decidir na implementação; default: botão re-gera respeitando o toggle).
- Badges de proveniência por seção: `via openrouter · do cache` (já existe o dado em `res`).

## 3. Mudanças de backend necessárias (pequenas, sem quebrar S1–S4)

1. **`src/generate.py :: answer(..., use_cache=True)`**
   - `True` (default): comportamento atual (lê cache; escreve sempre).
   - `False`: **pula a leitura** do cache mas **mantém a escrita** (cache segue aquecido; teste "sem cache" = chamada LLM fresca garantida).
   - Refatorar em `get_pass1(...)` + `get_pass2(pass1_text, ...)` internas p/ botões independentes (sem duplicar lógica de hash).
2. **`src/tts_provider.py :: synthesize(..., use_cache=True)`** — mesmo contrato do item 1.
3. **`app.py`**: `session_state` passa a guardar `pass1` e `pass2` separados (+ provider/cached por seção); expander de chunks com `expanded=False`; colunas via `st.columns(2)`.
4. Nada muda em: ingestão, Chroma/BM25, prompts, personas, formato do cache em disco.

## 4. Critérios de aceite (funcional)

Status: **implementado** (2026-09-23) — evidências em `STATE.md` (toggles em `app.py`, `get_pass1/get_pass2`).

- [x] Busca mostra só o expander colapsado; expandir revela os mesmos dados de hoje (top-5 + debug + macro).
- [x] Pass1 e Pass2 geram de forma independente; roteiro sem resumo gera o resumo antes, sem erro.
- [x] Toggle cache OFF → 2 cliques geram 2 chamadas LLM (badge "recém-gerado" nas 2); ON → 2ª é "do cache".
- [x] Áudio desabilitado sem roteiro; com roteiro, player + download como hoje.
- [x] AppTest headless sem exceção nos 3 fluxos (busca / pass1 / pass2+áudio).
- [x] `TASKS.md` atualizado (novo item S5b ou seção "UI").

## 5. Fora de escopo (próxima rodada estética)

Cores, fontes, CSS custom, textos/labels em PT, responsivo/mobile, landing inicial, logo. Nada disso entra aqui.
