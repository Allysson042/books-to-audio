"""Microcopy do produto — fonte única de todo texto de interface (U0).

Regras de voz em `docs/UX/06-guia-visual.md` §7: direto, PT-BR, sentence case,
sem jargão de engenharia na tela principal.
"""

from __future__ import annotations

PAGE_TITLE = "Generative Deep Learning — Books to Audio"
PAGE_ICON = "🎧"  # placeholder até existir `assets/icon.png`
TITLE = "Generative Deep Learning"
SUBTITLE = "Pergunte, leia o resumo ou ouça o capítulo"

ASK_PLACEHOLDER = "Pergunte ou peça resumo de capítulo — ex: O que é ELBO em VAEs?"

EMPTY_TITLE = "O que você quer entender?"
EMPTY_HELP = "Escolha uma pergunta pronta ou digite a sua."
EMPTY_CHIPS = [
    "O que é ELBO em VAEs?",
    "Explique GANs vs Diffusion",
    "Resuma o Cap 4",
]

MAPA_MISSING = ("Mapa do livro ausente — rode a ingestão para habilitar o escopo "
                "por capítulo.")

SCOPE_ALL = "Livro todo"

PERSONA_LABELS = {"tecnico_direto": "Técnico", "iniciante_guiado": "Iniciante"}
STRATEGY_LABELS = {"vectorless": "sumário navegável", "vetorial": "busca semântica"}

# -- U2: header (escopo/persona) e popover de ajustes -------------------------
PERSONA_OPTIONS = {"Técnico": "tecnico_direto", "Iniciante": "iniciante_guiado"}
STRATEGY_OPTIONS = {"Sumário navegável": "vectorless", "Busca semântica": "vetorial"}

SCOPE_LABEL = "Onde buscar"
PERSONA_LABEL = "Explicar para"
ADVANCED_LABEL = "⚙ Ajustes"
STRATEGY_LABEL = "Como buscar"
RERANK_LABEL = "Reordenar resultados"
RERANK_HELP = "Reordena os trechos por relevância antes de resumir. Só na busca semântica."
IGNORE_CACHE_LABEL = "Ignorar cache (forçar nova geração)"
IGNORE_CACHE_HELP = "Desligado usa o que já foi gerado (instantâneo). Ligado gera tudo de novo."
PREMIUM_LABEL = "Voz premium · ≈US$0,06 por áudio"
PREMIUM_NO_KEY = ("Voz premium indisponível: falta `OPENROUTER_API_KEY`. "
                  "Geramos com a voz grátis (Edge).")
MAP_LABEL = "Mapa do livro ({n})"

AUDIO_DOWNLOAD = "Baixar áudio"
AUDIO_DISABLED = "Gerar áudio"

# -- U1: jornada linear (Pergunta → Fontes → Resumo → Roteiro → Áudio) --------
STAGES = ["Pergunta", "Fontes", "Resumo", "Roteiro", "Áudio"]

PASS1_TITLE = "RESUMO TÉCNICO"
PASS2_TITLE = "ROTEIRO FALADO"
AUDIO_TITLE = "ÁUDIO"

NEW_QUESTION = "↺ Nova pergunta"
RETRY = "Tentar de novo"
DETAILS = "Detalhes"
SOURCES_FAILED_TITLE = "FONTES INDISPONÍVEIS"
NOT_FOUND = "Nada neste escopo. Tente o livro todo."

BTN_LISTEN = "▶ Ouvir"
BTN_PASS1 = "Só o resumo técnico"
BTN_PASS2 = "Só o roteiro falado"
BTN_GEN_P1 = "Gerar resumo técnico"
BTN_GEN_P2 = "Gerar roteiro falado"
BTN_GEN_AUDIO = "Gerar áudio"
BTN_AUDIO_REGEN = "Regerar áudio"
REGERAR = "↻ Regerar"
REGERAR_HINT = "Regenera do zero — ignora o cache."

P1_EMPTY = "Ainda não gerado · ≈15 s"
P2_EMPTY = "Ainda não gerado · ≈20 s"
P2_WAITS_FOR_P1 = "Espera o resumo técnico · geramos junto"
AUDIO_EMPTY = "O áudio vem do roteiro falado."
AUDIO_ORPHAN = "O áudio exibido é de um roteiro anterior."
AUDIO_NOTICE_PREMIUM = "A voz premium não respondeu. Gerando com a voz grátis (Edge)."

PREMIUM_CONFIRM = "Confirmo o custo (~US$0,06 por áudio)"
PREMIUM_COST = "≈US$0,06 · voz premium"
PREMIUM_GATE = "Confirme o custo no rail antes de gerar o áudio pago."
FREE_COST = "grátis"
CHAIN_HINT = "resumo + roteiro + áudio"
RAIL_NEEDS_QUERY = "Faça uma pergunta para liberar as ações."

SEARCH_RUNNING_TREE = "Lendo o sumário…"
SEARCH_RUNNING_VECTOR = "Buscando os trechos…"
SEARCH_DONE = "Fontes prontas"
SEARCH_FAILED = "A busca falhou"

STEP_RESUMO = "Escrevendo o resumo…"
STEP_ROTEIRO = "Adaptando para fala…"
STEP_AUDIO = "Sintetizando o áudio…"
RUN_LABEL = {
    "listen": "Preparando o áudio…",
    "pass1": "Escrevendo o resumo…",
    "pass2": "Escrevendo o roteiro…",
    "audio": "Sintetizando o áudio…",
}
RUN_DONE = "Pronto"
RUN_FAILED = "Falhou"

# Erro = fato + 1 ação (§8 do guia). Detalhes técnicos ficam em expander.
STAGE_ERROR = {
    "fontes": "A busca não respondeu.",
    "resumo": "O resumo técnico não foi gerado.",
    "roteiro": "O roteiro falado não foi gerado.",
    "audio": "O áudio não foi gerado.",
}
STAGE_RETRY = {"fontes": "pass1", "resumo": "pass1", "roteiro": "pass2", "audio": "audio"}

# Rótulos humanos de provider: nada de `openrouter/free` ou `opencode-subprocess` na tela.
_PROVIDER_LABELS = {
    "gemini": "Gemini",
    "openrouter": "OpenRouter",
    "opencode-subprocess": "local",
}


def context_line(n_trechos: int, persona: str, strategy: str,
                 rerank: bool = False) -> str:
    """`10 trechos · sumário navegável · Técnico` (+ ` · reordenado` no vetorial)."""
    parts = [
        f"{n_trechos} trecho" if n_trechos == 1 else f"{n_trechos} trechos",
        STRATEGY_LABELS.get(strategy, strategy),
        PERSONA_LABELS.get(persona, persona),
    ]
    if strategy == "vetorial" and rerank:
        parts.append("reordenado")
    return " · ".join(parts)


def provenance(provider: str, cached: bool, chained: bool = False) -> str:
    """Proveniência honesta: cache manda na mensagem, provider só quando gera agora."""
    if cached:
        return "instantâneo · já gerado"
    if chained:
        return "gerado junto com o roteiro"
    name = _PROVIDER_LABELS.get((provider or "").strip().lower(), "")
    return f"gerado agora · {name}" if name else "gerado agora"


def audio_minutes(chars: int) -> float:
    """≈900 chars/min de fala em PT-BR (estimativa do guia §7)."""
    return round(max(chars, 0) / 900, 1)


def audio_label(chars: int) -> str:
    """`Gerar áudio (≈6 min)` — duração calculada, nunca '5-8min'."""
    return f"Gerar áudio (≈{audio_minutes(chars):g} min)"


def voice_name(voice: str) -> str:
    """`pt-BR-FranciscaNeural` → `Francisca`; `pt-BR-Luana:MAI-Voice-2.1` → `Luana`."""
    raw = (voice or "").split("-", 2)[-1].split(":")[0]
    return raw.replace("Neural", "") or voice


def audio_meta(chars: int, voice: str, premium: bool, engine: str = "") -> str:
    """`≈6 min · voz Francisca · Edge` (+ `instantâneo` quando veio do cache)."""
    if premium and str(engine).startswith("edge"):
        label = "Edge (fallback)"  # premium falhou e caiu para a voz grátis
    else:
        label = "premium" if premium else "Edge"
    parts = [f"≈{audio_minutes(chars):g} min", f"voz {voice_name(voice)}", label]
    if engine == "cache":
        parts.append("instantâneo")
    return " · ".join(parts)


# -- U3: fontes (citação, relevância, trecho) ---------------------------------
SEE_SNIPPET = "ver trecho"
MACRO_LABEL = "Abertura do capítulo · Cap {n}"
RELEVANCE_HINT = "relevância relativa nesta pergunta"
SEARCH_DETAILS = "Detalhes da busca"
THINKING_LABEL = "Raciocínio da navegação"
TYPE_LABELS = {
    "text": "texto",
    "code": "código",
    "caption": "legenda",
    "table": "tabela",
    "figure": "figura",
}


def sources_header(n: int, summary: str = "") -> str:
    """`Fontes (10) · Cap 4 · p.96–112` (resumo de 1 linha, colapsável)."""
    base = f"Fontes ({n})"
    return f"{base} · {summary}" if summary else base


# -- U4: sessão e histórico ---------------------------------------------------
SESSION_LABEL = "☰ Sessão"
SESSION_EMPTY = "Nenhuma pergunta nesta sessão."
SESSION_NEW = "Nova pergunta"
SESSION_EXPORT = "Exportar sessão (.md)"
SESSION_CLEAR = "Limpar sessão"
SESSION_CONFIRM = "Confirmar"
SESSION_CURRENT = "●"
SESSION_EXPORT_NAME = "gdl-sessao.md"
SESSION_TITLE = "Sessão"
TURN_PARTS = {"pass1": "resumo", "pass2": "roteiro", "mp3": "áudio"}

# Mapas reversos dos selects do header (o `session_state` guarda o label).
PERSONA_LABELS_BY_SLUG = {slug: label for label, slug in PERSONA_OPTIONS.items()}
STRATEGY_LABELS_BY_SLUG = {slug: label for label, slug in STRATEGY_OPTIONS.items()}

# Export `.md` (U4): cabeçalho e rótulos das seções.
EXPORT_TITLE = "# Sessão — Generative Deep Learning"
EXPORT_SOURCES = "### Fontes"
EXPORT_RESUMO = "### Resumo técnico"
EXPORT_ROTEIRO = "### Roteiro falado"

# -- U5: player dock e modo apresentação --------------------------------------
AUDIO_IN_DOCK = "Áudio pronto — player fixo acima da pergunta."
AUDIO_UNAVAILABLE = "Áudio indisponível — baixe o arquivo."
PRESENT_LABEL = "Modo apresentação"
PRESENT_HINT = "Modo apresentação · leitura ampliada, perguntas de exemplo abaixo"
PRESENT_EXIT = "Sair do modo apresentação"
DOCK_QUERY_CHARS = 48


def dock_meta(chars: int, voice: str, engine: str = "") -> str:
    """`≈6 min · voz Francisca · Edge` — título curto com a pergunta vem do app."""
    parts = [f"≈{audio_minutes(chars):g} min", f"voz {voice_name(voice)}"]
    if engine:
        parts.append(str(engine))
    return " · ".join(parts)