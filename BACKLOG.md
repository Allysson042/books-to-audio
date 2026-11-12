# BACKLOG.md — Ajustes pequenos e bugs conhecidos

> Caixa de entrada do que incomoda mas não vale interromper o sprint.
> **Não** é o plano de marcos (isso é `TASKS.md`) nem design travado (`ARCHITECTURE.md`).
> Registrar aqui não significa "vai ser feito agora" — significa "não esqueci".

## Como registrar
- Uma linha por item, ID incremental `B<n>`. **Nunca reutilize** um ID.
- `Onde` = `arquivo:linha` ou símbolo. É o que o `executor` usa para achar o ponto sem investigar.
- `Pri` = `P1` trava demo/uso · `P2` incomoda mas tem contorno · `P3` cosmético.
- Resolveu? Move a linha para **Resolvidos** com data + commit. Não apague: vira histórico.
- Se o item crescer e virar refactor de verdade, ele sai daqui e vira etapa em `TASKS.md`.

## Aberto
| ID | Data | Sintoma | Onde | Impacto | Pri |
|---|---|---|---|---|---|
| B1 | 2026-11-11 | Toggle "Modo offline" é cosmético: só aparece num caption, não altera nenhum caminho de leitura de cache | `app.py:45` (toggle) + `app.py:136` (caption) | Parece ter fallback offline na demo e não tem | P2 |

## Resolvidos
| ID | Fechado | Sintoma | Fix (commit) |
|---|---|---|---|
| B2 | 2026-11-11 | Campo de pergunta disparava geração com texto parcial ao trocar de aba do navegador | `9b99de7` — `st.chat_input` + query efetiva só do submit (`session_state["query"]`) |
| B3 | 2026-11-11 | Input era `st.text_input` de 1 linha, sem botão de enviar | `9b99de7` — input estilo chat (`st.chat_input`, Enter envia) |
| B4 | 2026-11-11 | Retrieval rodava em todo rerun, não memoizado por query | `9b99de7` — memoização `ret_ctx`/`top5`/`cands` (10,8s → 0,0s no rerun) |
