# Roadmap de implementação (U0 → U5)

Ordem pensada para entregar valor visual a cada sessão de 2 h e nunca deixar o app quebrado
entre fases. Nada aqui foi implementado. Cada fase é uma tarefa de `executor` com arquivos e
aceite explícitos. **U0+U1 têm spec executável em `05-spec-u0-u1.md`.**

## Visão geral

| Fase | Entrega | Esforço | Risco | Arquivos principais |
|---|---|---|---|---|
| U0 | Tema, tipografia, título, empty state com chips, correções pontuais de áudio | 2–3 h | Baixo | `.streamlit/config.toml`, `src/ui/theme.py`, `app.py` |
| U1 | Jornada linear: stepper, seções empilhadas, 1 CTA, progresso persistente, fim dos reruns | 5–7 h | Médio | `app.py`, `src/ui/stages.py`, `src/ui/actions.py` |
| U2 | Sidebar em camadas + honestidade de custo/estado | 3–4 h | Baixo | `app.py`, `src/ui/settings.py` |
| U3 | Fontes com score/snippet/página + debug em popover | 4 h | Baixo | `src/ui/sources.py`, `app.py` |
| U4 | Histórico de sessão, reabrir, exportar | 6–8 h | Médio | `src/ui/history.py`, `app.py` |
| U5 | Player dock, modo apresentação, responsivo, QA dark/light | 3 h | Médio | `src/ui/theme.py`, `app.py` |

**Corte mínimo para o seminário (10–13 h):** U0 + U1 + o dock do U5. U3 melhora a "prova do
RAG" na banca; U2 e U4 podem ficar para depois.

---

## U0 — Fundamentos visuais

**Objetivo:** o app deixa de parecer script e passa a ter identidade, sem mexer no fluxo.

**Status (2026-11-27): implementado**, com revisão final fechando dois bugs (CSS sumindo no
rerun e `[server] headless` indevido). Pendências conscientes: pin de versão, medida de 68 ch
(fica para o U1) e conferência visual humana do dark.

Tarefas:

- [x] `.streamlit/config.toml` com `[theme]`, `[theme.light]` e `[theme.dark]`; sem `base`
      (segue o SO), sem `[server]`; `font = "sans-serif"`/`codeFont = "monospace"` (valores
      aceitos pela 1.64).
- [x] `src/ui/__init__.py` e `src/ui/theme.py` com `TOKENS`, `CSS`, `inject(st)` e
      `audio_mime()` (tokens de `06` §3, incluindo `on-primary`/`on-accent`).
- [x] `st.set_page_config`: `page_title` humano e `page_icon` 🎧 (placeholder). **Não** foi
      usado `initial_sidebar_state="collapsed"` — esconderia escopo/persona antes do U2.
- [x] Título de 2 linhas: `Generative Deep Learning` + subtítulo de uma frase.
- [x] Empty state com 3 chips (`copy.EMPTY_CHIPS`, textos aprovados no mock; `golden.json`
      segue como fonte de avaliação, não da UI).
- [x] Caption de contexto humano (`N trechos · sumário navegável · Técnico`).
- [ ] Aplicar `.gdl-read` (68 ch) na coluna de leitura — **adiado para o U1**; no U0 só a
      página é limitada a 1120 px.
- [x] Correções pontuais: `mime`/`format` do áudio (U21), badge do Pass1 encadeado (U19),
      aviso quando `mapa_livro.json` falta (U24) e duração calculada no botão de áudio (U26).
- [ ] Pin `streamlit>=1.64,<2` em `requirements.txt` (afeta o ambiente de todos; combinar).
- [x] Python do venv verificado (**3.14**); a f-string de `app.py:143` (U22) roda.

Aceite verificado:

- [x] AppTest renderiza sem exceção e **CSS permanece nos reruns** (`1 1`).
- [x] Chip define a pergunta e dispara a busca (executor; consumiu 1 chamada LLM no teste).
- [x] Download/mime corretos; badge honesto; aviso de mapa.
- [ ] Conferência visual claro/escuro (sem navegador nesta sessão) — **pendente humana**.
- [ ] Fluxos completos busca / Pass1 / Pass2+áudio não foram reexecutados no U0.

---

## U1 — Jornada linear (o coração da mudança)

**Objetivo:** 2 ações até o áudio; o usuário sempre sabe em que estágio está.

**Status (2026-11-27): implementado.** Validação estrutural: sem abas, AppTest offline nos dois
estados (vazio/gerado), CSS presente nos reruns, smoke 200. **Não exercitado** o fluxo real
`Ouvir` com LLM/TTS (custo) — pendente de teste manual com cache quente.

Tarefas:

- [x] Remover `st.tabs` e empilhar Pergunta → Fontes → Resumo → Roteiro → Áudio em cards
      (`st.container(border=True)`) com placeholders, sem abas.
- [x] `src/ui/stages.py`: `derive()` + `rail()` com os 5 estágios (● ◐ ○ ✕), renderizado antes
      e depois da busca.
- [x] `src/ui/actions.py`: **um** `type="primary"` (`▶ Ouvir`). Os secundários só aparecem
      quando o artefato ainda não existe (depois, a regeneração mora no `↻` do card).
- [x] Fluxo "Ouvir": resumo → roteiro → áudio encadeados, com `st.status` por etapa e tempo.
- [x] Sem `st.rerun()` de geração: intenção via `on_click` (fila) + placeholders preenchidos no
      mesmo run. **Desvio:** a fila usa o rerun natural do widget, não um rerun explícito.
- [x] Botões desabilitados sem fontes / sem confirmação premium; o status cobre o "em execução".
- [x] Áudio amarrado ao roteiro+voz (`mp3_sig`); trocar voz/roteiro mostra "áudio de um roteiro
      anterior" + `Regerar áudio`.
- [x] Erro de busca com `Tentar de novo` (invalida `ret_ctx`), detalhes em expander.
- [x] Estados vazios com estimativa (`≈15 s`, `≈20 s`, `≈N min` calculado).
- [x] `st.chat_input` mantido no corpo; "↺ Nova pergunta" no card (em vez do form inline).
- [x] Extra: `↻ Regerar` (ignora cache) em resumo/roteiro, invalidando os downstream; limpeza de
      `top5/cands/ret_err` ao trocar de contexto.

Aceite verificado:

- [x] Caminho mínimo: 1 pergunta + "▶ Ouvir" (a execução real não foi disparada em teste).
- [x] Nenhum `st.rerun()` disparado por geração.
- [x] Áudio obsoleto não é exibido; nome de voz premium correto (`Luana`, não `2.1`).
- [x] Toda falha tem 1 ação no próprio card.
- [ ] Teste manual do fluxo completo (busca → resumo → roteiro → áudio) e do player.
- [ ] Conferência visual humana do sticky/dark e do mobile (não prioritário).

Notas de honestidade técnica:

- **Streamlit não cancela chamada síncrona em andamento.** A UI não promete cancelamento
  instantâneo nem barra de progresso de um Pass1 que não faz streaming.
- `st.chat_input` dentro de `columns`/tabs/expander quebra (comentário existente); não mover.
- O rail é renderizado antes da execução; o texto de estimativa dele pode ficar um run atrás
  depois de gerar o roteiro (os cards já estão atualizados). Polir no U5.

---

## U2 — Sidebar em duas camadas

**Objetivo:** sumir com jargão da tela principal sem perder nenhum controle.

**Status (2026-11-27): implementado.** Validação: AppTest sem uma única sidebar, selects no
header, premium desabilitado/forçado sem key, CSS nos reruns, smoke 200. A sidebar foi
**removida** (não ficou com Sessão/Ajustes); o mapa do livro foi para dentro de "⚙ Ajustes"
até o U4 criar a Sessão.

Tarefas:

- [x] Sem `st.sidebar.*`: **Ajustes** (avançado) em `st.popover("⚙ Ajustes")`; **Sessão**
      fica para o U4.
- [x] Escopo e persona viram selects compactos no header (`Onde buscar` / `Explicar para`),
      ao lado do título. `SCOPE_TO_CHAPTER` elimina o parsing do label (U25).
- [x] Microcopy traduzido: `Como buscar` (Sumário navegável / Busca semântica),
      `Reordenar resultados`, `Ignorar cache`, `Voz premium · ≈US$0,06 por áudio`.
- [x] Cache invertido: `Ignorar cache (forçar nova geração)`, default OFF; `use_cache = not`.
- [x] Premium: custo no rótulo, `disabled` + motivo visível sem `OPENROUTER_API_KEY`;
      troca de voz invalida o áudio pela `mp3_sig`.
- [x] `use_rerank` só entra no `ctx` com `strategy == "vetorial"`.
- [x] `Modo offline` removido (B1 continua no backlog).

Aceite verificado:

- [x] Antes de gerar: pergunta, escopo e persona visíveis; avançado atrás de um clique.
- [x] Nenhum `vectorless`/`cross-encoder`/`Modo offline`/`Usar cache` na tela.
- [x] Nenhum controle sem efeito real.
- [x] Alternar re-rank no vectorless não dispara busca (por construção do `ctx`).
- [ ] Conferência visual humana do header/popover (sem navegador na sessão).

---

## U3 — Confiança nas fontes

**Status (2026-11-27): implementado.** AppTest nos dois modos (vetorial/vectorless) e caminho
de erro, CSS 1/1, smoke 200; sem `selectbox` de chunk. Pendente só conferência visual humana.

Tarefas:

- [x] `src/ui/sources.py`: bloco `Fontes (N) · Cap X · p.a–b` (colapsado), card por fonte com
      citação, seção, tipo humanizado, barra de relevância normalizada (0–100) e snippet de
      ~160 chars.
- [x] Normalização por estratégia: vetorial `rerank` → `rrf`; vectorless `tree_fit` →
      `in_scope` → `tree_lex`. Min–max; todos iguais → 100. A barra mostra `NN%` +
      "relevância relativa nesta pergunta"; o bruto fica no popover de detalhes.
- [x] "Ver trecho" em **popover** por fonte (não expander: aninhar expander é proibido no
      Streamlit). Código vai em `st.code`, resto em `st.write`.
- [x] `Detalhes da busca` em popover com a tabela RRF/re-rank (strings, `width="stretch"`) e o
      "Raciocínio da navegação" do vectorless.
- [x] Abertura do capítulo **antes** das fontes, em popover, com o macro **inteiro** (sem o
      corte de 3.000 chars).
- [x] Citação em negrito, formato único em toda a UI.

Aceite verificado:

- [x] Nenhum `selectbox` de chunk; toda fonte mostra citação/seção/tipo/relevância/snippet.
- [x] Debug em popover, fechado por padrão (2 cliques).
- [x] Nenhum truncamento silencioso (macro completa; snippet é preview com `…` e "ver trecho").
- [x] Mesmo componente nas duas estratégias (campos de score diferentes).
- [x] Snippet não interpreta markdown do chunk (`` ` ``, `*`, `_`, `<` preservados).
- [ ] Conferência visual humana dos cards/popovers.

---

## U4 — Sessão e histórico

**Status (2026-11-27): implementado.** AppTest sem LLM: restaurar turno, "Nova pergunta" e
"Limpar" OK; turnos não duplicam; `len(turns)` estável; CSS 1/1; smoke 200. Export validado por
unitário. Pendente só conferência visual (popover estreito/dark).

Tarefas:

- [x] `session_state["turns"]`: turnos com `{id, ts, key, query, scope, persona, strategy,
      rerank, chapter, ctx, top5, pass1, pass2, mp3, mp3_sig, mp3_engine, premium}`;
      **máximo 8**, mais recente primeiro, upsert por `(query, scope, persona, strategy, rerank)`.
- [x] Painel **☰ Sessão** no header (não há mais sidebar): pergunta truncada + `Cap 4 · 14:02 ·
      resumo + roteiro + áudio`; `●` no turno atual. Clicar restaura **sem chamar LLM/TTS**.
- [x] `Nova pergunta`, `Limpar sessão` (checkbox de confirmação) e `Exportar sessão (.md)`.
- [x] Turnos anteriores nunca são apagados na troca de `ctx`; o `☰` é preenchido no fim do run,
      já com o áudio recém-gerado.
- [x] Memória: `cands` (top-20) não é guardado; reabrir usa `top5` no debug. Só textos/metadados.

Aceite verificado:

- [x] Segunda pergunta mantém a primeira acessível.
- [x] Reabrir não dispara chamada externa (AppTest offline; nenhum `[llm-call]`/`[tts-call]`).
- [x] Export gera `.md` com pergunta, fontes, resumo e roteiro (seções ausentes omitidas).
- [x] `Limpar sessão` volta ao estado inicial sem rerun manual.
- [ ] Conferência visual humana do popover no header estreito e no dark.

---

## U5 — Polimento de apresentação

**Status (2026-11-27): implementado.** AppTest: modo normal (rail + `▶ Ouvir`), apresentação
(sem rail, chips + sair), dock com MP3 temporário, CSS 1/2, smoke 200.
**Ajustes pós-U5 (2026-11-27):** superfície dos cards por tema (`#FFFFFF`/`#1A1917`) e **player
custom** servido por `/app/static` (fallback nativo), validados com AppTest + `curl` 200.
Requer **reiniciar** o app para o static serving. Pendente: conferência visual humana
(dock/player, cards no dark, 390 px) e capturas.

Tarefas:

- [x] Player dock fixo com **player custom** (iframe + `/app/static`, play/seek/tempo/download)
      e **fallback nativo** `st.audio`; o card de áudio não duplica o player. Exige
      `server.enableStaticServing=true` e reinício do app; sem isso, cai no nativo.
- [x] `Modo apresentação` em `⚙ Ajustes`: coluna única sem rail, leitura maior, 3 chips das
      douradas e botão de sair. **Dark não é forçado por código** (o Streamlit não permite por
      sessão) — fica como escolha do SO/menu.
- [ ] QA **sem quebrar** em 390 px (mobile não é prioridade; exige só ausência de overflow
      horizontal e alvos ≥ 44 px no caminho principal) — **não verificado sem navegador**.
- [x] Foco visível (`:focus-visible` com `--primary-color`) e respiro de 8rem para o dock/input.
- [ ] QA dark/light com o checklist de `06-guia-visual.md` §10 — **pendente humano**.
- [ ] QA keyboard-only (Tab/Enter/Space) e leitor de tela no fluxo principal — **pendente**.
- [x] `padding-bottom` e dark via vars; sem CDN.
- [x] Atualizar `docs/STATE.md`, este roadmap e `07-resultado.md` com evidências.

Aceite verificado:

- [x] Dock só com áudio válido do roteiro/voz atuais; download único.
- [x] Apresentação sem rail, chips de exemplo e saída clara; `▶ Ouvir` não aparece.
- [x] Nenhuma exceção nos dois modos.
- [ ] Sem scroll horizontal em 390 px e fluxo só com teclado — **pendente humano**.
- [ ] Screenshots antes/depois — **pendente**.

Desvio consciente: com **voz premium** ligada, a confirmação de custo mora no rail; no modo
apresentação não há como confirmar sem sair do modo (o áudio fica bloqueado). Documentar na demo.

---

## Correções pontuais embutidas nas fases

| ID | Correção | Fase |
|---|---|---|
| U6 | Áudio órfão: `mp3` não é limpo ao regerar roteiro/trocar voz | U1 |
| U7 | `ret_err` grudado sem retry; `ret_ctx` gravado em falha | U1 |
| U19 | Badge "recém-gerado" para Pass1 encadeado que veio do cache | U0 |
| U21 | `mime="audio/mpeg"` para `.wav` do Piper | U0 |
| U22 | f-string PEP 701 exige Python ≥ 3.12 | U0 (antes de editar) |
| U24 | Falha silenciosa quando `mapa_livro.json` falta | U0 |
| U26 | Duração "5-8min" hardcoded vs ~16 min reais | U1 |
| U23 | Sidebar sem `st.form` dispara rerun por widget | U2 (avaliar `st.form` nos ajustes) |
| U18 | Macro truncada em 3000 chars | U3 |
| U20 | `help` inacessível, alvos pequenos | U5 |

## Riscos e mitigação

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| CSS depende de `data-testid` e quebra em upgrade do Streamlit | Média | Visual | Pin `>=1.64,<2`; preferir `.st-key-*`; um só lugar de CSS |
| `position: sticky` não funciona dentro de containers do Streamlit | Média | Player | Testar no início do U5; fallback: dock no topo do conteúdo |
| `st.container(horizontal=True)`/`st.space` ausentes ou diferentes | Baixa | Layout | `st.columns` como fallback; validar assinatura antes |
| AppTest não cobre player/áudio | Certa | Validação | Checar `download_button`; teste manual com arquivo real |
| Remover tabs quebra estado/rotas de teste | Baixa | Regressão | Chaves de `session_state` mantidas (`pass1/pass2/mp3`) |
| CTA único dispara 2 LLM + TTS sem aviso | Média | Custo/demo | Estimativa e custo no botão; confirmar 1ª vez com premium |
| Histórico cresce e estoura memória | Baixa | Performance | Limite de 8 turnos; guardar só textos |
| HF Hub pendura 12 min na 1ª busca (B5) | Alta | Demo | Não é escopo de UX; documentar aviso "carregando modelo" e tratar em B1/S5 |
| Sem internet, ícones/fontes externas falham | Média | Visual | Zero CDN; ícones com fallback textual |

## Validação (além do AppTest)

1. **Roteiro de 3 tarefas** com 2 colegas (5 min cada):
   (a) ouvir a explicação de ELBO; (b) comparar resumo técnico e roteiro;
   (c) voltar a uma pergunta anterior. Medir tempo e nº de hesitações.
2. **Checklist de demo**: projetor 1366×768, dark, zoom 125%, sem mouse (teclado).
3. **Comparação com o baseline** de `01-auditoria.md` §8 (ações, cliques, jargão, erros
   sem ação, medida de linha).
4. **Regressão funcional**: `python scripts/eval_retrieval.py` antes/depois de U1 para
   garantir que a camada visual não tocou em retrieval.

## Depois deste plano (não agora)

- Registrar em `TASKS.md` a seção "UX" com as fases aprovadas (só após decisão do escopo).
- Itens pequenos que sobrarem viram `B<n>` no `BACKLOG.md`.
- `ui-refactor.md` continua sendo histórico; este conjunto é a rodada **estética e de
  interação** que ele deixou explicitamente de fora.
