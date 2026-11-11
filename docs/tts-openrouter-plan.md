# TTS via OpenRouter — plano de implementação

Data: 2026-10-06. Pesquisa base: 23 modelos em `/audio/speech`; shortlist PT-BR no chat de 06/10.
Princípio: Edge-TTS segue default grátis; OpenRouter-TTS é **upgrade selecionável** (nunca dependência).

## 1. Design (mesma interface, novo provider)

```
personas/*.yaml: tts_voice passa a aceitar IDs OpenRouter
      (ex. tecnico: "pt-BR-Pedro:MAI-Voice-2.1" | iniciante: "pt-BR-Luana:MAI-Voice-2.1")
                          |
src/tts_provider.py: class OpenRouterTTSProvider
  - POST /audio/speech {model, input, voice, response_format: mp3} via httpx (sem dep nova)
  - model default via env OPENROUTER_TTS_MODEL (default: microsoft/mai-voice-2.1)
  - fallback de modelo: gemini-3.8-flash-tts (confirmar PT-BR) -> fish s2.1-pro-free ($0, teste)
  - retorna (mp3, engine) igual aos demais — app.py não muda a chamada
                          |
Ordem de tentativa: Edge-TTS (grátis) -> OpenRouterTTS (pago) -> Piper (offline),
  com toggle na sidebar "Voz premium (OpenRouter)" p/ forçar/pular o pago.
```

## 2. Fatiamento de roteiro longo (obrigatório)

- Alguns modelos limitam input (ex. 3000 chars / 120s por request); roteiro 5-8min (~8-15k chars) **não cabe em 1 chamada**.
- `synthesize_long(text, voice, engine)`: quebra por parágrafo (respeita frase, alvo ~2500 chars/fatia),
  sintetiza cada fatia (cache por hash de CADA fatia — reuso entre roteiros!), concatena via ffmpeg
  (fallback: wave + `audioop`? não — exigir ffmpeg OU salvar fatias separadas + playlist m3u).
- Player/download recebem o MP3 final como hoje; debug pode listar N fatias + custo estimado.

## 3. Cache e custo

- Cache por `(TTS_VERSION|engine|model|voice|texto)` — fatias reutilizáveis; roteiro igual = R$0 na 2ª vez.
- `[llm-call]`-style: log `[tts-call] engine model voice chars estimado_R$` por fatia no terminal.
- Trava de segurança: `TTS_MAX_CHARS` (default ~15000) — acima disso, erro claro em vez de torrar crédito.
- Estimativa: roteiro 3000 chars no MAI ≈ $0,06–0,07; demo (3 áudios) < $0,25.

## 4. Vozes (verificar na implementação — catálogo muda)

- Primário: `microsoft/mai-voice-2.1` (6 vozes pt-BR explícitas; estilos `narrator`/`educational` via provider.options).
- Fallback: `google/gemini-3.8-flash-tts` (confirmar PT-BR na prática) → `fish-audio/s2.1-pro-free` ($0).
- Descarta p/ PT-BR: kokoro-82m (vozes EN), minimax (sem locale PT explícito).

## 5. Aceite

Status: **implementado** (2026-10-06) — evidências em `STATE.md` (`synthesize_premium`, `split_slices`, fallback Edge em `app.py`).

- [x] Toggle premium OFF = comportamento idêntico a hoje (Edge), zero gasto.
- [x] Toggle ON + key válida = MP3 via MAI, player + download funcionando, badge `via openrouter-tts`.
- [x] Roteiro longo (>1 fatia) concatena sem cliques; AppTest sem exceção (mock httpx ou cache).
- [x] Sem key/crédito: erro legível "sem crédito OpenRouter — caindo p/ Edge-TTS" (fallback, não exceção).
- [x] `.env.example` documenta `OPENROUTER_TTS_MODEL` (+ comentário de custo).

## 6. Fora de escopo (depois)

Clonagem de voz (`input_references`), streaming PCM realtime, avaliação MOS (nota 1-5 ouvindo douradas), SSML/style fino por trecho.
