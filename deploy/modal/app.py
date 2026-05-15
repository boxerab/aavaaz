"""Aavaaz — Modal GPU serverless transcription with web demo.

Deploy with:
    modal deploy app.py

Develop with live-reload:
    modal serve app.py

Visit the root URL to access the drag-and-drop transcription demo.
POST to /v1/audio/transcriptions for the OpenAI-compatible API.

Environment variables (set via Modal Secrets):
    AAVAAZ_MODEL          Whisper model name (default: large-v3)
    AAVAAZ_LANGUAGE       Language code, or empty for auto-detect
    AAVAAZ_OUTPUT_FORMAT  json | text | srt | vtt (default: json)
    AAVAAZ_ENABLE_PII     1 to enable PII redaction (default: 0)
    AAVAAZ_ENABLE_FORMAT  1 to enable smart formatting (default: 1)
    AAVAAZ_API_KEY        Optional API key for authentication
"""

from __future__ import annotations

import modal

WHISPER_MODEL = "large-v3"

# Path to the web UI files inside the container.
WEB_DIR = "/web"

app = modal.App("aavaaz-transcribe")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install(
        "faster-whisper>=1.0",
        "fastapi[standard]",
        "python-multipart",
    )
    .run_commands(
        f"python -c \"from faster_whisper import WhisperModel; WhisperModel('{WHISPER_MODEL}', device='cpu')\""
    )
    .add_local_dir("../../aavaaz/web", remote_path=WEB_DIR)
    .add_local_dir("../../aavaaz/aavaaz", remote_path="/root/aavaaz_pkg/aavaaz")
    .add_local_file("../../pyproject.toml", remote_path="/root/aavaaz_pkg/pyproject.toml")
    .run_commands("pip install /root/aavaaz_pkg")
)


@app.cls(
    image=image,
    gpu="T4",
    timeout=600,
    secrets=[modal.Secret.from_name("aavaaz-config", required_hint=False)],
    container_idle_timeout=120,
)
@modal.concurrent(max_inputs=4)
class Transcriber:
    @modal.enter()
    def load_model(self):
        import os

        from faster_whisper import WhisperModel

        model_name = os.environ.get("AAVAAZ_MODEL", WHISPER_MODEL)
        self.model = WhisperModel(model_name, device="cuda", compute_type="float16")
        self.language = os.environ.get("AAVAAZ_LANGUAGE") or None
        self.api_key = os.environ.get("AAVAAZ_API_KEY")

    @modal.asgi_app()
    def web(self):
        import os

        import fastapi
        from fastapi.responses import HTMLResponse
        from fastapi.staticfiles import StaticFiles

        web_app = fastapi.FastAPI(title="Aavaaz Transcription Demo")

        # Serve static assets (logo, etc.)
        web_app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @web_app.get("/", response_class=HTMLResponse)
        async def index():
            index_path = os.path.join(WEB_DIR, "index.html")
            with open(index_path) as f:
                return f.read()

        @web_app.post("/v1/audio/transcriptions")
        async def transcribe(request: fastapi.Request):
            return await self._handle_transcription(request)

        @web_app.get("/health")
        async def health():
            return {"status": "ok"}

        return web_app

    async def _handle_transcription(self, request):
        import os
        import tempfile
        import uuid
        from pathlib import Path

        import fastapi

        # Auth check
        if self.api_key:
            auth = request.headers.get("Authorization")
            if not auth or auth != f"Bearer {self.api_key}":
                raise fastapi.HTTPException(status_code=401, detail="Unauthorized")

        content_type = request.headers.get("content-type", "")

        with tempfile.TemporaryDirectory() as tmpdir:
            if "multipart/form-data" in content_type:
                form = await request.form()
                upload = form.get("file")
                if upload is None:
                    raise fastapi.HTTPException(status_code=400, detail="No 'file' field")
                filename = getattr(upload, "filename", None) or f"{uuid.uuid4().hex}.wav"
                local_path = os.path.join(tmpdir, Path(filename).name)
                content = await upload.read()
                Path(local_path).write_bytes(content)
            elif "application/json" in content_type:
                import base64

                payload = await request.json()
                if "audio_base64" in payload:
                    filename = payload.get("filename", f"{uuid.uuid4().hex}.wav")
                    local_path = os.path.join(tmpdir, Path(filename).name)
                    audio_bytes = base64.b64decode(payload["audio_base64"])
                    Path(local_path).write_bytes(audio_bytes)
                else:
                    raise fastapi.HTTPException(
                        status_code=400, detail="Provide 'file' (multipart) or 'audio_base64' (JSON)"
                    )
            elif "application/octet-stream" in content_type:
                local_path = os.path.join(tmpdir, "audio.wav")
                body = await request.body()
                Path(local_path).write_bytes(body)
            else:
                raise fastapi.HTTPException(
                    status_code=400,
                    detail="Unsupported Content-Type. Use multipart/form-data, application/json, or application/octet-stream",
                )

            result = self._transcribe(local_path)

        fmt = os.environ.get("AAVAAZ_OUTPUT_FORMAT", "json")
        if fmt == "text":
            text = "\n".join(seg["text"] for seg in result["segments"])
            return fastapi.Response(content=text, media_type="text/plain")
        return result

    def _transcribe(self, audio_path: str) -> dict:
        import os

        segments, info = self.model.transcribe(
            audio_path, language=self.language, word_timestamps=True
        )
        segments = list(segments)

        pipeline = self._build_pipeline()
        results = []
        for seg in segments:
            entry = {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            }
            if seg.words:
                entry["words"] = [
                    {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                    for w in seg.words
                ]
            for fn in pipeline:
                entry = fn(entry)
            results.append(entry)

        return {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "segments": results,
        }

    def _build_pipeline(self) -> list:
        import os

        fns = []
        if os.environ.get("AAVAAZ_ENABLE_FORMAT", "1") == "1":
            from aavaaz.features.formatting import smart_format

            fns.append(smart_format)
        if os.environ.get("AAVAAZ_ENABLE_PII", "0") == "1":
            from aavaaz.features.pii_redaction import redact_pii

            fns.append(redact_pii)
        return fns
