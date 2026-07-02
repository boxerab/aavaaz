"""Tests for the public API (aavaaz.AavaazServer) and built-in plugin wiring."""

import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("whisper_live", MagicMock())
sys.modules.setdefault("whisper_live.server", MagicMock())


def test_public_api_exports():
    import aavaaz
    from aavaaz import AavaazServer, PluginRegistry

    assert aavaaz.AavaazServer is AavaazServer
    assert PluginRegistry is not None


def test_serve_applies_overrides_then_runs():
    from aavaaz import AavaazServer

    server = AavaazServer()
    calls = []
    server.run = lambda: calls.append("ran")
    server.serve(word_timestamps=True, hotwords="Foo,Bar")
    assert server.word_timestamps is True
    assert server.hotwords == "Foo,Bar"
    assert calls == ["ran"]


def test_serve_rejects_unknown_kwarg():
    from aavaaz import AavaazServer

    server = AavaazServer()
    with pytest.raises(TypeError):
        server.serve(does_not_exist=1)


def test_feature_flags_enable_builtin_plugins():
    from aavaaz import AavaazServer, PluginRegistry

    reg = PluginRegistry()
    reg.add("formatting", lambda s: s, enabled=False)
    reg.add("audio_intelligence", lambda s: s, enabled=False)
    reg.add("pii_redaction", lambda s: s, enabled=False)

    server = AavaazServer(
        plugin_registry=reg, enable_intelligence=True, enable_formatting=True
    )
    server.configure_plugins()

    enabled = {p["name"]: p["enabled"] for p in reg.list_plugins()}
    assert enabled["audio_intelligence"] is True
    assert enabled["formatting"] is True
    assert enabled["pii_redaction"] is False


def test_intelligence_plugin_enriches_segment():
    """The registered intelligence plugin should add analysis to a segment."""
    from aavaaz.plugins.builtins import _make_intelligence_plugin

    plugin = _make_intelligence_plugin()
    result = plugin({"text": "I love this product, it works great.", "start": 0, "end": 2})
    assert "sentiment" in result
    assert "topics" in result
    assert "entities" in result
