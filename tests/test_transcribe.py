"""Tests for aavaaz.transcribe output formatting (SRT/VTT/JSON)."""

import json
import sys
from unittest.mock import MagicMock, patch

# transcribe.py imports faster_whisper at module load; mock it so we can import.
sys.modules.setdefault("faster_whisper", MagicMock())

import aavaaz.transcribe as t  # noqa: E402


def test_srt_timestamp_uses_comma():
    assert t._ts(1.5) == "00:00:01,500"
    assert t._ts(3661.25) == "01:01:01,250"


def test_vtt_timestamp_uses_period():
    # WebVTT requires a period decimal separator, not a comma
    assert t._ts(1.5, ".") == "00:00:01.500"
    assert t._ts(0.0, ".") == "00:00:00.000"


def _fake_model(segments, info):
    model = MagicMock()
    model.transcribe.return_value = (segments, info)
    return model


def test_transcribe_file_vtt_uses_period(tmp_path, capsys):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    seg = MagicMock(start=1.5, end=2.5, text=" hello ", words=[])
    info = MagicMock(language="en", language_probability=0.9, duration=2.5)
    with patch.object(t, "WhisperModel", return_value=_fake_model([seg], info)):
        t.transcribe_file(str(audio), output_format="vtt")
    out = capsys.readouterr().out
    assert out.startswith("WEBVTT")
    assert "00:00:01.500 --> 00:00:02.500" in out


def test_transcribe_file_json_emits_words(tmp_path, capsys):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    word = MagicMock(start=1.5, end=1.9, word="hi")
    seg = MagicMock(start=1.5, end=2.5, text="hi", words=[word])
    info = MagicMock(language="en", language_probability=0.9, duration=2.5)
    with patch.object(t, "WhisperModel", return_value=_fake_model([seg], info)):
        t.transcribe_file(str(audio), output_format="json")
    data = json.loads(capsys.readouterr().out)
    assert data["segments"][0]["words"] == [{"start": 1.5, "end": 1.9, "word": "hi"}]
