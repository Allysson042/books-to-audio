# Auditoria de UX/UI — estado atual

Levantamento em 2026-11-26 por leitura estática de `app.py` (257 linhas) + `src/markdown_math.py`,
`src/generate.py`, `src/tts_provider.py`, `personas/*.yaml`, `src/config.py`.
Contagens por `grep`; **nada foi executado** (o app carrega `sentence-transformers` e o HF Hub
pode pendurar ~12 min — ver B5).

## 1. Ficha da tela

| Atributo | Valor |
|---|---|
| `st.set_page_config` | `layout="wide"`, `page_title="Books to Audio — GDL"`, **sem `page_icon`** (`app.py:19`) |
| Título | `"Books to Audio — Generative Deep Learning"` (`app.py:20`) — único heading da página |
| Widgets interativos | **16**: 7 na sidebar + 9 no corpo |
| `st.columns` | **0** |
| `st.tabs` | 1 (2 abas) |
| `st.expander` | 2 (fontes + mapa) |
| `st.toggle` | **4** na sidebar (1 sem efeito) |
| `st.checkbox` | 3 (todos escondidos dentro do expander de fontes) |
| `st.button` / `download_button` | 4 / 2 |
| `st.metric` / `progress` / `toast` / `write_stream` | **0 / 0 / 0 / 0** |
| `st.form` | 0 → todo widget da sidebar dispara rerun completo |
| `st.cache_*` | 3× `cache_resource` (`app.py:63, 68, 73`) |
| CSS/tema custom | **nenhum** (sem `.streamlit/config.toml`, sem `st.markdown(<style>)`) |
| Imagens/logo | nenhuma |

## 2. Inventário vertical (o que o usuário vê, nesta ordem)

| Ordem | Elemento | Linha |
|---|---|---|
| 1 | Título (uma linha, nome do projeto + nome do livro) | 20 |
| 2 | Sidebar: Escopo, Persona, **Modo offline**, Usar cache, Re-rank, Estratégia, Voz premium, Mapa (expander com 14 caps) | 44–60 |
| 3 | `st.chat_input` — visualmente fixo no **rodapé** do container | 82 |
| 4 | `st.info` de onboarding com 3 exemplos **em texto morto** | 99 |
| 5 | Ao submeter: expander fechado `"Chunks recuperados (N) — ver fontes"` | 139 |
| 6 | Duas abas `Pass1 · resumo técnico` / `Pass2 · roteiro TTS` | 167 |
| 7 | Na aba Pass2, após o roteiro: caption de voz, botão de áudio, player, download | 220–257 |

Dentro do expander de fontes (139–165): 1 linha de markdown por chunk; checkbox "Raciocínio da
navegação"; `selectbox "Ver texto do chunk:"` + `st.write` cru; checkbox "Debug RAG" + tabela;
checkbox "Resumo macro"; e um `caption` com **7 parâmetros internos** (`offline: False`,
`cache: on`, `re-rank: off`…).

## 3. Jornada atual até o áudio

| # | Ação | Chamadas externas | Reruns | Feedback |
|---|---|---|---|---|
| 1 | Digita e dá Enter | busca (LLM da árvore ou Chroma+BM25) | 1 | spinner textual, some ao terminar |
| 2 | Abre a aba Pass2 | — | 0 | `"Nada gerado ainda."` |
| 3 | "Gerar roteiro" | **2 LLM** (Pass1 em silêncio + Pass2) | 1 | 1 spinner só; Pass1 "aparece de graça" na outra aba |
| 4 | "Gerar áudio (5-8min)" | 1+ TTS (N fatias no premium) | 1 | spinner; `n fatia(s)` só **depois** |

Caminho mínimo: **4 ações, 3 reruns, 2 trocas de contexto visual**. Quem quer ler o resumo antes:
+1 clique e +1 rerun. Cada rerun leva o scroll para o topo e podem trocar a aba ativa.

## 4. Sidebar: controle → efeito real

| Controle | Default | Efeito | Problema de UX |
|---|---|---|---|
| `Escopo` | Livro todo | filtro de capítulo + chave de cache | ok, mas é decisão de produto no meio de knobs |
| `Persona` | `tecnico_direto` | addendum + voz | valor exibido é **slug de código** |
| `Modo offline (cache demo)` | off | **nenhum** (só eco no caption) | **mente**; B1 aberto |
| `Usar cache (texto+áudio)` | on | pula leitura de cache | formulário negativo ("usar" on = padrão); OFF não invalida `ret_ctx` |
| `Re-rank (cross-encoder)` | off | só vetorial | jargão; no vectorless força rebusca inútil |
| `Estratégia` | `vectorless` | troca backend | valores são nomes de implementação |
| `Voz premium (OpenRouter TTS)` | off | escolhe provider TTS | custo só no tooltip; **não** invalida o MP3 exibido |
| `Mapa do livro` | — | leitura | 14 itens sem busca; ocupa a sidebar |

## 5. Achados

Severidade: **C** = quebra/engana a demo · **A** = custo cognitivo ou erro provável · **M** = fricção · **B** = cosmético.

| ID | Sev | Achado | Evidência | Impacto |
|---|---|---|---|---|
| U1 | A | "Chat" que não conversa: nova pergunta apaga `pass1/pass2/mp3`; não há histórico, follow-up nem comparação | `app.py:93-96`, `82-89` | O usuário não consegue estudar um capítulo em diálogo; cada pergunta recomeça |
| U2 | A | `st.rerun()` após gerar resumo/roteiro → página "pisca", scroll volta ao topo, aba pode mudar | `app.py:182, 208` | Perda de contexto a cada ação; pior no celular |
| U3 | A | Ações escondidas em abas: quem está no Pass1 não vê "Gerar roteiro"; quem está no Pass2 não vê o resumo pronto | `app.py:167-193` | O fluxo linear é quebrado; metade da tela é invisível |
| U4 | A | Sidebar mistura 3 decisões do ouvinte com 4 knobs de engenheiro, sem hierarquia | `app.py:44-54` | Carga cognitiva; plateia vê `vectorless`, `cross-encoder`, `cache` |
| U5 | **C** | `Modo offline` não faz nada — só aparece no caption | `app.py:46` vs `165` | Promete fallback de demo que não existe (B1) |
| U6 | A | Estado órfão: novo roteiro **não** limpa `mp3`; trocar voz premium/cache não invalida áudio | `app.py:206-207`, `249-254`, `92` | Player toca áudio de um roteiro que não está mais na tela |
| U7 | A | Erro de busca é gravado junto com `ret_ctx` e não tem "tentar de novo" | `app.py:121-129` | Falha de rede/quota vira tela travada até mudar query |
| U8 | A | Progresso efêmero: 5 spinners, 0 barra, 0 streaming, 0 toast; premium fatia N vezes sem progresso | `109, 117, 177, 195, 229` | Com 30–120 s de LLM (ou 12 min de HF Hub) o usuário acha que travou |
| U9 | M | Erros crus: `str(e)` direto; fallback premium cortado em 120 chars no meio da frase | `129, 184, 210, 248, 236-237` | Sem diagnóstico nem ação de saída |
| U10 | M | Custo do premium não aparece no botão; botão continua ativo sem `OPENROUTER_API_KEY` | `53-54, 227-240` | Risco de gasto/erro ao vivo na demo |
| U11 | A | Sem histórico, sem reset, sem exportar a sessão (só MP3) | ausência | Não dá para revisar nem reapresentar uma pergunta anterior |
| U12 | A | "Gerar resumo" com cache ON devolve texto idêntico **sem avisar**; não há "regenerar" explícito | `175` + `src/generate.py:94-95` | Usuário acha que o botão não funcionou |
| U13 | M | Empty state passivo: 3 exemplos em `st.info` não clicáveis, embora `scripts/golden.json` tenha perguntas douradas | `99-100` | Onboarding custa digitação; demo perde tempo |
| U14 | M | Fontes: 1 linha de markdown por chunk, texto cru via `selectbox`+`st.write`, 3 checkboxes como "modos" | `139-161` | Descoberta ruim; a prova do RAG (score, trecho, página) fica escondida |
| U15 | A | Sem medida de linha: `layout="wide"` + texto em largura total (~120–160 chars/linha em 27") | `19`, `149`, `172` | Leitura de resumo técnico desconfortável; pior no projetor |
| U16 | M | Zero identidade: sem `page_icon`, sem tema, sem subtítulo, sem headings de seção | `19-20` | Parece script interno, não produto de seminário |
| U17 | M | Microcopy misto PT/EN e jargão em caption (`offline: False`, `cache: on`, `re-rank: off`, `via openrouter`) | `162-165`, `38-39`, `242-243` | Vaza implementação para o ouvinte |
| U18 | B | Macro truncada em 3000 chars com reticências, sem aviso nem "ver completo" | `160-161` | Usuário não sabe que falta conteúdo |
| U19 | M | Proveniência enganosa: cache-hit do Pass1 encadeado é reportado como "recém-gerado"; badge ``via `cache` · do cache`` | `198-202`, `38-39` | Quebra a confiança no indicador |
| U20 | M | Acessibilidade: `chat_input` só com placeholder; `help` de botão desabilitado inacessível no toque; contraste/tema não controlados | `82-84`, `256-257` | Leitor de tela e uso em tablet pioram |
| U21 | B | Áudio: Piper pode devolver `.wav`, mas o download é rotulado `mime="audio/mpeg"` | `245-246` vs `src/tts_provider.py:229` | Arquivo baixado com MIME errado |
| U22 | M | f-string aninhada com aspas idênticas exige Python ≥3.12 (PEP 701) | `app.py:143` | `SyntaxError` em 3.10/3.11 (sem pin no repo) |
| U23 | M | Sidebar sem `st.form`: cada toggle/select dispara rerun e re-render completo | `44-54` | Configurar persona+escopo = 2 recarregamentos |
| U24 | M | `mapa_livro.json` ausente falha em silêncio: escopo vira só "Livro todo", sem aviso | `23-27` | Usuário não descobre que a ingestão está incompleta |
| U25 | B | Capítulo derivado por `split(":")` do label do selectbox | `43, 55` | Renomear o label quebra o filtro silenciosamente |
| U26 | M | Duração mentida: o botão promete "5-8min", mas `TTS_MAX_CHARS=15000` dá ~16 min de fala; a duração nunca é calculada | `227, 220` vs `src/config.py:103` | Expectativa errada na demo (áudio 2× mais longo que o anunciado) |

## 6. Leitura pelas heurísticas de Nielsen

| Heurística | Nota | Onde dói |
|---|---|---|
| 1. Visibilidade do status | **2/5** | spinners efêmeros, sem timeline, sem progresso de fatias, sem toast |
| 2. Correspondência com o mundo real | **2/5** | `vectorless`, `cross-encoder`, `Pass1/Pass2`, `tts_voice`, `re-rank 0.4821` |
| 3. Controle e liberdade | **2/5** | sem cancelar, sem reset, sem regenerar, sem desfazer |
| 4. Consistência e padrões | **3/5** | abas escondem ações; "Gerar resumo" às vezes não gera; botões primários competem |
| 5. Prevenção de erro | **2/5** | premium sem custo/credencial; TTS > limite só avisa depois; estado órfão de MP3 |
| 6. Reconhecer em vez de lembrar | **2/5** | sem histórico, sem exemplos clicáveis, sem "última pergunta" visível no topo |
| 7. Estética e minimalismo | **2/5** | 16 widgets, 8 controles permanentes, debug na cara, caption com 7 parâmetros |

## 7. O que já está certo (não jogar fora)

- Fontes dentro de **um** expander colapsado (decisão de `ui-refactor.md`, correta).
- `st.chat_input` com submit explícito + query efetiva em `session_state` (corrigiu B2/B3).
- Memoização `ret_ctx`/`top5`/`cands` — reruns de botão não rebuscam (B4).
- Badge de proveniência por seção (a ideia é boa; a linguagem/estado, não).
- Aviso de `TTS_MAX_CHARS` antes de sintetizar.
- Render híbrido de LaTeX no Pass1.
- Fallback premium → Edge automático (a mensagem precisa melhorar, o comportamento não).

## 8. Baseline para medir a melhoria

| Métrica | Hoje | Meta (pós-U1/U2) |
|---|---|---|
| Controles permanentes antes de gerar | 7 (sidebar) + 1 input | 3 (escopo, persona, pergunta) |
| Ações até o 1º áudio | 4 | **2** (pergunta + "Ouvir") |
| Reruns percebidos pelo usuário | 3 (pisca) | 0 (estado incremental) |
| Jargão de engenharia visível por padrão | 5 termos | 0 (só em "Avançado") |
| Erros sem ação de saída | 4 de 4 | 0 |
| Medida de linha do texto lido | ~120–160 ch | ≤ 76 ch |
| Contraste do texto principal | default do Streamlit | ≥ 4,5:1 (AA) |
| Estados de carregamento persistentes | 0 de 5 | 5 de 5 |
