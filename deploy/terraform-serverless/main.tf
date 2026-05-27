# Aavaaz SaaS — Serverless-First Deployment (Option D)
#
# Near-zero idle cost. Only pay when users transcribe.
#
# Architecture:
#   - Dashboard: Vercel (free tier) or S3+CloudFront
#   - SaaS API: Lambda + API Gateway
#   - Auth: Cognito (free tier up to 50k MAU)
#   - Database: DynamoDB (free tier: 25GB, 25 RCU/WCU)
#   - Batch transcription: Lambda (existing)
#   - Live transcription: Modal (existing, GPU pay-per-second)
#   - Billing: Stripe
#
# Monthly idle cost: ~$5 (Route53 + minimal API Gateway)
# Cost per transcription: ~$0.002-0.005/minute (Modal GPU time)
#
# Migration path to EKS:
#   When monthly revenue > $500, switch to deploy/terraform-saas/
#   for dedicated GPU nodes and lower per-minute costs.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# ---------- Variables ----------

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "domain" {
  description = "Domain name for the SaaS platform"
  type        = string
  default     = "aavaaz.dev"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "github_repo_url" {
  description = "GitHub repository URL for Amplify (e.g., https://github.com/user/aavaaz)"
  type        = string
}

variable "modal_ws_url" {
  description = "Modal WebSocket URL for live transcription"
  type        = string
  default     = "wss://your-workspace--aavaaz-live-web.modal.run/ws"
}

variable "stripe_publishable_key" {
  description = "Stripe publishable key (pk_live_... or pk_test_...)"
  type        = string
  default     = ""
}

# ---------- Cognito ----------

resource "aws_cognito_user_pool" "aavaaz" {
  name = "aavaaz-${var.environment}"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_uppercase = true
    require_symbols   = false
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = { Environment = var.environment }
}

resource "aws_cognito_user_pool_client" "dashboard" {
  name         = "aavaaz-dashboard"
  user_pool_id = aws_cognito_user_pool.aavaaz.id

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  supported_identity_providers = ["COGNITO"]

  callback_urls = [
    "https://app.${var.domain}/",
    "http://localhost:3000/",
  ]
  logout_urls = [
    "https://app.${var.domain}/",
    "http://localhost:3000/",
  ]
}

# ---------- DynamoDB Tables ----------

resource "aws_dynamodb_table" "api_keys" {
  name         = "aavaaz-api-keys-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "key_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "key_id"
    type = "S"
  }

  attribute {
    name = "key_hash"
    type = "S"
  }

  global_secondary_index {
    name            = "key-hash-index"
    hash_key        = "key_hash"
    projection_type = "ALL"
  }

  tags = { Environment = var.environment }
}

resource "aws_dynamodb_table" "usage" {
  name         = "aavaaz-usage-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "date"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "date"
    type = "S"
  }

  tags = { Environment = var.environment }
}

resource "aws_dynamodb_table" "subscriptions" {
  name         = "aavaaz-subscriptions-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "stripe_customer_id"
    type = "S"
  }

  global_secondary_index {
    name            = "stripe-customer-index"
    hash_key        = "stripe_customer_id"
    projection_type = "ALL"
  }

  tags = { Environment = var.environment }
}

resource "aws_dynamodb_table" "transcripts" {
  name         = "aavaaz-transcripts-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "created_at"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  tags = { Environment = var.environment }
}

# ---------- S3 (Audio Storage) ----------

resource "aws_s3_bucket" "audio" {
  bucket = "aavaaz-audio-${var.environment}-${var.region}"
  tags   = { Environment = var.environment }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id

  rule {
    id     = "expire-temp-uploads"
    status = "Enabled"
    filter {
      prefix = "uploads/"
    }
    expiration {
      days = 7
    }
  }

  rule {
    id     = "archive-transcripts"
    status = "Enabled"
    filter {
      prefix = "transcripts/"
    }
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
  }
}

# ---------- Lambda (SaaS API) ----------

resource "aws_iam_role" "saas_lambda" {
  name = "aavaaz-saas-lambda-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "saas_lambda" {
  name = "aavaaz-saas-lambda-policy"
  role = aws_iam_role.saas_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = [
          aws_dynamodb_table.api_keys.arn,
          "${aws_dynamodb_table.api_keys.arn}/index/*",
          aws_dynamodb_table.usage.arn,
          aws_dynamodb_table.subscriptions.arn,
          "${aws_dynamodb_table.subscriptions.arn}/index/*",
          aws_dynamodb_table.transcripts.arn,
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
        ]
        Resource = "${aws_s3_bucket.audio.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
    ]
  })
}

# ---------- API Gateway ----------

resource "aws_apigatewayv2_api" "saas" {
  name          = "aavaaz-saas-${var.environment}"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = [
      "https://app.${var.domain}",
      "http://localhost:3000",
    ]
    allow_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_headers = ["*"]
    max_age       = 3600
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.saas.id
  name        = "$default"
  auto_deploy = true
}

# ---------- Lambda Function ----------

resource "aws_ecr_repository" "saas_lambda" {
  name                 = "aavaaz-saas-lambda"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_lambda_function" "saas_api" {
  function_name = "aavaaz-saas-api-${var.environment}"
  role          = aws_iam_role.saas_lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.saas_lambda.repository_url}:latest"
  timeout       = 30
  memory_size   = 512

  environment {
    variables = {
      AAVAAZ_ENVIRONMENT      = var.environment
      AAVAAZ_COGNITO_REGION   = var.region
      AAVAAZ_COGNITO_POOL_ID  = aws_cognito_user_pool.aavaaz.id
      SAAS_DOMAIN             = "https://app.${var.domain}"
      AAVAAZ_PRICE_PER_MINUTE = "0.006"
    }
  }

  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.saas_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.saas.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.saas.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.saas_api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "catchall" {
  api_id    = aws_apigatewayv2_api.saas.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# ---------- Outputs ----------

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.aavaaz.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.dashboard.id
}

output "api_endpoint" {
  value = aws_apigatewayv2_api.saas.api_endpoint
}

output "audio_bucket" {
  value = aws_s3_bucket.audio.id
}

output "saas_lambda_ecr_url" {
  value = aws_ecr_repository.saas_lambda.repository_url
}

output "dynamodb_tables" {
  value = {
    api_keys      = aws_dynamodb_table.api_keys.name
    usage         = aws_dynamodb_table.usage.name
    subscriptions = aws_dynamodb_table.subscriptions.name
    transcripts   = aws_dynamodb_table.transcripts.name
  }
}
