"""Integration tests for the batch inference module (mocked transcriber)."""

import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

# Mock faster_whisper and whisper_live before import (if not already present).
# These mocks persist for the session — test_serverless.py also needs them.
_mock_fw = MagicMock()
_mock_fw.__spec__ = None
sys.modules.setdefault("faster_whisper", _mock_fw)
sys.modules.setdefault("faster_whisper.audio", MagicMock())
sys.modules.setdefault("faster_whisper.tokenizer", MagicMock())
sys.modules.setdefault("faster_whisper.vad", MagicMock())
sys.modules.setdefault("whisper_live", MagicMock())
sys.modules.setdefault("whisper_live.transcriber", MagicMock())
# Use a real ModuleType for this submodule so it does NOT auto-create a
# WhisperModel attribute (which would confuse lambda_handler's fallback import).
_wl_tfw = types.ModuleType("whisper_live.transcriber.transcriber_faster_whisper")
_wl_tfw.Segment = MagicMock()
_wl_tfw.TranscriptionInfo = MagicMock()
_wl_tfw.get_compression_ratio = MagicMock()
_wl_tfw.get_suppressed_tokens = MagicMock()
sys.modules.setdefault("whisper_live.transcriber.transcriber_faster_whisper", _wl_tfw)

from aavaaz.features.batch_inference import BatchInferenceWorker, BatchRequest  # noqa: E402


class TestBatchRequest:
    def test_defaults(self):
        audio = np.zeros(16000, dtype=np.float32)
        req = BatchRequest(audio=audio)
        assert req.language is None
        assert req.task == "transcribe"
        assert req.result is None
        assert req.error is None
        assert not req.future.is_set()

    def test_future_signaling(self):
        req = BatchRequest(audio=np.zeros(100, dtype=np.float32))
        req.future.set()
        assert req.future.is_set()


class TestBatchInferenceWorker:
    def test_start_and_stop(self):
        mock_transcriber = MagicMock()
        worker = BatchInferenceWorker(mock_transcriber, max_batch_size=4, batch_window_ms=10)
        worker.start()
        assert worker._thread is not None
        assert worker._thread.is_alive()
        worker.stop()
        worker._thread.join(timeout=2)
        assert not worker._thread.is_alive()

    def test_single_request_processed(self):
        """Submit a single request and verify it gets processed."""
        mock_transcriber = MagicMock()
        # Mock transcribe to return segments
        mock_segments = [MagicMock(start=0, end=1, text="hello")]
        mock_info = MagicMock()
        mock_transcriber.transcribe.return_value = (mock_segments, mock_info)

        worker = BatchInferenceWorker(mock_transcriber, max_batch_size=4, batch_window_ms=10)
        worker.start()

        try:
            audio = np.zeros(16000, dtype=np.float32)
            req = BatchRequest(audio=audio, language="en")
            worker.submit(req)
            req.future.wait(timeout=5)

            assert req.future.is_set()
            # Either result is set or error is set
            assert req.result is not None or req.error is not None
        finally:
            worker.stop()

    def test_queue_collects_batch(self):
        """Submit multiple requests quickly — they should be batched."""
        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = ([MagicMock()], MagicMock())

        worker = BatchInferenceWorker(mock_transcriber, max_batch_size=4, batch_window_ms=100)
        worker.start()

        try:
            requests = []
            for _ in range(3):
                req = BatchRequest(audio=np.zeros(16000, dtype=np.float32), language="en")
                worker.submit(req)
                requests.append(req)

            # Wait for all to complete
            for req in requests:
                req.future.wait(timeout=5)
                assert req.future.is_set()
        finally:
            worker.stop()
