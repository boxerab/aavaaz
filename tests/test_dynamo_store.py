"""Tests for the DynamoDB store (aavaaz.api.dynamo_store) against a moto mock.

Covers the fixes that only manifest on the real serverless path: reserved-word
UpdateExpression, float->Decimal usage, and API-key expiry enforcement.
"""

import importlib
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

ENV = "test"


def _create_tables():
    client = boto3.client("dynamodb", region_name="us-east-1")
    client.create_table(
        TableName=f"aavaaz-api-keys-{ENV}",
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "key_id", "AttributeType": "S"},
            {"AttributeName": "key_hash", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "key_id", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "key-hash-index",
                "KeySchema": [{"AttributeName": "key_hash", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    client.create_table(
        TableName=f"aavaaz-usage-{ENV}",
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "date", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "date", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    client.create_table(
        TableName=f"aavaaz-subscriptions-{ENV}",
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "stripe_customer_id", "AttributeType": "S"},
        ],
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "stripe-customer-index",
                "KeySchema": [
                    {"AttributeName": "stripe_customer_id", "KeyType": "HASH"}
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    client.create_table(
        TableName=f"aavaaz-transcripts-{ENV}",
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "created_at", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    client.create_table(
        TableName=f"aavaaz-team-{ENV}",
        AttributeDefinitions=[
            {"AttributeName": "owner_id", "AttributeType": "S"},
            {"AttributeName": "member_id", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "owner_id", "KeyType": "HASH"},
            {"AttributeName": "member_id", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AAVAAZ_ENVIRONMENT", ENV)
    with mock_aws():
        # reload inside the mock so the module builds its boto3 tables against it
        from aavaaz.api import dynamo_store

        importlib.reload(dynamo_store)
        _create_tables()
        yield dynamo_store


def test_update_subscription_reserved_words(db):
    # 'plan' and 'status' are DynamoDB reserved words; the pre-fix raw
    # UpdateExpression raised ValidationException on every webhook update.
    db.update_subscription("user-1", {"plan": "pro", "status": "active"})
    sub = db.get_subscription("user-1")
    assert sub["plan"] == "pro"
    assert sub["status"] == "active"

    # confirm the environment really rejects the raw form this fix replaced,
    # so the assertion above is a genuine regression guard
    with pytest.raises(ClientError):
        db._table_subscriptions.update_item(
            Key={"user_id": "user-1"},
            UpdateExpression="SET status = :s",
            ExpressionAttributeValues={":s": "canceled"},
        )


def test_record_usage_accepts_float(db):
    # round() yields a float; the resource layer rejects floats unless converted
    # to Decimal, so this raised TypeError before the fix.
    db.record_usage("user-1", 1.5)
    db.record_usage("user-1", 0.5)
    usage = db.get_usage("user-1", days=1)
    assert sum(u["audio_minutes"] for u in usage) == 2.0
    assert sum(u["requests"] for u in usage) == 2


def test_validate_api_key_respects_expiry(db):
    meta, secret = db.create_api_key("user-1", "ci")
    assert db.validate_api_key(secret) == "user-1"

    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    db._table_api_keys.update_item(
        Key={"user_id": "user-1", "key_id": meta["id"]},
        UpdateExpression="SET #e = :e",
        ExpressionAttributeNames={"#e": "expires_at"},
        ExpressionAttributeValues={":e": past},
    )
    assert db.validate_api_key(secret) is None


def test_api_key_roundtrip(db):
    meta, secret = db.create_api_key("user-1", "ci")
    assert secret.startswith("aavaaz_")
    assert [k["id"] for k in db.list_api_keys("user-1")] == [meta["id"]]
    assert db.revoke_api_key("user-1", meta["id"]) is True
    assert db.validate_api_key(secret) is None


def test_find_user_by_stripe_customer(db):
    db.update_subscription("user-1", {"stripe_customer_id": "cus_123"})
    assert db.find_user_by_stripe_customer("cus_123") == "user-1"
    assert db.find_user_by_stripe_customer("cus_absent") is None


def test_team_add_list_remove(db):
    member = db.add_member("owner-1", "a@x.com", "admin")
    assert member["email"] == "a@x.com"
    assert member["role"] == "admin"
    assert member["id"]
    assert [m["id"] for m in db.list_members("owner-1")] == [member["id"]]
    assert db.remove_member("owner-1", member["id"]) is True
    assert db.list_members("owner-1") == []


def test_team_add_duplicate_raises(db):
    db.add_member("owner-1", "a@x.com", "member")
    with pytest.raises(ValueError):
        db.add_member("owner-1", "a@x.com", "member")


def test_team_update_role(db):
    member = db.add_member("owner-1", "a@x.com", "member")
    updated = db.update_member_role("owner-1", member["id"], "viewer")
    assert updated["role"] == "viewer"


def test_team_update_missing_returns_none(db):
    # ConditionExpression makes a missing member return None, not create a row
    assert db.update_member_role("owner-1", "nope", "admin") is None
    assert db.list_members("owner-1") == []


def test_team_remove_missing_returns_false(db):
    assert db.remove_member("owner-1", "nope") is False


def test_team_isolated_per_owner(db):
    db.add_member("owner-1", "a@x.com", "member")
    assert db.list_members("owner-2") == []


def test_search_transcripts(db):
    db.save_transcript(
        "u1",
        {"id": "1", "text": "hello kubernetes world", "language": "en",
         "tags": {"project": "x"}},
    )
    db.save_transcript(
        "u1", {"id": "2", "text": "bonjour le monde", "language": "fr", "tags": {}}
    )
    assert len(db.search_transcripts("u1")) == 2
    assert [t["id"] for t in db.search_transcripts("u1", query="kubernetes")] == ["1"]
    assert [t["id"] for t in db.search_transcripts("u1", language="fr")] == ["2"]
    assert [
        t["id"] for t in db.search_transcripts("u1", tags={"project": "x"})
    ] == ["1"]
    assert db.search_transcripts("u1", query="nope") == []


def test_set_transcript_tags(db):
    db.save_transcript("u1", {"id": "1", "text": "hi", "language": "en"})
    created_at = db.list_transcripts("u1")[0]["created_at"]
    updated = db.set_transcript_tags("u1", created_at, {"team": "a"})
    assert updated["tags"] == {"team": "a"}
    assert db.set_transcript_tags("u1", "does-not-exist", {"x": "y"}) is None
