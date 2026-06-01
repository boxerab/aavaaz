# Aavaaz — Serverless batch transcription on AWS Lambda
#
# Usage:
#   cd deploy/terraform-lambda
#   terraform init
#   terraform apply
#
# This provisions:
#   - ECR repository for the Lambda container image
#   - Lambda function with configurable memory and timeout
#   - S3 bucket for audio uploads (with event trigger)
#   - S3 bucket for transcript output
#   - API Gateway (HTTP API) for REST-based transcription
#   - IAM roles with least-privilege policies

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------- Variables ----------

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "whisper_model" {
  description = "Whisper model baked into the container image"
  type        = string
  default     = "small"
}

variable "monthly_budget_limit_usd" {
  description = "Monthly AWS budget limit for this Lambda deployment account"
  type        = number
  default     = 50
}

variable "budget_alert_email" {
  description = "Optional email address for budget alerts"
  type        = string
  default     = ""
}

variable "enable_budget_shutdown" {
  description = "Disable the transcription Lambda when actual monthly spend reaches the budget limit"
  type        = bool
  default     = true
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB (more memory = more CPU)"
  type        = number
  default     = 3008
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds (max 900)"
  type        = number
  default     = 300
}

variable "output_format" {
  description = "Transcript output format: json, text, srt, vtt"
  type        = string
  default     = "json"
}

variable "enable_pii_redaction" {
  description = "Enable PII redaction in transcripts"
  type        = bool
  default     = false
}

variable "enable_api_gateway" {
  description = "Create an HTTP API Gateway for REST-based transcription"
  type        = bool
  default     = true
}

variable "store_audio" {
  description = "Store uploaded audio files in S3 (disabled by default)"
  type        = bool
  default     = false
}

# ---------- ECR ----------

resource "aws_ecr_repository" "aavaaz_lambda" {
  name                 = "aavaaz-lambda"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# ---------- S3 Buckets ----------

resource "aws_s3_bucket" "audio_input" {
  bucket_prefix = "aavaaz-audio-input-"
  force_destroy = true
}

resource "aws_s3_bucket_cors_configuration" "audio_input_cors" {
  bucket = aws_s3_bucket.audio_input.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT"]
    allowed_origins = ["*"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket" "transcript_output" {
  bucket_prefix = "aavaaz-transcripts-"
  force_destroy = true
}

resource "aws_s3_bucket_lifecycle_configuration" "input_cleanup" {
  bucket = aws_s3_bucket.audio_input.id

  rule {
    id     = "cleanup-processed-audio"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = 7
    }
  }
}

# ---------- Monthly Budget Guardrail ----------

resource "aws_budgets_budget" "lambda_monthly_usage" {
  name         = "aavaaz-lambda-monthly-usage"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = var.budget_alert_email == "" ? [] : [var.budget_alert_email]

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 80
      threshold_type             = "PERCENTAGE"
      notification_type          = "FORECASTED"
      subscriber_email_addresses = [notification.value]
    }
  }

  dynamic "notification" {
    for_each = var.budget_alert_email == "" ? [] : [var.budget_alert_email]

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 100
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [notification.value]
    }
  }

  dynamic "notification" {
    for_each = var.enable_budget_shutdown ? [aws_sns_topic.budget_shutdown[0].arn] : []

    content {
      comparison_operator       = "GREATER_THAN"
      threshold                 = 100
      threshold_type            = "PERCENTAGE"
      notification_type         = "ACTUAL"
      subscriber_sns_topic_arns = [notification.value]
    }
  }
}

resource "aws_sns_topic" "budget_shutdown" {
  count = var.enable_budget_shutdown ? 1 : 0
  name  = "aavaaz-lambda-budget-shutdown"
}

resource "aws_sns_topic_policy" "budget_shutdown" {
  count  = var.enable_budget_shutdown ? 1 : 0
  arn    = aws_sns_topic.budget_shutdown[0].arn
  policy = data.aws_iam_policy_document.budget_shutdown_topic[0].json
}

data "aws_iam_policy_document" "budget_shutdown_topic" {
  count = var.enable_budget_shutdown ? 1 : 0

  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }

    actions   = ["SNS:Publish"]
    resources = [aws_sns_topic.budget_shutdown[0].arn]
  }
}

# ---------- IAM ----------

resource "aws_iam_role" "lambda_exec" {
  name = "aavaaz-lambda-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_s3" {
  name = "aavaaz-lambda-s3"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.audio_input.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.audio_input.arn}/uploads/*"
      },
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject"]
        Resource = [
          "${aws_s3_bucket.transcript_output.arn}/transcripts/*",
          "${aws_s3_bucket.transcript_output.arn}/audio/*",
        ]
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role" "budget_shutdown" {
  count = var.enable_budget_shutdown ? 1 : 0
  name  = "aavaaz-budget-shutdown"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "budget_shutdown" {
  count = var.enable_budget_shutdown ? 1 : 0
  name  = "aavaaz-budget-shutdown"
  role  = aws_iam_role.budget_shutdown[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["lambda:PutFunctionConcurrency"]
        Resource = aws_lambda_function.transcribe.arn
      },
    ]
  })
}

# ---------- Lambda ----------

resource "aws_lambda_function" "transcribe" {
  function_name = "aavaaz-transcribe"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.aavaaz_lambda.repository_url}:latest"
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout

  environment {
    variables = {
      AAVAAZ_MODEL         = var.whisper_model
      AAVAAZ_OUTPUT_FORMAT = var.output_format
      AAVAAZ_OUTPUT_BUCKET = aws_s3_bucket.transcript_output.id
      AAVAAZ_OUTPUT_PREFIX = "transcripts/"
      AAVAAZ_ENABLE_PII    = var.enable_pii_redaction ? "1" : "0"
      AAVAAZ_ENABLE_FORMAT = "1"
      AAVAAZ_STORE_AUDIO   = var.store_audio ? "1" : "0"
      AAVAAZ_AUDIO_BUCKET  = var.store_audio ? aws_s3_bucket.transcript_output.id : ""
      AAVAAZ_AUDIO_PREFIX  = "audio/"
      AAVAAZ_INPUT_BUCKET  = aws_s3_bucket.audio_input.id
    }
  }
}

data "archive_file" "budget_shutdown" {
  count       = var.enable_budget_shutdown ? 1 : 0
  type        = "zip"
  source_file = "${path.module}/budget_shutdown.py"
  output_path = "${path.module}/.terraform/budget_shutdown.zip"
}

resource "aws_lambda_function" "budget_shutdown" {
  count            = var.enable_budget_shutdown ? 1 : 0
  function_name    = "aavaaz-budget-shutdown"
  role             = aws_iam_role.budget_shutdown[0].arn
  filename         = data.archive_file.budget_shutdown[0].output_path
  source_code_hash = data.archive_file.budget_shutdown[0].output_base64sha256
  handler          = "budget_shutdown.handler"
  runtime          = "python3.12"
  timeout          = 30

  environment {
    variables = {
      TARGET_FUNCTION_NAME = aws_lambda_function.transcribe.function_name
    }
  }
}

resource "aws_lambda_permission" "budget_shutdown_sns" {
  count         = var.enable_budget_shutdown ? 1 : 0
  statement_id  = "AllowBudgetShutdownSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.budget_shutdown[0].function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.budget_shutdown[0].arn
}

resource "aws_sns_topic_subscription" "budget_shutdown" {
  count     = var.enable_budget_shutdown ? 1 : 0
  topic_arn = aws_sns_topic.budget_shutdown[0].arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.budget_shutdown[0].arn
}

# Lambda Function URL — no 29s API Gateway timeout limitation
resource "aws_lambda_function_url" "transcribe" {
  function_name      = aws_lambda_function.transcribe.function_name
  authorization_type = "NONE"
}

# ---------- S3 Event Trigger ----------

resource "aws_lambda_permission" "s3_invoke" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.transcribe.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.audio_input.arn
}

resource "aws_s3_bucket_notification" "audio_uploaded" {
  bucket = aws_s3_bucket.audio_input.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.transcribe.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
  }

  depends_on = [aws_lambda_permission.s3_invoke]
}

# ---------- API Gateway (optional) ----------

resource "aws_apigatewayv2_api" "transcribe" {
  count         = var.enable_api_gateway ? 1 : 0
  name          = "aavaaz-transcribe"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "DELETE", "OPTIONS"]
    allow_headers = ["Authorization", "Content-Type"]
    max_age       = 86400
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  count                  = var.enable_api_gateway ? 1 : 0
  api_id                 = aws_apigatewayv2_api.transcribe[0].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.transcribe.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "transcribe" {
  count     = var.enable_api_gateway ? 1 : 0
  api_id    = aws_apigatewayv2_api.transcribe[0].id
  route_key = "POST /v1/audio/transcriptions"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
}

resource "aws_apigatewayv2_route" "web_root" {
  count     = var.enable_api_gateway ? 1 : 0
  api_id    = aws_apigatewayv2_api.transcribe[0].id
  route_key = "GET /"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
}

resource "aws_apigatewayv2_route" "web_static" {
  count     = var.enable_api_gateway ? 1 : 0
  api_id    = aws_apigatewayv2_api.transcribe[0].id
  route_key = "GET /static/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
}

resource "aws_apigatewayv2_route" "upload_url" {
  count     = var.enable_api_gateway ? 1 : 0
  api_id    = aws_apigatewayv2_api.transcribe[0].id
  route_key = "GET /v1/upload-url"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
}

resource "aws_apigatewayv2_route" "health" {
  count     = var.enable_api_gateway ? 1 : 0
  api_id    = aws_apigatewayv2_api.transcribe[0].id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
}

resource "aws_apigatewayv2_route" "transcription_status" {
  count     = var.enable_api_gateway ? 1 : 0
  api_id    = aws_apigatewayv2_api.transcribe[0].id
  route_key = "GET /v1/transcription/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
}

resource "aws_apigatewayv2_route" "transcription_cancel" {
  count     = var.enable_api_gateway ? 1 : 0
  api_id    = aws_apigatewayv2_api.transcribe[0].id
  route_key = "DELETE /v1/transcription/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
}

resource "aws_apigatewayv2_stage" "default" {
  count       = var.enable_api_gateway ? 1 : 0
  api_id      = aws_apigatewayv2_api.transcribe[0].id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw_invoke" {
  count         = var.enable_api_gateway ? 1 : 0
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.transcribe.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.transcribe[0].execution_arn}/*/*"
}

# ---------- Outputs ----------

output "ecr_repository_url" {
  value = aws_ecr_repository.aavaaz_lambda.repository_url
}

output "audio_input_bucket" {
  value = aws_s3_bucket.audio_input.id
}

output "transcript_output_bucket" {
  value = aws_s3_bucket.transcript_output.id
}

output "lambda_function_name" {
  value = aws_lambda_function.transcribe.function_name
}

output "api_endpoint" {
  value = var.enable_api_gateway ? "${aws_apigatewayv2_api.transcribe[0].api_endpoint}/v1/audio/transcriptions" : ""
}

output "web_demo_url" {
  value = var.enable_api_gateway ? aws_apigatewayv2_api.transcribe[0].api_endpoint : ""
}

output "function_url" {
  value = aws_lambda_function_url.transcribe.function_url
}
