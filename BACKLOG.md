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
| B2 | 2026-11-11 | Campo de pergunta dispara geração com texto **parcial** ao trocar de aba do navegador: o `text_input` comita no blur → rerun → `if q:` dispara retrieval/LLM sem botão | `app.py:78-79` (widget, `live=False`) + `app.py:88` (`if q:`) + `app.py:83-86` (wipe de pass1/pass2/mp3) | Gasta quota com pergunta incompleta, apaga resultados na tela | P1 |
| B3 | 2026-11-11 | Input de pergunta é `st.text_input` de 1 linha, sem botão de enviar e sem quebra de linha; trocar por input estilo chat (Enter envia, Shift+Enter quebra linha) | `app.py:78` | UX da demo; é o fix natural de B2 — resolver junto | P3 |
| B4 | 2026-11-11 | Retrieval roda em **todo** rerun (não memoizado por query): clicar "Gerar resumo"/"Gerar roteiro" reexecuta a busca e, no vectorless, pode chamar LLM de novo | `app.py:88-99` (busca) + `app.py:153`/`app.py:179` (`st.rerun`) | Latência e custo repetidos a cada clique | P2 |

## Resolvidos
| ID | Fechado | Sintoma | Fix (commit) |
|---|---|---|---|
