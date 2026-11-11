"""S4 — TTS grátis: Edge-TTS primário + Piper fallback. Cache em disco.

Uso:
    from src.tts_provider import synthesize
    mp3 = synthesize(roteiro_pass2, voice="pt-BR-AntonioNeural")

Cache: `cache/audio/{sha256(TTS_VERSION|voice|texto)}.mp3` (+ sidecar .json).
Nunca re-sintetiza se o MP3 existir (custo R$0 + demo offline).

Premium (plano docs/tts-openrouter-plan.md): `synthesize_premium()` usa
POST /audio/speech do OpenRouter, fatiando roteiros longos (limite por request)
com cache por fatia + concat via ffmpeg. Trava `TTS_MAX_CHARS` anti-torra-crédito.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "audio"
CACHE.mkdir(parents=True, exist_ok=True)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
TTS_VERSION = "v1"  # bump p/ invalidar todo o cache de áudio

OPENROUTER_TTS_URL = "https://openrouter.ai/api/v1/audio/speech"
OPENROUTER_TTS_MODEL = os.getenv("OPENROUTER_TTS_MODEL", "microsoft/mai-voice-2.1")
TTS_SLICE_CHARS = 2500   # alvo por fatia (seguro p/ limites de ~3000 chars/request)
TTS_MAX_CHARS = 15000    # trava de custo: acima disso, erro em vez de torrar crédito


def _key(text: str, voice: str) -> str:
    return hashlib.sha256(f"{TTS_VERSION}|{voice}|{text}".encode()).hexdigest()[:16]


def _ckey(engine: str, model: str, voice: str, text: str) -> str:
    return hashlib.sha256(f"{TTS_VERSION}|{engine}|{model}|{voice}|{text}".encode()).hexdigest()[:16]


def split_slices(text: str, limit: int = TTS_SLICE_CHARS) -> list[str]:
    """Quebra por parágrafo/frase até ~limit chars (nunca corta no meio da frase)."""
    slices, cur = [], ""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(paras) <= 1:  # sem parágrafos: quebra por frase
        paras = re.split(r"(?<=[.!?])\s+", text.strip())
    for p in paras:
        if len(cur) + len(p) + 1 <= limit or not cur:
            cur = (cur + " " + p).strip()
        else:
            slices.append(cur)
            cur = p
    if cur:
        slices.append(cur)
    return slices


def _ffmpeg_exe() -> str:
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError("ffmpeg ausente p/ concatenar fatias de áudio. "
                           "Instale com: venv/bin/pip install imageio-ffmpeg")


def synth_openrouter(text: str, voice: str, model: str | None = None,
                     api_key: str | None = None, use_cache: bool = True) -> Path:
    """1 request TTS (texto curto). Retorna MP3 do cache ou sintetiza."""
    import httpx
    model = model or OPENROUTER_TTS_MODEL
    api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY ausente no .env.")
    key = _ckey("openrouter-tts", model, voice, text)
    out = CACHE / f"{key}.mp3"
    if use_cache and out.exists():
        return out
    # Gemini TTS só entrega PCM 24kHz mono — convertemos p/ mp3 (demais: mp3 direto).
    want_pcm = "gemini" in model.lower() and "tts" in model.lower()
    r = None
    for attempt in (1, 2):  # 1 retry: o provider às vezes devolve 400/500 transitório
        r = httpx.post(OPENROUTER_TTS_URL, timeout=300, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/books-to-audio",
            "X-Title": "Books to Audio (seminario)",
        }, json={"model": model, "input": clean_for_speech(text),
                 "voice": voice, "response_format": "pcm" if want_pcm else "mp3"})
        if r.status_code == 200 and "audio" in r.headers.get("Content-Type", ""):
            break
        print(f"[tts-call] engine=openrouter-tts tentativa {attempt} falhou "
              f"({r.status_code}): {r.text[:500]}", flush=True)
        if attempt == 1:
            import time
            time.sleep(5)
    if r.status_code != 200 or "audio" not in r.headers.get("Content-Type", ""):
        raise RuntimeError(f"OpenRouter TTS falhou ({r.status_code}): {r.text[:200]}")
    if want_pcm:
        pcm = out.with_suffix(".pcm")
        pcm.write_bytes(r.content)
        subprocess.run([_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "s16le",
                        "-ar", "24000", "-ac", "1", "-i", str(pcm),
                        "-c:a", "libmp3lame", str(out)], check=True, timeout=300)
        pcm.unlink(missing_ok=True)
    else:
        out.write_bytes(r.content)
    (CACHE / f"{key}.json").write_text(json.dumps({
        "voice": voice, "model": model, "chars": len(text), "engine": "openrouter-tts",
        "created": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False), encoding="utf-8")
    print(f"[tts-call] engine=openrouter-tts model={model} voice={voice} "
          f"chars={len(text)} bytes={len(r.content)}", flush=True)
    return out


def synthesize_premium(text: str, voice: str, model: str | None = None,
                       api_key: str | None = None,
                       use_cache: bool = True) -> tuple[Path, str, int]:
    """Roteiro (qualquer tamanho) via OpenRouter TTS. Retorna (mp3_final, engine, n_fatias)."""
    if len(text) > TTS_MAX_CHARS:
        raise RuntimeError(f"Roteiro com {len(text)} chars > TTS_MAX_CHARS={TTS_MAX_CHARS}. "
                           f"Aborte p/ não torrar crédito.")
    model = model or OPENROUTER_TTS_MODEL
    slices = split_slices(text)
    parts = [synth_openrouter(s, voice, model, api_key, use_cache) for s in slices]
    if len(parts) == 1:
        return parts[0], "openrouter-tts", 1
    key = _ckey("openrouter-tts-cat", model, voice, text)
    out = CACHE / f"{key}.mp3"
    if use_cache and out.exists():
        return out, "cache", len(parts)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("".join(f"file '{p}'\n" for p in parts))
        lst = f.name
    subprocess.run([_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat",
                    "-safe", "0", "-i", lst, "-c:a", "libmp3lame", str(out)],
                   check=True, timeout=600)
    return out, "openrouter-tts", len(parts)


def clean_for_speech(text: str) -> str:
    """Remove sobras de markdown que o LLM deixa no roteiro (lidas em voz alta)."""
    text = re.sub(r"(?m)^\s*#{1,4}\s*", "", text)          # ## Títulos
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)            # **negrito**
    text = re.sub(r"`(.+?)`", r"\1", text)                  # `código`
    text = re.sub(r"(?m)^\s*[-*]\s+", "", text)             # bullets
    text = re.sub(r"\[(GANCHO|IDEIA[^\]]*|FECHAMENTO[^\]]*)\]", r"\1.", text,
                  flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


async def synth_edge(text: str, voice: str = "pt-BR-FranciscaNeural",
                   use_cache: bool = True) -> Path:
    """Edge-TTS (online, primário). Retorna MP3 do cache ou sintetiza."""
    import edge_tts
    key = _key(text, voice)
    out = CACHE / f"{key}.mp3"
    if use_cache and out.exists():
        return out
    comm = edge_tts.Communicate(clean_for_speech(text), voice)
    await comm.save(str(out))
    (CACHE / f"{key}.json").write_text(json.dumps({
        "voice": voice, "chars": len(text), "engine": "edge-tts",
        "created": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False), encoding="utf-8")
    return out


def synth_piper(text: str, voice: str = "pt-BR-FranciscaNeural",
                model_path: str = "pt_BR-faber-medium", use_cache: bool = True) -> Path:
    """Piper local (offline, fallback). Exige binário `piper` + modelo no PATH/dir."""
    if not shutil.which("piper"):
        raise RuntimeError("Piper não instalado (binário `piper` ausente). "
                           "Instale p/ fallback offline ou use Edge-TTS online.")
    key = _key(text, voice)
    out = CACHE / f"{key}.mp3"
    if use_cache and out.exists():
        return out
    plain = clean_for_speech(text)
    # piper gera wav no stdout -> convertemos p/ mp3 se ffmpeg existir, senão wav
    wav = out.with_suffix(".wav")
    subprocess.run(["piper", "--model", model_path, "--output_file", str(wav)],
                   input=plain, text=True, check=True, timeout=600)
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-i", str(wav), str(out)], check=True, timeout=300)
        wav.unlink(missing_ok=True)
        return out
    return wav


def synthesize(text: str, voice: str = "pt-BR-FranciscaNeural",
               use_cache: bool = True) -> tuple[Path, str]:
    """Caminho sync p/ o app: Edge-TTS, com Piper como fallback. Retorna (mp3, engine)."""
    key = _key(text, voice)
    out = CACHE / f"{key}.mp3"
    if use_cache and out.exists():
        return out, "cache"
    try:
        return asyncio.run(synth_edge(text, voice, use_cache)), "edge-tts"
    except Exception as e:
        try:
            return synth_piper(text, voice, use_cache=use_cache), "piper"
        except Exception:
            raise RuntimeError(f"Edge-TTS falhou ({str(e)[-200:]}) e Piper indisponível. "
                               f"Verifique a internet ou pré-gere o kit demo (S5).")
