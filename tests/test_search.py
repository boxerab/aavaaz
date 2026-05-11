"""Tests for search functionality."""

from aavaaz.api.search import search_segments


def test_search_finds_matching_segments():
    segments = [
        {"text": "Hello world", "start": 0, "end": 1},
        {"text": "Goodbye world", "start": 1, "end": 2},
        {"text": "Nothing here", "start": 2, "end": 3},
    ]
    results = search_segments(segments, "world")
    assert len(results) == 2
    assert all("match_count" in r for r in results)


def test_search_case_insensitive():
    segments = [{"text": "Hello World", "start": 0, "end": 1}]
    results = search_segments(segments, "hello")
    assert len(results) == 1


def test_search_no_match():
    segments = [{"text": "Hello", "start": 0, "end": 1}]
    results = search_segments(segments, "xyz")
    assert len(results) == 0
