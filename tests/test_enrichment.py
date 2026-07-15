"""Tests for the shared batch enrichment pipeline (Lambda + Modal)."""

from aavaaz.features.enrichment import (
    build_pipeline,
    enrich_result,
    intelligence_options,
)


def _apply(pipeline, text):
    for fn in pipeline:
        text = fn(text)
    return text


def test_features_pii_redacts():
    pipeline = build_pipeline({"pii": {"enabled": True, "types": ["email"]}})
    out = _apply(pipeline, "reach me at john@example.com")
    assert "john@example.com" not in out
    assert "[EMAIL_REDACTED]" in out


def test_features_profanity_masks():
    pipeline = build_pipeline(
        {"profanity": {"enabled": True, "mode": "partial", "extraWords": ["frobnicate"]}}
    )
    out = _apply(pipeline, "do not frobnicate the widget")
    assert "frobnicate" not in out


def test_features_disabled_is_noop():
    pipeline = build_pipeline({"pii": {"enabled": False}})
    assert pipeline == []


def test_enrich_result_adds_intelligence():
    result = {"segments": [{"text": "I love this product, it works great."}]}
    enrich_result(result, {"intelligence": {"sentiment": True}})
    assert "sentiment" in result.get("intelligence", {})


def test_intelligence_options_off_by_default(monkeypatch):
    monkeypatch.delenv("AAVAAZ_ENABLE_INTELLIGENCE", raising=False)
    assert intelligence_options(None) is None
    # nothing selected in the features dict -> also None
    assert intelligence_options({"intelligence": {}}) is None


def test_env_default_pipeline(monkeypatch):
    monkeypatch.setenv("AAVAAZ_ENABLE_FORMAT", "1")
    monkeypatch.setenv("AAVAAZ_ENABLE_PII", "1")
    # env path builds format + pii transforms
    assert len(build_pipeline(None)) == 2
