"""TTS grátis: Edge-TTS primário + Piper fallback. Cache em disco."""
from pathlib import Path
import hashlib

CACHE = Path("cache/audio"); CACHE.mkdir(parents=True, exist_ok=True)

def _key(text: str, voice: str) -> str:
    return hashlib.sha256(f"{voice}::{text}".encode()).hexdigest()[:16]

async def synth_edge(text: str, voice: str = "pt-BR-FranciscaNeural") -> Path:
    import edge_tts
    key = _key(text, voice)
    out = CACHE / f"{key}.mp3"
    if out.exists():
        return out
    comm = edge_tts.Communicate(text, voice)
    await comm.save(str(out))
    return out

def synth_piper(text: str, model_path: str = "pt_BR-faber-medium") -> Path:
    # TODO S4: integrar piper-tts local como fallback offline
    raise NotImplementedError("Conectar piper no Sprint 4")
