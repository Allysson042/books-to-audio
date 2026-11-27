# Spec de implementação — U0 + U1

Nível: pronto para o `executor`. **Nada implementado.** Só toca a camada de UI
(`app.py` + `src/ui/*`), nunca retrieval/geração/TTS/cache.

Defaults adotados (reversíveis, ver §9): CTA único "Ouvir" encadeando resumo→roteiro→áudio;
`Modo offline` removido da UI; tema `auto` (light/dark); abas substituídas por seções
empilhadas; UI 100% PT-BR (termos EN do glossário preservados).

## 0. Pré-condições

- Venv está em **Python 3.14** (ok). O `f-string` de `app.py:143` usa PEP 701; se alguém
  rodar em 3.10/3.11, corrigir antes (U22).
- `streamlit` instalado em 1.64. O CSS desta spec foi escrito para 1.64; pinar
  `>=1.64,<2` em `requirements.txt` (com aval da equipe).
- Nenhuma mudança em `src/config.py` é necessária. `use_cache` continua sendo o mesmo
  booleano; a UI passa `use_cache=not ignore_cache`.
- `scripts/golden.json` é a fonte dos chips (fallback: lista literal em `copy.py`).

## 1. Estrutura de arquivos

```
src/ui/
  __init__.py      # reexporta o essencial (inject, page_header, ...)
  theme.py         # TOKENS, CSS, inject(st), read_container()
  copy.py          # TODO o microcopy em um dict (fonte única)
  state.py         # Turn, init(), ctx_key(), derive_stages(), audio_sig(), clear()
  layout.py        # page_header(), stage_rail(), section_card(), provenance()
  empty.py         # empty_state(golden) -> pergunta escolhida | None
  actions.py       # action_rail(...) -> intent ("listen"|"pass1"|"pass2"|"audio"|None)
  sources.py       # (U3) lista de fontes; em U0/U1 mantém o expander atual
app.py             # orquestra estado, layout e chamadas existentes
assets/icon.png    # opcional (page_icon); se ausente, usar emoji
```

Regra: `app.py` deixa de conter markdown/labels longos; ele lê estado, chama `ui.*`,
executa o intent e preenche placeholders.

## 2. Schema de `session_state` (U0/U1)

| Chave | Tipo | Semântica |
|---|---|---|
| `q_input` | str | widget do `chat_input` (não usar como query) |
| `query` | str | última pergunta **submetida** |
| `settings` | dict | `{scope, chapter, persona, strategy, rerank, ignore_cache, premium_voice}` |
| `ctx` | tuple | `(query, scope, persona, strategy, rerank if strategy=="vetorial" else None)` |
| `ret_ctx` | tuple | ctx da busca memoizada |
| `top5`, `cands`, `ret_err`, `ret_elapsed` | — | como hoje |
| `pass1` | dict | `{text, provider, cached, elapsed, chunk_sig, persona}` |
| `pass2` | dict | `{text, provider, cached, elapsed, chars, voice}` |
| `audio` | dict | `{path, engine, chars, voice, sig}` — **substitui `mp3`** |
| `run` | dict | `{stage, t0, steps[]}` para o `st.status` |
| `turns` | list | (U4) histórico; em U1 pode ficar vazio |
| `ui` | dict | `{presentation: bool, advance_open: bool}` |

Chaves antigas (`mp3`) podem ser migradas: `if "mp3" in state and "audio" not in state`.

`state.audio_sig(text, voice)` = `sha1(voice + len(text) + text[:200] + text[-200:])`.
Se `audio["sig"] != audio_sig(pass2["text"], voice_atual)` → áudio obsoleto: não renderizar
player, mostrar "esta gravação é de um roteiro anterior" com botão de regerar (corrige U6).

`state.derive_stages(...)` devolve
`{"pergunta": "done", "fontes": "done"|"error"|"active", "resumo": "locked"|"empty"|"ready"|"active", ...}`.

## 3. Ordem de execução do `app.py`

```
1. set_page_config(layout="wide", initial_sidebar_state="collapsed", page_icon=...)
2. ui.theme.inject(st)
3. carregar MAPA (com aviso se ausente — U24)
4. st.chat_input(...)                    # obrigatoriamente no corpo, antes de columns
5. submitted -> state["query"]
6. settings <- widgets do header (popover)   # não na sidebar
7. invalidar ctx se mudou; se query nova: busca (memoizada por ret_ctx)
8. header + stage_rail
9. left, right = st.columns([2,1], gap="large")
10. placeholders: q, fontes, resumo, roteiro (left.empty())   # criados ANTES do rail
11. with right: intent = actions.rail(...)   # único CTA primary + 2 secundários
12. if intent: executar pipeline com st.status + tempo, gravando em state
13. preencher placeholders (pergunta, fontes, resumo, roteiro)
14. se state["audio"] e sig válido: dock fixo no fim do script
```

Por que placeholders antes do rail: o clique é conhecido no passo 11; o resultado pode ser
escrito nos containers já criados (passo 13) **sem `st.rerun()`**, preservando scroll e aba.

Importante: `st.chat_input` continua no topo do script (é o Streamlit que o posiciona no
rodapé). Não mover para dentro de `columns`/`container` (quebra — ver `app.py:79-81`).

### Pseudo-código mínimo

```python
# app.py (esqueleto, ~120 linhas)
from src import config
from src.ui import theme, copy, state, layout, empty, actions

st.set_page_config(page_title=copy.TITLE, page_icon=copy.ICON, layout="wide",
                   initial_sidebar_state="collapsed")
theme.inject(st)

mapa = load_mapa()                       # aviso se ausente
state.init(st.session_state)

q = st.chat_input(copy.ASK_PLACEHOLDER, max_chars=config.MAX_QUERY_CHARS, key="q_input")
if q and q.strip():
    state.new_query(st.session_state, q.strip())
state.sync_settings(st.session_state, layout.settings_widgets(mapa))

if state.needs_retrieval(st.session_state):
    state.retrieve(st.session_state, config)   # mesma lógica atual, com tempo

layout.page_header(st, st.session_state, mapa)
layout.stage_rail(st, state.derive_stages(st.session_state))

left, right = st.columns([2, 1], gap="medium")
ph = {k: left.empty() for k in ("q", "src", "p1", "p2")}

with right:
    intent = actions.rail(st, st.session_state, copy)

if intent:
    with st.status(copy.RUN_LABEL[intent], expanded=True) as box:
        state.run_intent(st.session_state, intent, box)   # usa get_pass1/get_pass2/synthesize
        box.update(label=copy.RUN_DONE, state="complete")

layout.question_card(ph["q"], st.session_state, copy)
sources.render(ph["src"], st.session_state)               # U0/U1: expander atual
layout.reading_card(ph["p1"], copy.PASS1, st.session_state.get("pass1"), ...)
layout.reading_card(ph["p2"], copy.PASS2, st.session_state.get("pass2"), ...)
layout.audio_dock(st, st.session_state)                   # só se sig válido
```

## 4. Assinaturas dos componentes

| Função | Entrada | Saída / efeito |
|---|---|---|
| `theme.inject(st)` | módulo | injeta CSS uma vez |
| `theme.read_container(st, key)` | módulo, str | `st.container` com classe `.gdl-read` |
| `layout.page_header(st, state, mapa)` | — | título, subtítulo, selects do header, popover Sessão |
| `layout.settings_widgets(mapa)` | — | dict de settings (sem escrever no state) |
| `layout.stage_rail(st, states)` | dict | HTML do rail (sem clique) |
| `layout.section_card(st, title, provenance, body_fn, actions)` | — | container com header + corpo |
| `layout.question_card(ph, state, copy)` | placeholder | card com pergunta + ✎ (form inline) |
| `layout.reading_card(ph, meta, payload, ...)` | placeholder | vazio/pronto/erro + ações de conteúdo |
| `layout.audio_dock(st, state)` | módulo | container sticky com `st.audio` + download |
| `empty.empty_state(st, golden, copy)` | — | chips; retorna pergunta escolhida |
| `actions.rail(st, state, copy)` | — | `"listen" \| "pass1" \| "pass2" \| "audio" \| None` |
| `state.run_intent(st_state, intent, box)` | — | executa e atualiza `pass1/pass2/audio` |
| `state.derive_stages(st_state)` | — | dict de estados |

Erros: `run_intent` captura `(RuntimeError, ValueError)`, grava `error` no card
correspondente e **não** levanta. A UI mostra `copy.ERROR[stage]` + ação.

## 5. Regras do rail de ações

| Intenção | Rótulo | Tipo | Quando habilita |
|---|---|---|---|
| `listen` | `▶ Ouvir · ≈{min} min` | primary | há `top5` |
| `pass1` | `Só o resumo técnico` | secondary | há `top5` |
| `pass2` | `Só o roteiro falado` | secondary | há `top5` (gera resumo junto) |
| `audio` | `Regerar áudio` | secondary | `pass2` e sig válido |

- Texto de apoio sob o primary: `resumo + roteiro + áudio` e `grátis` **ou**
  `≈US$0,06 · voz Luana` (premium). Sem `help=` como única fonte (U20).
- Premium sem `OPENROUTER_API_KEY` → toggle desabilitado com explicação visível.
- Durante execução: rail vira `st.status` com etapas (`fontes`, `resumo`, `roteiro`, `áudio`)
  e cronômetro; botões ficam `disabled`. "Parar" só entre etapas (limitação real).

## 6. Estimativas (não hardcode)

```python
def audio_minutes(chars: int) -> float:    # ~900 chars/min em pt-BR
    return round(chars / 900, 1)

def pass1_seconds(chunks: int) -> int:     # heurística conservadora
    return 10 + 4 * chunks
```

- Rótulo do áudio: `≈{audio_minutes(len(clean_for_speech(text)))} min` (corrige U26).
- Aviso de teto: se `chars > TTS_MAX_CHARS`, mostrar `N de 15.000` **antes** do clique e
  oferecer "encurtar roteiro" (gera Pass2 com `MAX_TOKENS` menor ou prompt de síntese;
  se não houver caminho barato, apenas orientar — não inventar pipeline novo em U1).

## 7. Ordem de trabalho (checkpoints independentes)

| Passo | Entrega | Validação |
|---|---|---|
| 1 | `theme.py` + `.streamlit/config.toml` + `page_icon` + título/subtítulo | AppTest roda; troca light/dark; sem erro de CSS |
| 2 | `empty.py` com chips do `golden.json` | clicar chip preenche `query` e busca |
| 3 | `layout.py` + remoção das abas (seções empilhadas, comportamento atual) | Pass1/Pass2 visíveis; cache/badges intactos |
| 4 | `actions.rail` + `run_intent` sem encadeamento | cada botão gera o seu e preenche o card; **sem `st.rerun`** |
| 5 | Encadeamento do `listen` + `st.status` + estimativas | 1 clique gera resumo+roteiro+áudio |
| 6 | `audio_sig`, retry de busca, microcopy final | áudio nunca órfão; erro com ação |
| 7 | QA (dark/light/390px/teclado) + screenshots | checklist de `03` §6 |

Cada passo deve deixar o app funcional. Se o passo 4 atrasar, o app ainda funciona no 3.

## 8. Validação (AppTest + manual)

```python
# scripts/apptest_ui.py (proposta; não existe hoje)
from streamlit.testing.v1 import AppTest

def run(query="O que é ELBO em VAEs?"):
    at = AppTest.from_file("app.py", default_timeout=180)
    at.run()
    assert not at.exception
    at.chat_input[0].set_value(query).run()
    assert not at.exception
    return at

# 1) busca
at = run(); assert len(at.expander) >= 1
# 2) pass1 isolado: clicar botão por rótulo
btn = next(b for b in at.button if "resumo" in b.label.lower()); btn.click().run()
assert not at.exception
# 3) áudio: AppTest 1.64 não expõe .audio -> validar download_button e existência do .mp3
```

Manual (obrigatório): fluxo "Ouvir" com cache quente; cache frio; erro forçado (query com
escopo vazio); premium OFF; dark/light; 390 px; teclado.

## 9. Defaults assumidos (reverter é barato)

| Decisão | Default adotado | Custo de reverter |
|---|---|---|
| Escopo da rodada | U0 + U1 (+ dock) | adiar U2–U5 não quebra nada |
| CTA "Ouvir" encadeia 3 etapas | sim | voltar a 3 botões = 1 bloco de `actions.rail` |
| `Modo offline` | removido da UI | religar um toggle de 3 linhas |
| Tema | `auto` (segue SO) | trocar `base` no `config.toml` |
| Abas | seções empilhadas | voltar `st.tabs` é 1 bloco |
| Sidebar | só Sessão + Avançado | mover selects de volta |
| UI | PT-BR | dicionário `copy.py` já centraliza |

## 10. Fora desta spec

- `sources.py` (U3): cards com score/snippet/página e popover de debug.
- Histórico de turnos (U4).
- Modo apresentação e dock responsivo (U5) — o dock entra em U1 de forma simples; o
  refinamento fica em U5.
- Qualquer alteração em `src/generate.py`, `src/tts_provider.py`, `src/retrieval*.py`,
  prompts, personas ou chaves de cache.