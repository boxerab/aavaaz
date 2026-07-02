# Aavaaz Design TODO

Gap between advertised features (README, `docs/site`) and what is actually wired. See `DESIGN.md` for current state. Items are unchecked = not done.

## Unwired feature modules

Code exists and is unit-tested, but nothing in a running entry point calls it.

- [ ] **Noise reduction** (`features/noise_reduction.py`) — wire as an audio preprocess in the batch paths (decode → `NoiseReducer.reduce` → transcribe from array). Needs the `noisereduce` dependency and a graceful skip when it is absent. Cannot go in the streaming path without WhisperLive changes (audio input is upstream).
- [ ] **Multichannel** (`features/multichannel.py`) — split channels and transcribe each in the batch paths, then merge with channel labels.
- [ ] **Model cache** (`features/model_cache.py`) — only useful where per-request model selection matters; Lambda/Modal load one model per container. Wire into a multi-model server variant, or drop.
- [ ] **Storage backends** (`features/storage.py`) — Lambda persists to S3 directly today; using the abstraction is a refactor, not new capability. Wire only if a pluggable backend (MinIO/local) is actually needed.
- [ ] **Transcript search & tagging** (`features/search.py`) — needs a persistent index and a REST endpoint. The in-memory `TranscriptIndex` does not survive Lambda; best implemented as a SaaS endpoint over stored transcripts.
- [ ] **ACL / RBAC** (`features/acl.py`) — `UserStore` (per-user keys, roles, quota, rate limit) is not connected. Wire into an auth backend option; the streaming server currently uses WhisperLive's single shared key.
- [ ] **Live translation relay** (`features/translation_relay.py`) — pub/sub relay is standalone; no entry point creates channels or feeds it segments.

## Partially wired

- [ ] **Paragraph segmentation** — wired in Lambda only (`AAVAAZ_ENABLE_PARAGRAPHS`). Extend to Modal (`app.py`) and, if wanted, the streaming pipeline (needs a final-flush pass, since it groups across segments).
- [ ] **Webhook delivery** — wired in Lambda only (synchronous, on `callback_url`). Add the async S3-trigger path (store the callback URL at upload, fire on completion) and mirror in Modal.
- [ ] **Intelligence / formatting / PII / profanity** — wired in the streaming server (flags) and Lambda; mirror the same env-gated enrichment in Modal `app.py` for parity.

## SaaS

- [ ] **Usage metering is disconnected** — `record_usage` / `record_transcript` are never called from any transcription path, so `/v1/saas/usage` and `/v1/saas/transcripts` always report zero / empty. Wire them into the transcription completion path (Lambda handler and/or SaaS-authenticated requests).
- [ ] Consider collapsing the dual SaaS implementation (`api/saas.py` vs `serverless/saas_lambda.py`) behind a shared route factory + store interface. Deferred; the shared `api/plans.py` mitigates the worst drift for now.

## Upstream (WhisperLive) — not fixable in this repo

- [ ] **Batch 30s truncation** — the batched inference path truncates audio to 30s. The code runs from the WhisperLive checkout mounted by Modal, not this repo. Fix upstream, or add a long-audio guard in `deploy/modal/app.py` that routes >30s files to the non-batched path.
- [ ] **Modal per-client feature race** — `deploy/modal/app_live.py` mutates the shared server's `segment_post_processor` per client under `@modal.concurrent`. Needs per-connection dispatch (a WhisperLive change) or `max_inputs=1`.

## Docs

- [ ] README / `docs/site` advertise the unwired modules above as if complete; align the marketing surface with `DESIGN.md`.
- [ ] `docs/site/index.html` shows a `noise_reduction="near_field"` client kwarg and REST paths that do not exist; `docs/USER_MANAGEMENT.md` imports `whisper_live.acl` (should be `aavaaz.features.acl`).
- [ ] `docs/TEST_MATRIX.md` references deleted test files.

## Deploy / infra (unverified — no cloud build in CI)

- [ ] Docker/Helm/Terraform changes made during the audit are unverified by an actual build/deploy. Add a CI job that at least builds the images and `helm template`s the chart.
- [ ] Transcribe Lambda Function URL is unauthenticated by design (`deploy/terraform-lambda`); decide whether that is acceptable.

## Dashboard

- [ ] Team page is a client-only mock; custom vocabulary is collected but never sent; upload output-format selector is a no-op; status page reports "operational" for any response (`no-cors`). See the audit for the full list.
