# Fluxos, informação e wireframes

Complementa `01-auditoria.md`. Aqui está o "como deve fluir e parecer", sem código.

## 1. Modelo mental

Hoje a tela responde "quais são meus parâmetros e onde está meu botão?".
O alvo responde **"em que ponto da história eu estou?"**:

```
PERGUNTA ──► FONTES ──► RESUMO ──► ROTEIRO ──► ÁUDIO
   você       prova       técnico     falado     ouve
```

Cada estágio tem 4 estados: **bloqueado** (depende do anterior), **vazio** (pronto para gerar),
**carregando** (com tempo estimado), **pronto** (com proveniência e ações). Um único CTA
principal percorre a trilha; o passo a passo vira opção.

## 2. Arquitetura da informação

Três níveis, do macro ao micro — e um nível transversal de sessão:

| Nível | Conteúdo | Onde vive na UI |
|---|---|---|
| **Livro** | 14 capítulos, 1 linha cada, página inicial | Tela de capítulos (quando não há pergunta) + seletor no header |
| **Capítulo** | resumo macro, intervalo de páginas, "ouvir capítulo" | Header chip + card de abertura do capítulo |
| **Pergunta** | fontes, resumo, roteiro, áudio | Coluna de leitura |
| **Sessão** (transversal) | perguntas desta sessão, reabrir, exportar | Painel lateral "Sessão" (U4) |

A sidebar deixa de ser o lugar de tudo. Ela passa a ter três blocos, nesta ordem:
**Sessão** (histórico, limpar, exportar) · **Ajustes** (escopo, persona) · **Avançado** (colapsado:
estratégia, re-rank, cache, voz premium, modo apresentação).

## 3. Wireframe — desktop (≥ 1100 px)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Generative Deep Learning            [Cap 4 · p.96 ▾] [Técnico ▾] [⚙ Sessão]  │
│ Pergunte, leia o resumo ou ouça o capítulo                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│ ①Pergunta ─ ②Fontes ─ ③Resumo ─ ④Roteiro ─ ⑤Áudio        (estado da trilha)  │
├───────────────────────────────────────────────┬──────────────────────────────┤
│ ┌ PERGUNTA ─────────────────────────────────┐ │ ┌ AÇÕES (sticky) ───────────┐ │
│ │ "O que é ELBO em VAEs?"            [✎]    │ │ │ ▶  Ouvir                  │ │
│ │ Cap 4 · p.96–112 · 10 trechos             │ │ │    resumo+roteiro+áudio   │ │
│ └───────────────────────────────────────────┘ │ │    ≈ 2 min · grátis       │ │
│                                               │ │                           │ │
│ ▸ FONTES (10) — ver trechos e páginas         │ │ ○  Só o resumo técnico    │ │
│                                               │ │ ○  Só o roteiro           │ │
│ ┌ RESUMO TÉCNICO ───────────────────────────┐ │ │ ───────────────────────── │ │
│ │ gerado agora · qwen3.8        [copiar ⤓]  │ │ │ Cap 4 · Técnico           │ │
│ │                                           │ │ │ Busca: sumário navegável  │ │
│ │ texto com citações [Cap 4, p.101],        │ │ │ [Ajustar]                 │ │
│ │ equações em bloco, medida ≤ 76ch          │ │ │                           │ │
│ └───────────────────────────────────────────┘ │ │ ▸ Avançado                │ │
│                                               │ │   motor de busca          │ │
│ ┌ ROTEIRO FALADO ───────────────────────────┐ │ │   reordenar resultados    │ │
│ │ gerado agora · voz Pedro · ≈6 min [⤓]     │ │ │   ignorar cache           │ │
│ │ texto limpo para fala, sem colchetes      │ │ │   voz premium ~US$0,06    │ │
│ └───────────────────────────────────────────┘ │ └───────────────────────────┘ │
├───────────────────────────────────────────────┴──────────────────────────────┤
│ ▶ ━━━━━━━●─────────── 02:14 / 06:11   voz Pedro · Edge    ⤓ MP3   ✕          │
└──────────────────────────────────────────────────────────────────────────────┘
```

Regras do wireframe:

- **Uma coluna de leitura com medida limitada** (máx. ~760 px / 76 ch) e uma coluna de ações.
  Em telas < 1100 px, a coluna de ações vira barra inferior.
- **Fontes ficam entre a pergunta e o resumo**, colapsadas, com um resumo de 1 linha
  ("10 trechos · Cap 4 · p.96–112"). O debug RAG sai daqui e vai para um popover.
- **Nada de abas.** Resumo e roteiro são seções empilhadas: a leitura é sequencial e o
  usuário vê o que já existe sem trocar de contexto.
- **Botões de gerar desaparecem quando o conteúdo existe**; no lugar aparecem ações de
  conteúdo (copiar, baixar, regenerar). Assim não existem dois "Gerar" competindo.
- **Player dock** só aparece quando há áudio e fica fixo no rodapé (fora da coluna de leitura).

## 4. Wireframe — mobile (< 700 px)

```
┌──────────────────────────────┐
│ GDL           [Cap 4 ▾] [⚙]  │
│ ①─②─③─④─⑤  (dots + rótulo)   │
├──────────────────────────────┤
│ "O que é ELBO em VAEs?"  [✎] │
│ 10 trechos · p.96–112        │
│ ▸ Fontes                     │
│                              │
│ RESUMO TÉCNICO               │
│ [texto, 16px, 1.6]           │
│                              │
│ ROTEIRO FALADO               │
│ [texto]                      │
├──────────────────────────────┤
│ ▶ Ouvir            ≈2 min    │  ← barra de ação fixa
├──────────────────────────────┤
│ ▶ ━━━━●──── 02:14  ⤓         │  ← player dock
└──────────────────────────────┘
```

- Stepper vira 5 pontos com o rótulo do estágio atual (não cabe a trilha inteira).
- Ações avançadas vivem no popover `⚙`, nunca em sidebar aberta.
- Alvos de toque ≥ 44 px; nada de `help=` como única explicação.

## 5. Tela inicial (sem pergunta) — hoje: um `st.info`

```
┌──────────────────────────────────────────────────────────────┐
│ Generative Deep Learning                                     │
│ Pergunte, leia o resumo ou ouça qualquer capítulo            │
│                                                              │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ O que você quer entender?              [ Perguntar → ]   │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ Comece por aqui                                              │
│ [O que é ELBO em VAEs?] [GANs vs Diffusion] [Resuma o Cap 4] │  ← chips clicáveis
│                                                              │
│ Ou navegue pelos capítulos                                   │
│ ┌ Cap 4 · Generative Models ──────────── p.96–112  [Abrir] ┐ │
│ │ 1 linha do resumo macro…                                 │ │
│ └──────────────────────────────────────────────────────────┘ │
│ ┌ Cap 5 · Autoregressive Models ──────── p.113–140 [Abrir] ┐ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

- Os 3 chips vêm de `scripts/golden.json` (já existem; hoje só o eval usa).
- Cards de capítulo usam `mapa_livro.json` (`title`, `summary_2lines`, páginas).
- **Restrição técnica**: `st.chat_input` é fixado pelo Streamlit no rodapé do corpo e
  quebra se for movido para dentro de tabs/columns/expander (`app.py:79-81`). Ele **fica
  no rodapé**; o wireframe mostra o bloco "O que você quer entender?" como âncora visual
  (título + chips), não como caixa de texto no topo. O "✎ editar pergunta" do QuestionCard
  usa um `st.form` com `st.text_input` inline (não tenta reposicionar o `chat_input`).

## 6. Estados (matriz por estágio)

| Estágio | Bloqueado | Vazio | Carregando | Pronto | Erro |
|---|---|---|---|---|---|
| Pergunta | — | chips + input | "buscando…" | card com ✎ | — |
| Fontes | se não há query | — | "lendo o sumário…" | 1 linha + expander | "Não achei neste capítulo → buscar no livro todo" |
| Resumo | sem fontes | "Gere o resumo (≈15 s)" | "escrevendo… 10–40 s" | texto + copiar/baixar/regenerar | "Falhou por quota → tentar de novo / usar cache" |
| Roteiro | sem resumo (gera junto) | "Gere o roteiro (≈20 s)" | "adaptando para fala…" | texto + duração estimada | idem, com ação |
| Áudio | sem roteiro | "≈6 min · Edge grátis" | "sintetizando 1/3 fatias…" | player + MP3 | "Premium falhou → gerar com Edge" |

Comportamentos transversais:

- **Cache é dito em humano**: "instantâneo (já gerado nesta máquina)" vs "gerado agora · 18 s".
  Nada de `via cache · do cache`.
- **Erro sempre tem 1 ação primária** (tentar de novo, cair para Edge, buscar no livro todo).
- **Progresso persistente**: `st.status` por estágio (não spinner solto) com o passo atual
  ("consultando 6 seções", "fatia 2/3") e cronômetro.
- **Limite de TTS**: o aviso aparece no card do roteiro **antes** do clique, com botão
  "encurtar roteiro" (gera versão de 12k chars) — ver decisão D7 em `04-roadmap.md`.
- **Regenerar** é um ícone no card com confirmação "ignorar cache e gerar de novo?".

## 7. Microcopy (antes → depois)

| Hoje (`app.py:linha`) | Proposto |
|---|---|
| `Books to Audio — Generative Deep Learning` (20) | `Generative Deep Learning` + subtítulo `Pergunte, leia o resumo ou ouça o capítulo` |
| `Escopo` (44) | `Onde buscar` (no popover de ajustes) |
| `Persona` (45) | `Explicar para` · `Técnico` / `Iniciante` |
| `Modo offline (cache demo)` (46) | remover até B1 existir (ou `Kit offline` com estado real) |
| `Usar cache (texto+áudio)` (47) | em Avançado: `Ignorar cache (forçar nova geração)` — default OFF |
| `Re-rank (cross-encoder)` (49) | em Avançado: `Reordenar resultados` |
| `Estratégia: vectorless/vetorial` (51) | `Como buscar` · `Sumário navegável (padrão)` / `Busca semântica` |
| `Voz premium (OpenRouter TTS)` (53) | `Voz premium · ≈US$0,06 por áudio` (desabilitado sem chave) |
| `Mapa do livro (nível 1)` (57) | sai da sidebar; vira telas de capítulo |
| `Digite uma pergunta no campo abaixo…` (99) | `O que você quer entender?` + chips |
| `Chunks recuperados (5) — ver fontes` (139) | `Fontes (10 trechos)` |
| `Ver texto do chunk:` (147) | `Ver trecho` (cards clicáveis, não selectbox) |
| `Debug RAG (tabela…)` (150) | popover `Detalhes da busca` → tabela |
| `Resumo macro Cap N (nível 2)` (160) | card de abertura do capítulo, sem checkbox |
| caption `Query: … offline: False …` (162) | remover; no máximo `10 trechos · sumário navegável` |
| `Pass1 · resumo técnico` (167) | `Resumo técnico` |
| `Pass2 · roteiro TTS` (167) | `Roteiro falado` |
| `Nada gerado ainda.` (174/192) | `Gere o resumo (≈15 s)` / `Gere o roteiro (≈20 s)` |
| `Gerar resumo` (175) | `Gerar resumo técnico` (ou `Regerar`) |
| `Gerar roteiro` (193) | `Gerar roteiro falado` (ou `Regerar`) |
| `Gerar áudio (5-8min)` (227) | `▶ Ouvir (≈6 min)` — duração **calculada** de `len(clean_for_speech)` (~900 ch/min), nunca hardcoded |
| `Roteiro pronto (N chars · voz …)` (220) | `≈6 min · voz Pedro` (duração calculada) |
| `Roteiro com N chars limpos excede…` (224) | `Roteiro longo para uma faixa só (N de 15.000). Encurtar para ≈7.000 (8 min)?` + botão |
| `Premium indisponível (…) — caindo p/ Edge-TTS grátis.` (236) | `A voz premium não respondeu. Gerando com a voz grátis (Edge).` |
| `Baixar MP3` (245) | `Baixar áudio` (com MIME/format corretos) |
| `Nada encontrado neste escopo. Tente 'Livro todo'.` (132) | `Nada neste capítulo.` + botão `Buscar no livro todo` + `Ver capítulos` |

## 8. Decisões de fluxo (e o que foi descartado)

| Decisão | Escolha | Por quê |
|---|---|---|
| Chat com bolhas (`st.chat_message`)? | **Não** | Resumos de ~2.500 tokens em bolha são ilegíveis; sem streaming, a bolha "vazia" por 40 s é pior que um estado de card |
| Histórico? | **Sim, como lista de perguntas** na sessão (U4) | Reabrir uma pergunta é o que a plateia pede ("volta na do ELBO") |
| Abas ou empilhado? | **Empilhado** | Uma história se lê de cima para baixo; abas escondem metade do fluxo (U3) |
| Um CTA ou três? | **1 primário + 2 secundários** | Demo: um clique para ouvir. Engenheiro: passos separados no mesmo rail |
| CTA "Ouvir" encadeia o quê? | resumo → roteiro → áudio, com timeline visível e botão "parar" | Menos cliques; o custo aparece antes do clique |
| Sidebar aberta? | **Colapsada por padrão**; ajustes em popover | Plateia não precisa ver 4 toggles (U4) |
| Escopo/persona por pergunta ou globais? | Globais, com chip visível no header e no card da pergunta | Trocar persona deve ser 1 clique e mostrar o que mudou |
| "Modo apresentação"? | Toggle no header: esconde avançado, aumenta escala, fixa dark | Sala de aula/projetor (P5) |

## 9. Mapa componente ↔ onde implementar (sem tocar no pipeline)

| Componente | Arquivo sugerido | Depende de |
|---|---|---|
| Tema + CSS + escala | `src/ui/theme.py` (novo) + `.streamlit/config.toml` (novo) | — |
| Header (título, chips, popover) | `src/ui/layout.py` (novo) + `app.py` | `mapa_livro.json` |
| StageRail (5 estágios) | `src/ui/stages.py` (novo) | estado em `session_state` |
| SourceCard + lista de fontes | `src/ui/sources.py` (novo) | `top5`/`cands` atuais |
| Action rail + PlayerDock | `src/ui/actions.py` (novo) | `get_pass1/get_pass2/synthesize*` |
| Ajustes + Avançado | `src/ui/settings.py` (novo) | `mapa_livro.json`, env |
| Empty state + chips de exemplo | `src/ui/empty.py` (novo) | `scripts/golden.json` |
| Histórico de sessão (U4) | `src/ui/history.py` (novo) | `session_state` |

Nada em `src/retrieval*.py`, `src/generate.py`, `src/tts_provider.py` precisa mudar para
U0–U3. U4 precisa de um helper de histórico, não de mudança nos providers.
