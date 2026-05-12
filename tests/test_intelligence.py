"""Tests for audio intelligence features (sentiment, topics, entities, summarization)."""

from aavaaz.features.audio_intelligence import (
    analyze_sentiment,
    detect_topics,
    extract_entities,
    summarize,
)


def test_sentiment_positive():
    result = analyze_sentiment("I love this product, it's absolutely amazing!")
    assert result["label"] == "positive"
    assert result["score"] > 0


def test_sentiment_negative():
    result = analyze_sentiment("This is terrible, I hate everything about it.")
    assert result["label"] == "negative"
    assert result["score"] < 0


def test_sentiment_neutral():
    result = analyze_sentiment("The meeting is at 3pm.")
    assert result["label"] == "neutral"


def test_detect_topics():
    text = "The artificial intelligence model uses deep learning neural networks for natural language processing."
    topics = detect_topics(text)
    assert isinstance(topics, list)
    assert len(topics) > 0
    # Returns list of dicts with 'topic' and 'count'
    assert "topic" in topics[0]
    assert "count" in topics[0]


def test_extract_entities_date():
    text = "The meeting is on January 15, 2024 at 3:00 PM."
    entities = extract_entities(text)
    assert isinstance(entities, dict)
    assert "date" in entities or "time" in entities


def test_extract_entities_money():
    text = "The product costs $1,500.00 which is 20% off."
    entities = extract_entities(text)
    assert "money" in entities
    assert "$1,500.00" in entities["money"]
    assert "percentage" in entities


def test_summarize():
    text = (
        "The quick brown fox jumps over the lazy dog. "
        "This sentence contains many words. "
        "Another sentence for testing purposes. "
        "Yet one more sentence to ensure we have enough text. "
        "The final sentence wraps up our test content."
    )
    result = summarize(text, num_sentences=2)
    assert isinstance(result, str)
    assert len(result) > 0
    # Summary should be shorter than original
    assert len(result) < len(text)
