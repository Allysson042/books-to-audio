"""Contrato comum para trocar de LLM grátis sem reescrever o app."""
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        ...

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        resp = self.model.generate_content(f"{system}\n\n{user}")
        return resp.text

class OpenCodeSubprocessProvider(LLMProvider):
    """Fallback experimental: chama `opencode run`. Frágil — usar só se free APIs falharem."""
    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        import subprocess, textwrap
        prompt = textwrap.shorten(f"{system}\n\n{user}", width=12000)
        out = subprocess.run(["opencode", "run", prompt], capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError(out.stderr[-2000:])
        return out.stdout
