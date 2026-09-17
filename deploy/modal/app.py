"""Aavaaz — Modal GPU serverless transcription with web demo.

Uses WhisperLive batch inference for GPU-accelerated transcription.

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
    AAVAAZ_ENABLE_PARAGRAPHS    1 to add paragraph segmentation (default: 0)
    AAVAAZ_ENABLE_INTELLIGENCE  1 to add sentiment/topics/entities (default: 0)
    AAVAAZ_API_KEY        Optional API key for authentication

    AAVAAZ_STORE_AUDIO    1 to store uploaded audio to a Modal Volume (default: 0)
    AAVAAZ_ENABLE_MULTICHANNEL  1 to transcribe each channel separately (default: 0)
    AAVAAZ_CHANNEL_LABELS       Comma-separated labels, one per channel

A per-request ``features`` object (JSON body field, or a ``features`` form field
holding JSON) overrides these env defaults, matching the Lambda batch path. A
``hotwords`` string and a ``callback_url`` (body or form field) bias recognition
and fire a webhook with the transcript on completion.
"""

import logging

import fastapi
import modal

logger = logging.getLogger("aavaaz.modal")
logger.setLevel(logging.INFO)

WHISPER_MODEL = "large-v3"

BATCH_TIMEOUT_SECONDS = 300
UNKNOWN_LANGUAGE = "unknown"

# Path to the web UI files inside the container.
WEB_DIR = "/web"

app = modal.App("aavaaz-transcribe")

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-runtime-ubuntu22.04", add_python="3.12"
    )
    .apt_install("ffmpeg")
    .pip_install(
        "faster-whisper>=1.0",
        "fastapi[standard]",
        "python-multipart",
        "tokenizers",
        "tqdm",
    )
    .run_commands("pip install --no-deps 'whisper-live>=0.10.0'")
    .run_commands(
        f'python -c "from faster_whisper import WhisperModel; '
        f"WhisperModel('{WHISPER_MODEL}', device='cpu')\""
    )
    .add_local_dir("../../aavaaz", remote_path="/root/aavaaz_pkg/aavaaz", copy=True)
    .add_local_file(
        "../../pyproject.toml", remote_path="/root/aavaaz_pkg/pyproject.toml", copy=True
    )
    .run_commands("pip install /root/aavaaz_pkg")
    .add_local_dir("../../aavaaz/web", remote_path=WEB_DIR)
)


# Optional: create this secret with `modal secret create aavaaz-config KEY=VALUE ...`
_aavaaz_secret = modal.Secret.from_name("aavaaz-config")

# Optional volume for storing audio uploads (only used when AAVAAZ_STORE_AUDIO=1).
_audio_volume = modal.Volume.from_name("aavaaz-audio-store", create_if_missing=True)
AUDIO_VOLUME_PATH = "/audio_store"


@app.cls(
    image=image,
    gpu="T4",
    timeout=600,
    secrets=[_aavaaz_secret],
    scaledown_window=120,
    volumes={AUDIO_VOLUME_PATH: _audio_volume},
)
@modal.concurrent(max_inputs=4)
class Transcriber:
    @modal.enter()
    def load_model(self):
        import os

        from whisper_live.batch_inference import BatchInferenceWorker
        from whisper_live.transcriber.transcriber_faster_whisper import WhisperModel

        model_name = os.environ.get("AAVAAZ_MODEL", WHISPER_MODEL)
        logger.info("Loading Whisper model: %s", model_name)
        self.model = WhisperModel(model_name, device="cuda", compute_type="float16")
        self.batch_worker = BatchInferenceWorker(
            self.model, max_batch_size=4, batch_window_ms=100
        )
        self.batch_worker.start()
        self.language = os.environ.get("AAVAAZ_LANGUAGE") or None
        self.api_key = os.environ.get("AAVAAZ_API_KEY")
        self.store_audio = os.environ.get("AAVAAZ_STORE_AUDIO", "0") == "1"
        logger.info("Model loaded. store_audio=%s", self.store_audio)

    @modal.asgi_app()
    def web(self):
        import os

        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import HTMLResponse
        from fastapi.staticfiles import StaticFiles

        web_app = fastapi.FastAPI(title="Aavaaz Transcription Demo")

        # allow the dashboard/browser clients to read /health and call the API
        web_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

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
        import contextlib
        import os
        import shutil
        import tempfile
        import time
        import uuid
        from pathlib import Path

        request_id = uuid.uuid4().hex[:12]
        logger.info("Request received: request_id=%s", request_id)

        # Auth check
        if self.api_key:
            auth = request.headers.get("Authorization")
            if not auth or auth != f"Bearer {self.api_key}":
                logger.warning("Unauthorized request: request_id=%s", request_id)
                raise fastapi.HTTPException(status_code=401, detail="Unauthorized")

        content_type = request.headers.get("content-type", "")
        response_format = None
        features = None
        hotwords = None
        callback_url = None

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                if "multipart/form-data" in content_type:
                    form = await request.form()
                    upload = form.get("file")
                    if upload is None:
                        raise fastapi.HTTPException(
                            status_code=400, detail="No 'file' field"
                        )
                    response_format = form.get("response_format")
                    raw_features = form.get("features")
                    if raw_features:
                        import json as _json

                        with contextlib.suppress(ValueError, TypeError):
                            features = _json.loads(raw_features)
                    hotwords = form.get("hotwords")
                    callback_url = form.get("callback_url")
                    filename = (
                        getattr(upload, "filename", None) or f"{uuid.uuid4().hex}.wav"
                    )
                    local_path = os.path.join(tmpdir, Path(filename).name)
                    content = await upload.read()
                    Path(local_path).write_bytes(content)
                    logger.info(
                        "Multipart upload: request_id=%s filename=%s size_bytes=%d",
                        request_id,
                        filename,
                        len(content),
                    )
                elif "application/json" in content_type:
                    import base64

                    payload = await request.json()
                    features = payload.get("features")
                    hotwords = payload.get("hotwords")
                    callback_url = payload.get("callback_url")
                    if "audio_base64" in payload:
                        filename = payload.get("filename", f"{uuid.uuid4().hex}.wav")
                        local_path = os.path.join(tmpdir, Path(filename).name)
                        audio_bytes = base64.b64decode(payload["audio_base64"])
                        Path(local_path).write_bytes(audio_bytes)
                        logger.info(
                            "JSON upload: request_id=%s filename=%s size_bytes=%d",
                            request_id,
                            filename,
                            len(audio_bytes),
                        )
                    else:
                        raise fastapi.HTTPException(
                            status_code=400,
                            detail="Provide 'file' (multipart) or 'audio_base64' (JSON)",
                        )
                elif "application/octet-stream" in content_type:
                    local_path = os.path.join(tmpdir, "audio.wav")
                    body = await request.body()
                    Path(local_path).write_bytes(body)
                    logger.info(
                        "Octet-stream upload: request_id=%s size_bytes=%d",
                        request_id,
                        len(body),
                    )
                else:
                    raise fastapi.HTTPException(
                        status_code=400,
                        detail=(
                            "Unsupported Content-Type. Use multipart/form-data, "
                            "application/json, or application/octet-stream"
                        ),
                    )

                # Optional audio storage
                if self.store_audio:
                    store_name = f"{uuid.uuid4().hex}_{os.path.basename(local_path)}"
                    store_path = os.path.join(AUDIO_VOLUME_PATH, store_name)
                    shutil.copy2(local_path, store_path)
                    logger.info(
                        "Stored audio: request_id=%s path=%s", request_id, store_path
                    )

                t0 = time.time()
                result = self._transcribe(local_path, features, hotwords)
                elapsed = time.time() - t0
                logger.info(
                    "Transcription complete: request_id=%s duration=%.1fs "
                    "segments=%d elapsed=%.2fs",
                    request_id,
                    result.get("duration", 0),
                    len(result.get("segments", [])),
                    elapsed,
                )
        except fastapi.HTTPException:
            raise
        except Exception:
            logger.exception("Unhandled error: request_id=%s", request_id)
            raise fastapi.HTTPException(status_code=500, detail="Internal server error")

        if callback_url:
            from aavaaz.features.webhook import send_webhook

            send_webhook(callback_url, result)

        fmt = response_format or os.environ.get("AAVAAZ_OUTPUT_FORMAT", "json")
        if fmt == "text":
            text = "\n".join(seg["text"] for seg in result["segments"])
            return fastapi.Response(content=text, media_type="text/plain")
        return result

    def _transcribe(
        self,
        audio_path: str,
        features: dict | None = None,
        hotwords: str | None = None,
    ) -> dict:
        import os

        from faster_whisper.audio import decode_audio

        from aavaaz.features import multichannel
        from aavaaz.features.enrichment import build_pipeline, enrich_result
        from aavaaz.features.noise_reduction import maybe_reduce_noise

        file_size = os.path.getsize(audio_path)
        logger.info(
            "Starting transcription: file=%s size_bytes=%d",
            os.path.basename(audio_path),
            file_size,
        )

        multichannel_enabled, channel_labels = multichannel.resolve(features)
        split_stereo = (
            multichannel_enabled and multichannel.count_channels(audio_path) > 1
        )
        decoded = decode_audio(audio_path, split_stereo=split_stereo)
        pipeline = build_pipeline(features)

        def transcribe_channel(audio):
            segments, info = self._run_batch(
                maybe_reduce_noise(audio, features), hotwords
            )
            return _segments_to_entries(segments, pipeline), info

        if split_stereo:
            out = multichannel.transcribe_channels(
                list(decoded), transcribe_channel, channel_labels
            )
        else:
            entries, info = transcribe_channel(decoded)
            out = {
                "language": info.language if info else UNKNOWN_LANGUAGE,
                "language_probability": info.language_probability if info else 0.0,
                "duration": info.duration if info else 0.0,
                "segments": entries,
            }

        enrich_result(out, features)
        return out

    def _run_batch(self, audio, hotwords: str | None):
        """Run one mono audio array through the WhisperLive batch worker."""
        from whisper_live.batch_inference import BatchRequest

        request = BatchRequest(
            audio=audio,
            language=self.language,
            word_timestamps=True,
            hotwords=hotwords or None,
        )
        self.batch_worker.submit(request)

        if not request.future.wait(timeout=BATCH_TIMEOUT_SECONDS):
            logger.error("Transcription timed out after %ds", BATCH_TIMEOUT_SECONDS)
            raise fastapi.HTTPException(
                status_code=504, detail="Transcription timed out"
            )

        if request.error:
            logger.error("Transcription failed: %s", request.error)
            raise request.error

        return request.result or [], request.info


def _segments_to_entries(segments, pipeline: list) -> list[dict]:
    """Convert WhisperLive segments to result dicts, applying the text pipeline."""
    entries = []
    for seg in segments:
        entry = {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
        if getattr(seg, "words", None):
            entry["words"] = [
                {
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability,
                }
                for w in seg.words
            ]
        for fn in pipeline:
            entry["text"] = fn(entry["text"])
        entries.append(entry)
    return entries
