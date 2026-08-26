"""Tests for the plugin registry and built-in plugins."""

from aavaaz.features.plugins import PluginRegistry
from aavaaz.plugins.builtins import (
    _make_filler_removal_plugin,
    _make_formatting_plugin,
    _make_pii_plugin,
    _make_profanity_plugin,
)
from aavaaz.plugins.builtins import registry as builtin_registry


def test_pii_plugin_redacts_email():
    plugin = _make_pii_plugin()
    segment = {"text": "Contact me at john@example.com please", "start": 0, "end": 1}
    result = plugin(segment)
    assert "[EMAIL_REDACTED]" in result["text"]
    assert "john@example.com" not in result["text"]


def test_pii_plugin_redacts_ssn():
    plugin = _make_pii_plugin()
    segment = {"text": "My SSN is 123-45-6789", "start": 0, "end": 1}
    result = plugin(segment)
    assert "[SSN_REDACTED]" in result["text"]


def test_profanity_plugin_masks():
    plugin = _make_profanity_plugin()
    segment = {"text": "What the fuck is this", "start": 0, "end": 1}
    result = plugin(segment)
    assert "fuck" not in result["text"]
    assert "f" in result["text"]  # partial mask keeps first char


def test_profanity_plugin_honours_configured_mode_and_extra_words():
    plugin = _make_profanity_plugin()
    plugin.mode = "remove"
    plugin.extra_words = {"blergh"}
    result = plugin({"text": "this blergh shit", "start": 0, "end": 1})
    assert result["text"] == "this"


def test_filler_removal_plugin_strips_fillers():
    plugin = _make_filler_removal_plugin()
    result = plugin({"text": "um so, you know, it works", "start": 0, "end": 1})
    assert "um" not in result["text"].split()
    assert "you know" not in result["text"]
    assert "works" in result["text"]


def test_filler_removal_plugin_aggressive_flag():
    plugin = _make_filler_removal_plugin()
    segment = {"text": "it is basically done", "start": 0, "end": 1}
    assert plugin(dict(segment))["text"] == "It is basically done"
    plugin.aggressive = True
    assert plugin(dict(segment))["text"] == "It is done"


def test_builtin_filler_removal_registered_disabled_between_formatting_and_intelligence():
    priorities = {p["name"]: p for p in builtin_registry.list_plugins()}
    filler = priorities["filler_removal"]
    assert filler["enabled"] is False
    assert (
        priorities["formatting"]["priority"]
        < filler["priority"]
        < priorities["audio_intelligence"]["priority"]
    )


def test_formatting_plugin_capitalizes():
    plugin = _make_formatting_plugin()
    segment = {"text": "hello world. how are you", "start": 0, "end": 1}
    result = plugin(segment)
    assert result["text"].startswith("Hello")


def test_registry_apply_order():
    reg = PluginRegistry()

    def add_exclaim(seg):
        seg["text"] = seg["text"] + "!"
        return seg

    def upper(seg):
        seg["text"] = seg["text"].upper()
        return seg

    reg.add("exclaim", add_exclaim, priority=10)
    reg.add("upper", upper, priority=20)

    result = reg.apply({"text": "hello"})
    # exclaim runs first (lower priority number), then upper
    assert result["text"] == "HELLO!"


def test_registry_disable():
    reg = PluginRegistry()
    reg.add("noop", lambda s: s, priority=10, enabled=False)
    assert len(reg.list_plugins()) == 1
    assert not reg.list_plugins()[0]["enabled"]
