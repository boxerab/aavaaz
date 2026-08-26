# Aavaaz SaaS Platform

This document describes the hosted SaaS version of Aavaaz — a managed
speech-to-text service where users sign up, get API keys, and pay per usage.

## Overview

The SaaS platform adds user management, billing, and a web dashboard on top of
the core Aavaaz transcription engine. It's designed with two deployment tracks:

| Track | Use Case | Idle Cost | When to Use |
|-------|----------|-----------|-------------|
| **Serverless** (`deploy/terraform-serverless/`) | Early stage, < $500/mo revenue | ~$5/mo | Start here |
| **Kubernetes** (`deploy/terraform-saas/`) | Scale stage, dedicated GPU fleet | ~$313/mo | When you have paying customers |

Both tracks share the same dashboard and API code — only the infrastructure differs.

## Architecture (Serverless Track)

```
┌─────────────────────────────────────────────────────────────┐
│    Vercel / S3+CloudFront                                    │
│    (Next.js Dashboard)                                       │
└─────────────────┬───────────────────────────────────────────┘
                  │
    ┌─────────────▼──────────────┐
    │  API Gateway (HTTP API)     │
    │  → Lambda (SaaS API)        │
    │  Cognito JWT authorizer     │
    └─────────────┬──────────────┘
                  │
    ┌─────────────▼──────────────┐
    │  DynamoDB (free tier)       │
    │  • api-keys                 │
    │  • usage                    │
    │  • subscriptions            │
    │  • transcripts              │
    └────────────────────────────┘

    Transcription backends (unchanged):
    • Batch: Lambda (existing deploy/terraform-lambda/)
    • Live:  Modal (existing deploy/modal/app_live.py)
```

## Architecture (Kubernetes Track)

```
    ┌────────────────────────────────────────────────────┐
    │  EKS Cluster                                        │
    │  ┌──────────────┐  ┌────────────────────────────┐  │
    │  │  Dashboard   │  │  Aavaaz GPU Pods            │  │
    │  │  + SaaS API  │  │  Karpenter (scale 0→N)     │  │
    │  └──────────────┘  └────────────────────────────┘  │
    └────────────────────────────────────────────────────┘
                 │
    ┌────────────▼──────────────────────────────┐
    │  RDS PostgreSQL │ ElastiCache Redis │ S3   │
    └───────────────────────────────────────────┘
```

## Components

### Dashboard (`dashboard/`)

Next.js 14 web application with:
- **Landing page** — feature overview and CTA
- **Authentication** — sign up, login, email verification (AWS Cognito)
- **API key management** — create, list, revoke keys
- **Usage dashboard** — quota bar, daily usage table
- **Billing** — plan selection (Free/Pro/Enterprise), Stripe checkout
- **Transcript history** — list completed jobs
- **Live demo** — microphone → WebSocket real-time transcription

Tech: Next.js 14, Tailwind CSS, AWS Amplify (Cognito), TypeScript.

### SaaS Backend API

Two implementations sharing the same endpoints:

1. **In-memory** (`aavaaz/api/saas.py`) — for local dev, mounts as FastAPI router
2. **DynamoDB** (`aavaaz/serverless/saas_lambda.py`) — for production Lambda deployment

Both accept an RS256 token from an identity provider once `AAVAAZ_JWT_JWKS_URL`,
`AAVAAZ_JWT_ISSUER` and `AAVAAZ_JWT_AUDIENCE` are set, and an HS256 token signed
with `AAVAAZ_JWT_SECRET`. The Lambda also accepts an `aavaaz_...` API key as the
bearer token. See `docs/KEYCLOAK_SSO.md`.

Endpoints:
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/saas/api-keys` | List user's API keys |
| POST | `/v1/saas/api-keys` | Create new API key |
| DELETE | `/v1/saas/api-keys/{id}` | Revoke an API key |
| GET | `/v1/saas/usage` | Get usage summary & daily breakdown |
| GET | `/v1/saas/subscription` | Get current subscription info |
| POST | `/v1/saas/checkout` | Create Stripe Checkout session |
| POST | `/v1/saas/billing-portal` | Create Stripe billing portal session |
| POST | `/v1/saas/stripe-webhook` | Handle Stripe webhook events |
| GET | `/v1/saas/transcripts` | List/search transcript history |
| GET | `/v1/saas/transcripts/{id}` | Get specific transcript |
| PATCH | `/v1/saas/transcripts/{id}/tags` | Replace a transcript's tags |
| DELETE | `/v1/saas/transcripts/{id}` | Delete a transcript (204, 404 if not yours) |
| GET | `/v1/saas/me/export` | Export the caller's profile, keys, transcripts, usage |
| DELETE | `/v1/saas/me/data` | Erase the caller's transcripts and usage records |
| GET | `/v1/saas/team` | List team members |
| POST | `/v1/saas/team` | Invite a team member |
| PATCH | `/v1/saas/team/{id}` | Change a member's role |
| DELETE | `/v1/saas/team/{id}` | Remove a member |

On the serverless track `{id}` is the transcript's `created_at` timestamp, which
is the DynamoDB sort key.

#### Transcript search

`GET /v1/saas/transcripts` filters the caller's own transcripts. All parameters
combine, and an empty parameter set returns the full history.

| Parameter | Meaning |
|-----------|---------|
| `q` | case-insensitive substring of the transcript text |
| `language` | exact language code |
| `model` | exact model name |
| `tag` | `key:value`, repeatable |
| `start` | ISO 8601 lower bound on created time, inclusive |
| `end` | ISO 8601 upper bound on created time, inclusive |

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$API/v1/saas/transcripts?model=large-v3&language=en&start=2026-01-01&end=2026-02-01"
```

#### Usage response

`GET /v1/saas/usage` reports the current month:

```json
{
  "current_month": {"audio_minutes": 3.5, "requests": 3, "characters": 19, "cost_usd": 0.021},
  "quota": {"audio_minutes_limit": 1000, "audio_minutes_used": 3.5},
  "plan": "pro",
  "by_model": {"large-v3": {"audio_minutes": 2.5, "requests": 2}},
  "by_language": {"en": {"audio_minutes": 2.5, "requests": 2}},
  "daily_usage": [{"date": "2026-08-25", "audio_minutes": 3.5, "requests": 3, "characters": 19, "cost_usd": 0.021}]
}
```

Transcriptions that arrive without a model or language name are counted under
`unknown`.

#### Deleting data

`DELETE /v1/saas/me/data` erases transcripts and usage records and returns the
counts:

```json
{"transcripts_deleted": 12, "usage_records_deleted": 30}
```

API keys survive it. Revoke them through `DELETE /v1/saas/api-keys/{id}`.

### Infrastructure as Code

| Directory | Description |
|-----------|-------------|
| `deploy/terraform-serverless/` | Cognito + DynamoDB + API Gateway + S3 (cheap) |
| `deploy/terraform-saas/` | EKS + Karpenter + RDS + Redis + S3 (scalable) |
| `deploy/terraform-lambda/` | Batch transcription Lambda (existing) |
| `deploy/modal/` | Live transcription on Modal GPU (existing) |

## Pricing Tiers

| Plan | Monthly | Included Minutes | Overage | Features |
|------|---------|-----------------|---------|----------|
| Free | $0 | 60 | — | REST API, 1 key, community support |
| Pro | $29 | 1,000 | $0.006/min | WebSocket, unlimited keys, diarization, PII redaction |
| Enterprise | Custom | Unlimited | Negotiated | Dedicated GPU, custom models, SSO, SLA |

## Getting Started (Development)

### 1. Run the dashboard locally

```bash
cd dashboard
cp .env.example .env.local
# Edit .env.local — for local dev, the API URL points to localhost
npm install
npm run dev
# → http://localhost:3000
```

### 2. Run the SaaS API locally

```bash
# From the aavaaz root, with venv activated
python -m aavaaz.saas_server
# → http://localhost:8001
# Endpoints: /v1/saas/api-keys, /v1/saas/usage, etc.
```

### 3. Run the transcription server

```bash
aavaaz serve --model large-v3
# → REST :8000, WebSocket :9090
```

## Production Deployment (Serverless)

### Step 1: Deploy infrastructure

```bash
cd deploy/terraform-serverless
terraform init
terraform apply
```

Outputs: Cognito pool ID, client ID, API Gateway URL, DynamoDB table names, S3 bucket.

### Step 2: Deploy the SaaS Lambda

```bash
# Build Lambda container
docker build -f Dockerfile.saas-lambda -t aavaaz-saas-lambda .

# Push to ECR (create repo first if needed)
aws ecr get-login-password | docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com
docker tag aavaaz-saas-lambda:latest <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/aavaaz-saas-lambda:latest
docker push <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/aavaaz-saas-lambda:latest

# Create Lambda function (or add to Terraform)
aws lambda create-function \
  --function-name aavaaz-saas-api \
  --package-type Image \
  --code ImageUri=<ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/aavaaz-saas-lambda:latest \
  --role <LAMBDA_ROLE_ARN> \
  --environment "Variables={STRIPE_SECRET_KEY=sk_...,AAVAAZ_COGNITO_POOL_ID=us-east-1_xxx}"
```

### Step 3: Deploy the dashboard

**AWS Amplify Hosting** (auto-deploys from GitHub — no extra account needed):

The Terraform in `deploy/terraform-serverless/` creates an Amplify app connected to
your GitHub repo. Just push to `main` and it builds + deploys automatically.

```bash
# If you want to trigger a manual deploy:
aws amplify start-job --app-id <APP_ID> --branch-name main --job-type RELEASE
```

Alternatively, for local testing without Amplify:
```bash
cd dashboard
npm run build && npm run start
```

### Step 4: Configure Stripe

1. Create a Product in Stripe Dashboard (e.g., "Aavaaz Pro")
2. Create a Price ($29/month recurring)
3. Set `STRIPE_PRICE_PRO` env var to the Price ID
4. Add webhook endpoint pointing to your API Gateway URL + `/v1/saas/stripe-webhook`
5. Set `STRIPE_WEBHOOK_SECRET` to the webhook signing secret

### Step 5: Connect domains

- `app.aavaaz.dev` → Vercel / CloudFront (dashboard)
- `api.aavaaz.dev` → API Gateway (SaaS API)
- Keep existing Modal URL for live WebSocket transcription

## Migration: Serverless → Kubernetes

When ready to scale:

1. Deploy `deploy/terraform-saas/` (EKS + Karpenter)
2. Migrate DynamoDB → PostgreSQL (script TBD)
3. Deploy Aavaaz Helm chart with SaaS values
4. Update DNS to point to ALB
5. Keep Lambda as fallback / batch processing

## File Map

```
aavaaz/
├── api/
│   ├── saas.py              # SaaS API router (in-memory, for dev)
│   └── dynamo_store.py      # DynamoDB data layer (for production)
├── serverless/
│   └── saas_lambda.py       # Lambda handler (Mangum + DynamoDB)
├── saas_server.py           # Standalone SaaS API server (for local dev / EKS)
├── Dockerfile.saas-lambda   # Lambda container image

dashboard/
├── src/
│   ├── app/
│   │   ├── layout.tsx       # Root layout + Providers
│   │   ├── page.tsx         # Landing page
│   │   ├── login/           # Cognito sign-in
│   │   ├── signup/          # Account creation
│   │   ├── confirm/         # Email verification
│   │   └── dashboard/
│   │       ├── layout.tsx   # Sidebar navigation
│   │       ├── page.tsx     # Overview + stats
│   │       ├── keys/        # API key management
│   │       ├── usage/       # Usage tracking
│   │       ├── billing/     # Plans + Stripe
│   │       ├── transcripts/ # Job history
│   │       └── live/        # Live demo (WebSocket)
│   └── lib/
│       ├── auth.tsx         # Cognito AuthProvider
│       ├── api.ts           # Typed API client
│       └── aws-config.ts    # Amplify configuration
├── .env.example
├── Dockerfile
└── package.json

deploy/
├── terraform-serverless/    # Cheap serverless infra (start here)
│   └── main.tf
├── terraform-saas/          # Full EKS + GPU infra (scale later)
│   ├── main.tf
│   ├── karpenter-gpu-nodepool.yaml
│   ├── helm-values-saas.yaml
│   ├── k8s-dashboard.yaml
│   └── README.md
├── terraform-lambda/        # Existing batch transcription
├── modal/                   # Existing live transcription (GPU)
└── helm/                    # Existing Helm chart
```
