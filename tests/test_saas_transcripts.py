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


@pytest.fixture(autouse=True)
def _clear():
    saas._transcripts.clear()
    yield
    saas._transcripts.clear()


def _seed():
    saas.record_transcript(
        "u1",
        {"id": "1", "text": "hello kubernetes world", "language": "en", "tags": {}},
    )
    saas.record_transcript(
        "u1", {"id": "2", "text": "bonjour le monde", "language": "fr", "tags": {}}
    )


def test_list_all_when_no_filter():
    _seed()
    out = _run(saas.list_transcripts(CLAIMS, q=None, language=None, tag=[]))
    assert {j["id"] for j in out} == {"1", "2"}


def test_text_search():
    _seed()
    out = _run(saas.list_transcripts(CLAIMS, q="kubernetes", language=None, tag=[]))
    assert [j["id"] for j in out] == ["1"]


def test_language_filter():
    _seed()
    out = _run(saas.list_transcripts(CLAIMS, q=None, language="fr", tag=[]))
    assert [j["id"] for j in out] == ["2"]


def test_tag_set_and_filter():
    _seed()
    tagged = _run(
        saas.set_transcript_tags("1", saas.SetTagsRequest(tags={"proj": "x"}), CLAIMS)
    )
    assert tagged["tags"] == {"proj": "x"}
    out = _run(saas.list_transcripts(CLAIMS, q=None, language=None, tag=["proj:x"]))
    assert [j["id"] for j in out] == ["1"]


def test_tag_missing_is_404():
    with pytest.raises(HTTPException) as exc:
        _run(saas.set_transcript_tags("nope", saas.SetTagsRequest(tags={}), CLAIMS))
    assert exc.value.status_code == 404
