# Aavaaz SaaS Platform — Deployment Guide

Production-grade hosted speech-to-text platform on AWS with Kubernetes GPU auto-scaling.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CloudFront CDN                             │
│              (Dashboard + API edge caching)                       │
└────────────────┬────────────────────────┬───────────────────────┘
                 │                        │
    ┌────────────▼───────┐   ┌────────────▼──────────────┐
    │   ALB (HTTPS/WSS)  │   │    API Gateway (REST)      │
    │   WebSocket routing │   │    /v1/audio/*             │
    └────────────┬───────┘   └────────────┬──────────────┘
                 │                        │
    ┌────────────▼────────────────────────▼───────────────┐
    │                  EKS Cluster                         │
    │  ┌──────────────┐  ┌────────────────────────────┐   │
    │  │  Dashboard   │  │  Aavaaz GPU Pods            │   │
    │  │  (Next.js)   │  │  g5.xlarge (A10G 24GB)     │   │
    │  │  + SaaS API  │  │  Karpenter auto-scale 0→N  │   │
    │  └──────────────┘  └────────────────────────────┘   │
    └─────────────────────────────────────────────────────┘
                 │
    ┌────────────▼─────────────────────────────────┐
    │  RDS PostgreSQL │ ElastiCache Redis │ S3      │
    └──────────────────────────────────────────────┘
```

## Components

| Component | Purpose | Technology |
|-----------|---------|-----------|
| Dashboard | User-facing web app (signup, keys, usage, billing) | Next.js 14 + Tailwind |
| SaaS API | API key mgmt, usage tracking, Stripe billing | FastAPI (Python) |
| Transcription | Live WebSocket + batch REST | Aavaaz + WhisperLive (GPU) |
| Auth | User registration & login | AWS Cognito |
| Billing | Subscriptions & metered usage | Stripe |
| Database | Users, keys, usage logs | PostgreSQL (RDS) |
| Cache | Rate limiting, sessions | Redis (ElastiCache) |
| Storage | Audio files, transcripts | S3 |
| GPU Scaling | Scale GPU nodes 0→N on demand | EKS + Karpenter |

## Quick Start (Development)

### 1. Dashboard

```bash
cd dashboard
cp .env.example .env.local
# Edit .env.local with your Cognito pool ID and API URL
npm install
npm run dev
# → http://localhost:3000
```

### 2. SaaS API

```bash
cd ..  # back to aavaaz root
source .venv/bin/activate
python -m aavaaz.saas_server
# → http://localhost:8001
```

### 3. Transcription Server

```bash
aavaaz serve --model large-v3 --batch-inference
# → REST on :8000, WebSocket on :9090
```

## Production Deployment

### Prerequisites

- AWS account with credits
- Terraform >= 1.5
- kubectl configured
- Stripe account (for billing)
- Domain name (e.g., aavaaz.dev)

### Step 1: Infrastructure

```bash
cd deploy/terraform-saas

# Create terraform.tfvars
cat > terraform.tfvars <<EOF
region      = "us-east-1"
domain      = "aavaaz.dev"
db_password = "$(openssl rand -base64 24)"
environment = "prod"
EOF

terraform init
terraform apply
```

This creates: VPC, EKS cluster, RDS, Redis, S3, Cognito, ECR repos.

### Step 2: Configure kubectl

```bash
aws eks update-kubeconfig --name aavaaz-saas --region us-east-1
```

### Step 3: Install Karpenter

```bash
helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter \
  --namespace karpenter --create-namespace \
  --set "settings.clusterName=aavaaz-saas" \
  --set "settings.interruptionQueue=aavaaz-saas" \
  --wait

# Apply GPU NodePool
kubectl apply -f karpenter-gpu-nodepool.yaml
```

### Step 4: Deploy Aavaaz

```bash
# Build and push images
aws ecr get-login-password | docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com

docker build -t aavaaz -f ../../Dockerfile ../..
docker tag aavaaz:latest <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/aavaaz:latest
docker push <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/aavaaz:latest

# Deploy with Helm
helm install aavaaz ../../deploy/helm/aavaaz \
  -f helm-values-saas.yaml \
  --set image.repository=<ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/aavaaz
```

### Step 5: Deploy Dashboard

```bash
cd ../../dashboard
docker build -t aavaaz-dashboard .
docker tag aavaaz-dashboard:latest <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/aavaaz-dashboard:latest
docker push <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/aavaaz-dashboard:latest

kubectl apply -f k8s-dashboard.yaml
```

### Step 6: DNS & SSL

Point your domain to the ALB:
- `api.aavaaz.dev` → ALB (transcription + SaaS API)
- `app.aavaaz.dev` → Dashboard service

## Pricing Tiers

| Plan | Price | Included | Overage |
|------|-------|----------|---------|
| Free | $0/mo | 60 min | — |
| Pro | $29/mo | 1,000 min | $0.006/min |
| Enterprise | Custom | Unlimited | Negotiated |

## Environment Variables

### SaaS API
| Variable | Description |
|----------|-------------|
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `STRIPE_PRICE_PRO` | Stripe Price ID for Pro plan |
| `AAVAAZ_JWT_SECRET` | JWT signing secret |
| `AAVAAZ_PRICE_PER_MINUTE` | Overage price per audio minute |
| `SAAS_DOMAIN` | Dashboard URL for Stripe redirects |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |

### Dashboard
| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_COGNITO_USER_POOL_ID` | Cognito User Pool ID |
| `NEXT_PUBLIC_COGNITO_CLIENT_ID` | Cognito App Client ID |
| `NEXT_PUBLIC_API_URL` | SaaS API base URL |
| `NEXT_PUBLIC_WS_URL` | WebSocket endpoint for live demo |

## Scaling Behavior

- **No load**: Karpenter terminates all GPU nodes (cost = $0 for GPUs)
- **First request**: Karpenter provisions a g5.xlarge (~2-3 min cold start)
- **Sustained load**: HPA scales pods, Karpenter provisions more nodes
- **Scale-down**: Nodes consolidate after 5 min idle, terminate when empty
- **Max capacity**: 8 GPUs (configurable in NodePool limits)

## Cost Estimate (us-east-1)

| Resource | Monthly Cost (idle) | Monthly Cost (moderate) |
|----------|-------------------|------------------------|
| EKS control plane | $73 | $73 |
| System nodes (2x m5.large) | $140 | $140 |
| GPU nodes (g5.xlarge) | $0 (scale to zero) | ~$800/GPU |
| RDS (db.t4g.medium) | $50 | $50 |
| Redis (cache.t4g.medium) | $45 | $45 |
| S3 + data transfer | ~$5 | ~$50 |
| **Total** | **~$313/mo** | **~$1,158/mo** |
