"""S4 — TTS grátis: Edge-TTS primário + Piper fallback. Cache em disco.

Uso:
    from src.tts_provider import synthesize
    mp3 = synthesize(roteiro_pass2, voice="pt-BR-AntonioNeural")

Cache: `cache/audio/{sha256(TTS_VERSION|voice|texto)}.mp3` (+ sidecar .json).
Nunca re-sintetiza se o MP3 existir (custo R$0 + demo offline).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "audio"
CACHE.mkdir(parents=True, exist_ok=True)
TTS_VERSION = "v1"  # bump p/ invalidar todo o cache de áudio


def _key(text: str, voice: str) -> str:
    return hashlib.sha256(f"{TTS_VERSION}|{voice}|{text}".encode()).hexdigest()[:16]


def clean_for_speech(text: str) -> str:
    """Remove sobras de markdown que o LLM deixa no roteiro (lidas em voz alta)."""
    text = re.sub(r"(?m)^\s*#{1,4}\s*", "", text)          # ## Títulos
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)            # **negrito**
    text = re.sub(r"`(.+?)`", r"\1", text)                  # `código`
    text = re.sub(r"(?m)^\s*[-*]\s+", "", text)             # bullets
    text = re.sub(r"\[(GANCHO|IDEIA[^\]]*|FECHAMENTO[^\]]*)\]", r"\1.", text,
                  flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


async def synth_edge(text: str, voice: str = "pt-BR-FranciscaNeural") -> Path:
    """Edge-TTS (online, primário). Retorna MP3 do cache ou sintetiza."""
    import edge_tts
    key = _key(text, voice)
    out = CACHE / f"{key}.mp3"
    if out.exists():
        return out
    comm = edge_tts.Communicate(clean_for_speech(text), voice)
    await comm.save(str(out))
    (CACHE / f"{key}.json").write_text(json.dumps({
        "voice": voice, "chars": len(text), "engine": "edge-tts",
        "created": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False), encoding="utf-8")
    return out


def synth_piper(text: str, voice: str = "pt-BR-FranciscaNeural",
                model_path: str = "pt_BR-faber-medium") -> Path:
    """Piper local (offline, fallback). Exige binário `piper` + modelo no PATH/dir."""
    if not shutil.which("piper"):
        raise RuntimeError("Piper não instalado (binário `piper` ausente). "
                           "Instale p/ fallback offline ou use Edge-TTS online.")
    key = _key(text, voice)
    out = CACHE / f"{key}.mp3"
    if out.exists():
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


def synthesize(text: str, voice: str = "pt-BR-FranciscaNeural") -> tuple[Path, str]:
    """Caminho sync p/ o app: Edge-TTS, com Piper como fallback. Retorna (mp3, engine)."""
    key = _key(text, voice)
    out = CACHE / f"{key}.mp3"
    if out.exists():
        return out, "cache"
    try:
        return asyncio.run(synth_edge(text, voice)), "edge-tts"
    except Exception as e:
        try:
            return synth_piper(text, voice), "piper"
        except Exception:
            raise RuntimeError(f"Edge-TTS falhou ({str(e)[-200:]}) e Piper indisponível. "
                               f"Verifique a internet ou pré-gere o kit demo (S5).")
