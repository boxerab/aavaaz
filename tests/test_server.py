"""Tests for AavaazServer initialization and CLI flag wiring."""

import sys
from unittest.mock import MagicMock, patch

from aavaaz.features.plugins import PluginRegistry

# Mock whisper_live before importing aavaaz.server
_mock_wl = MagicMock()
sys.modules.setdefault("whisper_live", _mock_wl)
sys.modules.setdefault("whisper_live.server", _mock_wl.server)

from aavaaz.server import AavaazServer  # noqa: E402


def test_server_init_stores_params():
    """Verify all constructor params are stored."""
    server = AavaazServer(
        host="127.0.0.1",
        port=9091,
        backend="faster_whisper",
        model="base",
        api_key="secret",
        rate_limit_rpm=100,
        metrics_port=9092,
        batch_inference=True,
        batch_max_size=4,
        batch_window_ms=25,
        word_timestamps=True,
        hotwords="hello,world",
        enable_diarization=True,
        max_speakers=5,
    )

    assert server.host == "127.0.0.1"
    assert server.port == 9091
    assert server.model == "base"
    assert server.api_key == "secret"
    assert server.rate_limit_rpm == 100
    assert server.metrics_port == 9092
    assert server.batch_inference is True
    assert server.batch_max_size == 4
    assert server.batch_window_ms == 25
    assert server.word_timestamps is True
    assert server.hotwords == "hello,world"
    assert server.enable_diarization is True
    assert server.max_speakers == 5


def test_server_run_passes_params():
    """Verify run() passes all params to WhisperLive's TranscriptionServer."""
    server = AavaazServer(
        model="tiny",
        batch_inference=True,
        api_key="key123",
        rate_limit_rpm=60,
        metrics_port=9091,
        word_timestamps=True,
        hotwords="test",
        enable_diarization=True,
        max_speakers=3,
    )

    with patch("aavaaz.server.TranscriptionServer") as mock_ts_cls:
        mock_ts = MagicMock()
        mock_ts_cls.return_value = mock_ts
        server.run()

        mock_ts.run.assert_called_once()
        call_kwargs = mock_ts.run.call_args[1]

        assert call_kwargs["faster_whisper_custom_model_path"] == "tiny"
        assert call_kwargs["batch_enabled"] is True
        assert call_kwargs["api_key"] == "key123"
        assert call_kwargs["rate_limit_rpm"] == 60
        assert call_kwargs["metrics_port"] == 9091
        assert call_kwargs["word_timestamps"] is True
        assert call_kwargs["hotwords"] == "test"
        assert call_kwargs["enable_diarization"] is True
        assert call_kwargs["max_speakers"] == 3


def test_server_run_wires_plugin_pipeline():
    """Verify the plugin registry's apply() is passed as segment_post_processor."""
    reg = PluginRegistry()
    reg.add("test_plugin", lambda s: s, priority=10)

    server = AavaazServer(plugin_registry=reg)

    with patch("aavaaz.server.TranscriptionServer") as mock_ts_cls:
        mock_ts = MagicMock()
        mock_ts_cls.return_value = mock_ts
        server.run()

        call_kwargs = mock_ts.run.call_args[1]
        assert call_kwargs["segment_post_processor"] is not None
        assert call_kwargs["segment_post_processor"] == reg.apply


def test_cli_parse_all_flags():
    """Verify CLI parses all serve flags correctly."""
    test_args = [
        "aavaaz", "serve",
        "--host", "0.0.0.0",
        "--port", "9090",
        "--model", "large-v3",
        "--api-key", "mykey",
        "--rate-limit-rpm", "120",
        "--metrics-port", "9091",
        "--batch-inference",
        "--batch-max-size", "16",
        "--batch-window-ms", "100",
        "--word-timestamps",
        "--hotwords", "foo,bar",
        "--enable-diarization",
        "--max-speakers", "8",
    ]

    with patch.object(sys, "argv", test_args), patch("aavaaz.server.AavaazServer") as mock_cls:
        mock_cls.return_value.run = MagicMock()
        from aavaaz.cli import main

        main()

        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args[1]
        assert kwargs["api_key"] == "mykey"
        assert kwargs["rate_limit_rpm"] == 120
        assert kwargs["metrics_port"] == 9091
        assert kwargs["batch_inference"] is True
        assert kwargs["batch_max_size"] == 16
        assert kwargs["batch_window_ms"] == 100
        assert kwargs["word_timestamps"] is True
        assert kwargs["hotwords"] == "foo,bar"
        assert kwargs["enable_diarization"] is True
        assert kwargs["max_speakers"] == 8
