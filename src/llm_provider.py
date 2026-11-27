"""Contrato comum para trocar de LLM grátis sem reescrever o app."""
import os
from abc import ABC, abstractmethod

from src import config


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        ...


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-3.6-flash"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model_name = model
        self.model = genai.GenerativeModel(model)
        # `system_instruction` só existe no construtor do SDK; cacheia por system.
        self._models: dict[str, object] = {}
        self._native_system = True

    def _model_for(self, system: str):
        if not self._native_system:
            return None
        model = self._models.get(system)
        if model is None:
            import google.generativeai as genai
            model = genai.GenerativeModel(self.model_name, system_instruction=system)
            self._models[system] = model
        return model

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        gen_cfg = {}
        if max_tokens:  # None/0 = deixa o default do modelo (comportamento antigo)
            gen_cfg["max_output_tokens"] = int(max_tokens)
        if config.LLM_TEMPERATURE is not None:
            gen_cfg["temperature"] = config.LLM_TEMPERATURE
        try:
            model = self._model_for(system)
        except Exception:  # SDK sem suporte: mantém a concatenação de antes
            model = None
        if model is not None:
            try:
                resp = model.generate_content(user, generation_config=gen_cfg or None)
                return resp.text
            except Exception as e:
                msg = str(e).lower()
                if not ("system_instruction" in msg or "invalid argument" in msg):
                    raise
                # Modelo/API recusou system_instruction: desliga e usa concatenação.
                self._native_system = False
                print(f"[llm-call] gemini sem system_instruction ({str(e)[:120]}) — "
                      f"usando concatenação.", flush=True)
        resp = self.model.generate_content(f"{system}\n\n{user}", generation_config=gen_cfg or None)
        return resp.text


class OpenRouterProvider(LLMProvider):
    """OpenRouter (OpenAI-compatible). Default `openrouter/free` = roteador de modelos grátis."""
    name = "openrouter"
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "openrouter/free"):
        self.api_key = api_key
        self.model = model
        self.model_name = model

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        import httpx
        payload = {"model": self.model, "max_tokens": max_tokens, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}]}
        if config.LLM_TEMPERATURE is not None:  # só envia se setado
            payload["temperature"] = config.LLM_TEMPERATURE
        r = httpx.post(self.URL, timeout=config.LLM_TIMEOUT, headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/books-to-audio",
            "X-Title": "Books to Audio (seminario)",
        }, json=payload)
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        # Modelos reasoning devolvem o pensamento em `reasoning` e a resposta em `content`.
        # Usa SÓ content (pensamento nunca vaza p/ tela); se vazio, falha p/ fallback.
        # (reasoning exclude:true quebra este modelo — content volta vazio. Não usar.)
        text = (msg.get("content") or "").strip()
        if not text.strip():
            raise RuntimeError(f"OpenRouter ({self.model}) devolveu conteúdo vazio: {str(msg)[:200]}")
        return text


class OpenCodeSubprocessProvider(LLMProvider):
    """Fallback experimental: chama `opencode run`. Frágil — usar só se free APIs falharem."""
    name = "opencode-subprocess"
    model_name = "opencode run"

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        import subprocess, textwrap
        prompt = textwrap.shorten(f"{system}\n\n{user}", width=config.LLM_PROMPT_CHARS)
        out = subprocess.run(["opencode", "run", prompt], capture_output=True, text=True,
                             timeout=config.LLM_TIMEOUT)
        if out.returncode != 0:
            raise RuntimeError(out.stderr[-2000:])
        return out.stdout


def build_chain(primary: str | None = None) -> list[LLMProvider]:
    """Cadeia de fallback a partir do `.env`: só entra provider com chave configurada.

    Ordem: LLM_PRIMARY (default `gemini`) primeiro, depois os demais com chave.
    `opencode-subprocess` entra por último (experimental).
    """
    from dotenv import load_dotenv
    load_dotenv()
    primary = (primary or os.getenv("LLM_PRIMARY", "gemini")).lower()
    candidates: dict[str, LLMProvider | None] = {
        "gemini": (GeminiProvider(os.environ["GEMINI_API_KEY"],
                                  os.getenv("GEMINI_MODEL", "gemini-3.6-flash"))
                   if os.getenv("GEMINI_API_KEY") else None),
        "openrouter": (OpenRouterProvider(os.environ["OPENROUTER_API_KEY"],
                                          os.getenv("OPENROUTER_MODEL", "openrouter/free"))
                       if os.getenv("OPENROUTER_API_KEY") else None),
        "opencode-subprocess": OpenCodeSubprocessProvider(),
    }
    chain = [candidates.pop(primary)] if primary in candidates else []
    chain += [p for p in candidates.values() if p is not None]
    return [p for p in chain if p is not None]


# Erros transitórios: vale retentar no MESMO provider antes de cair p/ o fallback.
_RETRY_NAMES = {
    "timeout", "timeoutexception", "connecttimeout", "readtimeout", "writetimeout",
    "pooltimeout", "connecterror", "remoteprotocolerror", "readerror", "transport",
    "transportor", "apiconnectionerror", "apitimeout", "serviceunavailable",
    "internalservererror", "deadlineexceeded", "resourceexhausted", "toomanyrequests",
    "retryerror", "servererror",
}
# Nunca retentar: credencial/contrato (cai direto p/ o fallback).
_NO_RETRY_STATUS = {400, 401, 403, 404, 422}


def _status_of(exc: Exception) -> int | None:
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None) if resp is not None else None
    if isinstance(status, int):
        return status
    for attr in ("status_code", "http_status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    code = getattr(exc, "code", None)  # google.api_core.exceptions
    if callable(code):
        try:
            code = code()
        except Exception:
            code = None
    for attr in ("value", "http_status", "code"):
        val = getattr(code, attr, None)
        if isinstance(val, int) and val != 0:
            return val
    return None


def _is_retryable(exc: Exception) -> bool:
    """Timeout / conexão / HTTP 5xx / 429 retentam; 401/403 e content vazio não."""
    status = _status_of(exc)
    if status is not None:
        return status == 429 or status >= 500
    names = {type(exc).__name__.lower(), type(exc).__mro__[1].__name__.lower()
             if len(type(exc).__mro__) > 1 else ""}
    msg = str(exc).lower()
    if any(n in _RETRY_NAMES for n in names if n):
        return True
    if "timeout" in msg or "timed out" in msg or "connection" in msg:
        return True
    if "429" in msg or "rate limit" in msg:
        return True
    if any(f"{s} " in msg or f" {s}" in msg for s in ("500", "502", "503", "504")):
        return True
    return False


def complete_with_fallback(system: str, user: str, max_tokens: int = 1500,
                           chain: list[LLMProvider] | None = None) -> tuple[str, str]:
    """Tenta cada provider em ordem; retorna (texto, nome_do_provider). Erro claro se todos falharem.

    Retry por provider: `config.LLM_RETRIES` tentativas extras, backoff 2s/5s, só em
    erro transitório (timeout/conexão/5xx/429). 401/403 e resposta vazia caem direto
    para o próximo provider.
    """
    import time
    errors: list[str] = []
    in_chars = len(system) + len(user)
    delays = (2.0, 5.0)
    attempts = 1 + max(0, config.LLM_RETRIES)
    for p in chain or build_chain():
        model = getattr(p, "model_name", getattr(p, "model", "?"))
        if not isinstance(model, str):
            model = getattr(model, "model_name", "?")
        for attempt in range(1, attempts + 1):
            t0 = time.time()
            try:
                text = p.complete(system, user, max_tokens)
                # Log p/ o terminal do servidor: visível em `streamlit run` e em scripts.
                print(f"[llm-call] provider={p.name} model={model} "
                      f"in={in_chars}ch(~{in_chars//4}tok) out={len(text)}ch(~{len(text)//4}tok) "
                      f"{time.time()-t0:.1f}s", flush=True)
                return text, p.name
            except Exception as e:
                print(f"[llm-call] provider={p.name} model={model} FALHOU "
                      f"({str(e)[-150:]})", flush=True)
                retry = attempt < attempts and _is_retryable(e)
                if not retry:
                    errors.append(f"{p.name}: {str(e)[-300:]}")
                    break
                delay = delays[min(attempt - 1, len(delays) - 1)]
                print(f"[llm-retry] provider={p.name} attempt={attempt}/{attempts} "
                      f"erro={str(e)[-120:]} espera={delay:.0f}s", flush=True)
                errors.append(f"{p.name}: {str(e)[-300:]}")
                time.sleep(delay)
    raise RuntimeError("Todos os LLM providers falharam. "
                       "Verifique GEMINI_API_KEY / OPENROUTER_API_KEY no .env. Detalhes: "
                       + " | ".join(errors))
