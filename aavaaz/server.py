"""
Aavaaz server — extends WhisperLive's TranscriptionServer with the full
plugin pipeline and extended REST API.

Uses WhisperLive's ``segment_post_processor`` hook to inject the Aavaaz
plugin pipeline without modifying WhisperLive core code.
"""

import logging
import os

from whisper_live.server import TranscriptionServer

from aavaaz.features.plugins import PluginRegistry
from aavaaz.plugins import registry as default_registry

logger = logging.getLogger(__name__)


class AavaazServer:
    """High-level server that wires WhisperLive with Aavaaz plugins and API."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9090,
        backend: str = "faster_whisper",
        model: str = "large-v3",
        *,
        enable_rest_api: bool = True,
        rest_port: int = 8000,
        plugin_registry: PluginRegistry | None = None,
        api_key: str | None = None,
        rate_limit_rpm: int = 0,
        metrics_port: int = 0,
        batch_inference: bool = False,
        batch_max_size: int = 8,
        batch_window_ms: int = 50,
        word_timestamps: bool = False,
        hotwords: str | None = None,
        enable_diarization: bool = False,
        max_speakers: int = 10,
        enable_formatting: bool = False,
        enable_pii: bool = False,
        enable_profanity: bool = False,
        enable_intelligence: bool = False,
        enable_paragraphs: bool = False,
    ):
        self.host = host
        self.port = port
        self.backend = backend
        self.model = model
        self.enable_rest_api = enable_rest_api
        self.rest_port = rest_port
        self.plugin_registry = plugin_registry or default_registry
        self.api_key = api_key
        self.rate_limit_rpm = rate_limit_rpm
        self.metrics_port = metrics_port
        self.batch_inference = batch_inference
        self.batch_max_size = batch_max_size
        self.batch_window_ms = batch_window_ms
        self.word_timestamps = word_timestamps
        self.hotwords = hotwords
        self.enable_diarization = enable_diarization
        self.max_speakers = max_speakers
        self.enable_formatting = enable_formatting
        self.enable_pii = enable_pii
        self.enable_profanity = enable_profanity
        self.enable_intelligence = enable_intelligence
        self.enable_paragraphs = enable_paragraphs

    def _paragraph_finalizer(self, transcript: list[dict]) -> dict | None:
        """End-of-stream hook: group the transcript into paragraphs.

        Returns a payload dict (sent to the client as a final message), or None
        when there is nothing to group.
        """
        if not transcript:
            return None
        from aavaaz.features.utterance import segment_into_paragraphs

        paragraphs = segment_into_paragraphs(transcript)
        return {"paragraphs": paragraphs} if paragraphs else None

    # built-in plugin name -> the AavaazServer flag that enables it
    _FEATURE_PLUGINS = {
        "formatting": "enable_formatting",
        "pii_redaction": "enable_pii",
        "profanity_filter": "enable_profanity",
        "audio_intelligence": "enable_intelligence",
    }

    def configure_plugins(self):
        """Enable the built-in post-processing plugins selected via feature flags.

        Built-ins are registered disabled so raw transcripts are never silently
        altered; this turns on the ones the operator asked for.
        """
        for plugin_name, flag in self._FEATURE_PLUGINS.items():
            if getattr(self, flag):
                self.plugin_registry.enable(plugin_name)

    def serve(self, **overrides):
        """Apply keyword overrides (e.g. word_timestamps=True) then start the server."""
        for key, value in overrides.items():
            if not hasattr(self, key):
                raise TypeError(f"serve() got an unexpected keyword argument '{key}'")
            setattr(self, key, value)
        self.run()

    def run(self):
        """Start the Aavaaz server (WhisperLive + plugins + REST API)."""
        self.configure_plugins()
        server = TranscriptionServer()

        logger.info(
            "Starting Aavaaz server on %s:%d (backend=%s, model=%s)",
            self.host,
            self.port,
            self.backend,
            self.model,
        )

        plugins = self.plugin_registry.list_plugins()
        logger.info("Loaded %d plugins: %s", len(plugins), [p["name"] for p in plugins])

        # Use the registry's apply() as the WhisperLive segment_post_processor
        post_processor = (
            self.plugin_registry.apply if len(self.plugin_registry) > 0 else None
        )

        # WhisperLive's server.run() has no kwargs for these server-wide
        # defaults, but its per-client code already reads them via the
        # options dict. Wrap initialize_client so Aavaaz's flags act as
        # defaults that any client can override via its WS handshake.
        original_init_client = server.initialize_client
        is_custom_model = self.model and (
            "/" in self.model or os.path.exists(self.model)
        )
        server_defaults = {
            "model": self.model,
            "word_timestamps": self.word_timestamps,
            "hotwords": self.hotwords,
            "enable_diarization": self.enable_diarization,
            "max_speakers": self.max_speakers,
        }

        def initialize_client_with_defaults(websocket, options, *args, **kwargs):
            for key, value in server_defaults.items():
                options.setdefault(key, value)
            return original_init_client(websocket, options, *args, **kwargs)

        server.initialize_client = initialize_client_with_defaults

        server.run(
            host=self.host,
            port=self.port,
            backend=self.backend,
            # Only pass as "custom path" when the model name actually looks
            # like one (HF org/repo or local path). Canonical short names
            # like "large-v3" flow through the per-client options dict.
            faster_whisper_custom_model_path=self.model if is_custom_model else None,
            enable_rest=self.enable_rest_api,
            rest_port=self.rest_port,
            segment_post_processor=post_processor,
            transcript_finalizer=(
                self._paragraph_finalizer if self.enable_paragraphs else None
            ),
            batch_enabled=self.batch_inference,
            batch_max_size=self.batch_max_size,
            batch_window_ms=self.batch_window_ms,
            metrics_port=self.metrics_port,
            api_key=self.api_key,
            rate_limit_rpm=self.rate_limit_rpm,
        )
