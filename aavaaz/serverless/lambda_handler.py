"""AWS Lambda handler for batch audio transcription.

Supports three trigger modes:

1. **S3 event** — automatically transcribes files uploaded to a bucket.
2. **API Gateway (JSON)** — POST an audio file URL or base64-encoded payload and
   receive the transcript in the response.
3. **API Gateway (multipart)** — POST a file via multipart/form-data (used by
   the web demo drag-and-drop UI).

The handler also serves the web demo UI on GET /.

Environment variables
---------------------
AAVAAZ_MODEL          Whisper model name (default: ``small``)
AAVAAZ_LANGUAGE       Language code, or empty for auto-detect
AAVAAZ_OUTPUT_FORMAT  ``json`` | ``text`` | ``srt`` | ``vtt`` (default: ``json``)
AAVAAZ_OUTPUT_BUCKET  S3 bucket for transcript output (S3 trigger mode)
AAVAAZ_OUTPUT_PREFIX  Key prefix inside output bucket (default: ``transcripts/``)
AAVAAZ_ENABLE_PII     ``1`` to enable PII redaction (default: ``0``)
AAVAAZ_ENABLE_FORMAT  ``1`` to enable smart formatting (default: ``1``)
AAVAAZ_ENABLE_PARAGRAPHS     ``1`` to add paragraph segmentation (default: ``0``)
AAVAAZ_ENABLE_INTELLIGENCE   ``1`` to add sentiment/topics/entities (default: ``0``)
AAVAAZ_STORE_AUDIO    ``1`` to store uploaded audio in S3 (default: ``0``)
AAVAAZ_AUDIO_BUCKET   S3 bucket for stored audio (defaults to output bucket)
AAVAAZ_AUDIO_PREFIX   Key prefix for stored audio (default: ``audio/``)
AAVAAZ_REQUIRE_API_KEY  ``1`` to require a valid SaaS API key on the API paths
                        (default: ``0``; the web-demo UI and health stay open)
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# CORS headers for browser access from GitHub Pages.
# ---------------------------------------------------------------------------
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
}


def _response(status_code: int, body: str, headers: dict | None = None) -> dict:
    """Build an API Gateway response with CORS headers."""
    h = {**_CORS_HEADERS}
    if headers:
        h.update(headers)
    return {"statusCode": status_code, "headers": h, "body": body}


# ---------------------------------------------------------------------------
# Global model cache — survives across warm Lambda invocations.
# ---------------------------------------------------------------------------
_model: Any = None


def _get_model() -> Any:
    """Return a cached WhisperModel, loading on first call."""
    global _model
    if _model is None:
        try:
            from whisper_live.transcriber.transcriber_faster_whisper import WhisperModel
        except ImportError:
            from faster_whisper import WhisperModel

        name = os.environ.get("AAVAAZ_MODEL", "small")
        logger.info("Loading Whisper model %s", name)
        _model = WhisperModel(name, device="cpu", compute_type="int8")
        logger.info("Model loaded")
    return _model


# ---------------------------------------------------------------------------
# Post-processing pipeline (optional)
# ---------------------------------------------------------------------------


def _build_pipeline(features: dict | None = None) -> list[Any]:
    """Return per-segment text transforms.

    With no features dict the pipeline is configured from AAVAAZ_* env vars (the
    deployment default). A per-request features dict (the dashboard FeaturesConfig
    shape) overrides that env config.
    """
    if features is None:
        fns: list[Any] = []
        if os.environ.get("AAVAAZ_ENABLE_FORMAT", "1") == "1":
            from aavaaz.features.formatting import smart_format

            fns.append(smart_format)
        if os.environ.get("AAVAAZ_ENABLE_PII", "0") == "1":
            from aavaaz.features.pii_redaction import redact_pii

            fns.append(redact_pii)
        return fns

    fns = []

    fmt = features.get("formatting") or {}
    if fmt.get("enabled"):
        from aavaaz.features.formatting import format_transcript

        capitalize = bool(fmt.get("capitalize", True))
        numbers = bool(fmt.get("numbers", True))
        smart = bool(fmt.get("smart", False))
        fns.append(
            lambda t: format_transcript(
                t, capitalize=capitalize, numbers=numbers, smart=smart
            )
        )

    pii = features.get("pii") or {}
    if pii.get("enabled"):
        from aavaaz.features.pii_redaction import redact_pii

        pii_types = set(pii.get("types") or []) or None
        custom = _compile_custom_pii(pii.get("customPatterns") or [])
        fns.append(
            lambda t: redact_pii(t, pii_types=pii_types, custom_patterns=custom)
        )

    prof = features.get("profanity") or {}
    if prof.get("enabled"):
        from aavaaz.features.profanity_filter import filter_profanity

        mode = prof.get("mode", "partial")
        extra = set(prof.get("extraWords") or []) or None
        fns.append(lambda t: filter_profanity(t, mode=mode, extra_words=extra))

    intel = features.get("intelligence") or {}
    if intel.get("fillerRemoval"):
        from aavaaz.features.audio_intelligence import remove_filler_words

        aggressive = bool(intel.get("fillerAggressive", False))
        fns.append(lambda t: remove_filler_words(t, aggressive=aggressive))

    return fns


def _compile_custom_pii(patterns: list[dict]) -> dict | None:
    """Compile dashboard customPatterns into redact_pii's {label: (regex, repl)} form."""
    compiled: dict[str, Any] = {}
    for p in patterns:
        pattern = p.get("pattern")
        if not pattern:
            continue
        try:
            compiled[p.get("label", pattern)] = (
                re.compile(pattern),
                p.get("replacement", "[REDACTED]"),
            )
        except re.error:
            logger.warning("Skipping invalid custom PII pattern: %s", pattern)
    return compiled or None


def _apply_pipeline(segment: dict, pipeline: list[Any]) -> dict:
    for fn in pipeline:
        segment["text"] = fn(segment["text"])
    return segment


def _detect_stable_language(model: Any, audio_path: str) -> str | None:
    """Auto-detect language using a short consensus window.

    Uses up to three 20s probes from the beginning of the audio and locks to
    the weighted-majority language to reduce transient language flips.
    """
    try:
        from faster_whisper.audio import decode_audio
    except Exception:
        return None

    try:
        audio = decode_audio(audio_path, sampling_rate=16000)
    except Exception:
        logger.exception("Language probe decode failed")
        return None

    if audio is None or len(audio) == 0:
        return None

    sample_rate = 16000
    window = 20 * sample_rate
    step = 10 * sample_rate
    max_probes = 3

    scores: dict[str, float] = {}
    probes = 0

    for i in range(max_probes):
        start = i * step
        end = min(start + window, len(audio))
        chunk = audio[start:end]
        if len(chunk) < 5 * sample_rate:
            break

        try:
            _, info = model.transcribe(
                chunk,
                language=None,
                vad_filter=True,
                word_timestamps=False,
            )
        except Exception:
            continue

        lang = getattr(info, "language", None)
        prob = float(getattr(info, "language_probability", 0.0) or 0.0)
        if not lang:
            continue

        scores[lang] = scores.get(lang, 0.0) + max(prob, 0.01)
        probes += 1

        if prob >= 0.9:
            logger.info(
                "Language probe locked early: lang=%s prob=%.2f",
                lang,
                prob,
            )
            return lang

    if not scores or probes == 0:
        return None

    best_lang = max(scores, key=scores.get)
    total = sum(scores.values())
    ratio = scores[best_lang] / total if total > 0 else 0.0

    if probes >= 2 and ratio >= 0.65:
        logger.info(
            "Language probe consensus: lang=%s ratio=%.2f probes=%d",
            best_lang,
            ratio,
            probes,
        )
        return best_lang

    logger.info(
        "Language probe inconclusive: probes=%d best=%s ratio=%.2f",
        probes,
        best_lang,
        ratio,
    )
    return None


# ---------------------------------------------------------------------------
# Core transcription
# ---------------------------------------------------------------------------


def _store_audio(audio_path: str, filename: str | None = None) -> str | None:
    """Optionally store audio to S3. Returns the S3 key or None if disabled."""
    if os.environ.get("AAVAAZ_STORE_AUDIO", "0") != "1":
        return None

    bucket = os.environ.get("AAVAAZ_AUDIO_BUCKET") or os.environ.get(
        "AAVAAZ_OUTPUT_BUCKET", ""
    )
    if not bucket:
        logger.warning("AAVAAZ_STORE_AUDIO=1 but no bucket configured")
        return None

    prefix = os.environ.get("AAVAAZ_AUDIO_PREFIX", "audio/")
    name = filename or os.path.basename(audio_path)
    key = f"{prefix}{uuid.uuid4().hex}_{name}"

    try:
        _s3_client().upload_file(audio_path, bucket, key)
        logger.info("Stored audio: s3://%s/%s", bucket, key)
        return key
    except Exception:
        logger.exception("Failed to store audio to s3://%s/%s", bucket, key)
        return None


def _transcribe(
    audio_path: str,
    progress_callback=None,
    features: dict | None = None,
    hotwords: str | None = None,
) -> dict:
    """Transcribe a local audio file and return a result dict.

    Args:
        audio_path: Path to the audio file.
        progress_callback: Optional callable(percent: int) called as segments complete.
        features: Optional per-request feature config overriding the env defaults.
        hotwords: Optional custom-vocabulary string to bias recognition.
    """
    file_size = os.path.getsize(audio_path)
    logger.info(
        "Starting transcription: file=%s size_bytes=%d model=%s",
        os.path.basename(audio_path),
        file_size,
        os.environ.get("AAVAAZ_MODEL", "small"),
    )
    t0 = time.time()

    model = _get_model()
    language = os.environ.get("AAVAAZ_LANGUAGE") or None
    if language is None:
        language = _detect_stable_language(model, audio_path)

    segments, info = model.transcribe(
        audio_path, language=language, word_timestamps=True, hotwords=hotwords or None
    )

    pipeline = _build_pipeline(features)
    results = []
    last_progress_pct = 0
    for seg in segments:
        entry = {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        }
        if seg.words:
            entry["words"] = [
                {
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability,
                }
                for w in seg.words
            ]
        entry = _apply_pipeline(entry, pipeline)
        results.append(entry)

        # Report progress based on audio position
        if progress_callback and info.duration > 0:
            pct = min(95, int((seg.end / info.duration) * 100))
            if pct >= last_progress_pct + 5:  # Report every 5%
                last_progress_pct = pct
                progress_callback(pct)

    elapsed = time.time() - t0
    logger.info(
        "Transcription complete: duration=%.1fs segments=%d language=%s elapsed=%.2fs",
        info.duration,
        len(results),
        info.language,
        elapsed,
    )

    result = {
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": results,
    }
    _enrich_result(result, features)
    return result


def _enrich_result(result: dict, features: dict | None = None) -> None:
    """Attach optional paragraph segmentation and intelligence analysis, in place."""
    # paragraphs stay env-gated: the dashboard config carries no paragraph toggle
    if os.environ.get("AAVAAZ_ENABLE_PARAGRAPHS", "0") == "1":
        from aavaaz.features.utterance import segment_into_paragraphs

        result["paragraphs"] = segment_into_paragraphs(result["segments"])

    intel_opts = _intelligence_options(features)
    if intel_opts is not None:
        from aavaaz.features.audio_intelligence import analyze_transcript

        full_text = " ".join(s["text"] for s in result["segments"])
        result["intelligence"] = analyze_transcript(full_text, **intel_opts)


def _intelligence_options(features: dict | None) -> dict | None:
    """Resolve analyze_transcript kwargs from features/env, or None if disabled."""
    if features is None:
        if os.environ.get("AAVAAZ_ENABLE_INTELLIGENCE", "0") == "1":
            return {}
        return None

    intel = features.get("intelligence") or {}
    if not any(
        intel.get(k)
        for k in ("sentiment", "topics", "entities", "summarize", "highlights")
    ):
        return None
    return {
        "sentiment": bool(intel.get("sentiment")),
        "topics": bool(intel.get("topics")),
        "entities": bool(intel.get("entities")),
        "summary": bool(intel.get("summarize")),
        "highlights": bool(intel.get("highlights")),
        "summary_sentences": int(intel.get("summarySentences", 3)),
        "topic_count": int(intel.get("topicsTopN", 5)),
        "max_highlights": int(intel.get("maxHighlights", 10)),
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


def _extract_bearer(event: dict) -> str | None:
    """Return the Bearer token from the Authorization header, if present."""
    headers = event.get("headers") or {}
    for k, v in headers.items():
        if k.lower() == "authorization" and isinstance(v, str):
            parts = v.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1].strip()
    return None


def _auth_error(event: dict) -> dict | None:
    """Return a 401 response when API-key auth is required and the key is missing/invalid.

    Auth is opt-in via AAVAAZ_REQUIRE_API_KEY=1 and validates the Bearer token against
    the SaaS DynamoDB store. Returns None when the request is allowed.
    """
    if os.environ.get("AAVAAZ_REQUIRE_API_KEY", "0") != "1":
        return None
    token = _extract_bearer(event)
    if not token:
        return _response(401, json.dumps({"error": "Missing API key"}))
    from aavaaz.api import dynamo_store

    if dynamo_store.validate_api_key(token) is None:
        return _response(401, json.dumps({"error": "Invalid API key"}))
    return None


def handler(event: dict, context: Any) -> dict:
    """Main Lambda entry point — dispatches to S3, web UI, or API handler."""
    request_id = (
        getattr(context, "aws_request_id", uuid.uuid4().hex)
        if context
        else uuid.uuid4().hex
    )
    logger.info("Request started: request_id=%s", request_id)

    try:
        if "Records" in event:
            return _handle_s3(event, context)

        # API Gateway v2 (HTTP API) uses requestContext.http.method
        http = event.get("requestContext", {}).get("http", {})
        method = http.get("method", event.get("httpMethod", "POST"))
        path = http.get("path", event.get("rawPath", event.get("path", "/")))

        # CORS preflight
        if method == "OPTIONS":
            return _response(204, "")

        if method == "GET":
            if path == "/health":
                return _response(200, json.dumps({"status": "ok", "mode": "batch"}))
            if path == "/v1/upload-url":
                return _auth_error(event) or _handle_upload_url(event)
            if path.startswith("/v1/transcription/"):
                return _auth_error(event) or _handle_transcription_status(event, path)
            return _handle_web_ui(event, path)

        if method == "DELETE" and path.startswith("/v1/transcription/"):
            return _auth_error(event) or _handle_transcription_cancel(path)

        return _auth_error(event) or _handle_api(event, context)
    except Exception:
        logger.exception("Unhandled error: request_id=%s", request_id)
        return _response(500, json.dumps({"error": "Internal server error"}))


def _handle_upload_url(event: dict) -> dict:
    """Generate a presigned S3 PUT URL for direct browser upload.

    Query params:
      filename — original filename (used as S3 key suffix)
      content_type — MIME type (default: application/octet-stream)
    """
    params = event.get("queryStringParameters") or {}
    filename = params.get("filename", f"{uuid.uuid4().hex}.wav")
    content_type = params.get("content_type", "application/octet-stream")

    bucket = os.environ.get("AAVAAZ_INPUT_BUCKET", "")
    if not bucket:
        # Fall back to the audio_input bucket from env
        bucket = os.environ.get("AAVAAZ_AUDIO_INPUT_BUCKET", "")
    if not bucket:
        return _response(500, json.dumps({"error": "Upload bucket not configured"}))

    # Sanitize filename
    safe_name = Path(filename).name
    key = f"uploads/{uuid.uuid4().hex}_{safe_name}"

    # Optional per-request feature config, url-safe base64 so it survives as ASCII
    # S3 object metadata and gets read back in the S3-trigger transcription path.
    put_params: dict[str, Any] = {
        "Bucket": bucket,
        "Key": key,
        "ContentType": content_type,
    }
    required_headers = {"Content-Type": content_type}
    metadata = {
        name: params[q]
        for name, q in (("features", "features_b64"), ("hotwords", "hotwords_b64"))
        if params.get(q)
    }
    if metadata:
        put_params["Metadata"] = metadata
        required_headers.update({f"x-amz-meta-{k}": v for k, v in metadata.items()})

    s3 = _s3_client()
    presigned_url = s3.generate_presigned_url(
        "put_object", Params=put_params, ExpiresIn=3600
    )

    return _response(
        200,
        json.dumps(
            {
                "upload_url": presigned_url,
                "key": key,
                "bucket": bucket,
                "required_headers": required_headers,
            }
        ),
        {"Content-Type": "application/json"},
    )


def _decode_upload_key(path: str) -> str | None:
    encoded_key = path[len("/v1/transcription/") :]
    try:
        padded = encoded_key + "=" * (-len(encoded_key) % 4)
        return base64.urlsafe_b64decode(padded).decode()
    except Exception:
        return None


def _transcription_keys(upload_key: str) -> tuple[str, str]:
    output_prefix = os.environ.get("AAVAAZ_OUTPUT_PREFIX", "transcripts/")
    stem = Path(upload_key).stem
    fmt = os.environ.get("AAVAAZ_OUTPUT_FORMAT", "json")
    ext = "json" if fmt == "json" else "txt"
    return f"{output_prefix}{stem}.{ext}", f"{output_prefix}{stem}.progress.json"


def _read_progress_status(s3: Any, bucket: str, progress_key: str) -> dict | None:
    try:
        obj = s3.get_object(Bucket=bucket, Key=progress_key)
        return json.loads(obj["Body"].read().decode())
    except Exception:
        return None


def _handle_transcription_status(event: dict, path: str) -> dict:
    """Check if a transcription result exists for a given upload key.

    GET /v1/transcription/{key_base64}
    Returns the transcript if ready, or 202 if still processing.
    """
    upload_key = _decode_upload_key(path)
    if upload_key is None:
        return _response(400, json.dumps({"error": "Invalid key encoding"}))

    output_bucket = os.environ.get("AAVAAZ_OUTPUT_BUCKET", "")

    if not output_bucket:
        return _response(500, json.dumps({"error": "Output bucket not configured"}))

    out_key, progress_key = _transcription_keys(upload_key)
    s3 = _s3_client()

    progress_status = _read_progress_status(s3, output_bucket, progress_key)
    if progress_status and progress_status.get("status") in {"canceled", "failed"}:
        return _response(
            200, json.dumps(progress_status), {"Content-Type": "application/json"}
        )

    try:
        obj = s3.get_object(Bucket=output_bucket, Key=out_key)
        body = obj["Body"].read().decode()
        # Clean up progress file
        with contextlib.suppress(Exception):
            s3.delete_object(Bucket=output_bucket, Key=progress_key)
        return _response(
            200,
            json.dumps({"status": "completed", "transcript": body}),
            {"Content-Type": "application/json"},
        )
    except s3.exceptions.NoSuchKey:
        progress = (progress_status or {}).get("progress", 0)
        return _response(
            202,
            json.dumps({"status": "processing", "progress": progress}),
            {"Content-Type": "application/json"},
        )
    except Exception:
        logger.exception("Error checking transcription status for key=%s", upload_key)
        return _response(
            202,
            json.dumps({"status": "processing", "progress": 0}),
            {"Content-Type": "application/json"},
        )


def _handle_transcription_cancel(path: str) -> dict:
    """Cancel client-side polling and remove pending upload/status objects."""
    upload_key = _decode_upload_key(path)
    if upload_key is None:
        return _response(400, json.dumps({"error": "Invalid key encoding"}))

    input_bucket = os.environ.get("AAVAAZ_INPUT_BUCKET", "") or os.environ.get(
        "AAVAAZ_AUDIO_INPUT_BUCKET", ""
    )
    output_bucket = os.environ.get("AAVAAZ_OUTPUT_BUCKET", "")
    if not output_bucket:
        return _response(500, json.dumps({"error": "Output bucket not configured"}))

    out_key, progress_key = _transcription_keys(upload_key)
    s3 = _s3_client()

    if input_bucket:
        with contextlib.suppress(Exception):
            s3.delete_object(Bucket=input_bucket, Key=upload_key)

    with contextlib.suppress(Exception):
        s3.delete_object(Bucket=output_bucket, Key=out_key)

    s3.put_object(
        Bucket=output_bucket,
        Key=progress_key,
        Body=json.dumps({"status": "canceled", "progress": 0}).encode(),
        ContentType="application/json",
    )

    return _response(
        200,
        json.dumps({"status": "canceled"}),
        {"Content-Type": "application/json"},
    )


def _decode_b64(raw: str | None) -> str | None:
    """Decode a url-safe base64 string stored in S3 object metadata."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        padded = raw + "=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode(padded).decode()
    except (ValueError, UnicodeDecodeError):
        return None


def _decode_features_metadata(raw: str | None) -> dict | None:
    """Decode the url-safe base64 features config stored in S3 object metadata."""
    decoded = _decode_b64(raw)
    if decoded is None:
        return None
    try:
        return json.loads(decoded)
    except json.JSONDecodeError:
        logger.warning("Ignoring unparseable features metadata")
        return None


def _read_object_config(s3: Any, bucket: str, key: str) -> tuple[dict | None, str | None]:
    """Read the optional per-request features + hotwords from S3 object metadata."""
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception:
        logger.warning("Could not read metadata for s3://%s/%s", bucket, key)
        return None, None
    meta = head.get("Metadata") or {}
    return _decode_features_metadata(meta.get("features")), _decode_b64(meta.get("hotwords"))


def _handle_s3(event: dict, context: Any) -> dict:
    """Process S3 put events — download, transcribe, upload result."""
    output_bucket = os.environ.get("AAVAAZ_OUTPUT_BUCKET", "")
    output_prefix = os.environ.get("AAVAAZ_OUTPUT_PREFIX", "transcripts/")
    s3 = _s3_client()
    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        obj_size = record["s3"]["object"].get("size", 0)
        logger.info("Processing s3://%s/%s size_bytes=%d", bucket, key, obj_size)

        stem = Path(key).stem
        progress_key = f"{output_prefix}{stem}.progress.json"

        def _write_status(
            status: str,
            progress: int,
            error: str | None = None,
            status_key: str = progress_key,
        ) -> None:
            if not output_bucket:
                return
            payload: dict[str, Any] = {"status": status, "progress": progress}
            if error:
                payload["error"] = error
            with contextlib.suppress(Exception):
                s3.put_object(
                    Bucket=output_bucket,
                    Key=status_key,
                    Body=json.dumps(payload).encode(),
                    ContentType="application/json",
                )

        def _report_progress(pct: int, _key: str = progress_key) -> None:
            """Write progress update to S3 for client polling."""
            _write_status("processing", pct)

        try:
            features, hotwords = _read_object_config(s3, bucket, key)
            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = os.path.join(tmpdir, os.path.basename(key))
                s3.download_file(bucket, key, local_path)
                _store_audio(local_path, os.path.basename(key))
                result = _transcribe(
                    local_path,
                    progress_callback=_report_progress if output_bucket else None,
                    features=features,
                    hotwords=hotwords,
                )

            if output_bucket:
                progress_status = _read_progress_status(s3, output_bucket, progress_key)
                if progress_status and progress_status.get("status") == "canceled":
                    logger.info(
                        "Skipping canceled transcription for s3://%s/%s", bucket, key
                    )
                    continue

            output = _format_output(result)
            ext = (
                "json"
                if os.environ.get("AAVAAZ_OUTPUT_FORMAT", "json") == "json"
                else "txt"
            )
            out_key = f"{output_prefix}{stem}.{ext}"

            if output_bucket:
                s3.put_object(Bucket=output_bucket, Key=out_key, Body=output.encode())
                logger.info("Wrote s3://%s/%s", output_bucket, out_key)
                results.append(
                    {
                        "input": f"s3://{bucket}/{key}",
                        "output": f"s3://{output_bucket}/{out_key}",
                    }
                )
            else:
                # Same bucket
                s3.put_object(Bucket=bucket, Key=out_key, Body=output.encode())
                results.append(
                    {
                        "input": f"s3://{bucket}/{key}",
                        "output": f"s3://{bucket}/{out_key}",
                    }
                )
        except Exception as exc:
            logger.exception("Failed processing s3://%s/%s", bucket, key)
            _write_status("failed", 0, str(exc))
            continue

        # Delete the input audio file from S3 after successful transcription
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            logger.info("Deleted input s3://%s/%s", bucket, key)
        except Exception:
            logger.warning("Failed to delete input s3://%s/%s", bucket, key)

    return {"statusCode": 200, "body": json.dumps({"results": results})}


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

_WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "web")


def _handle_web_ui(event: dict, path: str) -> dict:
    """Serve the web demo UI static files."""
    if path.startswith("/static/"):
        filename = path[len("/static/") :]
        # Sanitize: only allow known safe filenames
        safe_names = {"Collabora_Logo.svg": "image/svg+xml"}
        if filename not in safe_names:
            return _response(404, "Not found")
        filepath = os.path.join(_WEB_DIR, filename)
        with open(filepath) as f:
            content = f.read()
        return _response(200, content, {"Content-Type": safe_names[filename]})

    # Default: serve index.html
    filepath = os.path.join(_WEB_DIR, "index.html")
    with open(filepath) as f:
        content = f.read()
    return _response(200, content, {"Content-Type": "text/html"})


# ---------------------------------------------------------------------------
# Multipart form-data parsing
# ---------------------------------------------------------------------------


def _parse_multipart(event: dict) -> tuple[bytes | None, str | None, str | None]:
    """Extract file bytes, filename, and response_format from multipart form-data.

    Returns (file_bytes, filename, response_format) or (None, None, None) on failure.
    """
    content_type = ""
    headers = event.get("headers", {})
    for k, v in headers.items():
        if k.lower() == "content-type":
            content_type = v
            break

    if "boundary=" not in content_type:
        return None, None, None

    boundary = content_type.split("boundary=")[-1].strip()

    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        body_bytes = base64.b64decode(body)
    else:
        body_bytes = body.encode() if isinstance(body, str) else body

    # Parse multipart boundaries
    boundary_bytes = f"--{boundary}".encode()
    parts = body_bytes.split(boundary_bytes)

    file_bytes = None
    filename = None
    response_format = None

    for part in parts:
        if b"Content-Disposition:" not in part and b"content-disposition:" not in part:
            continue

        # Split headers from body at double newline
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            header_end = part.find(b"\n\n")
            if header_end == -1:
                continue
            header_section = part[:header_end].decode(errors="replace")
            part_body = part[header_end + 2 :]
        else:
            header_section = part[:header_end].decode(errors="replace")
            part_body = part[header_end + 4 :]

        # Strip trailing \r\n
        if part_body.endswith(b"\r\n"):
            part_body = part_body[:-2]

        header_lower = header_section.lower()
        if 'name="file"' in header_lower or 'name="file"' in header_section:
            file_bytes = part_body
            # Extract filename
            for token in header_section.split(";"):
                token = token.strip()
                if token.lower().startswith("filename="):
                    filename = token.split("=", 1)[1].strip('" ')
        elif 'name="response_format"' in header_lower:
            response_format = part_body.decode(errors="replace").strip()

    return file_bytes, filename, response_format


def _handle_api(event: dict, context: Any) -> dict:
    """Process API Gateway (REST or HTTP API) requests.

    Accepts:
    - multipart/form-data with a ``file`` field (web demo)
    - ``{"audio_url": "s3://bucket/key"}`` — download from S3
    - ``{"audio_base64": "<base64>", "filename": "audio.wav"}`` — inline audio
    """
    # Check for multipart form-data first
    headers = event.get("headers", {})
    content_type = ""
    for k, v in headers.items():
        if k.lower() == "content-type":
            content_type = v
            break

    if "multipart/form-data" in content_type:
        return _handle_multipart(event)

    try:
        body = event.get("body", "{}")
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode()
        payload = json.loads(body) if isinstance(body, str) else body
    except (json.JSONDecodeError, ValueError):
        logger.warning("Invalid JSON body received")
        return _response(400, json.dumps({"error": "Invalid JSON body"}))

    with tempfile.TemporaryDirectory() as tmpdir:
        if "audio_url" in payload:
            url = payload["audio_url"]
            if not url.startswith("s3://"):
                return _response(
                    400, json.dumps({"error": "Only s3:// URLs supported"})
                )
            parts = url[5:].split("/", 1)
            if len(parts) != 2:
                return _response(400, json.dumps({"error": "Invalid S3 URL"}))
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
            return _response(
                400, json.dumps({"error": "Provide 'audio_url' or 'audio_base64'"})
            )

        _store_audio(local_path)
        features = payload.get("features") if isinstance(payload, dict) else None
        hotwords = payload.get("hotwords") if isinstance(payload, dict) else None
        result = _transcribe(local_path, features=features, hotwords=hotwords)

    callback_url = payload.get("callback_url")
    if callback_url:
        from aavaaz.features.webhook import send_webhook

        send_webhook(callback_url, result)

    output = _format_output(result)
    fmt = os.environ.get("AAVAAZ_OUTPUT_FORMAT", "json")
    content_type = "application/json" if fmt == "json" else "text/plain"

    return _response(200, output, {"Content-Type": content_type})


def _handle_multipart(event: dict) -> dict:
    """Handle multipart/form-data file upload from the web demo."""
    file_bytes, filename, response_format = _parse_multipart(event)
    if file_bytes is None:
        return _response(400, json.dumps({"error": "No file found in multipart data"}))

    max_size = 25 * 1024 * 1024  # 25 MB
    if len(file_bytes) > max_size:
        return _response(
            413, json.dumps({"error": "File too large. Maximum size is 25 MB."})
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        safe_name = Path(filename or "audio.wav").name
        local_path = os.path.join(tmpdir, safe_name)
        Path(local_path).write_bytes(file_bytes)
        logger.info(
            "Multipart upload: filename=%s size_bytes=%d", safe_name, len(file_bytes)
        )
        _store_audio(local_path, safe_name)
        result = _transcribe(local_path)

    fmt = response_format or os.environ.get("AAVAAZ_OUTPUT_FORMAT", "json")
    if fmt == "text":
        text = "\n".join(seg["text"] for seg in result["segments"])
        return _response(200, text, {"Content-Type": "text/plain"})
    return _response(
        200, json.dumps(result, indent=2), {"Content-Type": "application/json"}
    )
