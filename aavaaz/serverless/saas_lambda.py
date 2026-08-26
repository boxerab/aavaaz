"""
Aavaaz SaaS API — Lambda handler via Mangum.

Deploy as a Lambda function behind API Gateway HTTP API.
All data stored in DynamoDB (serverless, pay-per-request).

Environment variables:
    STRIPE_SECRET_KEY       — Stripe secret key
    STRIPE_WEBHOOK_SECRET   — Stripe webhook signing secret
    STRIPE_PRICE_PRO        — Stripe Price ID for Pro plan
    SAAS_DOMAIN             — Dashboard URL (for Stripe redirects)
    AAVAAZ_ENVIRONMENT      — Environment name (prod, staging, dev)
    AAVAAZ_PRICE_PER_MINUTE — Overage price per audio minute
    AAVAAZ_COGNITO_REGION   — Cognito region
    AAVAAZ_COGNITO_POOL_ID  — Cognito User Pool ID
    AAVAAZ_JWT_JWKS_URL     — JWKS endpoint (defaults to the Cognito pool's)
    AAVAAZ_JWT_ISSUER       — expected `iss` claim (defaults to the Cognito pool)
    AAVAAZ_JWT_AUDIENCE     — expected `aud` claim (defaults to the Cognito client)
"""

import logging
import os
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel

from aavaaz.api import auth, plans
from aavaaz.api import dynamo_store as db

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────────────────

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO", "")
SAAS_DOMAIN = os.environ.get("SAAS_DOMAIN", "https://app.aavaaz.dev")
COGNITO_REGION = os.environ.get("AAVAAZ_COGNITO_REGION", "us-east-1")
COGNITO_POOL_ID = os.environ.get("AAVAAZ_COGNITO_POOL_ID", "")
COGNITO_CLIENT_ID = os.environ.get("AAVAAZ_COGNITO_CLIENT_ID", "")
COGNITO_ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_POOL_ID}"

API_KEY_PREFIX = "aavaaz_"
BEARER_PREFIX = "Bearer "
EXPORT_TRANSCRIPT_LIMIT = 1000
EXPORT_USAGE_DAYS = 3650

# ─── JWT Validation ──────────────────────────────────────────────────────────

auth.configure_jwks(
    os.environ.get("AAVAAZ_JWT_JWKS_URL") or f"{COGNITO_ISSUER}/.well-known/jwks.json",
    os.environ.get("AAVAAZ_JWT_ISSUER") or COGNITO_ISSUER,
    os.environ.get("AAVAAZ_JWT_AUDIENCE") or COGNITO_CLIENT_ID,
)


async def require_auth(request: Request) -> dict:
    """Validate a SaaS API key or an identity-provider JWT."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith(BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = auth_header[len(BEARER_PREFIX) :]

    if token.startswith(API_KEY_PREFIX):
        user_id = db.validate_api_key(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return {"sub": user_id}

    try:
        claims = auth.verify_token(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e

    # cognito sets token_use, other providers omit it
    if claims.get("token_use", "id") != "id":
        raise HTTPException(status_code=401, detail="Wrong token type")
    return {"sub": claims["sub"], "email": claims.get("email", "")}


# ─── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(title="Aavaaz SaaS API", version="0.9.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.aavaaz.dev",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request Models ──────────────────────────────────────────────────────────


class CreateKeyRequest(BaseModel):
    name: str


class InviteMemberRequest(BaseModel):
    email: str
    role: str = "member"


class UpdateMemberRequest(BaseModel):
    role: str


class SetTagsRequest(BaseModel):
    tags: dict[str, str]


class CheckoutRequest(BaseModel):
    plan: str


# ─── Health Check ────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aavaaz-saas-lambda"}


# ─── API Key Endpoints ───────────────────────────────────────────────────────


@app.get("/v1/saas/api-keys")
async def list_api_keys(claims: dict = Depends(require_auth)):
    return db.list_api_keys(claims["sub"])


@app.post("/v1/saas/api-keys")
async def create_api_key(body: CreateKeyRequest, claims: dict = Depends(require_auth)):
    metadata, raw_secret = db.create_api_key(claims["sub"], body.name)
    return {"key": metadata, "secret": raw_secret}


@app.delete("/v1/saas/api-keys/{key_id}")
async def revoke_api_key(key_id: str, claims: dict = Depends(require_auth)):
    success = db.revoke_api_key(claims["sub"], key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked"}


# ─── Team Endpoints ──────────────────────────────────────────────────────────


@app.get("/v1/saas/team")
async def list_team(claims: dict = Depends(require_auth)):
    return db.list_members(claims["sub"])


@app.post("/v1/saas/team")
async def invite_member(body: InviteMemberRequest, claims: dict = Depends(require_auth)):
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if body.role not in db.TEAM_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role '{body.role}'")
    try:
        return db.add_member(claims["sub"], email, body.role)
    except ValueError:
        raise HTTPException(status_code=409, detail="Member already exists") from None


@app.patch("/v1/saas/team/{member_id}")
async def update_member(
    member_id: str, body: UpdateMemberRequest, claims: dict = Depends(require_auth)
):
    if body.role not in db.TEAM_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role '{body.role}'")
    member = db.update_member_role(claims["sub"], member_id, body.role)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@app.delete("/v1/saas/team/{member_id}")
async def remove_member(member_id: str, claims: dict = Depends(require_auth)):
    if not db.remove_member(claims["sub"], member_id):
        raise HTTPException(status_code=404, detail="Member not found")
    return {"status": "removed"}


# ─── Usage Endpoints ─────────────────────────────────────────────────────────


def _merge_breakdowns(entries: list[dict], field: str) -> dict[str, dict]:
    totals: dict[str, dict] = {}
    for entry in entries:
        for name, counts in entry[field].items():
            running = totals.setdefault(name, {"audio_minutes": 0.0, "requests": 0})
            running["audio_minutes"] += counts["audio_minutes"]
            running["requests"] += counts["requests"]
    return totals


@app.get("/v1/saas/usage")
async def get_usage(claims: dict = Depends(require_auth)):
    user_id = claims["sub"]
    sub = db.get_subscription(user_id)
    entries = db.get_usage(user_id, days=datetime.now(UTC).day - 1)

    plan = sub.get("plan", "free")
    included_minutes = plans.included_minutes(plan)
    price = plans.price_per_minute(plan)

    total_minutes = sum(e["audio_minutes"] for e in entries)
    total_requests = sum(e["requests"] for e in entries)
    total_characters = sum(e["characters"] for e in entries)

    return {
        "current_month": {
            "audio_minutes": total_minutes,
            "requests": total_requests,
            "characters": total_characters,
            "cost_usd": total_minutes * price,
        },
        "quota": {
            "audio_minutes_limit": included_minutes,
            "audio_minutes_used": total_minutes,
        },
        "plan": plan,
        "by_model": _merge_breakdowns(entries, "by_model"),
        "by_language": _merge_breakdowns(entries, "by_language"),
        "daily_usage": [
            {
                "date": e["date"],
                "audio_minutes": e["audio_minutes"],
                "requests": e["requests"],
                "characters": e["characters"],
                "cost_usd": e["audio_minutes"] * price,
            }
            for e in entries
        ],
    }


# ─── Subscription Endpoints ─────────────────────────────────────────────────


@app.get("/v1/saas/subscription")
async def get_subscription(claims: dict = Depends(require_auth)):
    user_id = claims["sub"]
    sub = db.get_subscription(user_id)
    plan = sub.get("plan", "free")
    included_minutes = plans.included_minutes(plan)
    price = plans.price_per_minute(plan)

    return {
        "plan": plan,
        "status": sub.get("status", "active"),
        "current_period_end": sub.get("current_period_end", ""),
        "cancel_at_period_end": sub.get("cancel_at_period_end", False),
        "price_per_minute": price,
        "included_minutes": included_minutes,
    }


@app.post("/v1/saas/checkout")
async def create_checkout(body: CheckoutRequest, claims: dict = Depends(require_auth)):
    if body.plan not in plans.PURCHASABLE_PLANS:
        raise HTTPException(
            status_code=400, detail=f"Plan '{body.plan}' is not available for checkout"
        )

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured")

    import stripe

    stripe.api_key = STRIPE_SECRET_KEY
    user_id = claims["sub"]
    sub = db.get_subscription(user_id)

    # Get or create Stripe customer
    customer_id = sub.get("stripe_customer_id", "")
    if not customer_id:
        customer = stripe.Customer.create(metadata={"aavaaz_user_id": user_id})
        customer_id = customer.id
        db.update_subscription(user_id, {"stripe_customer_id": customer_id})

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_PRO, "quantity": 1}],
        success_url=f"{SAAS_DOMAIN}/dashboard/billing?success=true",
        cancel_url=f"{SAAS_DOMAIN}/dashboard/billing?canceled=true",
        metadata={"aavaaz_user_id": user_id, "plan": body.plan},
    )

    return {"url": session.url}


@app.post("/v1/saas/billing-portal")
async def create_portal(claims: dict = Depends(require_auth)):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured")

    import stripe

    stripe.api_key = STRIPE_SECRET_KEY
    user_id = claims["sub"]
    sub = db.get_subscription(user_id)
    customer_id = sub.get("stripe_customer_id", "")

    if not customer_id:
        raise HTTPException(status_code=400, detail="No billing account")

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{SAAS_DOMAIN}/dashboard/billing",
    )

    return {"url": session.url}


# ─── Stripe Webhook ──────────────────────────────────────────────────────────


@app.post("/v1/saas/stripe-webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook not configured")

    import stripe

    stripe.api_key = STRIPE_SECRET_KEY
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session["metadata"].get("aavaaz_user_id")
        if user_id:
            db.update_subscription(
                user_id,
                {
                    "plan": session["metadata"].get("plan", "pro"),
                    "stripe_subscription_id": session.get("subscription", ""),
                    "status": "active",
                },
            )

    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        user_id = db.find_user_by_stripe_customer(subscription["customer"])
        if user_id:
            db.update_subscription(
                user_id,
                {
                    "status": subscription["status"],
                    "cancel_at_period_end": subscription["cancel_at_period_end"],
                    "current_period_end": datetime.fromtimestamp(
                        subscription["current_period_end"], tz=UTC
                    ).isoformat(),
                },
            )

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        user_id = db.find_user_by_stripe_customer(subscription["customer"])
        if user_id:
            db.update_subscription(user_id, {"plan": "free", "status": "canceled"})

    return {"received": True}


# ─── Transcript History ──────────────────────────────────────────────────────


@app.get("/v1/saas/transcripts")
async def list_transcripts(
    claims: dict = Depends(require_auth),
    q: str | None = Query(None, description="full-text substring filter"),
    language: str | None = Query(None),
    tag: list[str] = Query(default_factory=list, description="key:value tag filters"),
    model: str | None = Query(None, description="exact model name"),
    start: str | None = Query(None, description="ISO 8601 lower bound, inclusive"),
    end: str | None = Query(None, description="ISO 8601 upper bound, inclusive"),
):
    if q or language or tag or model or start or end:
        tags = dict(t.split(":", 1) for t in tag if ":" in t)
        return db.search_transcripts(
            claims["sub"],
            query=q,
            language=language,
            tags=tags or None,
            model=model,
            start=start,
            end=end,
        )
    return db.list_transcripts(claims["sub"])


@app.get("/v1/saas/transcripts/{transcript_id}")
async def get_transcript(transcript_id: str, claims: dict = Depends(require_auth)):
    # transcript_id is the created_at timestamp (range key)
    result = db.get_transcript(claims["sub"], transcript_id)
    if not result:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return result


@app.patch("/v1/saas/transcripts/{transcript_id}/tags")
async def set_transcript_tags(
    transcript_id: str,
    body: SetTagsRequest,
    claims: dict = Depends(require_auth),
):
    result = db.set_transcript_tags(claims["sub"], transcript_id, body.tags)
    if not result:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return result


@app.delete("/v1/saas/transcripts/{transcript_id}", status_code=204)
async def delete_transcript(transcript_id: str, claims: dict = Depends(require_auth)):
    if not db.delete_transcript(claims["sub"], transcript_id):
        raise HTTPException(status_code=404, detail="Transcript not found")


# ─── GDPR Endpoints ──────────────────────────────────────────────────────────


@app.get("/v1/saas/me/export")
async def export_my_data(claims: dict = Depends(require_auth)):
    user_id = claims["sub"]
    sub = db.get_subscription(user_id)
    return {
        "profile": {
            "user_id": user_id,
            "email": claims.get("email", ""),
            "plan": sub.get("plan", "free"),
            "status": sub.get("status", "active"),
        },
        "api_keys": db.list_api_keys(user_id),
        "transcripts": db.list_transcripts(user_id, limit=EXPORT_TRANSCRIPT_LIMIT),
        "usage": db.get_usage(user_id, days=EXPORT_USAGE_DAYS),
    }


@app.delete("/v1/saas/me/data")
async def delete_my_data(claims: dict = Depends(require_auth)):
    return db.delete_user_data(claims["sub"])


# ─── Mangum Lambda Handler ───────────────────────────────────────────────────

handler = Mangum(app)
