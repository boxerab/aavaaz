"""AWS Lambda handler for batch audio transcription.

Supports two trigger modes:

1. **S3 event** — automatically transcribes files uploaded to a bucket.
2. **API Gateway** — POST an audio file URL or base64-encoded payload and
   receive the transcript in the response.

Environment variables
---------------------
AAVAAZ_MODEL          Whisper model name (default: ``small.en``)
AAVAAZ_LANGUAGE       Language code, or empty for auto-detect
AAVAAZ_OUTPUT_FORMAT  ``json`` | ``text`` | ``srt`` | ``vtt`` (default: ``json``)
AAVAAZ_OUTPUT_BUCKET  S3 bucket for transcript output (S3 trigger mode)
AAVAAZ_OUTPUT_PREFIX  Key prefix inside output bucket (default: ``transcripts/``)
AAVAAZ_ENABLE_PII     ``1`` to enable PII redaction (default: ``0``)
AAVAAZ_ENABLE_FORMAT  ``1`` to enable smart formatting (default: ``1``)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

import boto3
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Global model cache — survives across warm Lambda invocations.
# ---------------------------------------------------------------------------
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    """Return a cached WhisperModel, loading on first call."""
    global _model
    if _model is None:
        name = os.environ.get("AAVAAZ_MODEL", "small.en")
        logger.info("Loading Whisper model %s", name)
        _model = WhisperModel(name, device="cpu", compute_type="int8")
        logger.info("Model loaded")
    return _model


# ---------------------------------------------------------------------------
# Post-processing pipeline (optional)
# ---------------------------------------------------------------------------

def _build_pipeline() -> list[Any]:
    """Return a list of segment transform functions based on env config."""
    fns: list[Any] = []

    if os.environ.get("AAVAAZ_ENABLE_FORMAT", "1") == "1":
        from aavaaz.features.formatting import smart_format
        fns.append(smart_format)

    if os.environ.get("AAVAAZ_ENABLE_PII", "0") == "1":
        from aavaaz.features.pii_redaction import redact_pii
        fns.append(redact_pii)

    return fns


def _apply_pipeline(segment: dict, pipeline: list[Any]) -> dict:
    for fn in pipeline:
        segment = fn(segment)
    return segment


# ---------------------------------------------------------------------------
# Core transcription
# ---------------------------------------------------------------------------

def _transcribe(audio_path: str) -> dict:
    """Transcribe a local audio file and return a result dict."""
    model = _get_model()
    language = os.environ.get("AAVAAZ_LANGUAGE") or None
    segments, info = model.transcribe(audio_path, language=language, word_timestamps=True)
    segments = list(segments)

    pipeline = _build_pipeline()
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
        entry = _apply_pipeline(entry, pipeline)
        results.append(entry)

    return {
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": results,
    }


def _format_output(result: dict) -> str:
    """Format the transcription result according to AAVAAZ_OUTPUT_FORMAT."""
    fmt = os.environ.get("AAVAAZ_OUTPUT_FORMAT", "json")
    if fmt == "text":
        return "\n".join(seg["text"] for seg in result["segments"])
    if fmt == "srt":
        lines = []
        for i, seg in enumerate(result["segments"], 1):
            lines.append(str(i))
            lines.append(f"{_ts(seg['start'])} --> {_ts(seg['end'])}")
            lines.append(seg["text"])
            lines.append("")
        return "\n".join(lines)
    if fmt == "vtt":
        lines = ["WEBVTT", ""]
        for seg in result["segments"]:
            lines.append(f"{_ts(seg['start'])} --> {_ts(seg['end'])}")
            lines.append(seg["text"])
            lines.append("")
        return "\n".join(lines)
    # default: json
    return json.dumps(result, indent=2)


def _ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ---------------------------------------------------------------------------
# Lambda handlers
# ---------------------------------------------------------------------------

_s3 = None


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def handler(event: dict, context: Any) -> dict:
    """Main Lambda entry point — dispatches to S3 or API Gateway handler."""
    if "Records" in event:
        return _handle_s3(event, context)
    return _handle_api(event, context)


def _handle_s3(event: dict, context: Any) -> dict:
    """Process S3 put events — download, transcribe, upload result."""
    output_bucket = os.environ.get("AAVAAZ_OUTPUT_BUCKET", "")
    output_prefix = os.environ.get("AAVAAZ_OUTPUT_PREFIX", "transcripts/")
    s3 = _s3_client()
    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        logger.info("Processing s3://%s/%s", bucket, key)

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = os.path.join(tmpdir, os.path.basename(key))
            s3.download_file(bucket, key, local_path)
            result = _transcribe(local_path)

        output = _format_output(result)
        stem = Path(key).stem
        ext = "json" if os.environ.get("AAVAAZ_OUTPUT_FORMAT", "json") == "json" else "txt"
        out_key = f"{output_prefix}{stem}.{ext}"

        if output_bucket:
            s3.put_object(Bucket=output_bucket, Key=out_key, Body=output.encode())
            logger.info("Wrote s3://%s/%s", output_bucket, out_key)
            results.append({"input": f"s3://{bucket}/{key}", "output": f"s3://{output_bucket}/{out_key}"})
        else:
            # Same bucket
            s3.put_object(Bucket=bucket, Key=out_key, Body=output.encode())
            results.append({"input": f"s3://{bucket}/{key}", "output": f"s3://{bucket}/{out_key}"})

    return {"statusCode": 200, "body": json.dumps({"results": results})}


def _handle_api(event: dict, context: Any) -> dict:
    """Process API Gateway (REST or HTTP API) requests.

    Accepts:
    - ``{"audio_url": "s3://bucket/key"}`` — download from S3
    - ``{"audio_base64": "<base64>", "filename": "audio.wav"}`` — inline audio
    """
    try:
        body = event.get("body", "{}")
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode()
        payload = json.loads(body) if isinstance(body, str) else body
    except (json.JSONDecodeError, ValueError):
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON body"})}

    with tempfile.TemporaryDirectory() as tmpdir:
        if "audio_url" in payload:
            url = payload["audio_url"]
            if not url.startswith("s3://"):
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "Only s3:// URLs supported"}),
                }
            parts = url[5:].split("/", 1)
            if len(parts) != 2:
                return {"statusCode": 400, "body": json.dumps({"error": "Invalid S3 URL"})}
            bucket, key = parts
            local_path = os.path.join(tmpdir, os.path.basename(key))
            _s3_client().download_file(bucket, key, local_path)

        elif "audio_base64" in payload:
            filename = payload.get("filename", f"{uuid.uuid4().hex}.wav")
            safe_name = Path(filename).name
            local_path = os.path.join(tmpdir, safe_name)
            audio_bytes = base64.b64decode(payload["audio_base64"])
            Path(local_path).write_bytes(audio_bytes)

        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Provide 'audio_url' or 'audio_base64'"}),
            }

        result = _transcribe(local_path)

    output = _format_output(result)
    fmt = os.environ.get("AAVAAZ_OUTPUT_FORMAT", "json")
    content_type = "application/json" if fmt == "json" else "text/plain"

    return {
        "statusCode": 200,
        "headers": {"Content-Type": content_type},
        "body": output,
    }
