# Aavaaz SaaS — Serverless Deployment

Near-zero idle cost deployment. Everything runs on your existing AWS account.

## What Gets Created

| Resource | Service | Free Tier? | Monthly Cost |
|----------|---------|-----------|-------------|
| Auth | Cognito | Yes (50k MAU) | $0 |
| Database | DynamoDB | Yes (25GB) | $0 |
| API | API Gateway + Lambda | Yes (1M req) | ~$0 |
| Storage | S3 | Yes (5GB) | ~$1 |
| Dashboard | Amplify Hosting | Yes (1000 min/mo build) | ~$0 |
| DNS | Route53 | No | $0.50/zone |
| **Total idle** | | | **~$2-5/mo** |

## Prerequisites

- AWS CLI configured (`aws configure`)
- Terraform >= 1.5
- GitHub repo (for Amplify auto-deploy)
- Stripe account (you already have this)
- A domain (optional — works without one using AWS-provided URLs)

## Deploy

```bash
cd deploy/terraform-serverless

# Create your config
cat > terraform.tfvars <<EOF
region                 = "us-east-1"
domain                 = "aavaaz.dev"
environment            = "prod"
github_repo_url        = "https://github.com/YOUR_ORG/aavaaz"
modal_ws_url           = "wss://your-workspace--aavaaz-live-web.modal.run/ws"
stripe_publishable_key = "pk_live_..."
EOF

terraform init
terraform apply
```

## After Terraform

1. **Build & push the SaaS Lambda image:**
   ```bash
   cd ../..  # back to aavaaz root
   
   # Get ECR login
   aws ecr get-login-password --region us-east-1 | \
     docker login --username AWS --password-stdin $(terraform -chdir=deploy/terraform-serverless output -raw saas_lambda_ecr_url | cut -d/ -f1)
   
   # Build and push
   docker build -f Dockerfile.saas-lambda -t aavaaz-saas-lambda .
   docker tag aavaaz-saas-lambda:latest $(terraform -chdir=deploy/terraform-serverless output -raw saas_lambda_ecr_url):latest
   docker push $(terraform -chdir=deploy/terraform-serverless output -raw saas_lambda_ecr_url):latest
   
   # Update Lambda to use new image
   aws lambda update-function-code \
     --function-name aavaaz-saas-api-prod \
     --image-uri $(terraform -chdir=deploy/terraform-serverless output -raw saas_lambda_ecr_url):latest
   ```

2. **Set Stripe secrets** (can't store in Terraform state):
   ```bash
   aws lambda update-function-configuration \
     --function-name aavaaz-saas-api-prod \
     --environment "Variables={
       STRIPE_SECRET_KEY=sk_live_...,
       STRIPE_WEBHOOK_SECRET=whsec_...,
       STRIPE_PRICE_PRO=price_...,
       AAVAAZ_ENVIRONMENT=prod,
       AAVAAZ_COGNITO_REGION=us-east-1,
       AAVAAZ_COGNITO_POOL_ID=$(terraform output -raw cognito_user_pool_id),
       SAAS_DOMAIN=https://app.aavaaz.dev,
       AAVAAZ_PRICE_PER_MINUTE=0.006
     }"
   ```

3. **Connect Amplify** — push to your `main` branch and Amplify auto-deploys the dashboard.

4. **Stripe webhook** — add endpoint in Stripe Dashboard:
   - URL: `$(terraform output -raw api_endpoint)/v1/saas/stripe-webhook`
   - Events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`

## Test Locally

```bash
# Terminal 1: SaaS API (in-memory, no AWS needed)
source .venv/bin/activate
python -m aavaaz.saas_server
# → http://localhost:8001

# Terminal 2: Dashboard
cd dashboard
npm install
npm run dev
# → http://localhost:3000

# Terminal 3: Transcription server (if testing live demo)
aavaaz serve --model small
# → REST :8000, WebSocket :9090
```

For local dev, update `dashboard/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8001
NEXT_PUBLIC_WS_URL=ws://localhost:9090/ws
```

## Outputs

After `terraform apply`:
```
cognito_user_pool_id = "us-east-1_xxxxxxx"
cognito_client_id    = "xxxxxxxxxxxxxxxxxxxxxxxxxx"
api_endpoint         = "https://xxxxxxxx.execute-api.us-east-1.amazonaws.com"
audio_bucket         = "aavaaz-audio-prod-us-east-1"
```

## Upgrading to Kubernetes

When you outgrow serverless (>$500/mo revenue, need dedicated GPUs):

1. See `deploy/terraform-saas/README.md`
2. Migrate DynamoDB → PostgreSQL
3. Deploy Helm chart with GPU auto-scaling
4. Total migration time: ~1 day
