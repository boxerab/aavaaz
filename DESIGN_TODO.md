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
- [x] **Per-request features in the batch Lambda** — `_handle_api` now reads `payload["features"]` (dashboard FeaturesConfig shape) and the S3-trigger path reads the same config from object metadata (`features_b64` → presign → `head_object`). Both override the env defaults. Diarization/translation/ensemble/noise-reduction are intentionally ignored here (not available in the faster-whisper batch path).

## SaaS

- [x] **Usage metering** — the batch Lambda now records usage + a transcript record on the transcription completion path for authenticated requests. `_handle_api`/`_handle_multipart` use the resolved `user_id`; the S3 large-file path carries `user_id` through object metadata (set at presign time) and meters in `_handle_s3`. Metering is a no-op when unauthenticated (public demo). Requires `AAVAAZ_REQUIRE_API_KEY=1` to have a user to attribute to.
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
- [x] Transcribe Lambda auth — opt-in `AAVAAZ_REQUIRE_API_KEY=1` gates the API paths on a valid SaaS key (Bearer, validated against DynamoDB); default off keeps the public web demo working. Usage metering is wired on top of this (see SaaS section).

## Dashboard

- [ ] Team page is a client-only mock; status page reports "operational" for any response (`no-cors`); integrations page connects nothing. See the audit for the full list.
- [x] Custom vocabulary — the upload page now sends `aavaaz-custom-vocab` as hotwords (JSON body + S3 metadata); the batch Lambda passes them to `model.transcribe`. Per-word boost is UI-only (faster-whisper hotwords has no weighting; words are ordered highest-boost first).
- [x] Upload output-format selector — SRT/VTT now generate real cues instead of plain text with a fake extension.
- [x] API key persistence — created keys are saved to `aavaaz-api-key` so batch requests carry `Authorization` (note: the transcribe Lambda still doesn't enforce it; unauthenticated by design).
