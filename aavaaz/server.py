"""
Aavaaz server — extends WhisperLive's TranscriptionServer with the full
plugin pipeline and extended REST API.

Uses WhisperLive's ``segment_post_processor`` hook to inject the Aavaaz
plugin pipeline without modifying WhisperLive core code.
"""

import logging
from typing import Optional

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
        plugin_registry: Optional[PluginRegistry] = None,
    ):
        self.host = host
        self.port = port
        self.backend = backend
        self.model = model
        self.enable_rest_api = enable_rest_api
        self.rest_port = rest_port
        self.plugin_registry = plugin_registry or default_registry

    def run(self):
        """Start the Aavaaz server (WhisperLive + plugins + REST API)."""
        server = TranscriptionServer()

        logger.info(
            "Starting Aavaaz server on %s:%d (backend=%s, model=%s)",
            self.host, self.port, self.backend, self.model,
        )

        plugins = self.plugin_registry.list_plugins()
        logger.info("Loaded %d plugins: %s", len(plugins), [p["name"] for p in plugins])

        # Use the registry's apply() as the WhisperLive segment_post_processor
        post_processor = self.plugin_registry.apply if len(self.plugin_registry) > 0 else None

        server.run(
            host=self.host,
            port=self.port,
            backend=self.backend,
            faster_whisper_custom_model_path=self.model,
            enable_rest_api=self.enable_rest_api,
            rest_api_port=self.rest_port,
            segment_post_processor=post_processor,
        )
