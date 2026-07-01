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


def test_shared_plan_tables():
    assert plans.included_minutes("pro") == 1000
    assert plans.included_minutes("unknown") == 60
    assert plans.price_per_minute("free") == 0.0
