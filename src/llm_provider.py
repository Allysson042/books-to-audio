"""Contrato comum para trocar de LLM grátis sem reescrever o app."""
import os
from abc import ABC, abstractmethod

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
    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        resp = self.model.generate_content(f"{system}\n\n{user}")
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
        r = httpx.post(self.URL, timeout=120, headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/books-to-audio",
            "X-Title": "Books to Audio (seminario)",
        }, json={"model": self.model, "max_tokens": max_tokens, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}]})
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        # Router grátis pode devolver modelo de reasoning (content null) — usa o reasoning ou falha p/ fallback.
        text = msg.get("content") or msg.get("reasoning") or ""
        if not text.strip():
            raise RuntimeError(f"OpenRouter ({self.model}) devolveu conteúdo vazio: {str(msg)[:200]}")
        return text

class OpenCodeSubprocessProvider(LLMProvider):
    """Fallback experimental: chama `opencode run`. Frágil — usar só se free APIs falharem."""
    name = "opencode-subprocess"
    model_name = "opencode run"

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        import subprocess, textwrap
        prompt = textwrap.shorten(f"{system}\n\n{user}", width=12000)
        out = subprocess.run(["opencode", "run", prompt], capture_output=True, text=True, timeout=120)
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


def complete_with_fallback(system: str, user: str, max_tokens: int = 1500,
                           chain: list[LLMProvider] | None = None) -> tuple[str, str]:
    """Tenta cada provider em ordem; retorna (texto, nome_do_provider). Erro claro se todos falharem."""
    import time
    errors: list[str] = []
    in_chars = len(system) + len(user)
    for p in chain or build_chain():
        model = getattr(p, "model_name", getattr(p, "model", "?"))
        if not isinstance(model, str):
            model = getattr(model, "model_name", "?")
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
            errors.append(f"{p.name}: {str(e)[-300:]}")
    raise RuntimeError("Todos os LLM providers falharam. "
                       "Verifique GEMINI_API_KEY / OPENROUTER_API_KEY no .env. Detalhes: "
                       + " | ".join(errors))
