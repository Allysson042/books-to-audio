# Design system mínimo (Streamlit 1.64)

> **A partir de 2026-11-27 o contrato visual é `06-guia-visual.md`.** Este arquivo permanece
> como racional da proposta. Onde houver divergência de medida (rótulo de seção 13 px caixa
> alta, corpo de leitura 16/26, `on-primary`/`on-accent`), **vale o guia**.

Objetivo: dar consistência visual sem sair do Streamlit e sem dependência externa.
Duas camadas:

1. **Tema nativo** — `.streamlit/config.toml` (novo arquivo). Muda cor/fonte/tema em todo
   componente, inclusive `st.audio`, `st.dataframe` e sidebar.
2. **`src/ui/theme.py`** — um único bloco de CSS + helpers (`page_header`, `card`,
   `stage_rail`, `chip`, `player_dock`). Nada de `<style>` espalhado pelo `app.py`.

> Regra: o CSS só cobre o que o tema não alcança (largura de leitura, sticky, stepper).
> Seletor do Streamlit não é API pública — todo seletor usado aqui precisa de comentário
> com a versão testada (1.64) e de um teste rápido após upgrade.

## 1. Tema (`.streamlit/config.toml`)

```toml
# Sem `base`: segue a preferência claro/escuro do SO/navegador.
# Valores de `font`/`codeFont` aceitos na 1.64 usam hífen: "sans-serif", "monospace".
[theme]
primaryColor = "#0E6F63"
backgroundColor = "#FBFAF7"
secondaryBackgroundColor = "#F2EFE9"
textColor = "#1B1A17"
font = "sans-serif"
codeFont = "monospace"

# 1.64 aceita blocos por modo; se o parser reclamar, remover e usar só o bloco acima.
[theme.light]
primaryColor = "#0E6F63"
backgroundColor = "#FBFAF7"
secondaryBackgroundColor = "#F2EFE9"
textColor = "#1B1A17"

[theme.dark]
primaryColor = "#4FD1BD"
backgroundColor = "#12110F"
secondaryBackgroundColor = "#1A1917"
textColor = "#EDEAE3"

[browser]
gatherUsageStats = false
```

Escolha de paleta: **papel quente + verde-petróleo**. Justificativa: leitura longa (papel),
tom de "livro", accent frio para ação; nada de azul corporativo. O accent de áudio é
violeta, usado **só** no player (diferencia "texto" de "som").

## 2. Tokens

### Cor

| Token | Light | Dark | Uso |
|---|---|---|---|
| `bg` | `#FBFAF7` | `#12110F` | fundo da página |
| `surface` | `#FFFFFF` | `#1A1917` | cards |
| `surface-alt` | `#F2EFE9` | `#24221F` | header, hover, chips |
| `border` | `#E4DFD5` | `#33302B` | 1px de card/divisória |
| `text` | `#1B1A17` | `#EDEAE3` | corpo |
| `muted` | `#5C574E` | `#A8A29A` | caption, metadados |
| `primary` | `#0E6F63` | `#4FD1BD` | CTA único, links, foco |
| `primary-weak` | `#E3F1EE` | `#14332F` | fundo de chip ativo |
| `accent-audio` | `#6D28D9` | `#A78BFA` | player, botão de áudio |
| `success` | `#157F3D` | `#4ADE80` | "pronto", "do cache" |
| `warning` | `#A15C07` | `#FBBF24` | limite, fallback |
| `error` | `#B3261E` | `#F87171` | falha |
| `focus` | `#0E6F63` 40% | `#4FD1BD` 50% | anel de foco |

Contraste alvo: corpo ≥ 7:1, metadados ≥ 4,5:1, CTA ≥ 4,5:1. Nunca usar cor como único sinal
(sempre ícone/rótulo junto).

### Tipografia

| Papel | Tamanho / linha | Peso | Onde |
|---|---|---|---|
| Display | 30 / 38 | 600 | título do header |
| Seção (h2) | 20 / 28 | 600 | "Resumo técnico", "Roteiro falado" |
| Corpo | 16 / 26 | 400 | leitura (medida ≤ 76 ch) |
| UI | 14 / 20 | 500 | labels, botões, chips |
| Metadados | 13 / 18 | 400 | proveniência, páginas, duração |
| Código | 13 / 20 | 400 | `doc_id`, tabela de debug |

Sem webfont: `font = "sans serif"` usa a stack do sistema. Motivo: kit offline (B1/S5) e
zero requisição externa. `codeFont` mono para `doc_id`.

### Espaço, raio e sombra

- Escala: `4 · 8 · 12 · 16 · 24 · 32 · 48`.
- Raio: `8` botões/inputs · `12` cards · `999` chips.
- Sombra: só uma — `0 1px 2px rgba(0,0,0,.06)`; nada de blur grande.
- Largura: página `1120px`; leitura `720px` (≈ 76 ch); rail de ações `320px`; gutter `32px`.
- Densidade: 24 px entre seções, 12 px entre título e corpo, 8 px entre metadados.

## 3. Catálogo de componentes

### 3.1 PageHeader

```
Generative Deep Learning                    [Cap 4 · p.96 ▾] [Técnico ▾] [⚙]
Pergunte, leia o resumo ou ouça o capítulo
```

`st.title` + `st.caption` + duas `st.selectbox` com `label_visibility="collapsed"` e
`st.popover("⚙")`. Escopo/persona deixam a sidebar (U2). Em mobile, vira título + `⚙`
(escopo e persona dentro do popover).

### 3.2 StageRail

```
● Pergunta ─ ● Fontes ─ ◐ Resumo ─ ○ Roteiro ─ ○ Áudio
```

Não é navegação: é **status**. Estados: `done` (● primary), `active` (◐, com pulso discreto
ou cronômetro), `locked` (○ muted), `error` (● error). Implementação: `st.markdown` com
HTML/classes próprias (não usar `st.pills`, que sugere seleção). Em mobile: 5 dots +
`3 de 5 · Resumo`.

### 3.3 QuestionCard

```
┌────────────────────────────────────────────┐
│ "O que é ELBO em VAEs?"              [✎]   │
│ Cap 4 · p.96–112 · 10 trechos · instantâneo │
└────────────────────────────────────────────┘
```

`st.container(border=True)`. O ✎ devolve o foco ao input de pergunta (U4).

### 3.4 SourceList / SourceCard

```
▸ Fontes (10 trechos) · Cap 4 · p.96–112
  ┌ 1 ────────────────────────────────────────────────┐
  │ [Cap 4, p.101] · Variational Autoencoders         │
  │ seção 4.2 · texto · relevância ███████░░░ 0,87    │
  │ "…the ELBO is a lower bound on the log-likelihood…"│
  │                                       [ver página] │
  └───────────────────────────────────────────────────┘
```

- Colapsado, o cabeçalho já entrega: quantidade, capítulo e faixa de páginas.
- Cada fonte é um card com citação, seção, tipo, barra de relevância **normalizada** e
  snippet de 2 linhas (o `in_scope`/`rerank` bruto fica no popover de detalhes).
- "ver página" abre o trecho completo no card (sem `selectbox`).
- Debug RAG (tabela RRF) vai em `st.popover("Detalhes da busca")`.

### 3.5 ReadingCard (resumo/roteiro)

```
┌ RESUMO TÉCNICO ──────────────── gerado agora · 22 s ─┐
│ texto…                                               │
│                                         [⧉] [⤓] [↻] │
└──────────────────────────────────────────────────────┘
```

- Cabeçalho: rótulo + proveniência humana ("gerado agora · 22 s" / "instantâneo · já gerado").
- Rodapé: copiar, baixar `.md`, regenerar (com confirmação se for ignorar cache).
- Vazio: `Gere o resumo técnico · ≈15 s` com botão secundário.
- Nunca dois CTAs primários na mesma tela: no rail só um é `type="primary"`.

### 3.6 PrimaryCTA (rail)

```
┌ AÇÕES ────────────────────────┐
│ ▶  Ouvir                      │  ← primary
│    resumo + roteiro + áudio   │
│    ≈2 min · grátis            │
│                               │
│ ○  Só o resumo técnico        │  ← secondary
│ ○  Só o roteiro               │  ← secondary
│ ───────────────────────────── │
│ Cap 4 · Técnico               │
│ Busca: sumário navegável      │
│ [Ajustar]                     │
└───────────────────────────────┘
```

- Custo/estimativa sempre embaixo do rótulo (nunca só no `help`).
- Premium: `≈US$0,06 · voz Luana` e botão desabilitado sem `OPENROUTER_API_KEY`.
- Durante execução: vira lista de etapas (`st.status`) com "parar".

### 3.7 PlayerDock

```
▶ ━━━━━━━━●──────────── 02:14 / 06:11   Pedro · Edge   ⤓ MP3  ✕
```

`st.container(border=True)` + CSS `position: sticky; bottom: 0`. Usa `st.audio` nativo
(sem player custom). Mostra título curto, engine e MIME correto. ✕ fecha o dock e mantém
o arquivo no cache. Não prometer velocidade/seek avançado — o nativo não tem.

### 3.8 EmptyState + chips

Chips são `st.button` em `st.container(horizontal=True)` (verificar suporte em 1.64; senão
`st.columns`). Fonte: `scripts/golden.json`. Sem emoji; texto curto.

### 3.9 ErrorAction

```
⚠ A voz premium não respondeu.
  [Gerar com a voz grátis (Edge)]  [Ver detalhes]
```

Toda falha: **o que aconteceu** (1 linha, sem stack) + **1 ação** + detalhes no popover.
Nunca `str(e)` cru no corpo.

### 3.10 AdvancedPanel (popover)

`st.popover("⚙ Avançado")` no rail (ou no header, no mobile): motor de busca, reordenar,
ignorar cache, voz premium, modo apresentação. Cada item com uma frase de consequência.

## 4. CSS mínimo (`src/ui/theme.py`)

```python
# src/ui/theme.py — um único ponto de estilo. Testado em Streamlit 1.64.
CSS = """
<style>
:root {
  --gdl-bg: #FBFAF7; --gdl-surface: #FFFFFF; --gdl-border: #E4DFD5;
  --gdl-text: #1B1A17; --gdl-muted: #5C574E; --gdl-primary: #0E6F63;
  --gdl-accent: #6D28D9;
}
@media (prefers-color-scheme: dark) {
  :root {
    --gdl-bg: #12110F; --gdl-surface: #1A1917; --gdl-border: #33302B;
    --gdl-text: #EDEAE3; --gdl-muted: #A8A29A; --gdl-primary: #4FD1BD;
    --gdl-accent: #A78BFA;
  }
}
/* Largura de página e respiro */
[data-testid="stAppViewContainer"] .block-container {
  max-width: 1120px; padding-top: 2.5rem; padding-bottom: 6rem;
}
/* Medida de leitura: aplicado a um container com key="read" */
.gdl-read { max-width: 76ch; font-size: 1rem; line-height: 1.65; }
.gdl-read h2 { margin: 2rem 0 .5rem; font-size: 1.25rem; }
.gdl-read p { margin: 0 0 1rem; }
/* Sidebar mais estreita e sem rolagem horizontal */
[data-testid="stSidebar"] { min-width: 280px; max-width: 280px; }
/* Stepper */
.gdl-rail { display:flex; gap:.5rem; align-items:center; font-size:.875rem; }
.gdl-rail .done { color: var(--gdl-primary); }
.gdl-rail .locked { color: var(--gdl-muted); }
/* Player fixo */
.gdl-dock { position: sticky; bottom: 0; z-index: 10;
            background: var(--gdl-surface); border-top:1px solid var(--gdl-border); }
/* Foco visível (acessibilidade) */
:where(button, a, input, [role="tab"]):focus-visible {
  outline: 2px solid var(--gdl-primary); outline-offset: 2px;
}
@media (max-width: 700px) {
  [data-testid="stAppViewContainer"] .block-container { padding: 1rem .75rem 8rem; }
  .gdl-read { max-width: 100%; }
}
</style>
"""

def inject(page) -> None:
    page.markdown(CSS, unsafe_allow_html=True)
```

Regras de segurança/robustez:

- HTML custom **só para cromo** (rail, chips, cabeçalhos de card). Texto de LLM/chunk usa
  `st.markdown`/`st.write` — nunca concatenar chunk em HTML (escaping).
- Variáveis CSS (`--gdl-*`) definidas em `:root` via `theme.py`, para light/dark seguirem
  o tema sem duplicar regra.
- Sem `!important`; sem reset global; sem esconder elementos nativos (`#MainMenu`,
  toolbar) além do que o tema já faz.
- Selector por `data-testid` é o mais estável; `key`/classe `.st-key-read` é ainda melhor
  quando o Streamlit expõe a key (1.39+). Preferir `.st-key-<key>` a `nth-child`.

## 5. Ícones e mídia

- Ícones: `:material/play_arrow:` etc. em labels (1.64 renderiza). **Verificar se a fonte
  é embarcada**; se depender de CDN, cair para texto (`▶`, `⤓`) para não quebrar offline.
- Sem emoji como status (varia por SO e quebra leitura de tela).
- Sem imagens decorativas no MVP; `page_icon` pode ser um emoji único ou `.png` local em
  `assets/` (novo). Preferir `.png` local.
- Áudio tem transcrição por definição (o roteiro na tela) — requisito de acessibilidade já
  atendido desde que o roteiro fique visível ao lado do player.

## 6. Acessibilidade (checklist de aceite)

- [ ] Contraste AA em light **e** dark (checar com DevTools/axe).
- [ ] Nenhum controle só com placeholder; `label_visibility` só quando houver rótulo visível
      equivalente (chips do header têm label textual).
- [ ] Ordem de tabulação = ordem visual; foco visível em todos os interativos.
- [ ] Alvos de toque ≥ 44×44 px (chips e botões do dock).
- [ ] Estado nunca só por cor (rail usa ●/◐/○ + texto; status usa ícone + palavra).
- [ ] Zoom 200% sem scroll horizontal forçado (medida de leitura ajuda).
- [ ] `prefers-reduced-motion` respeitado (sem pulso no estágio ativo).
- [ ] Captions não são o único lugar de informação crítica (limite de TTS, custo).
- [ ] Nome de arquivo baixado previsível: `gdl-cap4-elbo-resumo.md`, `gdl-cap4-elbo.mp3`.

## 7. Estados visuais padronizados

| Estado | Cor | Rótulo | Ícone |
|---|---|---|---|
| pronto | success | `pronto` | ✓ |
| gerado agora | muted | `gerado agora · 22 s` | — |
| instantâneo | success | `instantâneo` | ↺ |
| em execução | primary | `escrevendo… 12 s` | ◐ |
| aviso | warning | `roteiro longo` | ! |
| falha | error | `não respondeu` | ✕ |
| bloqueado | muted | `depende do resumo` | ○ |

## 8. O que não fazer

- Não trocar Streamlit por outro framework nem usar componente React custom.
- Não usar gradiente, vidro/frosted, sombra forte, animação de entrada.
- Não colocar dois botões primários na mesma dobra.
- Não usar `st.metric` para scores de retrieval (número cru não significa nada ao ouvinte).
- Não exibir `provider`/modelo como identidade principal — no máximo metadado discreto.
- Não hardcodar texto em imagem; todo texto é selecionável.
- Não depender de CDN (fonte, ícone, JS) — a demo pode rodar sem internet.
