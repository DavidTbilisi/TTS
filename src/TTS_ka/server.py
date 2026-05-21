"""FastAPI HTTP server exposing TTS generation as a local REST service.

Install with::

    pip install TTS_ka[server]
    TTS_ka serve --port 7777

Endpoints
---------
* ``GET  /``          — basic health check (200 OK).
* ``GET  /voices``    — JSON list of available voices.
* ``POST /synthesize`` — body ``{"text": "...", "lang": "en", "voice": "..."}``;
  returns streamed ``audio/mpeg``.

When the ``TTS_API_TOKEN`` env var is set, every request must carry a
matching ``Authorization: Bearer <token>`` header or receive HTTP 401.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import asdict
from typing import Optional

from .constants import MAX_PARALLEL_WORKERS
from . import voices as _voices


class MissingExtraError(RuntimeError):
    """Raised when fastapi/uvicorn aren't installed."""

    def __init__(self) -> None:
        super().__init__(
            "TTS_ka serve requires 'fastapi' and 'uvicorn'. "
            "Install with: pip install TTS_ka[server]"
        )


def _check_token(authorization: Optional[str], expected: Optional[str]) -> bool:
    """Return True if the incoming Authorization header is acceptable."""
    if not expected:
        return True
    if not authorization:
        return False
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    return parts[1] == expected


def _generation_semaphore() -> "asyncio.Semaphore":
    """Module-level semaphore shared across requests to cap concurrent generation."""
    global _SEM
    if "_SEM" not in globals():
        _SEM = asyncio.Semaphore(MAX_PARALLEL_WORKERS)
    return _SEM


def create_app(token: Optional[str] = None):
    """Build the FastAPI app. Importing FastAPI is deferred so tests can mock it."""
    try:
        from fastapi import FastAPI, HTTPException, Header, Request
        from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse
    except ImportError:
        raise MissingExtraError()

    from .fast_audio import fast_generate_audio  # local import to avoid cycles

    app = FastAPI(title="TTS_ka", version="serve")
    token_value = token if token is not None else os.environ.get("TTS_API_TOKEN")

    def _auth_or_401(authorization: Optional[str]):
        if not _check_token(authorization, token_value):
            raise HTTPException(status_code=401, detail="invalid or missing token")

    @app.get("/", response_class=PlainTextResponse)
    async def root() -> str:
        return "TTS_ka serve OK"

    @app.get("/voices")
    async def list_voices(authorization: Optional[str] = Header(default=None)):
        _auth_or_401(authorization)
        return JSONResponse([asdict(v) for v in _voices.all_voices()])

    @app.post("/synthesize")
    async def synthesize(
        request: Request,
        authorization: Optional[str] = Header(default=None),
    ):
        _auth_or_401(authorization)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid JSON body")
        text = body.get("text", "")
        lang = body.get("lang", "en")
        voice = body.get("voice")
        if not text:
            raise HTTPException(status_code=400, detail="missing 'text'")
        if lang not in {"ka", "ru", "en"}:
            raise HTTPException(status_code=400, detail=f"invalid lang {lang!r}")
        if voice and _voices.get_voice(voice) is None:
            raise HTTPException(status_code=400, detail=f"unknown voice {voice!r}")

        sem = _generation_semaphore()

        async def stream_audio():
            async with sem:
                with tempfile.NamedTemporaryFile(
                    suffix=".mp3", delete=False
                ) as tmp:
                    out_path = tmp.name
                try:
                    ok = await fast_generate_audio(text, lang, out_path,
                                                    quiet=True, voice=voice)
                    if not ok:
                        return
                    with open(out_path, "rb") as f:
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    try:
                        os.remove(out_path)
                    except OSError:
                        pass

        return StreamingResponse(stream_audio(), media_type="audio/mpeg")

    return app


def run_server(host: str = "127.0.0.1", port: int = 7777,
                token: Optional[str] = None) -> None:
    """Start the uvicorn server. Blocks until interrupted."""
    try:
        import uvicorn
    except ImportError:
        raise MissingExtraError()
    app = create_app(token=token)
    uvicorn.run(app, host=host, port=port, log_level="info")
