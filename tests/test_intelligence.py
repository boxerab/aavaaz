"""Tests for audio intelligence features (sentiment, topics, entities, summarization)."""

from aavaaz.features.audio_intelligence import (
    analyze_sentiment,
    detect_topics,
    extract_entities,
    remove_filler_words,
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
    text = (
        "The artificial intelligence model uses deep learning"
        " neural networks for natural language processing."
    )
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


def test_filler_removal_leaves_no_comma_before_sentence_end():
    assert remove_filler_words("we ship on Friday, you know") == "We ship on Friday"
    assert remove_filler_words("we ship on Friday, um. Then test") == "We ship on Friday. Then test"


def test_filler_removal_drops_commas_around_mid_sentence_filler():
    assert remove_filler_words("I think, uh, you know, we should") == "I think we should"


def test_filler_removal_keeps_comma_after_opening_word():
    assert remove_filler_words("Yes, um, I agree") == "Yes, I agree"


def test_sentiment_inflected_negative_word():
    assert analyze_sentiment("the customer is frustrated with the delay")["label"] == "negative"


def test_sentiment_negation():
    assert analyze_sentiment("The service was not good")["label"] == "negative"
    assert analyze_sentiment("This is not bad at all")["label"] == "positive"


def test_sentiment_but_clause():
    assert analyze_sentiment("It works but the setup was painful")["label"] == "negative"
