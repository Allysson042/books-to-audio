# Guia visual — contrato de identidade e componentes

Status: **aprovado em 2026-11-27** (fluxo e identidade validados pelo usuário; mobile **não** é
prioridade desta rodada). Este é o arquivo de verdade visual para futuras sessões.

| Arquivo | Papel |
|---|---|
| `03-design-system.md` | racional da proposta (por que cada token existe) |
| `mockup.html` | preview navegável (fonte da sensação visual) |
| **`06-guia-visual.md`** | **contrato**: valores, medidas, regras e checklist |
| `05-spec-u0-u1.md` | spec de implementação do U0+U1 |
| `src/ui/theme.py` / `src/ui/copy.py` | implementação (a partir do U0) |

Se o mock e este guia divergirem na **medida** (px, cor, espaçamento), **o guia vence** —
atualize o mock no mesmo commit. Se divergirem na **intenção**, abra discussão antes de mexer.

## 1. Conceito

**“Caderno de estudo”**: fundo de papel quente, superfícies brancas, verde-petróleo para ação e
violeta reservado ao áudio. Tipografia do sistema, sem webfont. Calmo, legível, sóbrio — não é
dashboard corporativo nem landing de startup.

Três palavras: **quente · legível · calmo**.

Nunca: gradiente, vidro/frosted, neon, sombra difusa, emoji decorativo, caixa alta no corpo de
texto, mais de um botão primário na mesma tela, animação de entrada.

## 2. Regras invioláveis

1. **Um** CTA primário por tela. Secundários são outline.
2. Cor nunca é o único sinal (sempre ícone ou palavra junto).
3. Jargão de engenharia só existe dentro de “Avançado”.
4. Custo e estimativa ficam **no botão**, nunca só no `help`.
5. Toda falha tem **1 ação de saída** visível.
6. Cache é dito em humano: `instantâneo` · `gerado agora · 22 s`.
7. Leitura em medida ≤ **68 ch** (máx. 76).
8. Zero CDN (fonte, ícone, JS). A demo pode rodar offline.
9. Texto de LLM/chunk nunca vira HTML — só `st.markdown`/`st.write`.
10. Mobile: **não quebrar** (sem overflow em 390 px), mas não otimizar nesta rodada.

## 3. Tokens (canônico)

Variáveis CSS em `src/ui/theme.py` (`:root` e `html[data-theme="dark"]`). A tabela abaixo é a
referência; não crie cor nova sem aprovação.

| Token | Light | Dark | Uso |
|---|---|---|---|
| `bg` | `#FBFAF7` | `#12110F` | fundo da página |
| `surface` | `#FFFFFF` | `#1A1917` | cards, header, player |
| `alt` | `#F2EFE9` | `#24221F` | chips, hover, trilho, código |
| `border` | `#E4DFD5` | `#33302B` | 1 px de card/divisória |
| `text` | `#1B1A17` | `#EDEAE3` | corpo |
| `muted` | `#5C574E` | `#A8A29A` | metadados, caption |
| `primary` | `#0E6F63` | `#4FD1BD` | CTA, links, foco, barra de relevância |
| `primary-weak` | `#E3F1EE` | `#14332F` | fundo de chip ativo/badge ok |
| `on-primary` | `#FFFFFF` | `#06231F` | texto sobre `primary` |
| `accent` | `#6D28D9` | `#A78BFA` | **só** áudio (play, onda, dock) |
| `on-accent` | `#FFFFFF` | `#1B1030` | texto sobre `accent` |
| `accent-weak` | `#EDE7FD` | `#241B3F` | fundo de destaque de áudio |
| `success` | `#157F3D` | `#4ADE80` | pronto, cache, etapa concluída |
| `warning` | `#A15C07` | `#FBBF24` | limite, fallback |
| `error` | `#B3261E` | `#F87171` | falha |
| `error-weak` | `#FBEAE8` | `#2A1615` | fundo de card de erro |

Contraste mínimo: corpo ≥ 7:1, metadados ≥ 4,5:1, CTA/ícones ≥ 4,5:1. Texto sobre `primary`
e `accent` **sempre** via `on-primary`/`on-accent` (no dark, o fundo é claro e o texto escuro).

## 4. Tipografia, espaço e layout

Stack do sistema (`-apple-system, Segoe UI, Roboto, …`), sem webfont. Números de tempo usam
`font-variant-numeric: tabular-nums`.

| Papel | Tamanho / linha | Peso | Uso |
|---|---|---|---|
| Display | 26 / 34 | 700 | título da página (`Generative Deep Learning`) |
| Subtítulo | 13 / 20 | 400 | frase abaixo do título, `muted` |
| Rótulo de seção | 13 / 18 | 700, caixa alta, `letter-spacing .06em` | `RESUMO TÉCNICO`, `ROTEIRO FALADO` |
| Corpo de leitura | **16 / 26** | 400 | Pass1/Pass2, medida 68 ch |
| Compacto | 14 / 20 | 400 | cards de fonte, ações |
| Metadados | 12 / 18 | 400 | proveniência, páginas, duração |
| Mono | 13 / 20 | 400 | `doc_id`, equação, tabela de debug |

Grade: página `1120 px`; leitura `720 px`; rail de ações `310 px`; gutter `28 px`.
Espaço: `4 · 8 · 12 · 16 · 24 · 32`. Raio: `8` botões/inputs · `12` cards · `999` chips.
Sombra: `0 1px 2px rgba(0,0,0,.06)`; no dark, **nenhuma** (separação por borda).

Wireframes e estados: `02-fluxos-e-wireframes.md`.

## 5. Anatomia dos componentes

Medidas extraídas do mock aprovado. `src/ui/theme.py` expõe as classes `gdl-*`; todo card usa
`st.container(border=True)` ou a classe `.gdl-card`.

| Componente | Medidas | Estados | Notas |
|---|---|---|---|
| **Header** | padding `24 28 12`; h1 26/700; sub 13 `muted`; selects pill 12 com borda `border` | — | escopo/persona no header; ☰ abre Sessão |
| **StageRail** | 12,5; gap 8; separador `border` | `done` primary/600 · `active` text/600 + ◐ · `locked` muted 55% · `error` error/600 | símbolos `● ◐ ○ ✕`; não é navegável |
| **QuestionCard** | qtext 19/650; meta 11,5 `muted`; ✎ botão 8×4 | — | pergunta sempre visível acima dos resultados |
| **Fontes** | summary 13/600; meta 12; card `alt`, raio 10, padding `10 12`; citação 12,5/700; tipo 10 caixa alta pill; barra `78×5`; snippet 11,5 itálico 2 linhas | colapsado / aberto | “detalhes da busca” no popover; debug nunca aberto por padrão |
| **ReadingCard** | rótulo 13/700 caixa alta; proveniência 11,5; corpo 16/26; ações 12 (⧉ ⤓ ↻) | vazio (ação + estimativa) · carregando · pronto · erro | um card por artefato; ações de conteúdo no cabeçalho |
| **ActionRail** | largura 310, `sticky top 12`; CTA 15/650, padding `13 16`, raio 10; ghost 13, padding `10 14`; meta 11,5 | habilitado / disabled (opacity .5 + motivo) | CTA com estimativa e custo em `small` |
| **PlayerDock** | **`position: fixed`** acima do input (`bottom: 5.5rem`, ajuste fino conforme a altura do chat input); barra full-width com conteúdo centralizado na largura do app; play 38 `accent`; progresso/tempo no iframe; download no player | tocando / pausado / fallback nativo | `st.iframe` + `static/`; fallback `st.audio` sem static serving |
| **Badge** | padding `3 9`, raio 999, 10,5/600 | ok `primary-weak`+success · mut `alt`+muted · warn `error-weak`+warning · err `error-weak`+error | nunca só cor: prefixo `✓ ! ✕` |
| **Chips** | 12,5; padding `7 13`; raio 999 | hover borda primary | vêm de `scripts/golden.json` |
| **Capítulos** | padding `12 14`; raio 12; título 13; resumo 11,5; páginas 10,5 | hover borda primary | telas de capítulo (U4/U5) |
| **Erro** | borda `error`; fundo `error-weak`; texto 13; ações 12 | — | fato + 1 ação + “detalhes” |
| **Sessão (drawer)** | 330; header 13 caixa alta; turno 12; rodapé 11 | atual (borda primary) | exportar `.md`, limpar |

## 6. Modo escuro (requisito aprovado)

**Não é inversão automática.** Os tokens do §3 são explícitos; nada de `filter: invert()`.

- Superfícies em três degraus: `bg #12110F` → `surface #1A1917` → `alt #24221F`.
- Sem sombra: borda `#33302B` faz a separação. Card não “flutua”.
- Primário vira **menta** (`#4FD1BD`) e o texto sobre ele é escuro (`on-primary #06231F`).
  Nunca use branco sobre o primário no dark.
- Áudio continua violeta-claro (`#A78BFA`) com texto escuro (`on-accent #1B1030`).
- `muted` `#A8A29A` (≥ 7:1 sobre `bg`) — metadados continuam legíveis.
- Nada de preto puro (`#000`) nem branco puro (`#FFF`) como fundo.
- Componentes nativos (`st.audio`, `st.dataframe`, `st.selectbox`) seguem o tema do Streamlit;
  verificar visualmente — se algum ignorar, corrigir por token, não por CSS agressivo.
- O comparativo “Antes” no mock pode permanecer claro: é a UI legada, não o produto.
- Implementação: `.streamlit/config.toml` com `[theme.light]` e `[theme.dark]` (Streamlit 1.64).
  Se o build não aceitar os blocos, usar `base="light"` e a troca pelo menu do app; registrar.
- **Armadilha do CSS custom:** o Streamlit reconstrói a árvore a cada rerun. O `<style>` precisa
  ser emitido **em todo run** — nunca guarde a injeção em `session_state`, ou o tema custom
  desaparece no primeiro clique.

Checklist do dark: 3 superfícies, bordas visíveis, CTA legível, `muted` legível, disabled
distinguível, badges ok/warn/err, dock e play, chips, tabela de debug, foco visível.

Preview: `mockup.html` → **10 · Escuro** (ou `◐ Tema`).

## 7. Voz e microcopy

Tom: direto, PT-BR, sentence case, sem exclamação, sem “por favor”, sem “ops”.
Termos EN do glossário (RAG, VAE, GAN, ELBO…) permanecem em EN.

Regras:

- Ação no botão começa com verbo: `Ouvir`, `Gerar resumo técnico`, `Baixar áudio`.
- Estimativa sempre calculada: `≈6 min` (chars/900), nunca “5-8min”.
- Cache: `instantâneo` (já gerado) vs `gerado agora · 22 s`.
- Erro: **fato + ação** (“A voz premium não respondeu.” + “Gerar com a voz grátis”).
- Jargão traduzido na tela principal:

| Não usar | Usar |
|---|---|
| `vectorless` / `vetorial` | `Sumário navegável` / `Busca semântica` |
| `cross-encoder` / `re-rank` | `Reordenar resultados` |
| `chunks` | `trechos` / `fontes` |
| `Pass1` / `Pass2` | `Resumo técnico` / `Roteiro falado` |
| `cache on/off` | `instantâneo` / `Ignorar cache` |
| `TTS` | `áudio` / `voz` |

Textos canônicos vivem em `src/ui/copy.py` (a partir do U0) — não inline no `app.py`.

## 8. Estados e feedback

| Estado | Aparência | Regra |
|---|---|---|
| Vazio | card com ação + estimativa (`Gere o resumo · ≈15 s`) | nunca “Nada gerado ainda.” |
| Carregando | `st.status` com etapas, cronômetro, botões disabled | “Parar” só entre etapas (Streamlit não cancela chamada síncrona) |
| Pronto | card + proveniência + ações de conteúdo | regenerar pede confirmação se for ignorar cache |
| Cache | `instantâneo` (success) | não dizer “do cache”/provider no corpo |
| Aviso | badge `!` + texto | limite de TTS mostrado **antes** do clique |
| Erro | card de erro + ação + detalhes | nunca `str(e)` cru |

## 9. Como alterar o padrão

1. Descreva a intenção e o estado que falta.
2. Use token existente; cor/medida nova exige aprovação (registre no changelog).
3. Respeite a escala de espaço e a medida de leitura.
4. Verifique contraste nos dois temas.
5. Atualize `mockup.html` **e** este guia no mesmo commit.
6. Rode o checklist (§10) e o AppTest.

## 10. Checklist de revisão visual

- [ ] Um CTA primário na tela.
- [ ] Hierarquia de 3 níveis (display / seção / corpo) + metadados.
- [ ] Leitura ≤ 68 ch; página ≤ 1120 px.
- [ ] Contraste AA em light **e** dark.
- [ ] `on-primary`/`on-accent` corretos no dark.
- [ ] Nenhum jargão fora de “Avançado”.
- [ ] Custo/estimativa no botão.
- [ ] Toda falha tem ação.
- [ ] Cache em linguagem humana.
- [ ] Foco visível e ordem de tabulação.
- [ ] Alvos ≥ 44 px (mobile não é prioridade, mas não quebrar).
- [ ] Sem CDN/fonte externa.
- [ ] Texto de LLM nunca injetado como HTML.
- [ ] Mock e guia atualizados juntos.
- [ ] `AppTest` sem exceção (player via `download_button`).

## 11. Changelog do padrão

- **2026-11-27** — identidade e fluxo aprovados. Corpo de leitura fixado em **16/26** (mock
  elevado de 15 para 16); rótulo de seção fixado em **13 caixa alta** (substitui o h2 20/28
  proposto em `03`); modo escuro explicitado como requisito; mobile declarado não-prioritário;
  tokens `on-primary`/`on-accent` adicionados; estimativas calculadas; cache em humano.
  Na implementação do U0: `font = "sans-serif"`/`codeFont = "monospace"` (hífen é o valor
  aceito pela 1.64); sem `[server] headless`; CSS re-emitido a cada rerun.
- **2026-11-27 (U5)** — player dock sticky (card não duplica player), modo apresentação em
  coluna única sem rail (dark **não** forçado por sessão), foco visível e `padding-bottom` de
  8rem para o dock/input. Pendente de conferência visual humana.
- **2026-11-27 (ajustes pós-U5)** — superfície dos cards explícita (`#FFFFFF` no claro,
  `#1A1917` no escuro) via keys `gdl_card_*` + `st.context.theme.type` (fallback `color-mix`);
  dock virou barra full-width colada no input; player **custom** em iframe (`st.iframe` com
  fallback `components.html`) servido por `/app/static/`, com fallback nativo `st.audio`.
  `enableStaticServing` exige reiniciar o app.
- **2026-11-27 (dock fixo)** — o dock passou de `position: sticky` (ficava no fim do conteúdo)
  para **`position: fixed; bottom: 5.5rem`**, sempre acima da barra de pergunta; conteúdo
  centralizado em `max(1rem, (100vw - 1120px)/2)`; conteúdo com `padding-bottom: 10rem`.