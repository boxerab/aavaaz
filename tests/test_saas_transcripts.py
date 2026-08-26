"""Tests for the in-memory SaaS transcript search + tagging routes.

Calls the async handlers directly. FastAPI Query() defaults are markers, not
values, so query params are always passed explicitly here.
"""

import asyncio

import pytest
from fastapi import HTTPException

from aavaaz.api import saas

CLAIMS = {"sub": "u1"}


def _run(coro):
    return asyncio.run(coro)


def _list(**filters):
    params = {"q": None, "language": None, "tag": [], "model": None, "start": None, "end": None}
    params.update(filters)
    return _run(saas.list_transcripts(CLAIMS, **params))


@pytest.fixture(autouse=True)
def _clear():
    saas._transcripts.clear()
    yield
    saas._transcripts.clear()


def _seed():
    saas.record_transcript(
        "u1",
        {
            "id": "1",
            "text": "hello kubernetes world",
            "language": "en",
            "model": "small",
            "created_at": "2026-01-10T09:00:00+00:00",
            "tags": {},
        },
    )
    saas.record_transcript(
        "u1",
        {
            "id": "2",
            "text": "bonjour le monde",
            "language": "fr",
            "model": "large-v3",
            "created_at": "2026-03-20T09:00:00+00:00",
            "tags": {},
        },
    )


def test_list_all_when_no_filter():
    _seed()
    assert {j["id"] for j in _list()} == {"1", "2"}


def test_text_search():
    _seed()
    assert [j["id"] for j in _list(q="kubernetes")] == ["1"]


def test_language_filter():
    _seed()
    assert [j["id"] for j in _list(language="fr")] == ["2"]


def test_model_filter():
    _seed()
    assert [j["id"] for j in _list(model="large-v3")] == ["2"]
    assert [j["id"] for j in _list(model="small")] == ["1"]
    assert _list(model="tiny") == []


def test_date_range_filter():
    _seed()
    assert [j["id"] for j in _list(start="2026-02-01T00:00:00+00:00")] == ["2"]
    assert [j["id"] for j in _list(end="2026-02-01T00:00:00+00:00")] == ["1"]
    assert {
        j["id"] for j in _list(start="2026-01-01T00:00:00+00:00", end="2026-12-31T00:00:00+00:00")
    } == {"1", "2"}


def test_date_bounds_are_inclusive():
    _seed()
    assert [j["id"] for j in _list(start="2026-03-20T09:00:00+00:00")] == ["2"]
    assert [j["id"] for j in _list(end="2026-01-10T09:00:00+00:00")] == ["1"]


def test_naive_timestamp_is_read_as_utc():
    _seed()
    assert [j["id"] for j in _list(start="2026-02-01T00:00:00")] == ["2"]


def test_malformed_timestamp_is_400():
    _seed()
    with pytest.raises(HTTPException) as exc:
        _list(start="not-a-date")
    assert exc.value.status_code == 400


def test_recorded_transcript_gets_created_at():
    saas.record_transcript("u1", {"id": "3", "text": "hi"})
    assert saas._transcripts["u1"][0]["created_at"]


def test_tag_set_and_filter():
    _seed()
    tagged = _run(saas.set_transcript_tags("1", saas.SetTagsRequest(tags={"proj": "x"}), CLAIMS))
    assert tagged["tags"] == {"proj": "x"}
    assert [j["id"] for j in _list(tag=["proj:x"])] == ["1"]


def test_tag_missing_is_404():
    with pytest.raises(HTTPException) as exc:
        _run(saas.set_transcript_tags("nope", saas.SetTagsRequest(tags={}), CLAIMS))
    assert exc.value.status_code == 404


def test_delete_transcript():
    _seed()
    assert _run(saas.delete_transcript("1", CLAIMS)) is None
    assert [j["id"] for j in _list()] == ["2"]


def test_delete_transcript_of_another_user_is_404():
    _seed()
    with pytest.raises(HTTPException) as exc:
        _run(saas.delete_transcript("1", {"sub": "u2"}))
    assert exc.value.status_code == 404
