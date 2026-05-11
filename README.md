# Aavaaz

**Production-grade speech-to-text platform built on [WhisperLive](https://github.com/collabora/WhisperLive).**

Aavaaz (आवाज़, "voice" in Hindi) extends WhisperLive with enterprise features
that compete with Deepgram, ElevenLabs, and AssemblyAI — while keeping the
core transcription engine open-source.

## Features

| Category | Capabilities |
|----------|-------------|
| **Transcription** | Real-time WebSocket streaming, REST API (OpenAI-compatible), batch inference, multichannel audio |
| **Intelligence** | Speaker diarization, sentiment analysis, topic detection, entity extraction, summarization |
| **Post-processing** | Smart formatting, PII redaction, profanity filtering, noise reduction, utterance/paragraph segmentation |
| **Platform** | Webhook delivery, transcript search & tagging, storage backends (local/S3), ACL/auth, GDPR compliance, Prometheus metrics |
| **Deployment** | Docker, Helm charts, GPU auto-detection, model caching, SSE streaming |

## Quick Start

```bash
pip install aavaaz

# Start the server
aavaaz serve --model large-v3

# Transcribe a file
aavaaz transcribe audio.wav

# OpenAI-compatible REST endpoint
curl -X POST http://localhost:8000/v1/audio/transcriptions \
  -F file=@audio.wav -F model=large-v3
```

## Architecture

Aavaaz uses WhisperLive as its transcription engine and extends it via the
plugin system:

```
┌─────────────────────────────────────────┐
│              Aavaaz Server               │
│  ┌─────────────────────────────────┐    │
│  │  REST API / WebSocket / Web UI  │    │
│  └──────────────┬──────────────────┘    │
│  ┌──────────────┴──────────────────┐    │
│  │        Plugin Pipeline          │    │
│  │  diarization → formatting →     │    │
│  │  PII redaction → intelligence   │    │
│  └──────────────┬──────────────────┘    │
│  ┌──────────────┴──────────────────┐    │
│  │     WhisperLive Core Engine     │    │
│  │  faster-whisper / TensorRT /    │    │
│  │  OpenVINO                       │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## Development

```bash
git clone git@github.com:collabora/aavaaz.git
cd aavaaz
pip install -e ".[dev]"
pytest
```

## License

[MPL-2.0](LICENSE)
