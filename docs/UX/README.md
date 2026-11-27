# UX / UI — plano de melhoria visual e de interação

Data: 2026-11-26 · Status: **proposta, nada implementado**
Alvo: `app.py` (257 linhas) + tema/estilo Streamlit (hoje inexistentes).
Fora do alvo: retrieval, geração, TTS, cache, prompts, ingestão.

Este plano não rediscute design travado (`../../ARCHITECTURE.md`). Ele parte do
código atual e propõe uma camada visual/interativa por cima, **sem mudar contratos**
(`get_pass1`/`get_pass2`/`synthesize*`/`TreeStore`).

## Diagnóstico em 3 linhas

1. A tela **parece um chat, mas é um formulário**: cada pergunta nova apaga o
   resumo, o roteiro e o áudio (`app.py:93-96`) — não há histórico, comparação
   nem pergunta de acompanhamento.
2. A sidebar mistura **decisão do ouvinte** (escopo, persona) com **botões de
   engenheiro** (re-rank, estratégia, cache) em 8 controles, e um deles
   (`Modo offline`) é cosmético — mente para a plateia (B1 no `BACKLOG.md`).
3. O caminho até o áudio são **4 ações, 3 reruns e 2 trocas de aba**, com o
   resultado em largura total de tela e sem indicador de progresso persistente.

## Princípios (ordem de precedência)

| # | Princípio | Consequência prática |
|---|---|---|
| P1 | **Uma jornada, não um painel** | A tela conta Pergunta → Fontes → Resumo → Roteiro → Áudio (stepper) |
| P2 | **Divulgação progressiva** | Modo demo esconde tudo que é parâmetro; engenheiro abre "Avançado" |
| P3 | **Estado honesto e persistente** | Nada de toggle cosmético; progresso visível; cache dito em linguagem humana |
| P4 | **Caminho feliz em 2 ações** | 1 CTA principal gera e toca; passo a passo é opção, não obrigação |
| P5 | **Legibilidade de sala** | Medida de linha ≤ 76ch, contraste AA, dark e light testados no projetor |
| P6 | **Resiliência de demo** | Toda falha tem ação de saída; nada trava a apresentação |

## Arquivos deste plano

| Arquivo | Conteúdo | Quando usar |
|---|---|---|
| `01-auditoria.md` | Inventário da UI atual, heurísticas de Nielsen, achados U1–U26 com `app.py:linha`, baseline numérico | Antes de qualquer mudança; base para priorizar |
| `02-fluxos-e-wireframes.md` | Jornada alvo, wireframes desktop/mobile/apresentação, estados, microcopy antes→depois | Definir o "como deve parecer e fluir" |
| `03-design-system.md` | Tema `.streamlit/config.toml`, tokens de cor/tipografia/espaço, catálogo de componentes, CSS mínimo, acessibilidade | Implementar U0–U5 de forma consistente |
| `04-roadmap.md` | Fases U0→U5 com esforço, arquivos, critérios de aceite, riscos e validação | Executar em ordem, delegando ao `executor` |
| `05-spec-u0-u1.md` | Spec executável de U0+U1: arquivos, schema de `session_state`, assinaturas, pseudo-código, ordem de trabalho e testes | Entregar ao `executor` quando a rodada for aprovada |
| `mockup.html` | **Mock navegável** (autocontido, sem CDN): 10 cenários, fluxo animado do "Ouvir", mobile 390 px, catálogo de componentes, comparativo antes × depois e modo escuro | `xdg-open docs/UX/mockup.html` (ou abrir no navegador) |
| `06-guia-visual.md` | **Contrato visual** (aprovado 2026-11-27): conceito, tokens light/dark, tipografia, anatomia com medidas, voz/microcopy, checklist de revisão | Ler antes de qualquer mudança visual; atualizar junto com o mock |
| `07-resultado.md` | **Antes × depois** da rodada, arquivos da camada de UI, evidências, desvios, pendências e roteiro de demo | Resumo para a banca e checklist do seminário |

## Ordem de execução (resumo)

| Fase | Tema | Esforço | Impacto | Depende de |
|---|---|---|---|---|
| **U0** | Fundamentos visuais (tema, título, empty state, microcopy) | 2–3 h | Alto (percepção) | — |
| **U1** | Jornada linear (stepper, CTA único, progresso persistente, fim dos reruns cegos) | 5–7 h | **Muito alto** | U0 |
| **U2** | Sidebar em duas camadas ("Ajustes" × "Avançado"), custo e honestidade | 3–4 h | Alto | U1 |
| **U3** | Confiança nas fontes (SourceCard, score, destaque, debug em popover) | 4 h | Alto (prova do RAG) | U1 |
| **U4** | Histórico de sessão (turnos, reabrir, exportar) | 6–8 h | Médio (profundidade) | U1 |
| **U5** | Polimento de apresentação (player dock, atalhos, responsivo, QA dark/light) | 3 h | Médio | U0–U4 |

Esforço total: **23–29 h** (~3 sprints de 2 h/semana + folga). Nada disso bloqueia S5.

**Status (2026-11-27):** U0–U5 implementados — tema light/dark; jornada linear sem abas com
CTA único "Ouvir"; sidebar removida (header + `⚙ Ajustes`); fontes em cards; **☰ Sessão** com
turnos reabríveis sem LLM; **dock com player custom** (static serving, fallback nativo) e
**modo apresentação**; cards com superfície própria por tema. Resumo antes/depois e roteiro de
demo em `07-resultado.md`. Falta a validação humana (fluxo real, player/dark/390 px) e
**reiniciar o app** para ativar o static serving.

## Mock navegável (revisão visual)

```bash
xdg-open docs/UX/mockup.html          # abre direto no navegador
# ou, se preferir via servidor local:
python3 -m http.server -d docs/UX 8000   # http://localhost:8000/mockup.html
```

O mock é **um arquivo só**, sem CDN e sem build. Cenários:

| Botão | O que mostra |
|---|---|
| 1 · Início | estado vazio com chips (perguntas douradas) e cards de capítulo |
| 2 · Buscando | progresso persistente com etapas e cronômetro |
| 3 · Fontes | cards de fonte com página, tipo, relevância e snippet |
| 4 · Pronto | jornada completa com player dock |
| 5 · Erro | falha com ação de saída ("buscar no livro todo") |
| 6 · Mobile | 390 px, ações empilhadas |
| 7 · Antes × depois | UI atual (com pins U1–U6) ao lado da proposta |
| 8 · Componentes | cores, tipografia, botões, badges, microcopy |
| 9 · Apresentação | modo seminário (esconde avançado, aumenta leitura) |
| 10 · Escuro | a proposta inteira no tema escuro (ou use ◐ Tema) |

No cenário 1–6: **▶ Ouvir** anima a jornada; **☰** abre a sessão/histórico (U4);
**◐ Tema** alterna claro/escuro. O conteúdo é **ilustrativo** (não é saída real do RAG).

## Decisões aprovadas (2026-11-27)

> O usuário aprovou fluxo e identidade. As decisões abaixo deixaram de ser "defaults" e
> passaram a ser contrato; o detalhe visual está em `06-guia-visual.md`.

1. **`Modo offline`**: removido da UI até B1 existir (religar é 1 toggle).
2. **CTA único "Ouvir"** encadeia resumo → roteiro → áudio, com estimativa e custo visíveis;
   premium pede confirmação na 1ª vez.
3. **Tema**: identidade clara como padrão + **modo escuro completo** (requisito aprovado),
   via `[theme.light]`/`[theme.dark]` no `config.toml`.
4. **Tabs → empilhado**: Resumo → Roteiro na mesma coluna de leitura.
5. **Persona default**: mantido `tecnico_direto` (mudar é 1 linha).
6. **Escopo da rodada**: U0 + U1 + dock do U5; U2–U5 ficam prontos no roadmap.
7. **Idioma da UI**: 100% PT-BR, termos EN do glossário preservados (texto em `copy.py`).
8. **Mobile**: **não é prioridade** desta rodada — apenas não quebrar em 390 px.

## Regras de trabalho

- **Contrato visual**: qualquer componente novo ou ajuste de cor/medida segue
  `06-guia-visual.md`; atualize mock + guia no mesmo commit.
- Cada fase vira uma tarefa de `executor` com arquivos e aceite explícitos
  (`04-roadmap.md`); nada de refactor "de passagem".
- Validação é manual + `AppTest` headless (não há pytest). AppTest desta versão
  **não tem `.audio`**: checar player via `download_button`.
- Tema/CSS entram em **um único módulo** (`src/ui/theme.py`) para não espalhar
  `st.markdown("<style>")` pelo app.
- Sem dependência nova, sem CDN externo (kit offline), sem componente React.
