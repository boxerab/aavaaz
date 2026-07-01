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


def _make_profanity_plugin():
    """Create a profanity filter plugin."""
    from aavaaz.features.profanity_filter import filter_profanity

    def profanity_plugin(segment):
        if "text" in segment:
            segment["text"] = filter_profanity(segment["text"])
        return segment

    return profanity_plugin


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
registry.add("formatting", _make_formatting_plugin(), priority=10, enabled=False)
registry.add("pii_redaction", _make_pii_plugin(), priority=20, enabled=False)
registry.add("profanity_filter", _make_profanity_plugin(), priority=30, enabled=False)

try:
    registry.add(
        "audio_intelligence", _make_intelligence_plugin(), priority=90, enabled=False
    )
except ImportError:
    logger.debug("Audio intelligence module not available")
