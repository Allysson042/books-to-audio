# Mapa mental por imagem — plano (2026-11-27)

> Status: **M0 implementado e validado (2026-11-27)**; M1 (imagem) não iniciado.
> Decisões travadas (§9): SVG é o default, imagem só no botão "Estilizar",
> Nano Banana 2 priorizado no M1. Objetivo: fechar o trio de modalidades
> (texto = Pass1/Pass2, áudio = TTS) com **imagem**, gerando um mapa mental a partir do
> resumo técnico (Pass1) para ajudar o leitor a organizar as ideias.
> Fontes consultadas: `openrouter.ai/docs/features/multimodal/image-generation`,
> `GET /api/v1/images/models`, `GET /api/v1/images/models/{id}/endpoints` (preços reais,
> consultados em 2026-11-27).

> **Visualização em tela cheia (2026-11-27):** o card do mapa tem "⛶ Ver em tela cheia",
> que publica `<hash>.html` + `<hash>.svg` em `static/mind/` (`src/ui/mindmap_view.py`) e
> abre em nova aba com `min-width:1200px`, tema claro/escuro e zoom do navegador. Sem
> static serving, o app mostra aviso + "Baixar SVG". O pipeline do mapa não muda.

## 1. Achado principal (ler antes de escolher modelo)

Mapa mental vive de **rótulo correto**. Modelos de imagem são bons em estética e ruins em
texto arbitrário: erram acento, trocam palavras e inventam rótulos. Se o mapa é o artefato
que o leitor usa para estudar, texto errado é pior que não ter mapa.

Por isso o desenho recomendado separa **conteúdo** de **renderização**:

| Desenho | Como | Custo | Texto PT-BR | Serve ao seminário? |
|---|---|---|---|---|
| **A. Determinístico** | LLM → JSON do outline → layout próprio em SVG | US$ 0 | 100% fiel | Prova o pipeline, mas não usa modelo generativo de imagem |
| **B. Generativo puro** | Pass1 → prompt → `POST /api/v1/images` | US$ 0,002–0,15 | risco alto (OCR ruim, acentos, rótulos inventados) | Usa o modelo, mas pode entregar mapa ilegível |
| **C. Híbrido (recomendado)** | LLM → JSON → SVG "rascunho" → modelo de imagem redesenha via `input_references` | US$ 0,007–0,04 | bom, se o modelo respeitar o rascunho; validar com OCR | Usa modelo generativo **e** garante um mapa fiel de fallback |

Recomendação: **C**, com **A como fallback obrigatório** (se API falhar, quota estourar ou
o texto sair corrompido, a UI mostra o SVG). Isso mantém a regra do projeto (R$ 0 no default)
e ainda contempla a modalidade de imagem.

## 2. Catálogo OpenRouter (preço por imagem, 2026-11-27)

### Preço fixo por imagem (melhor custo-benefício)

| Modelo | US$/img | Params relevantes | Observação |
|---|---|---|---|
| `recraft/recraft-v4.1-flash` | **0,007** | `aspect_ratio`, `n` | tier rápido da Recraft, família focada em *graphic design*/ilustração |
| `recraft/recraft-v4.1-flash-v2` | **0,007** | `aspect_ratio`, `n` | idem; existe variante `:free` **que expira em 2026-11-28** (só para teste comparativo) |
| `black-forest-labs/flux-3-image-klein` | 0,008 (768) / 0,009 (1K) / 0,011 (1.5K) | `resolution`, `aspect_ratio`, `output_format`, `seed` | FLUX klein, bom traço, texto fraco |
| `meta/muse-image` | 0,010 | `aspect_ratio`, `size`, `output_format` | agêntico, raciocina antes de renderizar |
| `krea/krea-2-medium-turbo` | 0,015 | `resolution`, `aspect_ratio` | rápido, estético |
| `bytedance-seed/seedream-5-0-flash` | 0,018 | `resolution`, `aspect_ratio`, `background`, `seed` | bom em composição densa |
| `qwen/qwen-image-2.1-turbo` | 0,018 | `resolution`, `aspect_ratio`, `seed` | renderiza texto pequeno razoavelmente |
| `sourceful/riverflow-v2.5-fast` | 0,019 | `resolution`, `aspect_ratio`, `background` | workflow de produção |
| `bytedance-seed/seedream-5-5` | 0,020 (0,035 high-res) | `resolution`, `aspect_ratio`, `background` | topo da linha Seedream |

### Cobrança por token (estimar ~1.290 tokens por imagem 1K)

| Modelo | US$/1M out | ≈ US$/img 1K | Observação |
|---|---|---|---|
| `openai/gpt-image-1-mini` | 8 | **0,002 (low) · 0,008 (medium) · 0,033 (high)** | melhor texto/legibilidade da faixa barata; `low` pode ser pequeno demais para rótulos |
| `openai/gpt-image-2.6-flare` | 30 | 0,008 · 0,03 · 0,12 | texto forte, caro no high |
| `google/gemini-3.1-flash-lite-image` | 30 | ≈ 0,039 | Nano Banana 2 Lite, rápido |
| `google/gemini-2.5-flash-image` | 30 | ≈ 0,039 | "Nano Banana" original, famoso por infográficos legíveis |
| `google/gemini-nano-banana-2.1` | 30 | ≈ 0,039 | sucessor, edição multi-ref |
| `google/gemini-3.1-flash-image` | 60–66 | ≈ 0,08 | Nano Banana 2, melhor qualidade do tier Flash |
| `google/gemini-3-pro-image` | 120 | ≈ 0,15 | topo, só se o mapa for peça central da demo |
| `microsoft/mai-image-2.7-flash` | 10 | ≈ 0,013 | mesma família do TTS premium já usado |

### Shortlist (decidida em 2026-11-27)

1. **Prioridade do M1 — qualidade visual:** `google/gemini-3.1-flash-image` (Nano Banana 2,
   ≈US$ 0,08/img). Escolhido para o botão "Estilizar": é o que entrega o mapa apresentável
   do seminário e o melhor texto do tier Flash.
2. **Alternativa barata:** `recraft/recraft-v4.1-flash-v2` — US$ 0,007, família desenhada
   para design gráfico (setas, blocos, hierarquia). Entra no A/B como piso de custo.
3. **Controle de legibilidade:** `openai/gpt-image-1-mini` em `quality=medium` (≈US$ 0,008) —
   testar `low` (≈US$ 0,002); serve de referência de texto correto.

Custo do M1: 3 modelos × 2 perguntas = 6 imagens ≈ **US$ 0,19** (dominado pelo Nano Banana).
Operação normal no default SVG: **US$ 0**. Cada "Estilizar" com Nano Banana 2: **≈US$ 0,08**.

## 3. Arquitetura de integração

```
Pass1 (texto técnico, já cacheado)
   │
   ├─► [Pass M] LLM texto → outline JSON (rótulos curtos, 2 níveis, citações no rodapé)
   │        cache: cache/mind_{hash}.json   (MINDMAP_VERSION)
   │
   ├─► [Renderer A] SVG determinístico  → static/mind_{hash}.svg   (US$ 0, offline, fiel)
   │
   └─► [Renderer B] OpenRouter Images   → cache/images/{hash}.png
            prompt = template + rótulos do outline
            input_references = PNG do SVG (modo híbrido)
            cache: modelo+aspecto+resolução+outline+versão
   │
   └─► Card "🧠 Mapa mental" no app (SVG sempre; PNG se escolhido/gerado)
```

### Módulos novos (não criar ainda)

| Arquivo | Papel | Espelha |
|---|---|---|
| `src/mindmap.py` | `build_outline(pass1, query, scope) -> dict`, `outline_to_svg(outline) -> str`, `outline_to_prompt(outline) -> str` | `src/generate.py` (cache por hash) |
| `src/image_provider.py` | `generate(prompt, *, model, aspect_ratio, resolution, input_refs) -> (Path, meta)` via `httpx` puro | `src/tts_provider.py` (`synth_openrouter`, retry, sidecar) |
| `src/ui/mindmap_card.py` | render do card (SVG inline ou `<img src="/app/static/...">`) | `src/ui/player.py` (cópia p/ `static/`, cache-bust, prune) |

Sem dependência nova obrigatória: SVG é gerado como string (layout em Python). Evitar
`graphviz`/`mermaid` (binário ausente e `npx` não é offline-safe). Se o layout radial ficar
trabalhoso, `Pillow` entra só como opção (`requirements.txt` hoje não tem PIL).

### Config (`src/config.py`, padrão `env_*`)

```
MINDMAP_ENABLED=false        # default: nada aparece
MINDMAP_MODE=svg             # svg | image | hybrid
MINDMAP_MAX_BRANCHES=5       # nós de 1º nível
MINDMAP_MAX_DEPTH=2          # 2 = netos
MINDMAP_LABEL_CHARS=40
MINDMAP_VERSION=v1           # bust do outline
IMAGE_MODEL=                 # vazio = desliga o render generativo (R$ 0)
IMAGE_QUALITY=medium
IMAGE_ASPECT=4:3
IMAGE_RESOLUTION=1K
IMAGE_TIMEOUT=120
IMAGE_RETRIES=1
IMAGE_VERSION=v1
```

`IMAGE_MODEL` vazio por default mantém a promessa "R$ 0 no default"; pins pagos só no `.env`
local, como já é feito com `OPENROUTER_TTS_MODEL`.

### Cache e custo

- Outline: `cache/mind_{sha16(MINDMAP_VERSION|scope|query|sig8(pass1))}.json` — 1 chamada
  de texto barata, invalidada com `MINDMAP_VERSION`/`PROMPT_VERSION`.
- Imagem: `cache/images/{sha16(IMAGE_VERSION|model|aspect|resolution|quality|prompt)}.png`
  + sidecar `.json` com `usage.cost` devolvido pela API (a doc confirma `usage.cost`).
- Usar `response_format: "b64_json"` e gravar local: a URL assinada expira em 24 h e
  não serve como cache.
- Cobrança é *all-or-nothing*: falha/cancelamento não é cobrado; 502 volta como erro.
  Continua valendo retry só em 429/5xx/timeout (mesma política do LLM).
- Fallback de degradação: `image`/`hybrid` → SVG → nada, nunca derrubar o card.

### UI

- Novo placeholder `ph_map` junto de `app.py:261-268` e card renderizado no bloco
  `436-527`, **entre Pass1 (`467-480`) e Pass2 (`482-499`)**.
- Não criar 6º estágio: `src/ui/stages.py` (22-46) e `copy.STAGES` são fixos em 5.
  O mapa é uma seção do card do Pass1, com botão próprio ("Gerar mapa mental") e intent
  `map` em `_run` (`app.py:328-382`).
- Ajustes: `st.selectbox` "Mapa mental: desligado / SVG / imagem / híbrido" no popover
  (padrão dos toggles em `app.py:56-88`), só habilitado se `OPENROUTER_API_KEY` existir
  quando não for SVG.
- Reaproveitar `src/ui/player.py` para servir o arquivo: copiar para `static/`, URL
  `/app/static/<nome>?v=<mtime>` (constantes em `player.py:21-22`), prune por mtime.

## 4. Contrato do outline (Pass M)

```json
{
  "titulo": "VAEs e o ELBO",
  "ramos": [
    {"rotulo": "Objetivo", "filhos": ["latent space", "reconstrução"]},
    {"rotulo": "Trade-off", "filhos": ["fidelidade", "regularização"]}
  ],
  "citacoes": ["Cap 3, p. 71", "Cap 3, p. 74"]
}
```

Regras do prompt (system + user):
- Derivar **somente** do Pass1; proibido introduzir conceito novo.
- 3–5 ramos, ≤3 filhos por ramo, rótulo ≤40 chars, sem markdown, sem `[colchetes]`.
- Manter termos do glossário em EN (`src/prompts.py`).
- Citações só no rodapé (`citacoes`), nunca dentro dos rótulos.
- Saída JSON pura; parser tolerante (cercas ```` ```json ````, vírgula final) + retry 1x.

## 5. Prompt da imagem (renderer B)

Template curto (~1.200 chars) para não pagar prompt grande:

```
Clean flat-vector mind map infographic on a plain white background, {aspect}.
Center node: "{titulo}". {N} branches connected by smooth arrows:
{para cada ramo} branch "{rotulo}" with children {filhos}.
Render EXACTLY the text given, in Brazilian Portuguese, preserving accents.
No other words, no watermark, no signature, no decorative letters.
Palette: 2 colors + neutral, high contrast, generous spacing, legible at 1K.
```

No modo híbrido, anexar o SVG rasterizado em `input_references` e trocar a 1ª linha por
"Redraw this exact mind map in a clean flat-vector style, keeping every label identical".

## 6. Validação e aceite

- `scripts/eval_mindmap.py` (novo): roda as 5 douradas de `scripts/golden.json`, valida
  schema (ramos 3–5, rótulos ≤40, citações presentes), mede tempo e custo.
- Fidelidade do rótulo: comparar `outline` × texto do SVG (deve ser idêntico) e, na imagem,
  fazer OCR opcional via Gemini visão e diff de strings. **Aceite: ≥90% dos rótulos
  idênticos**; abaixo disso, o modo `image` não vira default.
- Log `[image-call]` (modelo, aspecto, resolução, `usage.cost`, segundos) no padrão
  `[llm-call]`/`[tts-call]`.
- Offline: SVG sempre disponível; PNG só se estiver em `cache/images/`.
- AppTest: card não quebra sem chave, sem rede e com outline inválido.

## 7. Riscos

| Risco | Mitigação |
|---|---|
| Texto corrompido/acentos errados | SVG como fonte da verdade; modo imagem só com aceite de OCR |
| Modelo inventa conceito | outline 100% derivado do Pass1 + validação de schema |
| Custo inesperado | `IMAGE_MODEL` vazio por default; trava por `MAX_IMAGES`/dia se necessário |
| Suporte a parâmetro varia por modelo | checar `supported_parameters` no endpoint antes de enviar |
| `:free` da Recraft expira 2026-11-28 | usar só em teste A/B, nunca como default |
| URL expira em 24 h | `b64_json` + arquivo local |
| `static/` cresce | prune por mtime, igual ao player |

## 8. Fases

- **M0 (grátis):** outline JSON + SVG determinístico + card + cache + régua. Prova valor
  sem gastar nada e já entrega mapa fiel no seminário. **Feito em 2026-11-27**:
  `src/mindmap.py`, card no Pass1 (`intent=map`), `scripts/eval_mindmap.py`, knobs
  `MINDMAP_*`. Validado com LLM real (2/2 mapas, 5 ramos, rótulos dentro do viewBox) e
  AppTest (0 exceções). Custo medido ≈US$ 0,00018/mapa.
- **M1:** `src/image_provider.py` + `POST /api/v1/images`, acionado pelo botão
  **"Estilizar"** (nunca automático). A/B `gemini-3.1-flash-image` (prioridade) ×
  `recraft-v4.1-flash-v2` (piso de custo) × `gpt-image-1-mini` (controle de texto) nas 5
  douradas; default do botão conforme aceite de OCR e preço.
- **M2 (opcional):** modo híbrido com `input_references` (SVG rasterizado como rascunho) —
  só se o M1 mostrar que o texto sem rascunho não atinge o aceite.

## 9. Decisões travadas (2026-11-27)

1. **Default = SVG** (fiel, grátis, offline). Imagem generativa só pelo botão **"Estilizar"**;
   se a API falhar ou o OCR reprovar, a UI mantém o SVG.
2. **Card do Pass1**: o mapa é uma seção do resumo técnico (`app.py:467-480`), com botão e
   intent `map` em `_run`. Não mexer em `src/ui/stages.py`/`copy.STAGES`.
3. **Nano Banana 2** (`google/gemini-3.1-flash-image`, ≈US$ 0,08) é a prioridade do M1;
   Recraft e gpt-image-1-mini entram como alternativas de custo/controle.

Ponto ainda em aberto (medido no M1): `quality=low` do gpt-image-1-mini entrega 1K legível?

## 10. Achados do M0 (2026-11-27)

Três coisas que só apareceram com o Pass1 real:

1. **`finish_reason=length` era ignorado** pelo `OpenRouterProvider`. O DeepSeek gastava os
   2.000 `max_tokens` em `reasoning` (`reasoning_tokens=2000`, `content` vazio ou JSON cortado)
   e o texto truncado voltava como sucesso — podendo envenenar o cache do Pass1/Pass2, não só
   o do mapa. Corrigido: truncamento agora é erro e cai no fallback.
2. **`reasoning.effort=none`** resolve o mapa e sai 4,5× mais barato (US$ 0,00018 vs 0,00135),
   com `finish_reason=stop` e JSON completo. Virou knob `MINDMAP_REASONING`.
3. **Heurístico não pode ser cacheado** (era `provider=heuristic cached=True` eterno). Agora só
   resultado de LLM grava cache, e cache legado heurístico é descartado.

Também: SVG com altura fixa cortava 5 ramos × 3 filhos — `viewBox` agora é dinâmico
(`H = max(900, conteúdo + rodapé)`).

## 11. Tela cheia e legibilidade (2026-11-27)

O mapa no card encolhia junto com a coluna: `width="100%"` num viewBox de 1200 px deixava os
rótulos com ~7 px. Correção em `src/ui/mindmap_view.py` (só apresentação; `src/mindmap.py`
intocado):

- **`embed(svg)`**: extrai `W×H` do `viewBox`, fixa o SVG no tamanho natural e envolve num
  `div` com `overflow:auto; max-height:70vh`. Em coluna estreita o mapa **rola** em vez de
  encolher.
- **`publish(svg, title)`**: grava `static/mind/<hash>.html|.svg` (poda por mtime) e a nova aba
  ocupa a viewport (`svg{height:calc(100vh - 96px)}`), com zoom próprio **− / + / Ajustar**
  (0,6–2,5), "Baixar SVG" e "Abrir original". Em telas <1280 px mantém `min-width:1200px` com
  rolagem, para não esmagar o texto.
- Tema: `data-theme` herdado do Streamlit + `prefers-color-scheme` de fallback; SVG usa
  `currentColor`, então segue claro/escuro.
- Sem static serving (`player.enabled()` falso): `publish` devolve `None`, o card mostra aviso
  e o download do SVG continua disponível — nunca levanta exceção.

## 12. Resultado do M1 (2026-11-27)

Provider de imagem (`src/image_provider.py`) + botão "🎨 Estilizar" implementados. Régua
`scripts/eval_images.py` (OCR via visão, recall dos rótulos esperados):

| Modelo | US$/img | Recall Q1 | Recall Q2 | Tempo | Veredito |
|---|---|---|---|---|---|
| `google/gemini-3.1-flash-image` (Nano Banana 2) | 0,067 | **100%** | **100%** | 8,5 s | **default recomendado** |
| `recraft/recraft-v4.1-flash-v2` | 0,007 | 92–95% | 57–67% | 2,5 s | opção barata (fallback) |
| `openai/gpt-image-1-mini` | 0,050 | 62% | 90% | 40 s | descartado (pior custo-benefício) |

Custo da avaliação: US$ 0,25 + 0,15 (reteste com teto de rótulos) ≈ US$ 0,40.
`IMAGE_MODEL` segue **vazio por default** (R$ 0); o `.env` local escolhe o modelo.

Achados técnicos:

1. **Recraft devolve WebP** mesmo com `response_format=b64_json` → provider sniffa
   PNG/JPEG/WebP por magic bytes, grava a extensão correta e confia nos bytes quando
   `media_type` divergir.
2. **21 rótulos é demais para o prompt.** O teto `IMAGE_MAX_LABELS=12` (título → ramos →
   filhos) subiu o Recraft de 57% para 67% e levou o Nano Banana a 100%, sem tocar no SVG
   (que continua com todos os nós).
3. **`google/gemini-3.1-flash` não existe** no OpenRouter; o OCR usa
   `google/gemini-3.1-flash-lite`.
4. `gpt-image-1-mini` custou **US$ 0,05** (não os 0,008 do catálogo) em `1K/medium`.

Pendências do M1: decidir o joelho `IMAGE_MAX_LABELS` (8/12/16) com mais perguntas e
avaliar o modo híbrido (`input_references` com o SVG rasterizado) — hoje o prompt é
text-only.
