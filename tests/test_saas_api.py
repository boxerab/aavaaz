"""Tests for the SaaS management API (in-memory router in aavaaz.api.saas)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aavaaz.api import plans, saas
from aavaaz.api.auth import require_auth


@pytest.fixture
def client():
    # fresh in-memory store per test
    saas._api_keys.clear()
    saas._key_hash_to_id.clear()
    saas._usage.clear()
    saas._subscriptions.clear()
    saas._transcripts.clear()

    app = FastAPI()
    app.include_router(saas.router)
    current_user = {"sub": "user-1"}
    app.dependency_overrides[require_auth] = lambda: dict(current_user)

    tc = TestClient(app)
    tc.current_user = current_user
    return tc


def test_api_key_lifecycle(client):
    resp = client.post("/v1/saas/api-keys", json={"name": "ci"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["secret"].startswith("aavaaz_")
    key_id = body["key"]["id"]

    assert [k["id"] for k in client.get("/v1/saas/api-keys").json()] == [key_id]

    assert client.delete(f"/v1/saas/api-keys/{key_id}").status_code == 200
    assert client.get("/v1/saas/api-keys").json() == []


def test_api_keys_are_per_user(client):
    client.post("/v1/saas/api-keys", json={"name": "mine"})
    client.current_user["sub"] = "user-2"
    assert client.get("/v1/saas/api-keys").json() == []


def test_default_subscription_is_free(client):
    body = client.get("/v1/saas/subscription").json()
    assert body["plan"] == "free"
    assert body["included_minutes"] == 60
    assert body["price_per_minute"] == 0.0


def test_checkout_rejects_non_purchasable_plan(client):
    # enterprise is not self-service; must be rejected before any billing call
    resp = client.post("/v1/saas/checkout", json={"plan": "enterprise"})
    assert resp.status_code == 400


def test_checkout_pro_passes_allowlist_then_needs_billing(client, monkeypatch):
    # pro clears the allowlist; without STRIPE_SECRET_KEY it is 503, not 400
    monkeypatch.setattr(saas, "STRIPE_SECRET_KEY", "")
    resp = client.post("/v1/saas/checkout", json={"plan": "pro"})
    assert resp.status_code == 503


def test_usage_reports_characters_and_breakdowns(client):
    saas.record_usage("user-1", 2.0, characters=11, model="small", language="en")
    saas.record_usage("user-1", 1.0, characters=5, model="large-v3", language="fr")
    saas.record_usage("user-1", 0.5, characters=3, model="small", language="en")

    body = client.get("/v1/saas/usage").json()
    assert body["current_month"]["audio_minutes"] == 3.5
    assert body["current_month"]["requests"] == 3
    assert body["current_month"]["characters"] == 19
    assert body["by_model"] == {
        "small": {"audio_minutes": 2.5, "requests": 2},
        "large-v3": {"audio_minutes": 1.0, "requests": 1},
    }
    assert body["by_language"] == {
        "en": {"audio_minutes": 2.5, "requests": 2},
        "fr": {"audio_minutes": 1.0, "requests": 1},
    }
    assert body["daily_usage"][-1]["characters"] == 19


def test_usage_without_model_or_language_is_unattributed(client):
    saas.record_usage("user-1", 1.0)
    body = client.get("/v1/saas/usage").json()
    assert body["by_model"] == {"unknown": {"audio_minutes": 1.0, "requests": 1}}
    assert body["by_language"] == {"unknown": {"audio_minutes": 1.0, "requests": 1}}


def test_usage_is_per_user(client):
    saas.record_usage("user-1", 1.0, model="small")
    client.current_user["sub"] = "user-2"
    body = client.get("/v1/saas/usage").json()
    assert body["current_month"]["requests"] == 0
    assert body["by_model"] == {}


def test_delete_transcript(client):
    saas.record_transcript("user-1", {"id": "t1", "text": "hi"})
    assert client.delete("/v1/saas/transcripts/t1").status_code == 204
    assert client.get("/v1/saas/transcripts").json() == []
    assert client.delete("/v1/saas/transcripts/t1").status_code == 404


def test_export_my_data(client):
    client.post("/v1/saas/api-keys", json={"name": "ci"})
    saas.record_transcript("user-1", {"id": "t1", "text": "hi"})
    saas.record_usage("user-1", 1.0, characters=2, model="small", language="en")

    body = client.get("/v1/saas/me/export").json()
    assert body["profile"]["user_id"] == "user-1"
    assert body["profile"]["plan"] == "free"
    assert [k["name"] for k in body["api_keys"]] == ["ci"]
    assert "key_hash" not in body["api_keys"][0]
    assert [t["id"] for t in body["transcripts"]] == ["t1"]
    assert body["usage"][0]["by_model"] == {"small": {"audio_minutes": 1.0, "requests": 1}}


def test_export_is_scoped_to_the_caller(client):
    saas.record_transcript("user-1", {"id": "t1", "text": "hi"})
    client.current_user["sub"] = "user-2"
    body = client.get("/v1/saas/me/export").json()
    assert body["transcripts"] == []
    assert body["usage"] == []


def test_delete_my_data(client):
    client.post("/v1/saas/api-keys", json={"name": "ci"})
    saas.record_transcript("user-1", {"id": "t1", "text": "hi"})
    saas.record_transcript("user-1", {"id": "t2", "text": "ho"})
    saas.record_usage("user-1", 1.0)

    body = client.delete("/v1/saas/me/data").json()
    assert body == {"transcripts_deleted": 2, "usage_records_deleted": 1}
    assert client.get("/v1/saas/transcripts").json() == []
    assert client.get("/v1/saas/usage").json()["current_month"]["requests"] == 0
    # api keys are credentials, not personal records
    assert len(client.get("/v1/saas/api-keys").json()) == 1


def test_delete_my_data_leaves_other_users_alone(client):
    saas.record_transcript("user-2", {"id": "t1", "text": "hi"})
    assert client.delete("/v1/saas/me/data").json() == {
        "transcripts_deleted": 0,
        "usage_records_deleted": 0,
    }
    assert [t["id"] for t in saas._transcripts["user-2"]] == ["t1"]


def test_shared_plan_tables():
    assert plans.included_minutes("pro") == 1000
    assert plans.included_minutes("unknown") == 60
    assert plans.price_per_minute("free") == 0.0
