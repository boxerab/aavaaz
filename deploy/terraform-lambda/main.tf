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
  default     = "small.en"
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

resource "aws_s3_bucket" "transcript_output" {
  bucket_prefix = "aavaaz-transcripts-"
  force_destroy = true
}

resource "aws_s3_bucket_lifecycle_configuration" "input_cleanup" {
  bucket = aws_s3_bucket.audio_input.id

  rule {
    id     = "cleanup-processed-audio"
    status = "Enabled"

    expiration {
      days = 7
    }
  }
}

# ---------- IAM ----------

resource "aws_iam_role" "lambda_exec" {
  name = "aavaaz-lambda-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
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
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.audio_input.arn}/*"
      },
      {
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.transcript_output.arn}/*"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
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
    }
  }
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
    filter_suffix       = ".wav"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.transcribe.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".mp3"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.transcribe.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".flac"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.transcribe.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".m4a"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.transcribe.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".ogg"
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
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type"]
    max_age       = 86400
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  count              = var.enable_api_gateway ? 1 : 0
  api_id             = aws_apigatewayv2_api.transcribe[0].id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.transcribe.invoke_arn
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
