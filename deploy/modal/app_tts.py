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
    scaledown_window=900,
)
@modal.concurrent(max_inputs=4)
class TTSServer:
    """Fish Speech TTS server on Modal GPU."""

    @modal.enter()
    def load_model(self):
        """Load Fish Speech model into GPU memory."""
        import sys

        sys.path.insert(0, "/opt/fish-speech")

        import numpy as np
        import soundfile as sf
        import torch

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.api_key = os.environ.get("AAVAAZ_API_KEY", "")
        self.model_path = "/models/fish-speech-1.5"
        self.torch = torch
        self.np = np
        self.sf = sf

        # Load the LLM for semantic code generation
        from fish_speech.models.text2semantic.inference import load_model
        from fish_speech.text import split_text

        self.split_text = split_text
        precision = torch.bfloat16
        self.model, self.decode_one_token = load_model(
            self.model_path, self.device, precision, compile=False
        )
        with torch.device(self.device):
            self.model.setup_caches(
                max_batch_size=1,
                max_seq_len=self.model.config.max_seq_len,
                dtype=next(self.model.parameters()).dtype,
            )

        # Load the VQGAN decoder for codes → audio
        from hydra import compose, initialize_config_dir
        from hydra.core.global_hydra import GlobalHydra
        from hydra.utils import instantiate

        GlobalHydra.instance().clear()

        with initialize_config_dir(
            version_base="1.3",
            config_dir="/opt/fish-speech/fish_speech/configs",
        ):
            cfg = compose(config_name="firefly_gan_vq")

        self.vqgan = instantiate(cfg)
        vqgan_ckpt = os.path.join(
            self.model_path, "firefly-gan-vq-fsq-8x1024-21hz-generator.pth"
        )
        state_dict = torch.load(
            vqgan_ckpt, map_location=self.device, mmap=True, weights_only=True
        )
        if "state_dict" in state_dict:
            state_dict = state_dict["state_dict"]
        if any("generator" in k for k in state_dict):
            state_dict = {
                k.replace("generator.", ""): v
                for k, v in state_dict.items()
                if "generator." in k
            }
        self.vqgan.load_state_dict(state_dict, strict=False, assign=True)
        self.vqgan.eval()
        self.vqgan.to(self.device)

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

        @web_app.post("/v1/tts/stream")
        async def tts_stream(request: fastapi.Request):
            """Generate speech with real-time progress via SSE.

            Request JSON body:
                text (str): Text to synthesize (required)

            Returns: text/event-stream with progress events, final event has base64 audio.
            """
            import asyncio
            import base64
            import json
            import threading

            self._check_auth(request)

            body = await request.json()
            text = body.get("text", "").strip()
            if not text:
                raise fastapi.HTTPException(400, "'text' field is required")
            if len(text) > 5000:
                raise fastapi.HTTPException(400, "Text exceeds 5000 character limit")

            # Shared state for progress reporting
            state = {
                "progress": 0,
                "stage": "",
                "done": False,
                "error": None,
                "audio": None,
                "time": None,
            }

            def run_synthesis():
                t0 = time.time()
                try:
                    chunks = self.split_text(text, 100)
                    total_segments = len(chunks)
                    state["stage"] = (
                        f"Generating speech (0/{total_segments} segments)..."
                    )
                    state["progress"] = 5

                    audio_bytes = self._synthesize_tracked(text, total_segments, state)
                    elapsed = time.time() - t0
                    state["audio"] = base64.b64encode(audio_bytes).decode()
                    state["time"] = f"{elapsed:.3f}s"
                    state["progress"] = 100
                    state["stage"] = "Done!"
                except Exception as e:
                    state["error"] = str(e)
                finally:
                    state["done"] = True

            thread = threading.Thread(target=run_synthesis, daemon=True)
            thread.start()

            async def generate():
                last_progress = -1
                while not state["done"]:
                    await asyncio.sleep(0.3)
                    if state["progress"] != last_progress:
                        last_progress = state["progress"]
                        evt = json.dumps(
                            {"progress": state["progress"], "stage": state["stage"]}
                        )
                        yield f"data: {evt}\n\n"

                # Final event
                if state["error"]:
                    err_evt = json.dumps({"error": state["error"]})
                    yield f"data: {err_evt}\n\n"
                else:
                    final_evt = json.dumps(
                        {
                            "progress": 100,
                            "stage": "Done!",
                            "audio": state["audio"],
                            "processing_time": state["time"],
                        }
                    )
                    yield f"data: {final_evt}\n\n"

            from starlette.responses import StreamingResponse

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        return web_app

    def _synthesize(self, text: str) -> bytes:
        """Run Fish Speech inference using Python API."""
        state = {"progress": 0, "stage": ""}
        chunks = self.split_text(text, 100)
        return self._synthesize_tracked(text, len(chunks), state)

    def _synthesize_tracked(self, text, total_segments, state) -> bytes:
        """Run Fish Speech inference with progress tracking via shared state."""
        import gc
        import io

        import numpy as np
        import torch
        from fish_speech.models.text2semantic.inference import generate_long
        from fish_speech.utils import autocast_exclude_mps

        torch.manual_seed(42)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(42)

        # Generate semantic codes
        state["stage"] = f"Generating speech (0/{total_segments} segments)..."
        state["progress"] = 10

        generator = generate_long(
            model=self.model,
            device=self.device,
            decode_one_token=self.decode_one_token,
            text=text,
            num_samples=1,
            max_new_tokens=0,
            top_p=0.7,
            repetition_penalty=1.2,
            temperature=0.7,
            compile=False,
            iterative_prompt=True,
            chunk_length=100,
            prompt_text=None,
            prompt_tokens=None,
        )

        # Decode each segment individually (matches official inference engine)
        audio_segments = []
        segment_idx = 0
        for response in generator:
            if response.action == "sample":
                segment_idx += 1
                # Progress: 10% to 80% during code generation
                pct = 10 + int((segment_idx / max(total_segments, 1)) * 70)
                state["progress"] = min(80, pct)
                state["stage"] = (
                    f"Generating speech ({segment_idx}/{total_segments} segments)..."
                )
                logger.info("Segment %d/%d generated", segment_idx, total_segments)

                # Decode this segment's codes to audio immediately
                with (
                    torch.no_grad(),
                    autocast_exclude_mps(device_type=self.device, dtype=torch.bfloat16),
                ):
                    codes = response.codes
                    feature_lengths = torch.tensor([codes.shape[1]], device=self.device)
                    audio = self.vqgan.decode(
                        indices=codes[None], feature_lengths=feature_lengths
                    )[0].squeeze()
                    audio_segments.append(audio.float().cpu().numpy())

            elif response.action == "next":
                pass

        if not audio_segments:
            raise RuntimeError("No audio generated")

        state["progress"] = 90
        state["stage"] = "Finalizing..."

        # Concatenate audio segments
        audio_np = np.concatenate(audio_segments, axis=0)

        # Clean up GPU memory
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()

        state["progress"] = 95
        state["stage"] = "Encoding WAV..."

        # Convert to WAV bytes
        sample_rate = self.vqgan.spec_transform.sample_rate
        buf = io.BytesIO()
        self.sf.write(buf, audio_np, sample_rate, format="WAV")
        return buf.getvalue()
