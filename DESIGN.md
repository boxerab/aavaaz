# Aavaaz Design

Speech-to-text platform built as a thin extension over [WhisperLive](https://github.com/collabora/WhisperLive). WhisperLive is the engine; Aavaaz adds a post-processing plugin pipeline, batch/serverless handlers, a SaaS layer, and deploy tooling.

## Engine boundary (important)

The transcription engine, the streaming WebSocket protocol, VAD, cross-client batch inference, speaker diarization, and the Prometheus metrics endpoint all live in **WhisperLive** (an installed dependency, or a locally-mounted checkout on Modal). Aavaaz does not reimplement these. The `--batch-inference`, `--enable-diarization`, and `--metrics-port` CLI flags pass straight through to `whisper_live.server`. Earlier aavaaz copies of `batch_inference`/`diarization`/`metrics` were stale duplicates and have been removed.

## Components

- `aavaaz/server.py` — `AavaazServer` wraps `whisper_live.server.TranscriptionServer`. It injects the plugin pipeline through WhisperLive's `segment_post_processor` hook and passes model/word-timestamp/hotword/diarization/batch/metrics/auth/rate-limit options through the per-client options dict. `serve(**overrides)` sets attributes then calls `run()`.
- `aavaaz/features/plugins.py` — `PluginRegistry`: ordered, per-segment post-processors (`apply(segment) -> segment`).
- `aavaaz/plugins/builtins.py` — registers the built-in plugins (`formatting`, `pii_redaction`, `profanity_filter`, `audio_intelligence`) **disabled by default**. `AavaazServer` enables the ones selected via `enable_*` flags / `--smart-format`/`--pii-redaction`/`--profanity-filter`/`--intelligence`, so raw transcripts are never silently altered.
- `aavaaz/cli.py` — `aavaaz serve | transcribe | version`.
- `aavaaz/transcribe.py` — offline file transcription via faster-whisper (`text`/`json`/`srt`/`vtt`; SRT uses a comma decimal, VTT a period).
- `aavaaz/features/*` — feature modules (see status table).

## Entry points / deployment paths

| Path | File | Engine | Notes |
|---|---|---|---|
| Self-hosted streaming | `aavaaz serve` → `server.py` | WhisperLive | WS 9090 + REST 8000; plugin pipeline applies per segment; `--noise-reduction` preprocesses live frames; `--paragraphs`/`--intelligence`/`--callback-url` run at stream end |
| AWS Lambda (batch) | `serverless/lambda_handler.py` | faster-whisper (own pipeline) | S3-trigger + API Gateway; the primary batch path |
| Modal (GPU) | `deploy/modal/app_live.py` (live), `app.py` (batch), `app_tts.py` | WhisperLive (mounted) | `app.py` mounts WhisperLive from a hardcoded local path |
| SaaS API (self-host) | `saas_server.py` → `api/saas.py` | n/a | in-memory store; JWT auth (HS256 secret or RS256 JWKS) |
| SaaS API (serverless) | `serverless/saas_lambda.py` | n/a | DynamoDB (`api/dynamo_store.py`); Cognito or any JWKS provider; Mangum |
| Dashboard | `dashboard/` | n/a | Next.js static export SPA; Cognito; calls the SaaS API |
| Infra | `deploy/{terraform*,helm,modal}`, `Dockerfile*` | n/a | ECS/Lambda/EKS/Amplify |

## Feature module status

Wired = reachable through a running entry point. Library = importable but not connected to any pipeline/endpoint.

| Module | Status | Where wired |
|---|---|---|
| `formatting` | Wired | streaming plugin (`--smart-format`), lambda, modal |
| `pii_redaction` | Wired | streaming plugin (`--pii-redaction`), lambda, modal |
| `profanity_filter` | Wired | streaming plugin (`--profanity-filter`, `--profanity-mode`, `--profanity-words`), lambda, modal, app_live |
| `audio_intelligence` | Wired | streaming plugin per segment + whole-transcript analysis at stream end (`--intelligence`); filler removal (`--filler-removal`); lambda (`AAVAAZ_ENABLE_INTELLIGENCE`), modal |
| `utterance` (paragraphs) | Wired | lambda + modal (`AAVAAZ_ENABLE_PARAGRAPHS`), streaming (`--paragraphs`) |
| `webhook` | Wired | lambda + modal (`callback_url` in request), streaming (`--callback-url`) |
| `plugins` | Wired (core) | server pipeline |
| `noise_reduction` | Wired | lambda + modal audio preprocess (`maybe_reduce_noise`), streaming frames (`--noise-reduction`, WhisperLive `audio_preprocessor` hook) |
| `multichannel` | Wired (batch) | lambda + modal per-channel split/merge (shared `transcribe_channels`) |
| `search` (TranscriptIndex) | Wired (SaaS self-host) | `/v1/saas/transcripts` filters (`q`, `language`, `tag`, `model`, `start`, `end`); serverless uses DynamoDB filter |

## Auth

- Streaming server: single shared API key (`--api-key`), enforced by WhisperLive (REST header + WS `?token=`); `/docs`, `/redoc`, `/openapi.json`, `/health` are exempt. `api/auth.py` provides JWT + static-key auth for the self-hosted SaaS router: HS256 via `AAVAAZ_JWT_SECRET`, RS256 verified against `AAVAAZ_JWT_JWKS_URL` / `AAVAAZ_JWT_ISSUER` / `AAVAAZ_JWT_AUDIENCE` (Keycloak, Cognito, Auth0, Okta).
- SaaS serverless: Cognito id tokens by default, any JWKS provider via the same env vars (`saas_lambda.require_auth`).
- Batch Lambda: optional SaaS API-key gate (`AAVAAZ_REQUIRE_API_KEY`, validated against DynamoDB).

## SaaS layer

Two parallel implementations of the same REST surface (`/v1/saas/*`): `api/saas.py` (in-memory, self-host) and `serverless/saas_lambda.py` (DynamoDB, Lambda). Both serve transcript search filters (`q`, `language`, `tag`, `model`, `start`, `end`), usage with `characters` plus `by_model`/`by_language` breakdowns, and the GDPR routes `DELETE /v1/saas/transcripts/{id}`, `GET /v1/saas/me/export`, `DELETE /v1/saas/me/data`. Plan pricing/quota tables and the purchasable-plan allowlist are the single source of truth in `api/plans.py`, shared by both. Billing is Stripe (checkout + webhook); the webhook derives the plan from an allowlist, not client input.

## Invariants / gotchas

- Built-in plugins are registered disabled; nothing post-processes unless explicitly enabled.
- Batch/diarization/metrics come from WhisperLive, not aavaaz.
- The SaaS API exists twice; keep behavior in sync via the shared `api/plans.py` (drift here caused duplicated bugs before).
- Line endings are enforced to LF via `.gitattributes`.
- Tests mock `faster_whisper`/`whisper_live` (see `tests/test_serverless.py` and per-file `sys.modules` setup); the ML stack is not installed for the default `pytest` run (`-m "not smoke"`).
