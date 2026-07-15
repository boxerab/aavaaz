"""Shared post-processing pipeline for the batch transcription paths.

Both the AWS Lambda handler and the Modal batch app build the same segment
transform pipeline and result enrichment. Keeping it here prevents the two
deployments from drifting.

Configuration comes from ``AAVAAZ_*`` env vars by default; a per-request
``features`` dict (the dashboard ``FeaturesConfig`` shape) overrides the env.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


def build_pipeline(features: dict | None = None) -> list[Any]:
    """Return per-segment text transforms.

    With no features dict the pipeline is configured from AAVAAZ_* env vars (the
    deployment default). A per-request features dict overrides that env config.
    """
    if features is None:
        fns: list[Any] = []
        if os.environ.get("AAVAAZ_ENABLE_FORMAT", "1") == "1":
            from aavaaz.features.formatting import smart_format

            fns.append(smart_format)
        if os.environ.get("AAVAAZ_ENABLE_PII", "0") == "1":
            from aavaaz.features.pii_redaction import redact_pii

            fns.append(redact_pii)
        return fns

    fns = []

    fmt = features.get("formatting") or {}
    if fmt.get("enabled"):
        from aavaaz.features.formatting import format_transcript

        capitalize = bool(fmt.get("capitalize", True))
        numbers = bool(fmt.get("numbers", True))
        smart = bool(fmt.get("smart", False))
        fns.append(
            lambda t: format_transcript(
                t, capitalize=capitalize, numbers=numbers, smart=smart
            )
        )

    pii = features.get("pii") or {}
    if pii.get("enabled"):
        from aavaaz.features.pii_redaction import redact_pii

        pii_types = set(pii.get("types") or []) or None
        custom = compile_custom_pii(pii.get("customPatterns") or [])
        fns.append(
            lambda t: redact_pii(t, pii_types=pii_types, custom_patterns=custom)
        )

    prof = features.get("profanity") or {}
    if prof.get("enabled"):
        from aavaaz.features.profanity_filter import filter_profanity

        mode = prof.get("mode", "partial")
        extra = set(prof.get("extraWords") or []) or None
        fns.append(lambda t: filter_profanity(t, mode=mode, extra_words=extra))

    intel = features.get("intelligence") or {}
    if intel.get("fillerRemoval"):
        from aavaaz.features.audio_intelligence import remove_filler_words

        aggressive = bool(intel.get("fillerAggressive", False))
        fns.append(lambda t: remove_filler_words(t, aggressive=aggressive))

    return fns


def compile_custom_pii(patterns: list[dict]) -> dict | None:
    """Compile dashboard customPatterns into redact_pii's {label: (regex, repl)} form."""
    compiled: dict[str, Any] = {}
    for p in patterns:
        pattern = p.get("pattern")
        if not pattern:
            continue
        try:
            compiled[p.get("label", pattern)] = (
                re.compile(pattern),
                p.get("replacement", "[REDACTED]"),
            )
        except re.error:
            logger.warning("Skipping invalid custom PII pattern: %s", pattern)
    return compiled or None


def enrich_result(result: dict, features: dict | None = None) -> None:
    """Attach optional paragraph segmentation and intelligence analysis, in place."""
    # paragraphs stay env-gated: the dashboard config carries no paragraph toggle
    if os.environ.get("AAVAAZ_ENABLE_PARAGRAPHS", "0") == "1":
        from aavaaz.features.utterance import segment_into_paragraphs

        result["paragraphs"] = segment_into_paragraphs(result["segments"])

    intel_opts = intelligence_options(features)
    if intel_opts is not None:
        from aavaaz.features.audio_intelligence import analyze_transcript

        full_text = " ".join(s["text"] for s in result["segments"])
        result["intelligence"] = analyze_transcript(full_text, **intel_opts)


def intelligence_options(features: dict | None) -> dict | None:
    """Resolve analyze_transcript kwargs from features/env, or None if disabled."""
    if features is None:
        if os.environ.get("AAVAAZ_ENABLE_INTELLIGENCE", "0") == "1":
            return {}
        return None

    intel = features.get("intelligence") or {}
    if not any(
        intel.get(k)
        for k in ("sentiment", "topics", "entities", "summarize", "highlights")
    ):
        return None
    return {
        "sentiment": bool(intel.get("sentiment")),
        "topics": bool(intel.get("topics")),
        "entities": bool(intel.get("entities")),
        "summary": bool(intel.get("summarize")),
        "highlights": bool(intel.get("highlights")),
        "summary_sentences": int(intel.get("summarySentences", 3)),
        "topic_count": int(intel.get("topicsTopN", 5)),
        "max_highlights": int(intel.get("maxHighlights", 10)),
    }
