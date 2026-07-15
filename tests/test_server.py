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
    """Verify run() passes top-level params to WhisperLive's TranscriptionServer.

    word_timestamps / hotwords / enable_diarization / max_speakers / model
    are NOT passed as run() kwargs — WhisperLive reads them per-client via
    the options dict. Aavaaz wraps initialize_client to inject them; the
    wrapper behavior is covered by test_server_run_injects_client_defaults.
    """
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

        # Canonical short names like "tiny" are NOT a custom path; the model
        # name flows through the options dict via the wrapper instead.
        assert call_kwargs["faster_whisper_custom_model_path"] is None
        assert call_kwargs["batch_enabled"] is True
        assert call_kwargs["api_key"] == "key123"
        assert call_kwargs["rate_limit_rpm"] == 60
        assert call_kwargs["metrics_port"] == 9091

        # These four are no longer passed at the run() level — they're
        # per-client defaults injected via the initialize_client wrapper.
        for removed in (
            "word_timestamps",
            "hotwords",
            "enable_diarization",
            "max_speakers",
            "model",
        ):
            assert removed not in call_kwargs, (
                f"{removed!r} should no longer be a run() kwarg; "
                f"it is injected per-client via initialize_client wrapper"
            )


def test_server_run_passes_custom_model_path():
    """HF-style names with '/' (e.g. 'distil-whisper/distil-large-v3') and
    local paths ARE passed as faster_whisper_custom_model_path."""
    server = AavaazServer(model="distil-whisper/distil-large-v3")
    with patch("aavaaz.server.TranscriptionServer") as mock_ts_cls:
        mock_ts = MagicMock()
        mock_ts_cls.return_value = mock_ts
        server.run()
        call_kwargs = mock_ts.run.call_args[1]
        assert (
            call_kwargs["faster_whisper_custom_model_path"]
            == "distil-whisper/distil-large-v3"
        )


def test_server_run_injects_client_defaults():
    """The wrapped initialize_client must setdefault the four flags + model
    into each client's options dict so WhisperLive's per-client code reads
    them correctly."""
    server = AavaazServer(
        model="tiny",
        word_timestamps=True,
        hotwords="acme,widget",
        enable_diarization=True,
        max_speakers=3,
    )
    with patch("aavaaz.server.TranscriptionServer") as mock_ts_cls:
        mock_ts = MagicMock()
        mock_ts_cls.return_value = mock_ts
        # Capture the wrapped initialize_client by stashing whatever value
        # gets assigned to it on the mock.
        server.run()

        # After server.run(), the wrapper should have replaced mock_ts.initialize_client.
        wrapped = mock_ts.initialize_client
        # Calling it with an empty options dict should fill in the defaults.
        sentinel_options = {}
        wrapped("fake_websocket", sentinel_options, "model_path_arg", None, False)
        assert sentinel_options["model"] == "tiny"
        assert sentinel_options["word_timestamps"] is True
        assert sentinel_options["hotwords"] == "acme,widget"
        assert sentinel_options["enable_diarization"] is True
        assert sentinel_options["max_speakers"] == 3

        # Client-supplied values must NOT be overwritten.
        client_options = {
            "model": "client-model",
            "hotwords": "client-hot",
            "word_timestamps": False,
        }
        wrapped("fake_websocket", client_options, "model_path_arg", None, False)
        assert client_options["model"] == "client-model"
        assert client_options["hotwords"] == "client-hot"
        assert client_options["word_timestamps"] is False
        # Unsupplied flags still get the server default.
        assert client_options["enable_diarization"] is True
        assert client_options["max_speakers"] == 3


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


def test_server_run_wires_paragraph_finalizer():
    """transcript_finalizer is passed only when paragraphs are enabled."""
    with patch("aavaaz.server.TranscriptionServer") as mock_ts_cls:
        mock_ts_cls.return_value = MagicMock()
        AavaazServer(enable_paragraphs=True).run()
        assert (
            mock_ts_cls.return_value.run.call_args[1]["transcript_finalizer"]
            is not None
        )

    with patch("aavaaz.server.TranscriptionServer") as mock_ts_cls:
        mock_ts_cls.return_value = MagicMock()
        AavaazServer(enable_paragraphs=False).run()
        assert (
            mock_ts_cls.return_value.run.call_args[1]["transcript_finalizer"] is None
        )


def test_paragraph_finalizer_groups_transcript():
    server = AavaazServer(enable_paragraphs=True)
    transcript = [
        {"start": 0.0, "end": 1.0, "text": "Hello there."},
        {"start": 1.0, "end": 2.0, "text": "How are you?"},
    ]
    payload = server._paragraph_finalizer(transcript)
    assert payload is not None
    assert "paragraphs" in payload
    assert len(payload["paragraphs"]) >= 1
    # empty transcript yields nothing to send
    assert server._paragraph_finalizer([]) is None


def test_cli_parse_all_flags():
    """Verify CLI parses all serve flags correctly."""
    test_args = [
        "aavaaz",
        "serve",
        "--host",
        "0.0.0.0",
        "--port",
        "9090",
        "--model",
        "large-v3",
        "--api-key",
        "mykey",
        "--rate-limit-rpm",
        "120",
        "--metrics-port",
        "9091",
        "--batch-inference",
        "--batch-max-size",
        "16",
        "--batch-window-ms",
        "100",
        "--word-timestamps",
        "--hotwords",
        "foo,bar",
        "--enable-diarization",
        "--max-speakers",
        "8",
        "--paragraphs",
    ]

    with (
        patch.object(sys, "argv", test_args),
        patch("aavaaz.server.AavaazServer") as mock_cls,
    ):
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
        assert kwargs["enable_paragraphs"] is True
        assert kwargs["max_speakers"] == 8
