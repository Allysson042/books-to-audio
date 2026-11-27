# Resultado da rodada UX/UI (U0–U5)

Data: 2026-11-27 · Status: **U0–U5 implementados** no código; falta apenas a conferência visual
humana e o teste manual do fluxo real com LLM/TTS.

Este arquivo é o **resumo antes/depois** para a banca e o roteiro de demo. O contrato visual
continua em `06-guia-visual.md`; o preview em `mockup.html`; o plano em `04-roadmap.md`.

## 1. Antes × depois

| Dimensão | Antes (auditoria, 26/11) | Depois |
|---|---|---|
| Estrutura | 2 abas (Pass1/Pass2) escondendo metade do fluxo | Pergunta → Fontes → Resumo → Roteiro → Áudio empilhados |
| Ação principal | 2 botões primários competindo + botão de áudio no fim | **1 CTA**: `▶ Ouvir` (encadeia resumo→roteiro→áudio) |
| Controles permanentes | 7 na sidebar (1 morto) | 3 no header; avançado em `⚙ Ajustes` |
| Jargão visível | `vectorless`, `cross-encoder`, `Modo offline`, `cache on/off` | 0 na tela principal |
| Estado | spinners efêmeros + `st.rerun` cego | `st.status` por etapa; resultado no mesmo run |
| Fontes | lista crua + `selectbox` de chunk | cards com citação, seção, tipo, relevância e snippet |
| Debug | 3 checkboxes + tabela inline | `Detalhes da busca` em popover |
| Macro | truncada em 3.000 chars | completa, em "Abertura do capítulo" |
| Áudio | órfão possível; player no card | `mp3_sig` + dock com **player custom** (fallback nativo) |
| Cards | sem fundo próprio; no dark só o contorno | superfície `#FFFFFF`/`#1A1917` por tema |
| Sessão | pergunta nova apagava tudo | ☰ com 8 turnos reabríveis sem LLM + export `.md` |
| Identidade | sem tema, título longo, linha de 120+ ch | tema claro/escuro, 1120 px, leitura 68 ch |
| Acessibilidade | só placeholder, ajuda em tooltip | foco visível, rótulos, estado nunca só por cor |

Métricas do baseline (`01-auditoria.md` §8) e alvo atingido:

| Métrica | Antes | Depois |
|---|---|---|
| Ações até o 1º áudio | 4 | **2** (pergunta + Ouvir) |
| Reruns percebidos | 3 | 0 (widgets + placeholders) |
| Controles antes de gerar | 7 + input | 2 selects + input |
| Erros sem ação | 4 de 4 | 0 |
| Medida de linha | ~120–160 ch | ≤ 68 ch |

## 2. Camada de UI (onde mexer)

```
app.py                 orquestra estado, layout e chamadas existentes
src/ui/theme.py        tokens, CSS (dock, foco, apresentação), MIME de áudio
src/ui/copy.py         TODO o microcopy + helpers de duração/voz/proveniência
src/ui/stages.py       trilha dos 5 estágios
src/ui/actions.py      rail (1 CTA + secundários condicionais)
src/ui/sources.py      cards de fonte, relevância normalizada, trechos, debug
src/ui/history.py      turnos, restore sem LLM, export .md, limpar
src/ui/player.py       player custom (iframe + /app/static) com fallback nativo
```

Nenhuma mudança em `src/retrieval*.py`, `src/generate.py`, `src/tts_provider.py`,
`src/prompts.py`, `personas/` ou chaves de cache.

## 3. O que foi validado (execução real)

- `py_compile` em `app.py` + `src/ui/*.py`.
- AppTest headless (sem LLM/TTS): busca vazia/gerada, fontes vetorial/vectorless, erro de busca,
  restauração de turno, nova pergunta, limpar sessão, apresentação, dock com MP3 temporário.
- CSS emitido em **todos** os reruns (`1 1`) — o bug do U0 não voltou.
- Smoke HTTP 200 em portas de teste; sem `[llm-call]`/`[tts-call]` nos testes.
- Normalização de relevância e `summary` de páginas (unitários).
- **Player custom**: iframe renderizado, MP3 publicado em `static/` e serviço real
  `/app/static/<arquivo>` → **200**; fallback nativo (`st.audio` + download) validado com
  `enableStaticServing` desligado; `stage`/prune não removem o áudio atual.
- Superfície dos cards presente no CSS (`--gdl-surface` + keys `gdl_card_*`).

## 4. Desvios conscientes

1. **Dark não é forçado** no modo apresentação: o Streamlit não permite trocar tema por sessão
   sem gambiarra. Fica como escolha do SO/menu; o tema escuro está completo em `config.toml`.
2. **Confirmação de custo premium** vive no rail; no modo apresentação não há como confirmar
   sem sair do modo (áudio fica bloqueado). Premium segue OFF por padrão.
3. **Mapa do livro** mora dentro de `⚙ Ajustes`, não em uma tela de capítulos dedicada (o mock
   previa uma navegação própria). O seletor de capítulo no header cobre o caso de uso.
4. **Reabrir turno** usa `top5` no debug (o top-20 não é guardado, por memória).
5. **Mobile** não é prioridade desta rodada: sem overflow no caminho principal, mas sem QA fino.
6. **Rótulos de seção** são `st.markdown("**RESUMO TÉCNICO**")`, não o label 13 px caixa alta do
   guia — diferença de 1 nível tipográfico a acertar se houver tempo.
7. **Player custom** exige `server.enableStaticServing=true` **e reinício** do app. Enquanto não
   reiniciar, o dock cai no player nativo automaticamente. A URL `/app/static/...` é absoluta
   (ok no uso local; atrás de subpath exigiria ajuste).
8. **Tema do iframe** usa `st.context.theme.type`; pode ficar um rerun atrasado ao trocar o tema
   no menu (limitação documentada do Streamlit). Sem `type`, cai em `prefers-color-scheme`.
9. **Dock fixo** usa `bottom: 5.5rem` para ficar acima do chat input de 1 linha. Se o input
   expandir (pergunta longa), pode encostar; o offset é ajustável em uma linha no CSS.

## 5. Pendências para o seminário (S5)

- [ ] **Teste manual do fluxo real** com LLM/TTS (voz gratuita): pergunta → Ouvir → player.
- [ ] **Reiniciar o app** para ativar `enableStaticServing` e ver o player custom (play/seek/tema);
      sem reinício, o dock mostra o nativo.
- [ ] **Conferência visual**: dock/player em 1366/1440, cards no dark, popovers, dark, 390 px.
- [ ] Capturas antes/depois para os slides.
- [ ] Pin `streamlit>=1.64,<2` em `requirements.txt` (afeta o ambiente de todos).
- [ ] Sincronizar `TASKS.md`, `ARCHITECTURE.md` e `README.md` (falam em sidebar/abas; edição
      bloqueada pela ferramenta do arquiteto).
- [ ] `scripts/demo_seed.py` (3 Q&A + 2 MP3) e kit offline (B1) — itens de S5, não desta rodada.
- [ ] MOS de áudio / avaliação com 2 pessoas (checklist de `01` §8).

## 6. Roteiro de demo (5–7 min)

1. Abrir com o livro todo e mostrar o header (capítulo, persona, ☰, ⚙).
2. Clicar num chip dourado ("O que é ELBO em VAEs?").
3. Expandir **Fontes** (10 trechos): citação, seção, tipo, relevância, snippet.
4. Abrir **Abertura do capítulo** (macro completa) e **Detalhes da busca** (RRF).
5. Ler 2 parágrafos do **Resumo técnico** (citações `[Cap X, p. Y]`).
6. **▶ Ouvir** (voz grátis) e mostrar o **dock** + download.
7. Trocar a persona: o áudio vira "roteiro anterior" (prova da `mp3_sig`).
8. Abrir **☰ Sessão**, reabrir a primeira pergunta (instantâneo, sem LLM) e **Exportar .md**.
9. Ligar **Modo apresentação** (leitura maior, sem rail, chips) e voltar.
10. Alternar claro/escuro e fechar.

## 7. Como manter o padrão

- Toda mudança visual segue `06-guia-visual.md` §2/§3/§10.
- Texto novo vai para `src/ui/copy.py`, nunca inline.
- Cor/medida nova exige atualizar o guia **e** `mockup.html` no mesmo commit.
- CSS fica só em `theme.py`; reemitir a cada run (nunca guardar em `session_state`).
- Depois de mexer, rodar AppTest (sem clicar em gerar) + smoke + `git diff` dos arquivos de UI.
