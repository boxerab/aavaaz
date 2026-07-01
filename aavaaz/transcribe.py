"""Offline file transcription using faster-whisper."""

import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel


def transcribe_file(
    path: str,
    model: str = "large-v3",
    output_format: str = "text",
    language: str | None = None,
):
    """Transcribe an audio file and print the result."""
    audio_path = Path(path)
    if not audio_path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    whisper = WhisperModel(model, device="auto", compute_type="auto")

    segments, info = whisper.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=(output_format == "json"),
    )

    segments = list(segments)

    if output_format == "text":
        for seg in segments:
            print(seg.text.strip())

    elif output_format == "json":
        result = {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "segments": [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                    "words": [
                        {"start": w.start, "end": w.end, "word": w.word}
                        for w in (seg.words or [])
                    ],
                }
                for seg in segments
            ],
        }
        print(json.dumps(result, indent=2))

    elif output_format == "srt":
        for i, seg in enumerate(segments, 1):
            print(i)
            print(f"{_ts(seg.start)} --> {_ts(seg.end)}")
            print(seg.text.strip())
            print()

    elif output_format == "vtt":
        print("WEBVTT\n")
        for seg in segments:
            print(f"{_ts(seg.start, '.')} --> {_ts(seg.end, '.')}")
            print(seg.text.strip())
            print()


def _ts(seconds: float, sep: str = ",") -> str:
    """Format seconds as an SRT/VTT timestamp. SRT uses a comma, VTT a period."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"
