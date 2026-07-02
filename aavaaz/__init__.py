"""Aavaaz — production-grade speech-to-text platform."""

__version__ = "0.9.0"


def __getattr__(name: str):
    # Lazy exports so `import aavaaz` stays light (server pulls in whisper_live).
    if name == "AavaazServer":
        from aavaaz.server import AavaazServer

        return AavaazServer
    if name == "PluginRegistry":
        from aavaaz.features.plugins import PluginRegistry

        return PluginRegistry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
