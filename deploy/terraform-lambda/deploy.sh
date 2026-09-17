#!/usr/bin/env bash
# Deploy Aavaaz Lambda transcription service with web demo.
#
# Prerequisites:
#   - AWS CLI configured (`aws configure`)
#   - Docker installed
#   - Terraform installed (>= 1.5)
#
# Usage:
#   cd deploy/terraform-lambda
#   ./deploy.sh

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
REPO_NAME="aavaaz-lambda"
WHISPER_MODEL="${AAVAAZ_MODEL:-small}"

echo "==> Initializing Terraform..."
terraform init

echo "==> Applying Terraform (creates ECR, Lambda, API Gateway, S3 buckets)..."
terraform apply -auto-approve

# Get ECR repository URL from Terraform output
ECR_URL=$(terraform output -raw ecr_repository_url)
ACCOUNT_ID=$(echo "$ECR_URL" | cut -d. -f1)

echo "==> Logging in to ECR..."
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$ECR_URL"

echo "==> Building container image (model: $WHISPER_MODEL)..."
cd ../..

docker build -f Dockerfile.lambda \
  --build-arg WHISPER_MODEL="$WHISPER_MODEL" \
  -t "$REPO_NAME:latest" .

echo "==> Tagging and pushing to ECR..."
docker tag "$REPO_NAME:latest" "$ECR_URL:latest"
docker push "$ECR_URL:latest"

echo "==> Updating Lambda to use new image..."
FUNCTION_NAME=$(cd deploy/terraform-lambda && terraform output -raw lambda_function_name)
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --image-uri "$ECR_URL:latest" \
  --region "$REGION" > /dev/null

echo "==> Waiting for Lambda update to complete..."
aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"

API_ENDPOINT=$(cd deploy/terraform-lambda && terraform output -raw api_endpoint)
WEB_URL=$(echo "$API_ENDPOINT" | sed 's|/v1/audio/transcriptions||')

echo ""
echo "============================================"
echo "  Deployment complete!"
echo "============================================"
echo "  Web demo:  $WEB_URL"
echo "  API:       $API_ENDPOINT"
echo "  Model:     $WHISPER_MODEL"
echo "============================================"
