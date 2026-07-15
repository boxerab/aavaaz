"""
Tests for performance characteristics (Test Matrix §21).

These tests verify performance boundaries and resource management.
Not benchmarks — they validate contracts like "doesn't crash under load"
and "memory doesn't grow unbounded".
"""

import time

import numpy as np
import pytest


class TestTranscriptionLatency:
    """21.1 - Transcription latency bounds."""

    @pytest.mark.smoke
    def test_tiny_model_latency_under_10s(self, tmp_path):
        """tiny.en model should transcribe 10s audio in under 10s on CPU."""
        pytest.importorskip("faster_whisper")
        import wave

        from faster_whisper import WhisperModel

        # Generate 10 seconds of audio
        sample_rate = 16000
        duration = 10.0
        n_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False)
        audio = (np.sin(2 * np.pi * 440 * t) * 32767 * 0.3).astype(np.int16)
        audio_path = tmp_path / "perf_test.wav"
        with wave.open(str(audio_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio.tobytes())

        model = WhisperModel("tiny.en", device="cpu", compute_type="int8")

        start = time.time()
        result = model.transcribe(str(audio_path), language="en")
        if isinstance(result, tuple):
            segments, info = result
            list(segments)
        else:
            # faster-whisper >= 1.0 returns generator directly
            list(result)
        elapsed = time.time() - start

        # Should complete within 10 seconds on modern CPU
        assert elapsed < 10.0, f"Transcription took {elapsed:.1f}s (expected < 10s)"


class TestMemoryManagement:
    """21.4 - Memory usage under sustained load."""

    def test_transcript_index_handles_many_entries(self):
        """Search index should handle 1000+ entries without issues."""
        from aavaaz.features.search import TranscriptIndex, TranscriptMetadata

        index = TranscriptIndex()
        for i in range(1000):
            meta = TranscriptMetadata(
                job_id=f"job_{i}",
                text=f"This is transcript number {i} with some text content",
            )
            index.add(meta)

        # Search should still be fast
        start = time.time()
        results = index.search(query="transcript number 500")
        elapsed = time.time() - start
        assert elapsed < 1.0
        assert len(results) > 0


