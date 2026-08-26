"""Integration tests for the multichannel audio module."""

import wave

import numpy as np

from aavaaz.features.multichannel import (
    count_channels,
    merge_channel_segments,
    split_channels,
    transcribe_channels,
)

SAMPLE_RATE = 16000


class TestSplitChannels:
    def test_stereo_split(self):
        # Interleaved stereo: L0, R0, L1, R1, L2, R2
        audio = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], dtype=np.float32)
        channels = split_channels(audio, channels=2)
        assert len(channels) == 2
        np.testing.assert_array_equal(channels[0], [1.0, 3.0, 5.0])
        np.testing.assert_array_equal(channels[1], [2.0, 4.0, 6.0])

    def test_mono_passthrough(self):
        audio = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        channels = split_channels(audio, channels=1)
        assert len(channels) == 1
        np.testing.assert_array_equal(channels[0], audio)

    def test_trims_incomplete_frame(self):
        # 5 samples, 2 channels -> only 4 usable
        audio = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float32)
        channels = split_channels(audio, channels=2)
        assert len(channels[0]) == 2
        assert len(channels[1]) == 2

    def test_empty_audio(self):
        audio = np.array([], dtype=np.float32)
        channels = split_channels(audio, channels=2)
        assert len(channels) == 2
        assert len(channels[0]) == 0

    def test_three_channels(self):
        audio = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9], dtype=np.float32)
        channels = split_channels(audio, channels=3)
        assert len(channels) == 3
        np.testing.assert_array_equal(channels[0], [1, 4, 7])
        np.testing.assert_array_equal(channels[1], [2, 5, 8])
        np.testing.assert_array_equal(channels[2], [3, 6, 9])


class TestMergeChannelSegments:
    def test_basic_merge(self):
        ch0 = [{"text": "hello", "start": 0.0, "end": 1.0}]
        ch1 = [{"text": "world", "start": 0.5, "end": 1.5}]
        merged = merge_channel_segments([ch0, ch1])
        assert len(merged) == 2
        assert merged[0]["channel"] == "ch0"
        assert merged[1]["channel"] == "ch1"
        # Sorted by start time
        assert float(merged[0]["start"]) <= float(merged[1]["start"])

    def test_custom_labels(self):
        ch0 = [{"text": "hi", "start": 0.0, "end": 1.0}]
        ch1 = [{"text": "hey", "start": 0.5, "end": 1.5}]
        merged = merge_channel_segments(
            [ch0, ch1], channel_labels=["agent", "customer"]
        )
        assert merged[0]["channel"] == "agent"
        assert merged[1]["channel"] == "customer"

    def test_empty_channels(self):
        merged = merge_channel_segments([[], []])
        assert merged == []

    def test_does_not_mutate_input(self):
        seg = {"text": "hi", "start": 0.0, "end": 1.0}
        merge_channel_segments([[seg]])
        assert "channel" not in seg


class _Info:
    def __init__(self, duration):
        self.language = "en"
        self.language_probability = 0.9
        self.duration = duration


class TestTranscribeChannels:
    def test_merges_per_channel_results(self):
        channels = [np.array([1.0]), np.array([2.0])]
        seen = []

        def transcribe(audio):
            seen.append(float(audio[0]))
            start = float(audio[0])
            return [{"text": f"ch{start}", "start": start, "end": start + 1}], _Info(
                start + 1
            )

        result = transcribe_channels(channels, transcribe, ["agent", "customer"])

        assert seen == [1.0, 2.0]
        assert [s["channel"] for s in result["segments"]] == ["agent", "customer"]
        assert result["language"] == "en"
        assert result["duration"] == 3.0  # longest channel wins


def _write_wav(path, channels):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(np.zeros(SAMPLE_RATE * channels, dtype=np.int16).tobytes())
    return path


class TestCountChannels:
    def test_stereo_file(self, tmp_path):
        assert count_channels(_write_wav(tmp_path / "stereo.wav", 2)) == 2

    def test_mono_file(self, tmp_path):
        assert count_channels(_write_wav(tmp_path / "mono.wav", 1)) == 1
