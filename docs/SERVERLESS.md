# Serverless Batch Transcription (AWS Lambda)

Aavaaz supports serverless deployment on AWS Lambda for batch audio
transcription.  This mode is ideal for file-based workloads where you don't
need real-time streaming — upload an audio file and receive the transcript.

## Architecture

```
                    ┌───────────────┐
  Upload audio ───▶ │  S3 (input)   │ ──── event ────▶ ┌─────────────────┐
                    └───────────────┘                   │  AWS Lambda     │
                                                        │  (aavaaz +      │
  POST /v1/audio ──▶ API Gateway ──────────────────────▶│  faster-whisper)│
  /transcriptions                                       └────────┬────────┘
                                                                 │
                                                        ┌────────▼────────┐
                                                        │  S3 (output)    │
                                                        │  or HTTP resp   │
                                                        └─────────────────┘
```

**Two trigger modes:**

| Mode | Trigger | Output |
|------|---------|--------|
| **S3 event** | Upload `.wav`/`.mp3`/`.flac`/`.m4a`/`.ogg` to the input bucket | Transcript written to output bucket |
| **REST API** | `POST /v1/audio/transcriptions` with S3 URL or base64 audio | Transcript in HTTP response |

## Quick Start

### 1. Build and push the container image

```bash
# From the project root
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker build -f Dockerfile.lambda \
  --build-arg WHISPER_MODEL=small.en \
  -t aavaaz-lambda .

docker tag aavaaz-lambda:latest <account>.dkr.ecr.us-east-1.amazonaws.com/aavaaz-lambda:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/aavaaz-lambda:latest
```

### 2. Deploy infrastructure

```bash
cd deploy/terraform-lambda
terraform init
terraform apply
```

### 3. Transcribe via S3

```bash
# Upload an audio file — transcription starts automatically
aws s3 cp recording.wav s3://$(terraform output -raw audio_input_bucket)/

# Check the output bucket for the transcript
aws s3 ls s3://$(terraform output -raw transcript_output_bucket)/transcripts/
```

### 4. Transcribe via REST API

```bash
# From an S3 URL
curl -X POST $(terraform output -raw api_endpoint) \
  -H "Content-Type: application/json" \
  -d '{"audio_url": "s3://my-bucket/recording.wav"}'

# With inline base64 audio
curl -X POST $(terraform output -raw api_endpoint) \
  -H "Content-Type: application/json" \
  -d "{\"audio_base64\": \"$(base64 -w0 recording.wav)\", \"filename\": \"recording.wav\"}"
```

## Configuration

All configuration is via environment variables on the Lambda function:

| Variable | Default | Description |
|----------|---------|-------------|
| `AAVAAZ_MODEL` | `small.en` | Whisper model (must match the model baked into the image) |
| `AAVAAZ_LANGUAGE` | *(auto)* | Language code (`en`, `fr`, etc.) or empty for auto-detect |
| `AAVAAZ_OUTPUT_FORMAT` | `json` | Output format: `json`, `text`, `srt`, `vtt` |
| `AAVAAZ_OUTPUT_BUCKET` | *(from Terraform)* | S3 bucket for transcript output |
| `AAVAAZ_OUTPUT_PREFIX` | `transcripts/` | Key prefix in the output bucket |
| `AAVAAZ_ENABLE_PII` | `0` | Set to `1` to enable PII redaction |
| `AAVAAZ_ENABLE_FORMAT` | `1` | Set to `1` to enable smart formatting |

## Terraform Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `aws_region` | `us-east-1` | AWS region |
| `whisper_model` | `small.en` | Model name (used in env vars) |
| `lambda_memory_mb` | `4096` | Lambda memory — more memory = more CPU |
| `lambda_timeout` | `300` | Timeout in seconds (max 900) |
| `output_format` | `json` | Transcript format |
| `enable_pii_redaction` | `false` | Enable PII redaction |
| `enable_api_gateway` | `true` | Create REST API endpoint |

## Model Selection

Lambda is CPU-only with a 10 GB memory limit.  Recommended models:

| Model | Memory | Latency (30s audio) | Quality |
|-------|--------|---------------------|---------|
| `tiny.en` | 1 GB | ~3 sec | Basic |
| `base.en` | 1.5 GB | ~5 sec | Good |
| `small.en` | 2.5 GB | ~10 sec | **Recommended** |
| `medium.en` | 5 GB | ~25 sec | High |

Use `int8` compute type (default in the Lambda image) to halve memory usage.

## Limitations

- **CPU only** — no GPU acceleration on Lambda
- **15-minute timeout** — files longer than ~10 minutes may time out with larger models
- **10 GB memory** — `large-v3` may not fit; use `small.en` or `medium.en`
- **Cold starts** — first invocation takes 15-30 seconds to load the model
  (subsequent warm invocations reuse the cached model)
- **No streaming** — batch/file mode only; use the ECS deployment for real-time WebSocket

## Cost Estimate

| Model | Memory | Typical duration | Cost per request |
|-------|--------|-----------------|-----------------|
| `small.en` | 4 GB | ~15 sec | ~$0.001 |
| `medium.en` | 8 GB | ~30 sec | ~$0.004 |

At 1,000 files/day with `small.en`: approximately **$1/day** + S3 storage.
