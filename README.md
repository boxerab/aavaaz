# Aavaaz

**Production-grade speech-to-text platform built on [WhisperLive](https://github.com/collabora/WhisperLive).**

Aavaaz (/aa-vaa-z/, आवाज़, "voice" in Hindi) is an open source extension of WhisperLive
with enterprise features that compete with Deepgram, ElevenLabs, and AssemblyAI.

## Features

| Category | Capabilities |
|----------|-------------|
| **Transcription** | Real-time WebSocket streaming, REST API (OpenAI-compatible), batch inference, multichannel audio (Lambda/Modal) |
| **Intelligence** | Speaker diarization, sentiment analysis, topic detection, entity extraction, summarization |
| **Post-processing** | Smart formatting, PII redaction, profanity filtering, noise reduction, filler word removal, utterance/paragraph segmentation |
| **Platform** | Webhook delivery, transcript search & tagging (SaaS API), S3 output storage (Lambda), API-key and JWT auth, JWT/SSO (JWKS), GDPR export/erasure, Prometheus metrics |
| **Deployment** | Docker, Helm charts, Terraform (AWS), **serverless (Lambda)**, **Modal (GPU)**, GPU auto-detection, model caching, SSE streaming |

## Quick Start

> **WhisperLive version note:** `aavaaz serve` uses hooks that are not in the
> published `whisper-live` 0.9.0 wheel yet. After any install below, replace
> it with the fork until a matching release exists:
> `pip install --no-deps "git+https://github.com/boxerab/WhisperLive@scaling-fixes"`

### Option 1: Install from PyPI (Recommended)

```bash
# Create a virtualenv (Python 3.12 or 3.13)
python3.12 -m venv .venv && source .venv/bin/activate

# Install aavaaz with WhisperLive + ML stack
pip install "aavaaz[whisper]"
pip install --no-deps "git+https://github.com/boxerab/WhisperLive@scaling-fixes"

# Start the server
aavaaz serve --model large-v3

# Transcribe a file
aavaaz transcribe audio.wav
```

### Option 2: Using `uv` (Fast & Reproducible)

```bash
# Install uv: https://docs.astral.sh/uv/
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv with Python 3.12 or 3.13
uv venv .venv --python python3.12
source .venv/bin/activate

# Install from PyPI
uv pip install "aavaaz[whisper]"
uv pip install --no-deps "git+https://github.com/boxerab/WhisperLive@scaling-fixes"

# Start the server
aavaaz serve --model large-v3

# Transcribe a file
aavaaz transcribe audio.wav
```

### Option 3: Local Development Install

```bash
git clone git@github.com:collabora/aavaaz.git
cd aavaaz
python3.12 -m venv .venv && source .venv/bin/activate

# Local editable install
pip install -e .

# With WhisperLive + dev tooling
pip install -e ".[whisper,dev]"
pip install --no-deps "git+https://github.com/boxerab/WhisperLive@scaling-fixes"
```

### Option 4: Using `pip` with Requirements Files

```bash
# Create a virtualenv (Python 3.12 or 3.13)
python3.12 -m venv .venv && source .venv/bin/activate

# Install base + ML stack (about 8 GB, mostly torch)
pip install -r requirements/whisper.txt
pip install --no-deps "git+https://github.com/boxerab/WhisperLive@scaling-fixes"

# Or install just base (fast, no ML):
# pip install -r requirements/base.txt

# Start the server (requires ML stack)
aavaaz serve --model large-v3

# Transcribe a file
aavaaz transcribe audio.wav

# OpenAI-compatible REST endpoint. The `model` form field takes a stock size,
# a local path, or an HF repo, and defaults to the server's `--model`.
curl -X POST http://localhost:8000/v1/audio/transcriptions \
  -F model=small \
  -F file=@audio.wav
```

### Note on Storage

The full ML stack (torch, torchaudio, CUDA libraries) needs about **8 GB** of disk.
If you hit disk quota errors, consider:
- Using `uv` which is faster and handles large downloads better
- Installing on a machine with more space
- Using serverless deployments (AWS Lambda / Modal) instead of local

### Requirements Files

- `requirements/base.txt` — Core dependencies only (fastapi, uvicorn, boto3)
- `requirements/whisper.txt` — Full ML stack (torch, whisper-live>=0.9.0, etc)
- `requirements/dev.txt` — Development tools (pytest, ruff, etc)

## Architecture

Aavaaz uses WhisperLive as its transcription engine and extends it via the
plugin system:

```
┌─────────────────────────────────────────┐
│              Aavaaz Server               │
│  ┌─────────────────────────────────┐    │
│  │      REST API / WebSocket       │    │
│  └──────────────┬──────────────────┘    │
│  ┌──────────────┴──────────────────┐    │
│  │        Plugin Pipeline          │    │
│  │  formatting → PII redaction →   │    │
│  │  profanity → intelligence       │    │
│  └──────────────┬──────────────────┘    │
│  ┌──────────────┴──────────────────┐    │
│  │    WhisperLive Core Engine      │    │
│  │  faster-whisper / TensorRT /    │    │
│  │  OpenVINO, VAD, diarization     │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## Advanced Features

### Word-Level Timestamps
Enable per-word timing and confidence scores in transcription segments:
```python
from aavaaz import AavaazServer

server = AavaazServer()
server.serve(word_timestamps=True)
```
When enabled, each segment includes a `words` array:
```json
{
  "segments": [{
    "start": "0.000", "end": "2.500", "text": "Hello world", "completed": true,
    "words": [
      {"word": "Hello", "start": "0.000", "end": "0.800", "probability": 0.95},
      {"word": " world", "start": "0.900", "end": "2.500", "probability": 0.88}
    ]
  }]
}
```

### Custom Vocabulary / Hotwords
Boost recognition of specific terms (product names, acronyms, domain jargon):
```python
from aavaaz import AavaazServer

server = AavaazServer()
server.serve(hotwords="Aavaaz,TensorRT,OpenVINO")
```
The `hotwords` parameter is a comma-separated string passed directly to faster-whisper's keyword boosting. Also available in the REST API via the `hotwords` form field.

### Speaker Diarization
Real-time speaker identification using pyannote.audio embeddings:
```bash
pip install pyannote.audio
```
```python
from aavaaz import AavaazServer

server = AavaazServer()
server.serve(enable_diarization=True, max_speakers=4)
```
When enabled, completed segments include a `speaker` field:
```json
{"start": "0.000", "end": "2.500", "text": "Hello", "speaker": "SPEAKER_00", "completed": true}
```

### Streaming Post-Processing Flags
Post-processing options for `aavaaz serve`:
```bash
aavaaz serve --model large-v3 \
  --noise-reduction near_field \
  --profanity-filter --profanity-mode full --profanity-words foo,bar \
  --filler-removal --filler-aggressive \
  --intelligence --paragraphs \
  --callback-url https://example.com/hook
```
- `--noise-reduction {near_field,far_field}` — reduce noise on live audio frames before transcription.
- `--profanity-mode {partial,full,remove}` — how `--profanity-filter` masks a match.
- `--profanity-words a,b` — extra words added to the profanity list.
- `--filler-removal` — drop filler words ("um", "you know") from each segment.
- `--filler-aggressive` — also drop borderline fillers ("like", "actually", "right").
- `--intelligence` — per-segment sentiment/topics/entities, plus a final `{"intelligence": ...}` message with summary and highlights for the whole transcript.
- `--paragraphs` — a final `{"paragraphs": [...]}` message at stream end.
- `--callback-url URL` — POST the final transcript (segments, paragraphs, intelligence) to URL, with retries.

### Authentication
Protect both REST API and WebSocket connections with a shared API key:
```bash
aavaaz serve --model large-v3 --api-key "my-secret-key"
```
- **REST API**: Requires `Authorization: Bearer my-secret-key` header
- **WebSocket**: Requires either `Authorization: Bearer my-secret-key` header or `?token=my-secret-key` query parameter

Unauthenticated connections receive HTTP 401 before any GPU resources are allocated.

Set `AAVAAZ_JWT_SECRET` to the HS256 secret the rest of the platform signs with and the WebSocket requires a platform token on every handshake as well. A browser offers it as `new WebSocket(url, ["bearer", token])`, other clients send an `Authorization: Bearer <token>` header. The token must carry `exp` and `sub` and must not carry `aud`, which is what stops a session token minted for another service being replayed here. With the variable unset the WebSocket accepts any client and says so in a warning at startup.

### Rate Limiting
Limit REST API requests per client IP (sliding 60-second window):
```bash
aavaaz serve --model large-v3 --rate-limit-rpm 60
```
Clients exceeding the limit receive HTTP 429.

### Batch Inference
Batch multiple client sessions into single GPU calls for higher throughput:
```bash
aavaaz serve --model large-v3 --batch-inference --batch-max-size 16 --batch-window-ms 50
```
`--batch-max-queue-wait` (default 0.5 seconds) turns new clients away with a WAIT message once requests sit in the batch queue longer than that. `--batch-max-admissions-per-s` (default 5) caps how many new clients get in per second, so a burst of reconnects cannot overshoot the queue before the wait reflects it.

### Prometheus Metrics
Monitor server health with a Prometheus `/metrics` endpoint:
```bash
aavaaz serve --model large-v3 --metrics-port 9091
```
Tracks active connections, transcription latency, segment counts, and error rates.

### SSE Streaming
Stream transcription results via Server-Sent Events from the REST API:
```bash
curl -X POST http://localhost:8000/v1/audio/transcriptions \
  -F file=@audio.wav -F stream=true
```
Returns real-time segment events as `text/event-stream`.

### Plugin System
Extend the transcription pipeline with custom post-processors:
```python
from aavaaz import AavaazServer, PluginRegistry

registry = PluginRegistry()
registry.add("my_plugin", my_post_processor_fn, priority=50)

server = AavaazServer(plugin_registry=registry)
server.serve()
```
Plugins receive each transcription segment dict and return the modified dict.
Passing your own registry replaces the built-in plugins; use `from aavaaz.plugins import registry`
and `registry.add(...)` to extend the built-ins instead.

## Scaling Guide

### Single GPU
```bash
aavaaz serve --model large-v3 --batch-inference
```

### Docker Compose
```yaml
services:
  aavaaz:
    build: .
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    ports:
      - "9090:9090"
      - "8000:8000"
```

### Kubernetes (Helm)
```bash
helm install aavaaz deploy/helm/aavaaz \
  --set model=large-v3 \
  --set replicaCount=3
```
Each replica requests one `nvidia.com/gpu` (see `values.yaml` `resources`).

### AWS (Terraform)
```bash
cd deploy/terraform
terraform init
terraform apply -var="model=large-v3" -var="api_key=my-secret"
```
Provisions VPC, ALB, ECS with GPU instances (g5.xlarge), ECR, and CloudWatch.
See [deploy/terraform/README.md](deploy/terraform/README.md) for full options.

### AWS Lambda (Serverless)

For batch file transcription without managing servers:

Production role: Lambda is the batch transcription path.

```bash
# Build and push the Lambda container image
docker build -f Dockerfile.lambda --build-arg WHISPER_MODEL=small -t aavaaz-lambda .

# Deploy infrastructure
cd deploy/terraform-lambda
terraform init
terraform apply

# Upload audio — transcript appears automatically in the output bucket
aws s3 cp recording.wav s3://$(terraform output -raw audio_input_bucket)/

# Or use the REST API
curl -X POST $(terraform output -raw api_endpoint) \
  -H "Content-Type: application/json" \
  -d '{"audio_url": "s3://my-bucket/recording.wav"}'
```

See [docs/SERVERLESS.md](docs/SERVERLESS.md) for full configuration, model
selection, cost estimates, and limitations.

### Modal (GPU Serverless)

Deploy on Modal for on-demand GPU transcription with zero infrastructure:

Production role: Modal is used for live WebSocket transcription (`deploy/modal/app_live.py`).
The `deploy/modal/app.py` endpoint is an optional GPU batch API.

```bash
cd deploy/modal
pip install modal
modal setup
modal deploy app_live.py

# Optional: deploy the GPU batch API endpoint
# modal deploy app.py

# Transcribe
# Live websocket URL is exposed by app_live.py deployment output.
```

Scales to zero after two idle minutes; the first connection after that waits for a container cold start.
See [docs/MODAL.md](docs/MODAL.md) for full configuration.

## Development

```bash
git clone git@github.com:collabora/aavaaz.git
cd aavaaz
pip install -e ".[dev]"
pytest
```

## License

[MPL-2.0](LICENSE)
