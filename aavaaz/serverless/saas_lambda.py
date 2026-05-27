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
"""

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel

from aavaaz.api import dynamo_store as db

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────────────────

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO", "")
SAAS_DOMAIN = os.environ.get("SAAS_DOMAIN", "https://app.aavaaz.dev")
PRICE_PER_MINUTE = float(os.environ.get("AAVAAZ_PRICE_PER_MINUTE", "0.006"))
COGNITO_REGION = os.environ.get("AAVAAZ_COGNITO_REGION", "us-east-1")
COGNITO_POOL_ID = os.environ.get("AAVAAZ_COGNITO_POOL_ID", "")

# ─── Cognito JWT Validation ──────────────────────────────────────────────────

_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        import jwt

        jwks_url = (
            f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"
            f"{COGNITO_POOL_ID}/.well-known/jwks.json"
        )
        _jwks_client = jwt.PyJWKClient(jwks_url)
    return _jwks_client


async def require_auth(request: Request) -> dict:
    """Validate Cognito JWT from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = auth_header[7:]

    # Also accept SaaS API keys (aavaaz_...)
    if token.startswith("aavaaz_"):
        user_id = db.validate_api_key(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return {"sub": user_id}

    # Validate Cognito JWT
    try:
        import jwt as pyjwt

        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        claims = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_POOL_ID}",
        )
        return {"sub": claims["sub"], "email": claims.get("email", "")}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


# ─── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(title="Aavaaz SaaS API", version="0.1.0")

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


# ─── Usage Endpoints ─────────────────────────────────────────────────────────


@app.get("/v1/saas/usage")
async def get_usage(claims: dict = Depends(require_auth)):
    user_id = claims["sub"]
    sub = db.get_subscription(user_id)
    entries = db.get_usage(user_id, days=30)

    plan = sub.get("plan", "free")
    included_minutes = {"free": 60, "pro": 1000, "enterprise": 999999}.get(plan, 60)
    price = {"free": 0.0, "pro": PRICE_PER_MINUTE, "enterprise": 0.004}.get(
        plan, PRICE_PER_MINUTE
    )

    total_minutes = sum(e["audio_minutes"] for e in entries)
    total_requests = sum(e["requests"] for e in entries)

    return {
        "current_month": {
            "audio_minutes": total_minutes,
            "requests": total_requests,
            "cost_usd": total_minutes * price,
        },
        "quota": {
            "audio_minutes_limit": included_minutes,
            "audio_minutes_used": total_minutes,
        },
        "plan": plan,
        "daily_usage": [
            {
                "date": e["date"],
                "audio_minutes": e["audio_minutes"],
                "requests": e["requests"],
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
    included_minutes = {"free": 60, "pro": 1000, "enterprise": 999999}.get(plan, 60)
    price = {"free": 0.0, "pro": PRICE_PER_MINUTE, "enterprise": 0.004}.get(
        plan, PRICE_PER_MINUTE
    )

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
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
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
                        subscription["current_period_end"], tz=timezone.utc
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
async def list_transcripts(claims: dict = Depends(require_auth)):
    return db.list_transcripts(claims["sub"])


@app.get("/v1/saas/transcripts/{transcript_id}")
async def get_transcript(transcript_id: str, claims: dict = Depends(require_auth)):
    # transcript_id is the created_at timestamp (range key)
    result = db.get_transcript(claims["sub"], transcript_id)
    if not result:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return result


# ─── Mangum Lambda Handler ───────────────────────────────────────────────────

handler = Mangum(app)
