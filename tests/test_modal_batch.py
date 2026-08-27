"""Tests for the Modal batch endpoint (deploy/modal/app.py).

``modal`` and the ML stack are stubbed in ``sys.modules`` so the real endpoint
code runs against a fake batch worker.
"""

import importlib.util
import json
import sys
import types
import wave
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "deploy" / "modal" / "app.py"
WEB_DIR = REPO_ROOT / "aavaaz" / "web"
SAMPLE_RATE = 16000


def _identity_decorator(*args, **kwargs):
    return lambda obj: obj


def _stub_modal() -> types.ModuleType:
    """A ``modal`` module whose decorators leave the class untouched."""
    modal = types.ModuleType("modal")
    app = MagicMock()
    app.cls = _identity_decorator
    modal.App = MagicMock(return_value=app)
    modal.Image = MagicMock()
    modal.Secret = MagicMock()
    modal.Volume = MagicMock()
    modal.concurrent = _identity_decorator
    modal.enter = _identity_decorator
    modal.asgi_app = _identity_decorator
    return modal


class FakeWord:
    def __init__(self, word, start, end, probability):
        self.word = word
        self.start = start
        self.end = end
        self.probability = probability


class FakeSegment:
    def __init__(self, text=" Hello world ", start=0.0, end=1.5):
        self.start = start
        self.end = end
        self.text = text
        self.words = [
            FakeWord("Hello", start, 0.5, 0.9),
            FakeWord("world", 0.5, end, 0.8),
        ]


class FakeInfo:
    language = "en"
    language_probability = 0.99
    duration = 1.5


class FakeBatchWorker:
    """Completes every submitted request immediately, recording it."""

    def __init__(self):
        self.requests = []

    def submit(self, request):
        self.requests.append(request)
        request.result = [FakeSegment()]
        request.info = FakeInfo()
        request.future.set()


@pytest.fixture(scope="module")
def modal_app():
    """Import deploy/modal/app.py with modal and faster_whisper stubbed out."""
    stubbed = ("modal", "faster_whisper", "faster_whisper.audio", "whisper_live.batch_inference")
    before = {name: sys.modules[name] for name in stubbed if name in sys.modules}

    sys.modules.setdefault("modal", _stub_modal())
    sys.modules.setdefault("faster_whisper", MagicMock())

    audio_module = types.ModuleType("faster_whisper.audio")
    audio_module.decode_audio = MagicMock()
    sys.modules["faster_whisper.audio"] = audio_module

    batch_module = types.ModuleType("whisper_live.batch_inference")

    class BatchRequest:
        def __init__(
            self,
            audio,
            language=None,
            word_timestamps=False,
            hotwords=None,
        ):
            import threading

            self.audio = audio
            self.language = language
            self.word_timestamps = word_timestamps
            self.hotwords = hotwords
            self.future = threading.Event()
            self.result = None
            self.info = None
            self.error = None

    batch_module.BatchRequest = BatchRequest
    sys.modules.setdefault("whisper_live", types.ModuleType("whisper_live"))
    sys.modules["whisper_live.batch_inference"] = batch_module

    spec = importlib.util.spec_from_file_location("modal_batch_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WEB_DIR = str(WEB_DIR)
    yield module

    # put sys.modules back: a MagicMock left under "faster_whisper" is not a
    # package, so every later test importing a submodule of it fails
    for name in stubbed:
        if name in before:
            sys.modules[name] = before[name]
        else:
            sys.modules.pop(name, None)


@pytest.fixture
def transcriber(modal_app, monkeypatch):
    monkeypatch.setenv("AAVAAZ_ENABLE_FORMAT", "0")
    monkeypatch.setenv("AAVAAZ_ENABLE_PII", "0")
    instance = modal_app.Transcriber()
    instance.language = "en"
    instance.api_key = None
    instance.store_audio = False
    instance.batch_worker = FakeBatchWorker()
    return instance


@pytest.fixture
def client(transcriber):
    return TestClient(transcriber.web())


def _write_wav(path: Path, channels: int) -> Path:
    samples = np.zeros(SAMPLE_RATE * channels, dtype=np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(samples.tobytes())
    return path


def _mono_audio():
    return np.zeros(SAMPLE_RATE, dtype=np.float32)


def test_multipart_returns_word_timestamps(transcriber, client, tmp_path):
    """Every request asks for word timestamps and the words reach the response."""
    sys.modules["faster_whisper.audio"].decode_audio = MagicMock(
        return_value=_mono_audio()
    )
    wav = _write_wav(tmp_path / "mono.wav", channels=1)

    response = client.post(
        "/v1/audio/transcriptions", files={"file": ("mono.wav", wav.read_bytes())}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "en"
    assert body["segments"][0]["text"] == "Hello world"
    assert [w["word"] for w in body["segments"][0]["words"]] == ["Hello", "world"]
    assert transcriber.batch_worker.requests[0].word_timestamps is True


def test_multipart_passes_hotwords(transcriber, client, tmp_path):
    """A hotwords form field reaches the BatchRequest."""
    sys.modules["faster_whisper.audio"].decode_audio = MagicMock(
        return_value=_mono_audio()
    )
    wav = _write_wav(tmp_path / "mono.wav", channels=1)

    response = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("mono.wav", wav.read_bytes())},
        data={"hotwords": "Kubernetes, Anthropic"},
    )

    assert response.status_code == 200
    assert transcriber.batch_worker.requests[0].hotwords == "Kubernetes, Anthropic"


def test_json_body_passes_hotwords(transcriber, client, tmp_path):
    """A hotwords JSON body field reaches the BatchRequest."""
    import base64

    sys.modules["faster_whisper.audio"].decode_audio = MagicMock(
        return_value=_mono_audio()
    )
    wav = _write_wav(tmp_path / "mono.wav", channels=1)

    response = client.post(
        "/v1/audio/transcriptions",
        json={
            "audio_base64": base64.b64encode(wav.read_bytes()).decode(),
            "filename": "mono.wav",
            "hotwords": "Aavaaz",
        },
    )

    assert response.status_code == 200
    assert transcriber.batch_worker.requests[0].hotwords == "Aavaaz"


def test_multichannel_merges_labelled_channels(transcriber, client, tmp_path):
    """A stereo file is transcribed per channel and merged with channel labels."""
    left = np.zeros(SAMPLE_RATE, dtype=np.float32)
    right = np.ones(SAMPLE_RATE, dtype=np.float32)
    sys.modules["faster_whisper.audio"].decode_audio = MagicMock(
        return_value=(left, right)
    )
    wav = _write_wav(tmp_path / "stereo.wav", channels=2)

    response = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("stereo.wav", wav.read_bytes())},
        data={
            "features": json.dumps(
                {"multichannel": {"enabled": True, "labels": ["agent", "customer"]}}
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [seg["channel"] for seg in body["segments"]] == ["agent", "customer"]
    assert len(transcriber.batch_worker.requests) == 2
    assert transcriber.batch_worker.requests[0].word_timestamps is True


def test_multichannel_skips_split_for_mono_file(transcriber, client, tmp_path):
    """Multichannel on a mono file transcribes once and adds no channel label."""
    sys.modules["faster_whisper.audio"].decode_audio = MagicMock(
        return_value=_mono_audio()
    )
    wav = _write_wav(tmp_path / "mono.wav", channels=1)

    response = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("mono.wav", wav.read_bytes())},
        data={"features": json.dumps({"multichannel": {"enabled": True}})},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(transcriber.batch_worker.requests) == 1
    assert "channel" not in body["segments"][0]
    assert (
        sys.modules["faster_whisper.audio"].decode_audio.call_args.kwargs[
            "split_stereo"
        ]
        is False
    )
