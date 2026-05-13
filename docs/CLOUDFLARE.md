# Cloudflare Workers AI Transcription

Aavaaz supports serverless transcription on Cloudflare Workers using the
built-in **Workers AI** Whisper model (`@cf/openai/whisper`).  Cloudflare
runs inference on their GPU fleet — no model management, no cold starts.

## Architecture

```
                         ┌──────────────────────┐
  POST /transcribe ────▶ │  Cloudflare Worker    │
  (audio bytes or        │  ┌─────────────────┐ │
   base64 JSON)          │  │  Workers AI      │ │
                         │  │  @cf/openai/     │ │
                         │  │  whisper         │ │
                         │  └────────┬────────┘ │
                         │  ┌────────▼────────┐ │
                         │  │ Post-processing  │ │
                         │  │ PII / Formatting │ │
                         │  └────────┬────────┘ │
                         └───────────┼──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │  R2 (optional) or   │
                          │  HTTP response      │
                          └─────────────────────┘
```

## Quick Start

### 1. Install Wrangler

```bash
npm install -g wrangler
wrangler login
```

### 2. Deploy

```bash
cd deploy/cloudflare
wrangler deploy
```

That's it.  The Worker is live at `https://aavaaz-transcribe.<your-subdomain>.workers.dev`.

### 3. Transcribe

```bash
# Raw binary upload
curl -X POST https://aavaaz-transcribe.example.workers.dev \
  -H "Content-Type: application/octet-stream" \
  --data-binary @recording.wav

# JSON with base64
curl -X POST https://aavaaz-transcribe.example.workers.dev \
  -H "Content-Type: application/json" \
  -d "{\"audio_base64\": \"$(base64 -w0 recording.wav)\"}"
```

## Configuration

Edit `wrangler.toml` or set via `wrangler secret`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AAVAAZ_OUTPUT_FORMAT` | `json` | Output format: `json`, `text`, `srt`, `vtt` |
| `AAVAAZ_ENABLE_FORMAT` | `1` | Smart formatting (capitalize, punctuation) |
| `AAVAAZ_ENABLE_PII` | `0` | PII redaction (SSN, credit cards, emails, phones) |
| `AAVAAZ_API_KEY` | *(none)* | API key for Bearer token auth |

### R2 Storage (Optional)

To persist transcripts in Cloudflare R2:

```bash
# Create the bucket
wrangler r2 bucket create aavaaz-transcripts

# Uncomment the R2 binding in wrangler.toml
# [[r2_buckets]]
# binding = "TRANSCRIPTS"
# bucket_name = "aavaaz-transcripts"

wrangler deploy
```

## API Reference

### `POST /`

**Request formats:**

1. **Raw binary** — `Content-Type: application/octet-stream`
   ```
   POST / HTTP/1.1
   Content-Type: application/octet-stream
   [audio bytes]
   ```

2. **Base64 JSON** — `Content-Type: application/json`
   ```json
   {
     "audio_base64": "<base64-encoded audio>",
     "filename": "recording.wav"
   }
   ```

3. **R2 reference** (requires R2 binding) — `Content-Type: application/json`
   ```json
   {
     "audio_url": "r2://path/to/audio.wav"
   }
   ```

**Response** (JSON format):
```json
{
  "text": "Hello, this is a test recording.",
  "word_count": 6,
  "segments": [
    {
      "start": 0.0,
      "end": 2.5,
      "text": "Hello, this is a test recording.",
      "words": [...]
    }
  ]
}
```

## Comparison: Cloudflare vs AWS Lambda

| | Cloudflare Workers AI | AWS Lambda |
|---|---|---|
| **Cold start** | ~0 (model always loaded) | 15-30 sec (model loading) |
| **Model** | `@cf/openai/whisper` (fixed) | Any Whisper model |
| **GPU** | Cloudflare's fleet | CPU only |
| **Free tier** | 10,000 neurons/day | 1M requests/month |
| **Max audio** | ~30 sec per request | Limited by timeout (5 min) |
| **Custom models** | No | Yes |
| **Pipeline** | Formatting + PII | Full Aavaaz pipeline |
| **Word timestamps** | Limited | Full |

## Limitations

- **Model fixed** to `@cf/openai/whisper` — no custom or fine-tuned models
- **Audio length** limited to ~30 seconds per request (Workers AI constraint)
- **No diarization** — speaker identification not available
- **No custom vocabulary** — no hotword boosting
- **Post-processing in JS** — runs a JS port of formatting/PII, not the full Python pipeline
