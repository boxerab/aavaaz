"""Aavaaz — Modal GPU serverless TTS via Fish Speech.

Provides a text-to-speech HTTP API using the Fish Speech model.

Deploy with:
    cd deploy/modal && modal deploy app_tts.py

API:
    POST /v1/tts          - Generate speech from text
    GET  /health          - Health check

Environment variables (set via Modal Secrets):
    AAVAAZ_API_KEY        Optional API key for authentication
"""

import logging
import os
import subprocess
import time

import fastapi
import modal
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

logger = logging.getLogger("aavaaz.modal.tts")
logger.setLevel(logging.INFO)

MODEL_REPO = "fishaudio/fish-speech-1.5"
FISH_SPEECH_REPO = "https://github.com/fishaudio/fish-speech.git"
FISH_SPEECH_TAG = "v1.5.1"

app = modal.App("aavaaz-tts")

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-runtime-ubuntu22.04", add_python="3.12"
    )
    .apt_install("ffmpeg", "libsndfile1", "git", "build-essential", "portaudio19-dev")
    .run_commands(
        # Clone Fish Speech repo at the pinned tag
        f"git clone --depth 1 --branch {FISH_SPEECH_TAG} {FISH_SPEECH_REPO} /opt/fish-speech"
    )
    .pip_install(
        "torch==2.4.1",
        "torchaudio==2.4.1",
        "transformers>=4.36,<4.46",
        "tokenizers>=0.15",
        "sentencepiece",
        "safetensors",
        "regex",
        "protobuf",
        "huggingface_hub",
        "soundfile",
        "numpy",
        "fastapi[standard]",
        "loguru",
        "hydra-core",
        "lightning",
        "loralib",
        "vector-quantize-pytorch",
    )
    .run_commands(
        # Install fish-speech from cloned repo, skip pyaudio (not needed for server)
        "cd /opt/fish-speech && pip install -e . --no-deps",
        "cd /opt/fish-speech && pip install "
        '$(python -c "'
        "import tomllib; "
        "d=tomllib.load(open('pyproject.toml','rb')); "
        "deps=[x for x in d['project']['dependencies'] "
        "if 'pyaudio' not in x.lower()]; "
        "print(' '.join(deps))\")",
        # Download model weights at build time
        'python -c "'
        "from huggingface_hub import snapshot_download; "
        f"snapshot_download('{MODEL_REPO}', local_dir='/models/fish-speech-1.5')"
        '"',
        # Verify transformers + tokenizers work
        'python -c "from transformers import AutoTokenizer; print(AutoTokenizer)"',
    )
)

_aavaaz_secret = modal.Secret.from_name("aavaaz-config")

web_app = fastapi.FastAPI(title="Aavaaz TTS")
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.cls(
    image=image,
    gpu="A10G",
    secrets=[_aavaaz_secret],
    scaledown_window=300,
)
@modal.concurrent(max_inputs=4)
class TTSServer:
    """Fish Speech TTS server on Modal GPU."""

    @modal.enter()
    def load_model(self):
        """Load Fish Speech model into GPU memory."""
        import sys

        sys.path.insert(0, "/opt/fish-speech")

        import torch

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.api_key = os.environ.get("AAVAAZ_API_KEY", "")
        self.model_path = "/models/fish-speech-1.5"

        logger.info("Fish Speech TTS server ready (device=%s)", self.device)

    def _check_auth(self, request: fastapi.Request):
        """Verify API key if configured."""
        if not self.api_key:
            return
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != self.api_key:
            raise fastapi.HTTPException(status_code=401, detail="Invalid API key")

    @modal.asgi_app(label="aavaaz-tts")
    def serve(self):
        """Serve the FastAPI app."""

        @web_app.get("/health")
        def health():
            return {"status": "ok", "model": MODEL_REPO, "gpu": "A10G"}

        @web_app.get("/v1/tts/voices")
        def voices(request: fastapi.Request):
            self._check_auth(request)
            return {
                "voices": [
                    {"id": "default", "name": "Default (Random)", "language": "multi"},
                ],
                "note": "Upload reference audio in the request for voice cloning.",
            }

        @web_app.post("/v1/tts")
        async def tts(request: fastapi.Request):
            """Generate speech from text.

            Request JSON body:
                text (str): Text to synthesize (required)
                language (str): Language hint (optional)
                format (str): "wav" (default)

            Returns: audio/wav bytes
            """
            self._check_auth(request)

            body = await request.json()
            text = body.get("text", "").strip()
            if not text:
                raise fastapi.HTTPException(400, "'text' field is required")
            if len(text) > 5000:
                raise fastapi.HTTPException(400, "Text exceeds 5000 character limit")

            t0 = time.time()
            logger.info("TTS request: %d chars", len(text))

            try:
                audio_bytes = self._synthesize(text)
            except Exception as e:
                logger.error("TTS failed: %s", e)
                raise fastapi.HTTPException(500, f"Synthesis failed: {e}")

            elapsed = time.time() - t0
            logger.info("TTS done in %.2fs (%d bytes)", elapsed, len(audio_bytes))

            return Response(
                content=audio_bytes,
                media_type="audio/wav",
                headers={"X-Processing-Time": f"{elapsed:.3f}s"},
            )

        return web_app

    def _synthesize(self, text: str) -> bytes:
        """Run Fish Speech inference via CLI (most reliable path)."""
        import glob
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: text → semantic codes
            cmd_codes = [
                "python",
                "/opt/fish-speech/fish_speech/models/text2semantic/inference.py",
                "--text",
                text,
                "--checkpoint-path",
                self.model_path,
                "--output-path",
                os.path.join(tmpdir, "codes.npy"),
                "--num-samples",
                "1",
            ]
            r = subprocess.run(
                cmd_codes,
                capture_output=True,
                text=True,
                timeout=120,
                cwd="/opt/fish-speech",
            )
            if r.returncode != 0:
                raise RuntimeError(f"Semantic stage failed: {r.stderr[-2000:]}")

            # Find generated codes file
            codes_files = sorted(glob.glob(os.path.join(tmpdir, "codes*.npy")))
            if not codes_files:
                raise RuntimeError("No codes file produced")

            # Step 2: codes → audio waveform
            output_wav = os.path.join(tmpdir, "output.wav")
            cmd_audio = [
                "python",
                "/opt/fish-speech/fish_speech/models/vqgan/inference.py",
                "-i",
                codes_files[0],
                "--checkpoint-path",
                os.path.join(
                    self.model_path,
                    "firefly-gan-vq-fsq-8x1024-21hz-generator.pth",
                ),
                "--output-path",
                output_wav,
            ]
            r = subprocess.run(
                cmd_audio,
                capture_output=True,
                text=True,
                timeout=60,
                cwd="/opt/fish-speech",
            )
            if r.returncode != 0:
                raise RuntimeError(f"Audio stage failed: {r.stderr[-500:]}")

            # Find output (might default to "fake.wav")
            if not os.path.exists(output_wav):
                alt = os.path.join(tmpdir, "fake.wav")
                if os.path.exists(alt):
                    output_wav = alt
                else:
                    # Search for any wav
                    wavs = glob.glob(os.path.join(tmpdir, "*.wav")) + glob.glob(
                        "fake.wav"
                    )
                    if wavs:
                        output_wav = wavs[0]
                    else:
                        raise RuntimeError("No audio output produced")

            with open(output_wav, "rb") as f:
                return f.read()
