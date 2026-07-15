"""Tests for the serverless Lambda handler."""

import base64
import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# Mock heavy dependencies that aren't available in CI
_mock_fw = MagicMock()
sys.modules.setdefault("faster_whisper", _mock_fw)

# lambda_handler tries `from whisper_live.transcriber.transcriber_faster_whisper
# import WhisperModel` first; make that submodule a real, empty ModuleType so the
# import raises ImportError and the handler falls back to the mocked faster_whisper.
sys.modules.setdefault("whisper_live", MagicMock())
sys.modules.setdefault("whisper_live.transcriber", MagicMock())
sys.modules.setdefault(
    "whisper_live.transcriber.transcriber_faster_whisper",
    types.ModuleType("whisper_live.transcriber.transcriber_faster_whisper"),
)


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
def test_handler_dispatches_s3(mock_whisper, _env, tmp_path, monkeypatch):
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

        monkeypatch.setenv("AAVAAZ_OUTPUT_BUCKET", "output-bucket")
        result = handler(event, None)

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
def test_handler_adds_paragraphs_when_enabled(mock_whisper, _env, monkeypatch):
    """AAVAAZ_ENABLE_PARAGRAPHS should add paragraph segmentation to the output."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model
    monkeypatch.setenv("AAVAAZ_ENABLE_PARAGRAPHS", "1")

    from aavaaz.serverless.lambda_handler import handler

    event = {
        "body": json.dumps(
            {"audio_base64": base64.b64encode(b"x").decode(), "filename": "a.wav"}
        )
    }
    body = json.loads(handler(event, None)["body"])
    assert "paragraphs" in body
    assert body["paragraphs"][0]["text"] == "Hello world"


@patch("faster_whisper.WhisperModel")
def test_handler_adds_intelligence_when_enabled(mock_whisper, _env, monkeypatch):
    """AAVAAZ_ENABLE_INTELLIGENCE should attach analysis to the output."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model
    monkeypatch.setenv("AAVAAZ_ENABLE_INTELLIGENCE", "1")

    from aavaaz.serverless.lambda_handler import handler

    event = {
        "body": json.dumps(
            {"audio_base64": base64.b64encode(b"x").decode(), "filename": "a.wav"}
        )
    }
    body = json.loads(handler(event, None)["body"])
    assert "intelligence" in body
    assert "sentiment" in body["intelligence"]


@patch("faster_whisper.WhisperModel")
def test_handler_fires_webhook_callback(mock_whisper, _env):
    """A callback_url in the request should trigger a webhook POST of the result."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import handler

    event = {
        "body": json.dumps(
            {
                "audio_base64": base64.b64encode(b"x").decode(),
                "filename": "a.wav",
                "callback_url": "https://example.com/hook",
            }
        )
    }
    with patch("aavaaz.features.webhook.send_webhook") as mock_send:
        result = handler(event, None)

    assert result["statusCode"] == 200
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "https://example.com/hook"
    assert mock_send.call_args.args[1]["segments"][0]["text"] == "Hello world"


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


def _pii_segments():
    seg = MagicMock()
    seg.start = 0.0
    seg.end = 1.0
    seg.text = "email me at john@example.com"
    seg.words = []
    return [seg]


@patch("faster_whisper.WhisperModel")
def test_handler_api_applies_request_features(mock_whisper, _env):
    """Per-request features in the JSON body override env and run the pipeline."""
    model = MagicMock()
    model.transcribe.return_value = (_pii_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import handler

    event = {
        "body": json.dumps(
            {
                "audio_base64": base64.b64encode(b"x").decode(),
                "filename": "a.wav",
                "features": {
                    "pii": {"enabled": True, "types": ["email"]},
                    "intelligence": {"sentiment": True},
                },
            }
        )
    }
    result = handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    text = body["segments"][0]["text"]
    assert "john@example.com" not in text
    assert "[EMAIL_REDACTED]" in text
    # env has AAVAAZ_ENABLE_INTELLIGENCE unset, so this only runs via the request
    assert "sentiment" in body.get("intelligence", {})


def test_handler_api_requires_key_when_enabled(_env, monkeypatch):
    """With auth on and no key, the transcription API is rejected."""
    monkeypatch.setenv("AAVAAZ_REQUIRE_API_KEY", "1")
    from aavaaz.serverless.lambda_handler import handler

    event = {
        "body": json.dumps(
            {"audio_base64": base64.b64encode(b"x").decode(), "filename": "a.wav"}
        )
    }
    result = handler(event, None)
    assert result["statusCode"] == 401


@patch("faster_whisper.WhisperModel")
def test_handler_api_valid_key_allows(mock_whisper, _env, monkeypatch):
    """A valid SaaS key passes the gate and transcription proceeds."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model
    monkeypatch.setenv("AAVAAZ_REQUIRE_API_KEY", "1")

    from aavaaz.serverless.lambda_handler import handler

    event = {
        "headers": {"Authorization": "Bearer good-key"},
        "body": json.dumps(
            {"audio_base64": base64.b64encode(b"x").decode(), "filename": "a.wav"}
        ),
    }
    with (
        patch(
            "aavaaz.api.dynamo_store.validate_api_key", return_value="user-1"
        ) as validate,
        patch("aavaaz.api.dynamo_store.record_usage") as record_usage,
        patch("aavaaz.api.dynamo_store.save_transcript") as save_transcript,
    ):
        result = handler(event, None)

    assert result["statusCode"] == 200
    validate.assert_called_once_with("good-key")
    # metering runs for the authenticated user
    record_usage.assert_called_once()
    assert record_usage.call_args.args[0] == "user-1"
    save_transcript.assert_called_once()
    assert save_transcript.call_args.args[0] == "user-1"


def test_handler_api_invalid_key_rejected(_env, monkeypatch):
    """An unrecognized key is rejected with 401."""
    monkeypatch.setenv("AAVAAZ_REQUIRE_API_KEY", "1")
    from aavaaz.serverless.lambda_handler import handler

    event = {
        "headers": {"Authorization": "Bearer bad"},
        "body": json.dumps(
            {"audio_base64": base64.b64encode(b"x").decode(), "filename": "a.wav"}
        ),
    }
    with patch("aavaaz.api.dynamo_store.validate_api_key", return_value=None):
        result = handler(event, None)
    assert result["statusCode"] == 401


@patch("faster_whisper.WhisperModel")
def test_handler_multichannel_labels_segments(mock_whisper, _env, monkeypatch):
    """Multichannel splits per channel and merges with channel labels."""
    monkeypatch.setenv("AAVAAZ_LANGUAGE", "en")  # skip language auto-probe
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import handler

    event = {
        "body": json.dumps(
            {
                "audio_base64": base64.b64encode(b"x").decode(),
                "filename": "a.wav",
                "features": {
                    "multichannel": {"enabled": True, "labels": ["agent", "customer"]}
                },
            }
        )
    }
    fake_audio = types.ModuleType("faster_whisper.audio")
    fake_audio.decode_audio = MagicMock(return_value=(b"L", b"R"))
    with patch.dict(sys.modules, {"faster_whisper.audio": fake_audio}):
        result = handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert {s["channel"] for s in body["segments"]} == {"agent", "customer"}
    assert model.transcribe.call_count == 2  # one per channel


@patch("faster_whisper.WhisperModel")
def test_handler_api_passes_hotwords(mock_whisper, _env):
    """Custom-vocabulary hotwords in the JSON body reach the transcribe call."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import handler

    event = {
        "body": json.dumps(
            {
                "audio_base64": base64.b64encode(b"x").decode(),
                "filename": "a.wav",
                "hotwords": "Kubernetes, Anthropic",
            }
        )
    }
    result = handler(event, None)

    assert result["statusCode"] == 200
    assert model.transcribe.call_args.kwargs.get("hotwords") == "Kubernetes, Anthropic"


@patch("faster_whisper.WhisperModel")
def test_s3_features_from_object_metadata(mock_whisper, _env, monkeypatch):
    """The S3-trigger path reads per-request features from object metadata."""
    model = MagicMock()
    model.transcribe.return_value = (_pii_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import handler

    features_b64 = (
        base64.urlsafe_b64encode(
            json.dumps({"pii": {"enabled": True, "types": ["email"]}}).encode()
        )
        .decode()
        .rstrip("=")
    )

    event = {
        "Records": [
            {"s3": {"bucket": {"name": "in"}, "object": {"key": "clip.wav"}}}
        ]
    }

    with patch("aavaaz.serverless.lambda_handler._s3_client") as mock_s3:
        s3 = MagicMock()
        mock_s3.return_value = s3
        s3.download_file.side_effect = lambda b, k, p: open(p, "wb").close()
        s3.head_object.return_value = {"Metadata": {"features": features_b64}}

        monkeypatch.setenv("AAVAAZ_OUTPUT_BUCKET", "out")
        result = handler(event, None)

    assert result["statusCode"] == 200
    transcript_call = next(
        c
        for c in s3.put_object.call_args_list
        if c.kwargs.get("Key", "").endswith(".json")
        and not c.kwargs.get("Key", "").endswith(".progress.json")
    )
    written = json.loads(transcript_call.kwargs["Body"].decode())
    text = written["segments"][0]["text"]
    assert "john@example.com" not in text
    assert "[EMAIL_REDACTED]" in text


@patch("faster_whisper.WhisperModel")
def test_s3_records_usage_with_user_metadata(mock_whisper, _env, monkeypatch):
    """The S3 path meters usage when object metadata carries a user_id."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import handler

    event = {
        "Records": [{"s3": {"bucket": {"name": "in"}, "object": {"key": "clip.wav"}}}]
    }

    with (
        patch("aavaaz.serverless.lambda_handler._s3_client") as mock_s3,
        patch("aavaaz.api.dynamo_store.record_usage") as record_usage,
        patch("aavaaz.api.dynamo_store.save_transcript"),
    ):
        s3 = MagicMock()
        mock_s3.return_value = s3
        s3.download_file.side_effect = lambda b, k, p: open(p, "wb").close()
        s3.head_object.return_value = {"Metadata": {"user_id": "user-9"}}
        monkeypatch.setenv("AAVAAZ_OUTPUT_BUCKET", "out")
        result = handler(event, None)

    assert result["statusCode"] == 200
    record_usage.assert_called_once()
    assert record_usage.call_args.args[0] == "user-9"


@patch("faster_whisper.WhisperModel")
def test_s3_fires_webhook_from_metadata(mock_whisper, _env, monkeypatch):
    """The S3 path fires the callback_url stored in object metadata on completion."""
    model = MagicMock()
    model.transcribe.return_value = (_fake_segments(), _fake_info())
    mock_whisper.return_value = model

    from aavaaz.serverless.lambda_handler import handler

    cb_b64 = (
        base64.urlsafe_b64encode(b"https://example.com/hook").decode().rstrip("=")
    )
    event = {
        "Records": [{"s3": {"bucket": {"name": "in"}, "object": {"key": "clip.wav"}}}]
    }

    with (
        patch("aavaaz.serverless.lambda_handler._s3_client") as mock_s3,
        patch("aavaaz.features.webhook.send_webhook") as send,
    ):
        s3 = MagicMock()
        mock_s3.return_value = s3
        s3.download_file.side_effect = lambda b, k, p: open(p, "wb").close()
        s3.head_object.return_value = {"Metadata": {"callback_url": cb_b64}}
        monkeypatch.setenv("AAVAAZ_OUTPUT_BUCKET", "out")
        result = handler(event, None)

    assert result["statusCode"] == 200
    send.assert_called_once()
    assert send.call_args.args[0] == "https://example.com/hook"
    assert send.call_args.args[1]["segments"][0]["text"] == "Hello world"
