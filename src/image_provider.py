"""M1 — imagem generativa: `POST /api/v1/images` do OpenRouter. Cache em disco.

Espelha `src/tts_provider.py` (HTTP puro com httpx, retry, sidecar .json). O SVG do
mapa mental (`src/mindmap.py`) continua sendo o default fiel e grátis; esta imagem é
**adicional** e só é gerada pelo botão "Estilizar" da UI.

Default R$ 0: `IMAGE_MODEL` vazio desliga o renderer (ver `src/config.py`).

Uso:
    from src import image_provider
    path, meta = image_provider.generate(prompt)     # usa IMAGE_MODEL do .env
    image_provider.enabled()

Cache: `cache/images/{sha256(IMAGE_VERSION|model|aspect|resolution|quality|prompt)[:16]}`
com a extensão real do conteúdo (`.png`, `.jpg` ou `.webp`) + sidecar `.json` com
`usage.cost`, `media_type`, `bytes` e `path`. `response_format="b64_json"` sempre:
a URL assinada expira em 24 h e não serve como cache.

Nem todo modelo honra o PNG: `recraft/recraft-v4.1-flash-v2` devolve WebP mesmo com
`response_format=b64_json`. Por isso o formato é detectado pelos **magic bytes**
(`data[0].media_type` só confirma; divergência → vale o byte e sai aviso).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from src import config

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "images"
CACHE.mkdir(parents=True, exist_ok=True)
try:  # chave no `.env` também para scripts fora do Streamlit
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover - dotenv é obrigatório no requirements
    pass

OPENROUTER_IMAGES_URL = "https://openrouter.ai/api/v1/images"
IMAGE_VERSION = config.IMAGE_VERSION or "v1"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
# media_type (como devolvido pelo provider) → extensão no disco
_EXT_BY_TYPE = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
_KNOWN_EXTS = tuple(dict.fromkeys(_EXT_BY_TYPE.values()))
_BACKOFF = (2, 5)  # segundos entre tentativas (1ª e 2ª), como o restante do projeto
_OPTIONAL_KEYS = ("aspect_ratio", "resolution", "quality")


def _norm(value) -> str | None:
    """`""`/None viram None (parâmetro omitido do payload e da chave de cache)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sniff_type(raw: bytes) -> str | None:
    """Formato real pelos magic bytes: PNG/JPEG/WebP (ou None se desconhecido)."""
    if raw.startswith(PNG_MAGIC):
        return "image/png"
    if raw.startswith(JPEG_MAGIC):
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def enabled(api_key: str | None = None) -> bool:
    """Só há botão "Estilizar" com chave E modelo configurados (senão: custo zero)."""
    key = _norm(api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY"))
    return bool(key) and bool(_norm(config.IMAGE_MODEL))


def _cache_key(model: str, aspect: str | None, resolution: str | None,
               quality: str | None, prompt: str) -> str:
    raw = f"{IMAGE_VERSION}|{model}|{aspect}|{resolution}|{quality}|{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_payload(model: str, prompt: str, *, aspect: str | None,
                   resolution: str | None, quality: str | None) -> dict:
    payload = {"model": model, "prompt": prompt, "response_format": "b64_json", "n": 1}
    for key, value in (("aspect_ratio", aspect), ("resolution", resolution),
                       ("quality", quality)):
        if value:
            payload[key] = value
    return payload


def _post(api_key: str, payload: dict):
    import httpx
    return httpx.post(
        OPENROUTER_IMAGES_URL,
        timeout=config.IMAGE_TIMEOUT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/books-to-audio",
            "X-Title": "Books to Audio (seminario)",
        },
        json=payload,
    )


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def _is_transport_error(exc: Exception) -> bool:
    import httpx
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _http_error(resp) -> str:
    status = resp.status_code
    body = (getattr(resp, "text", "") or "")[:300]
    if status in (402, 403):
        return (f"OpenRouter Images recusou o pagamento (HTTP {status}): sem saldo ou "
                f"limite de gasto. Nada foi cobrado. Ajuste o crédito em "
                f"openrouter.ai/credits. Detalhe: {body}")
    return f"OpenRouter Images falhou (HTTP {status}). Detalhe: {body}"


def _extract_image(resp) -> tuple[bytes, float | None, str]:
    """Decodifica o b64, detecta o formato real e devolve `(bytes, custo, media_type)`.

    `data[0].media_type` é só confirmação: o byte manda (há modelo que declara PNG e
    devolve WebP). Divergência gera aviso no log, nunca exceção.
    """
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError("A resposta da imagem não é JSON válido.") from None
    items = data.get("data") if isinstance(data, dict) else None
    item = items[0] if isinstance(items, list) and items else {}
    b64 = item.get("b64_json") if isinstance(item, dict) else None
    if not b64:
        raise RuntimeError("A resposta da imagem veio sem b64_json.")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError):
        raise RuntimeError("b64_json inválido na resposta da imagem.") from None
    media_type = _sniff_type(raw)
    if media_type is None:
        raise RuntimeError(
            "A resposta da imagem tem formato desconhecido (os bytes não são PNG, "
            f"JPEG nem WebP): {raw[:12]!r}.")
    declared = _norm(item.get("media_type"))
    if declared:
        declared = declared.split(";")[0].strip().lower()
        if declared != media_type:
            print(f"[image-warn] media_type declarado={declared} != bytes={media_type}; "
                  f"usando {media_type}", flush=True)
    cost = None
    if isinstance(data, dict):
        usage = data.get("usage") or {}
        if isinstance(usage, dict) and isinstance(usage.get("cost"), (int, float)):
            cost = float(usage["cost"])
    return raw, cost, media_type


def _write_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)


def _read_sidecar(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cached_file(key: str, side: dict) -> Path | None:
    """Caminho do arquivo cacheado: o `path` do sidecar manda; senão, varre extensões."""
    recorded = _norm(side.get("path"))
    if recorded:
        cand = Path(recorded)
        if cand.is_file():
            return cand
    for ext in _KNOWN_EXTS:
        cand = CACHE / f"{key}{ext}"
        if cand.is_file():
            return cand
    return None


def generate(prompt: str, *, model: str | None = None,
             aspect_ratio: str | None = None, resolution: str | None = None,
             quality: str | None = None, use_cache: bool = True,
             api_key: str | None = None) -> tuple[Path, dict]:
    """Gera (ou lê do cache) uma imagem a partir do prompt.

    `meta` = `{"model","cost","cached","seconds","bytes","path","media_type"}`. Cache
    hit não faz HTTP e resolve o arquivo pelo `path` gravado no sidecar. `use_cache=False`
    pula a leitura e sempre escreve. Falha nunca deixa arquivo parcial: grava em tmp e
    só publica depois de detectar o formato.
    """
    model = _norm(model) or _norm(config.IMAGE_MODEL)
    if not model:
        raise RuntimeError("IMAGE_MODEL vazio: renderer de imagem desligado. "
                           "Defina IMAGE_MODEL no .env para usar o botão Estilizar.")
    prompt = str(prompt or "").strip()
    if not prompt:
        raise RuntimeError("Prompt de imagem vazio.")
    aspect = _norm(aspect_ratio) if aspect_ratio is not None else _norm(config.IMAGE_ASPECT)
    resolution = (_norm(resolution) if resolution is not None
                  else _norm(config.IMAGE_RESOLUTION))
    quality = _norm(quality) if quality is not None else _norm(config.IMAGE_QUALITY)

    key = _cache_key(model, aspect, resolution, quality, prompt)
    side = CACHE / f"{key}.json"

    if use_cache:
        side_data = _read_sidecar(side)
        out = _cached_file(key, side_data)
        if out is not None:
            raw_head = out.read_bytes()[:16]
            media_type = _norm(side_data.get("media_type")) or _sniff_type(raw_head)
            meta = {"model": model, "cost": None, "cached": True, "seconds": 0.0,
                    "bytes": out.stat().st_size, "path": str(out),
                    "media_type": media_type or "image/png"}
            if _norm(side_data.get("model")):
                meta["model"] = str(side_data["model"])
            if isinstance(side_data.get("cost"), (int, float)):
                meta["cost"] = float(side_data["cost"])
            print(f"[image-call] model={model} aspect={aspect or '-'} "
                  f"res={resolution or '-'} quality={quality or '-'} "
                  f"cost=${meta['cost']} s=0.0 cached=True", flush=True)
            return out, meta

    api_key = _norm(api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY"))
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY ausente no .env: não é possível gerar imagem.")

    full = _build_payload(model, prompt, aspect=aspect, resolution=resolution,
                          quality=quality)
    payload = full
    attempts = 1 + max(0, int(config.IMAGE_RETRIES))
    attempt = 0
    fallback_done = False
    resp = None
    t0 = time.time()

    while attempt < attempts:
        attempt += 1
        try:
            resp = _post(api_key, payload)
        except Exception as exc:  # noqa: BLE001 - timeout/conexão viram RuntimeError claro
            if _is_transport_error(exc) and attempt < attempts:
                time.sleep(_BACKOFF[min(attempt - 1, len(_BACKOFF) - 1)])
                continue
            raise RuntimeError(
                f"OpenRouter Images não respondeu ({type(exc).__name__}). "
                f"Verifique a conexão e tente de novo.") from None
        if resp.status_code == 200:
            break
        # 400/422: alguns modelos recusam aspect_ratio/resolution/quality → repete
        # UMA vez só com model+prompt+response_format.
        if resp.status_code in (400, 422) and not fallback_done:
            fallback_done = True
            payload = {k: v for k, v in full.items() if k not in _OPTIONAL_KEYS}
            continue
        if _retryable(resp.status_code) and attempt < attempts:
            time.sleep(_BACKOFF[min(attempt - 1, len(_BACKOFF) - 1)])
            continue
        raise RuntimeError(_http_error(resp))

    if resp is None or resp.status_code != 200:
        raise RuntimeError(_http_error(resp) if resp is not None
                           else "OpenRouter Images não respondeu.")

    raw, cost, media_type = _extract_image(resp)
    out = CACHE / f"{key}{_EXT_BY_TYPE[media_type]}"
    _write_atomic(out, raw)
    seconds = round(time.time() - t0, 2)
    meta = {"model": model, "cost": cost, "cached": False, "seconds": seconds,
            "bytes": len(raw), "path": str(out), "media_type": media_type}
    side.write_text(json.dumps({**meta, "version": IMAGE_VERSION,
                                "created": datetime.now(timezone.utc).isoformat()},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[image-call] model={model} aspect={aspect or '-'} "
          f"res={resolution or '-'} quality={quality or '-'} "
          f"cost=${cost} s={seconds} cached=False", flush=True)
    return out, meta


# -- self-test offline --------------------------------------------------------
_DEMO_OUTLINE = {
    "titulo": "VAEs e o ELBO",
    "ramos": [
        {"rotulo": "Objetivo", "filhos": ["latent space", "reconstrução"]},
        {"rotulo": "Trade-off", "filhos": ["fidelidade", "regularização"]},
        {"rotulo": "Loss", "filhos": ["ELBO", "divergência KL"]},
    ],
    "citacoes": ["Cap 3, p. 71", "Cap 3, p. 74"],
}


def _selftest() -> int:
    """Exercita HTTP/cache/erros com `httpx.post` monkeypatchado (sem rede)."""
    import shutil
    import tempfile

    import httpx

    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        print(("OK   " if cond else "FAIL ") + msg)
        ok = ok and cond

    def resp(status: int, body: dict) -> httpx.Response:
        req = httpx.Request("POST", OPENROUTER_IMAGES_URL)
        return httpx.Response(status, json=body, request=req)

    tiny_png = PNG_MAGIC + b"\x00" * 16
    b64_png = base64.b64encode(tiny_png).decode()
    # WebP 1×1 real (VP8 lossy): RIFF + tamanho + "WEBP" — o que o Recraft devolve.
    tiny_webp = base64.b64decode(
        "UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAwA0JaQAA3AA/vuUAAA=")
    b64_webp = base64.b64encode(tiny_webp).decode()

    def image_body(cost: float = 0.007) -> dict:
        return {"data": [{"b64_json": b64_png, "media_type": "image/png"}],
                "usage": {"cost": cost}}

    global CACHE
    old_cache = CACHE
    tmpdir = Path(tempfile.mkdtemp(prefix="gdl-img-selftest-"))
    CACHE = tmpdir
    real_post, real_sleep = httpx.post, time.sleep
    slept: list[float] = []
    time.sleep = lambda s: slept.append(s)  # type: ignore[assignment]
    try:
        # (a) 200 → grava, lê custo; 2ª chamada é cache hit sem POST.
        calls: list[dict] = []

        def ok_post(url, **kwargs):
            calls.append(kwargs.get("json") or {})
            return resp(200, image_body())

        httpx.post = ok_post
        p1, m1 = generate("selftest a", model="test/model", use_cache=True,
                          api_key="fake-key")
        check(p1.exists() and p1.suffix == ".png" and p1.read_bytes() == tiny_png,
              "(a) PNG gravado no cache com extensão .png")
        check(m1["cost"] == 0.007 and m1["cached"] is False,
              "(a) meta.cost lido de usage.cost")
        check(m1.get("media_type") == "image/png", "(a) meta.media_type=image/png")
        check(calls and calls[0].get("response_format") == "b64_json"
              and calls[0].get("n") == 1, "(a) payload usa b64_json e n=1")
        p2, m2 = generate("selftest a", model="test/model", use_cache=True,
                          api_key="fake-key")
        check(len(calls) == 1 and m2["cached"] is True and p2 == p1,
              "(a) 2ª chamada vem do cache sem POST")

        # (a2) WebP (como o Recraft devolve) → grava .webp, media_type correto e
        # o cache hit acha o arquivo pelo `path` do sidecar (não assume .png).
        def webp_post(url, **kwargs):
            return resp(200, {"data": [{"b64_json": b64_webp, "media_type": "image/webp"}],
                              "usage": {"cost": 0.007}})

        httpx.post = webp_post
        pw, mw = generate("selftest webp", model="test/model", api_key="fake-key")
        check(pw.exists() and pw.suffix == ".webp" and pw.read_bytes() == tiny_webp,
              "(a2) WebP gravado com extensão .webp (bytes intactos)")
        check(mw.get("media_type") == "image/webp" and mw["bytes"] == len(tiny_webp),
              "(a2) meta.media_type=image/webp e meta.bytes")
        side_data = json.loads(pw.with_suffix(".json").read_text(encoding="utf-8"))
        check(side_data.get("media_type") == "image/webp"
              and side_data.get("bytes") == len(tiny_webp)
              and Path(side_data.get("path", "")) == pw,
              "(a2) sidecar grava media_type, bytes e path")
        pw2, mw2 = generate("selftest webp", model="test/model", api_key="fake-key")
        check(pw2 == pw and mw2["cached"] is True and mw2.get("media_type") == "image/webp",
              "(a2) 2ª chamada: cache hit no .webp via sidecar")

        # (a3) media_type declarado mente (PNG) mas os bytes são WebP → vale o byte.
        def lying_post(url, **kwargs):
            return resp(200, {"data": [{"b64_json": b64_webp, "media_type": "image/png"}],
                              "usage": {"cost": 0.007}})

        httpx.post = lying_post
        pl, ml = generate("selftest mentira", model="test/model", api_key="fake-key")
        check(pl.suffix == ".webp" and ml.get("media_type") == "image/webp",
              "(a3) media_type divergente: bytes mandam (aviso no log)")

        # (b) 402 → RuntimeError sem retry (saldo/limite).
        calls_402: list[dict] = []

        def pay_post(url, **kwargs):
            calls_402.append(kwargs.get("json") or {})
            return resp(402, {"error": {"message": "insufficient credits"}})

        httpx.post = pay_post
        try:
            generate("selftest b", model="test/model", api_key="fake-key")
            check(False, "(b) 402 levanta RuntimeError")
        except RuntimeError as exc:
            check("402" in str(exc) and "saldo" in str(exc),
                  "(b) 402 levanta RuntimeError com mensagem de saldo")
        check(len(calls_402) == 1, "(b) 402 não retenta (1 POST)")

        # (c) 500 depois 200 → 2 POSTs, sucesso.
        calls_500: list[dict] = []

        def flaky_post(url, **kwargs):
            calls_500.append(kwargs.get("json") or {})
            if len(calls_500) == 1:
                return resp(500, {"error": {"message": "transient"}})
            return resp(200, image_body(0.01))

        httpx.post = flaky_post
        p3, m3 = generate("selftest c", model="test/model", api_key="fake-key")
        check(len(calls_500) == 2 and p3.exists() and m3["cost"] == 0.01,
              "(c) 500→200: 2 POSTs e sucesso")
        check(slept and slept[0] == 2, "(c) backoff de 2 s entre as tentativas")

        # (d) 400 com parâmetros → repete UMA vez sem eles e sucede.
        calls_400: list[dict] = []

        def param_post(url, **kwargs):
            calls_400.append(kwargs.get("json") or {})
            if len(calls_400) == 1:
                return resp(400, {"error": {"message": "unsupported parameter"}})
            return resp(200, image_body())

        httpx.post = param_post
        generate("selftest d", model="test/model", aspect_ratio="4:3",
                 resolution="1K", quality="medium", api_key="fake-key")
        first, second = calls_400[0], calls_400[-1]
        check(len(calls_400) == 2, "(d) 400 repete uma vez (2 POSTs)")
        check(all(k in first for k in _OPTIONAL_KEYS)
              and not any(k in second for k in _OPTIONAL_KEYS),
              "(d) 2º POST vai sem aspect/resolution/quality")
        check(second.get("model") == "test/model" and second.get("prompt") == "selftest d",
              "(d) model+prompt preservados no retry")

        # (e) formato realmente desconhecido → RuntimeError e nada é gravado.
        before = set(CACHE.iterdir())

        def bad_post(url, **kwargs):
            return resp(200, {"data": [{"b64_json": base64.b64encode(b"not-an-image").decode()}]})

        httpx.post = bad_post
        try:
            generate("selftest e", model="test/model", api_key="fake-key")
            check(False, "(e) formato desconhecido levanta RuntimeError")
        except RuntimeError as exc:
            check("desconhecido" in str(exc), "(e) formato desconhecido levanta RuntimeError")
        check(set(CACHE.iterdir()) == before, "(e) falha de validação não grava arquivo")
    finally:
        httpx.post, time.sleep = real_post, real_sleep
        CACHE = old_cache
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("SELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="M1 — imagem generativa (OpenRouter).")
    parser.add_argument("--live", action="store_true",
                        help="chama a API de verdade (custa por imagem)")
    parser.add_argument("--model", default=None, help="sobrescreve IMAGE_MODEL")
    parser.add_argument("--prompt", default=None, help="sobrescreve o prompt de exemplo")
    args = parser.parse_args(argv)

    if not args.live:
        return _selftest()

    from src.mindmap import outline_to_prompt

    model = _norm(args.model) or _norm(config.IMAGE_MODEL)
    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY ausente no .env — nada gerado (custo R$ 0).")
        return 0
    if not model:
        print("IMAGE_MODEL vazio (ou --model) — renderer desligado (custo R$ 0).")
        return 0
    prompt = args.prompt or outline_to_prompt(_DEMO_OUTLINE,
                                              config.IMAGE_ASPECT or "4:3")
    try:
        path, meta = generate(prompt, model=model)
    except RuntimeError as exc:
        print(f"ERRO: {exc}")
        return 1
    print(f"Imagem: {path}")
    print(f"Custo: US$ {meta['cost']} · {meta['seconds']}s · "
          f"{meta['bytes']} bytes · cached={meta['cached']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
