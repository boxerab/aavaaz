"""Tests for the serverless Lambda handler."""

import base64
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock heavy dependencies that aren't available in CI
_mock_fw = MagicMock()
sys.modules.setdefault("faster_whisper", _mock_fw)


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module-level caches between tests."""
    import aavaaz.serverless.lambda_handler as mod

    mod._model = None
    mod._s3 = None
    yield


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("AAVAAZ_MODEL", "tiny.en")
    monkeypatch.setenv("AAVAAZ_OUTPUT_FORMAT", "json")
    monkeypatch.setenv("AAVAAZ_ENABLE_FORMAT", "0")
    monkeypatch.setenv("AAVAAZ_ENABLE_PII", "0")


# -- Mock transcription result ------------------------------------------------


def _fake_segments():
    seg = MagicMock()
    seg.start = 0.0
    seg.end = 1.5
    seg.text = " Hello world "
    seg.words = []
    return [seg]


def _fake_info():
    info = MagicMock()
    info.language = "en"
    info.language_probability = 0.99
    info.duration = 1.5
    return info


# -- Tests ---------------------------------------------------------------------


@patch("faster_whisper.WhisperModel")
def test_handler_dispatches_s3(mock_whisper, _env, tmp_path):
    """S3 events should be routed to the S3 handler."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import handler

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "input-bucket"},
                    "object": {"key": "test.wav"},
                }
            }
        ]
    }

    with patch("aavaaz.serverless.lambda_handler._s3_client") as mock_s3:
        s3 = MagicMock()
        mock_s3.return_value = s3
        # download_file copies the file locally — create a dummy
        s3.download_file.side_effect = lambda b, k, p: open(p, "wb").close()

        os.environ["AAVAAZ_OUTPUT_BUCKET"] = "output-bucket"
        result = handler(event, None)
        del os.environ["AAVAAZ_OUTPUT_BUCKET"]

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert len(body["results"]) == 1
    assert body["results"][0]["input"] == "s3://input-bucket/test.wav"
    # put_object is called for both progress reporting and the final transcript
    transcript_calls = [
        c
        for c in s3.put_object.call_args_list
        if c.kwargs.get("Key", "").endswith(".json")
        and not c.kwargs.get("Key", "").endswith(".progress.json")
    ]
    assert len(transcript_calls) == 1


@patch("faster_whisper.WhisperModel")
def test_handler_api_s3_url(mock_whisper, _env):
    """API Gateway with audio_url should download from S3."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import handler

    event = {
        "body": json.dumps({"audio_url": "s3://my-bucket/audio.wav"}),
    }

    with patch("aavaaz.serverless.lambda_handler._s3_client") as mock_s3:
        s3 = MagicMock()
        mock_s3.return_value = s3
        s3.download_file.side_effect = lambda b, k, p: open(p, "wb").close()

        result = handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["language"] == "en"
    assert len(body["segments"]) == 1
    assert body["segments"][0]["text"] == "Hello world"


@patch("faster_whisper.WhisperModel")
def test_handler_api_base64(mock_whisper, _env):
    """API Gateway with base64-encoded audio."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import handler

    audio_bytes = b"\x00" * 100  # dummy
    event = {
        "body": json.dumps(
            {
                "audio_base64": base64.b64encode(audio_bytes).decode(),
                "filename": "test.wav",
            }
        ),
    }

    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["segments"][0]["text"] == "Hello world"


def test_handler_api_bad_url(_env):
    """Non-S3 URLs should be rejected."""
    from aavaaz.serverless.lambda_handler import handler

    event = {"body": json.dumps({"audio_url": "https://evil.com/audio.wav"})}
    result = handler(event, None)
    assert result["statusCode"] == 400


def test_handler_api_missing_body(_env):
    """Missing audio source should return 400."""
    from aavaaz.serverless.lambda_handler import handler

    event = {"body": json.dumps({})}
    result = handler(event, None)
    assert result["statusCode"] == 400


def test_handler_api_invalid_json(_env):
    """Invalid JSON should return 400."""
    from aavaaz.serverless.lambda_handler import handler

    event = {"body": "not json"}
    result = handler(event, None)
    assert result["statusCode"] == 400


def test_handler_cancels_uploaded_transcription(_env, monkeypatch):
    """DELETE /v1/transcription/{key} should mark the job canceled."""
    from aavaaz.serverless.lambda_handler import handler

    monkeypatch.setenv("AAVAAZ_INPUT_BUCKET", "input-bucket")
    monkeypatch.setenv("AAVAAZ_OUTPUT_BUCKET", "output-bucket")
    upload_key = "uploads/test.mov"
    encoded = base64.urlsafe_b64encode(upload_key.encode()).decode().rstrip("=")

    event = {
        "requestContext": {
            "http": {"method": "DELETE", "path": f"/v1/transcription/{encoded}"}
        }
    }

    with patch("aavaaz.serverless.lambda_handler._s3_client") as mock_s3:
        s3 = MagicMock()
        mock_s3.return_value = s3

        result = handler(event, None)

    assert result["statusCode"] == 200
    assert json.loads(result["body"])["status"] == "canceled"
    s3.delete_object.assert_any_call(Bucket="input-bucket", Key=upload_key)
    progress_call = s3.put_object.call_args
    assert progress_call.kwargs["Bucket"] == "output-bucket"
    assert progress_call.kwargs["Key"] == "transcripts/test.progress.json"
    assert json.loads(progress_call.kwargs["Body"].decode())["status"] == "canceled"


def test_handler_s3_failure_writes_failed_status(_env, monkeypatch):
    """S3 processing errors should be visible to polling clients."""
    from aavaaz.serverless.lambda_handler import handler

    monkeypatch.setenv("AAVAAZ_OUTPUT_BUCKET", "output-bucket")
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "input-bucket"},
                    "object": {"key": "uploads/broken.mov"},
                }
            }
        ]
    }

    with patch("aavaaz.serverless.lambda_handler._s3_client") as mock_s3:
        s3 = MagicMock()
        s3.download_file.side_effect = RuntimeError("download failed")
        mock_s3.return_value = s3

        result = handler(event, None)

    assert result["statusCode"] == 200
    progress_call = s3.put_object.call_args
    assert progress_call.kwargs["Key"] == "transcripts/broken.progress.json"
    progress = json.loads(progress_call.kwargs["Body"].decode())
    assert progress["status"] == "failed"
    assert "download failed" in progress["error"]


@patch("faster_whisper.WhisperModel")
def test_model_cached_across_calls(mock_whisper, _env):
    """Model should be loaded once and reused (warm start)."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import _get_model

    m1 = _get_model()
    m2 = _get_model()
    assert m1 is m2
    mock_whisper.assert_called_once()
