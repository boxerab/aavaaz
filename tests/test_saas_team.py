"""Tests for the in-memory SaaS team endpoints.

Calls the async route handlers directly (bypassing the FastAPI TestClient, which
needs httpx) with an explicit claims dict in place of the auth dependency.
"""

import asyncio

import pytest
from fastapi import HTTPException

from aavaaz.api import saas

CLAIMS = {"sub": "owner-1"}


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_team():
    saas._team.clear()
    yield
    saas._team.clear()


def test_invite_normalizes_and_lists():
    member = _run(
        saas.invite_member(
            saas.InviteMemberRequest(email="  Alice@Example.com ", role="admin"),
            CLAIMS,
        )
    )
    assert member["email"] == "alice@example.com"
    assert member["role"] == "admin"

    members = _run(saas.list_team(CLAIMS))
    assert [m["id"] for m in members] == [member["id"]]


def test_invite_duplicate_conflicts():
    _run(saas.invite_member(saas.InviteMemberRequest(email="a@x.com"), CLAIMS))
    with pytest.raises(HTTPException) as exc:
        _run(saas.invite_member(saas.InviteMemberRequest(email="a@x.com"), CLAIMS))
    assert exc.value.status_code == 409


def test_invite_rejects_bad_role():
    with pytest.raises(HTTPException) as exc:
        _run(
            saas.invite_member(
                saas.InviteMemberRequest(email="a@x.com", role="root"), CLAIMS
            )
        )
    assert exc.value.status_code == 400


def test_update_role():
    member = _run(
        saas.invite_member(saas.InviteMemberRequest(email="a@x.com"), CLAIMS)
    )
    updated = _run(
        saas.update_member(
            member["id"], saas.UpdateMemberRequest(role="viewer"), CLAIMS
        )
    )
    assert updated["role"] == "viewer"


def test_update_missing_is_404():
    with pytest.raises(HTTPException) as exc:
        _run(
            saas.update_member("nope", saas.UpdateMemberRequest(role="admin"), CLAIMS)
        )
    assert exc.value.status_code == 404


def test_remove_member():
    member = _run(
        saas.invite_member(saas.InviteMemberRequest(email="a@x.com"), CLAIMS)
    )
    _run(saas.remove_member(member["id"], CLAIMS))
    assert _run(saas.list_team(CLAIMS)) == []


def test_remove_missing_is_404():
    with pytest.raises(HTTPException) as exc:
        _run(saas.remove_member("nope", CLAIMS))
    assert exc.value.status_code == 404


def test_members_isolated_per_owner():
    _run(saas.invite_member(saas.InviteMemberRequest(email="a@x.com"), CLAIMS))
    assert _run(saas.list_team({"sub": "owner-2"})) == []
