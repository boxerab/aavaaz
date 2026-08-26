"""
Built-in Aavaaz plugins for the post-processing pipeline.

These plugins register with the PluginRegistry and run in the
segment post-processing pipeline. They are registered disabled so raw
transcripts are never silently altered; enable the ones you want with
registry.enable(name).
"""

import logging

from aavaaz.features.plugins import PluginRegistry

logger = logging.getLogger(__name__)

# Global default registry — the AavaazServer uses this unless overridden
registry = PluginRegistry()


def _make_pii_plugin():
    """Create a PII redaction plugin."""
    from aavaaz.features.pii_redaction import redact_pii

    def pii_plugin(segment):
        if "text" in segment:
            segment["text"] = redact_pii(segment["text"])
        return segment

    return pii_plugin


class _ProfanityPlugin:
    """Profanity filter plugin whose mode and word list stay settable after registration."""

    def __init__(self):
        self.mode = "partial"
        self.extra_words: set[str] | None = None

    def __call__(self, segment):
        from aavaaz.features.profanity_filter import filter_profanity

        if "text" in segment:
            segment["text"] = filter_profanity(
                segment["text"], mode=self.mode, extra_words=self.extra_words
            )
        return segment


class _FillerRemovalPlugin:
    """Filler word removal plugin whose aggressive flag stays settable after registration."""

    def __init__(self):
        self.aggressive = False

    def __call__(self, segment):
        from aavaaz.features.audio_intelligence import remove_filler_words

        if "text" in segment:
            segment["text"] = remove_filler_words(segment["text"], aggressive=self.aggressive)
        return segment


def _make_profanity_plugin():
    """Create a profanity filter plugin."""
    return _ProfanityPlugin()


def _make_filler_removal_plugin():
    """Create a filler word removal plugin."""
    return _FillerRemovalPlugin()


def configure_profanity(mode: str = "partial", extra_words: set[str] | None = None):
    """Set the options used by the registered profanity_filter plugin."""
    _profanity_plugin.mode = mode
    _profanity_plugin.extra_words = extra_words


def configure_filler_removal(aggressive: bool = False):
    """Set the options used by the registered filler_removal plugin."""
    _filler_removal_plugin.aggressive = aggressive


def _make_formatting_plugin():
    """Create a smart formatting plugin."""
    from aavaaz.features.formatting import format_transcript

    def formatting_plugin(segment):
        if "text" in segment:
            segment["text"] = format_transcript(
                segment["text"],
                capitalize=True,
                numbers=True,
                smart=True,
            )
        return segment

    return formatting_plugin


def _make_intelligence_plugin():
    """Create an audio intelligence plugin (sentiment, topics, entities)."""
    from aavaaz.features.audio_intelligence import (
        analyze_sentiment,
        detect_topics,
        extract_entities,
    )

    def intelligence_plugin(segment):
        text = segment.get("text", "")
        if text:
            segment["sentiment"] = analyze_sentiment(text)
            segment["topics"] = detect_topics(text)
            segment["entities"] = extract_entities(text)
        return segment

    return intelligence_plugin


# Register all built-in plugins with ascending priority, disabled by default
_profanity_plugin = _make_profanity_plugin()
_filler_removal_plugin = _make_filler_removal_plugin()

registry.add("formatting", _make_formatting_plugin(), priority=10, enabled=False)
registry.add("pii_redaction", _make_pii_plugin(), priority=20, enabled=False)
registry.add("profanity_filter", _profanity_plugin, priority=30, enabled=False)
registry.add("filler_removal", _filler_removal_plugin, priority=40, enabled=False)

try:
    registry.add("audio_intelligence", _make_intelligence_plugin(), priority=90, enabled=False)
except ImportError:
    logger.debug("Audio intelligence module not available")
