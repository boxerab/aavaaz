# Aavaaz Design TODO

Gap between advertised features (README, `docs/site`) and what is actually wired. See `DESIGN.md` for current state. Items are unchecked = not done.

## Unwired feature modules

Code exists and is unit-tested, but nothing in a running entry point calls it.

- [x] **Noise reduction** (`features/noise_reduction.py`) — wired in the batch paths via `maybe_reduce_noise` (Lambda decodes+reduces when enabled; Modal reduces the decoded array). Enabled by `AAVAAZ_ENABLE_NOISE_REDUCTION`/`AAVAAZ_NOISE_MODE` env or per-request `features.noiseReduction`. `noisereduce` added to the `whisper` extra; skips gracefully if absent. Streaming path still needs upstream audio-input access (WhisperLive owns the mic frames).
- [x] **Multichannel** (`features/multichannel.py`) — wired in the Lambda batch path: when enabled (`features.multichannel` / `AAVAAZ_ENABLE_MULTICHANNEL`), decodes with `split_stereo`, transcribes each channel, and merges onto one timeline with `channel` labels (`merge_channel_segments`). Modal batch path (single-array batch worker) not yet split; deferred.
- [x] **Transcript search & tagging** — SaaS endpoints over stored transcripts. `GET /v1/saas/transcripts?q=&language=&tag=key:val` filters (DynamoDB query+filter serverless; `TranscriptIndex` for the in-memory self-host); `PATCH /v1/saas/transcripts/{id}/tags` sets tags. Metering now stores the transcript text so it's searchable. Tested (moto + in-memory).
- [x] **Removed as unused/superseded**: `model_cache` (Lambda/Modal load one model per container), `storage` (Lambda writes S3 directly; abstraction was a no-op), `acl` (superseded by the SaaS API keys + team API), `translation_relay` (no entry point). Modules + their tests deleted; marketing cards removed.

## Partially wired

- [x] **Paragraph segmentation** — Lambda and Modal (shared `aavaaz.features.enrichment`), and now streaming too: `aavaaz serve --paragraphs` runs `segment_into_paragraphs` over the accumulated transcript at stream end and sends a final `{"paragraphs": [...]}` message. Enabled by a new WhisperLive `transcript_finalizer` hook (see Upstream).
- [x] **Webhook delivery** — Lambda: synchronous on the JSON API path, async on the S3 large-file path (callback URL stored at upload via `callback_url_b64` → object metadata, fired in `_handle_s3`). Modal: fires `callback_url` (body or form field) inline on completion. Full parity.
- [x] **Intelligence / formatting / PII / profanity / filler** — the batch enrichment pipeline is now shared between Lambda and Modal via `aavaaz/features/enrichment.py` (`build_pipeline`/`enrich_result`), env-gated with per-request `features` override. Modal `app.py` reads `features` from the JSON body or a `features` form field. Hotwords stay Lambda-only (Modal's batch worker takes `initial_prompt`, not hotwords). Streaming server still has its own plugin path.
- [x] **Per-request features in the batch Lambda** — `_handle_api` now reads `payload["features"]` (dashboard FeaturesConfig shape) and the S3-trigger path reads the same config from object metadata (`features_b64` → presign → `head_object`). Both override the env defaults. Noise reduction is now honored (see Unwired modules). Diarization/translation/ensemble are still ignored here (not available in the faster-whisper batch path).

## SaaS

- [x] **Usage metering** — the batch Lambda now records usage + a transcript record on the transcription completion path for authenticated requests. `_handle_api`/`_handle_multipart` use the resolved `user_id`; the S3 large-file path carries `user_id` through object metadata (set at presign time) and meters in `_handle_s3`. Metering is a no-op when unauthenticated (public demo). Requires `AAVAAZ_REQUIRE_API_KEY=1` to have a user to attribute to.
- [ ] Consider collapsing the dual SaaS implementation (`api/saas.py` vs `serverless/saas_lambda.py`) behind a shared route factory + store interface. Deferred; the shared `api/plans.py` mitigates the worst drift for now.

## Upstream (WhisperLive) — not fixable in this repo

- [x] **Batch 30s truncation** — fixed in the WhisperLive batch worker: `_process_batch` now routes items longer than one 30s window to the single (windowed) `transcribe()` path instead of the batched mel encode that `pad_or_trim`s to 30s. Only the multi-item batched path truncated; single requests were already fine. Test added upstream.
- [x] **Modal per-client feature race** — `app_live.py` now sets `segment_post_processor` on the per-connection client object (WhisperLive already supports per-client processors) instead of mutating the shared server, so concurrent clients under `@modal.concurrent` no longer cross-contaminate. No WhisperLive change needed.
- [x] **Streaming paragraph segmentation** — done via a new WhisperLive `transcript_finalizer` hook (parallel to `segment_post_processor`): `ServeClientBase.finalize()` calls it with the accumulated transcript when the stream ends while the socket is still open (fired after the recv loop breaks, before `cleanup`), and sends any returned dict to the client. `AavaazServer._paragraph_finalizer` uses it under `--paragraphs`. This is a WhisperLive-repo change (a generic hook, not aavaaz-specific), committed separately in the WhisperLive checkout.

## Docs

- [x] Broken code/API references fixed: JS SDK `analyze()`/`listModels()` (hit nonexistent `/v1/audio/intelligence`, `/v1/models`) removed; `sdks/README.md` endpoint table trimmed to real routes; `docs/site` REST path corrected to `/v1/audio/transcriptions`, `/v1/models` curl and `noise_reduction="near_field"` kwarg removed; `docs/USER_MANAGEMENT.md` import fixed to `aavaaz.features.acl`.
- [x] Library-only features in the `docs/site` feature grid now carry a `Planned` tag (translation relay, noise reduction, multichannel, model hot-swap, search, auto-highlights/chapters, find&replace, spelling hints; ACL/storage in the enterprise list marked "(Planned)"). The zero-code Multi-Model Ensemble card and the broken README Auto-Reconnect example were removed. Note: only the primary feature grid was swept; repeated mentions in the showcase/comparison sections may still overstate.
- [x] `docs/TEST_MATRIX.md` remapped to real coverage: ensemble rows → Not implemented; diarization/batch rows → ⚠️ passthrough-only (`test_server.py`, behavior in WhisperLive); storage → `test_security.py`; webhook delivery → `test_serverless.py`; HMAC signature → Not implemented.
- [x] Marketing showcase swept: the repeated library-only "Noise Reduction" card in the capabilities/showcase section is now marked "(Planned)" too, matching the feature grid.

## Deploy / infra (unverified — no cloud build in CI)

- [x] CI now has an `infra` job: `terraform validate` across all four `deploy/terraform*` dirs (verified locally, all valid) + `helm lint`/`helm template` on the chart. Image build not added (needs registry auth); this catches HCL/chart syntax and wiring errors.
- [x] Transcribe Lambda auth — opt-in `AAVAAZ_REQUIRE_API_KEY=1` gates the API paths on a valid SaaS key (Bearer, validated against DynamoDB); default off keeps the public web demo working. Usage metering is wired on top of this (see SaaS section).

## Dashboard

- [x] Integrations page honestly reframed: it's a reference catalog of webhook recipes (not a one-click connect). Subtitle + footer now describe the real mechanism (pass `callback_url`, Aavaaz POSTs standard transcript JSON, no `{{variable}}` substitution) instead of implying live integration and a nonexistent Settings→Webhook template engine.
- [x] Team page is now backed by a real API: `/v1/saas/team` (GET/POST/PATCH/DELETE) in both SaaS implementations (`api/saas.py` in-memory, `serverless/saas_lambda.py` on a new `aavaaz-team-{env}` DynamoDB table). The page loads/invites/role-changes/removes against it; the current user shows as owner from the auth context. No email is actually sent (invite creates the member record directly). Terraform adds the table + IAM grant.
- [x] Status page now does real readable health checks (CORS fetch, reads status code → operational/degraded/down) instead of the always-green `no-cors` hack; added CORS to the Modal web app so its `/health` is browser-readable; dropped the un-checkable CloudFront row and the fabricated "no incidents" history.
- [x] Custom vocabulary — the upload page now sends `aavaaz-custom-vocab` as hotwords (JSON body + S3 metadata); the batch Lambda passes them to `model.transcribe`. Per-word boost is UI-only (faster-whisper hotwords has no weighting; words are ordered highest-boost first).
- [x] Upload output-format selector — SRT/VTT now generate real cues instead of plain text with a fake extension.
- [x] API key persistence — created keys are saved to `aavaaz-api-key` so batch requests carry `Authorization` (note: the transcribe Lambda still doesn't enforce it; unauthenticated by design).

## Claims removed or rescoped in the 2026-08-26 docs audit

Wanted features that the README or `docs/site` advertised but no entry point delivers. Each is unchecked until wired, then put the claim back.

### No code behind it

- [ ] **GDPR compliance** — no erasure/purge/export endpoints anywhere; needs transcript + usage deletion on the SaaS APIs and a documented retention policy.
- [ ] **Storage backends (local/S3)** — Lambda writes S3 directly; there is no storage abstraction and no local backend for `aavaaz serve`.
- [ ] **ACL** — only the shared API key and SaaS JWT exist; no roles/permissions on transcripts (the deleted `acl` module had `UserStore`/RBAC).
- [ ] **SSO providers** — site claimed Keycloak, Auth0, Okta with RS256 JWKS. `api/auth.py` is HS256 only; RS256 exists only in `serverless/saas_lambda.py` hardcoded to Cognito. `docs/KEYCLOAK_SSO.md` documents a `--jwt_jwks_url` flag no CLI accepts.
- [ ] **Edge / Jetson Dockerfiles** — `docker/Dockerfile.edge` and `docker/Dockerfile.jetson` exist nowhere, but `docs/EDGE_DEPLOYMENT.md` still references them.
- [ ] **Published Aavaaz images** — `ghcr.io/collabora/aavaaz-{gpu,cpu,openvino}` and Docker Hub `collabora/aavaaz` do not exist; only the WhisperLive engine images do. Needs a registry publish job and CPU/OpenVINO/TensorRT variants of `Dockerfile`.
- [ ] **`/health` on the streaming REST API** — the Go SDK's `Health()` (status, clients, max_clients) GETs a route only the SaaS server and Lambda have. Add it to the WhisperLive REST app or drop it from the SDK.
- [ ] **Helm `gpu.enabled`** — the chart always requests one `nvidia.com/gpu`; no CPU-only toggle.
- [ ] **Fine-tuning tooling** — `docs/FINE_TUNING.md` is a guide, no training script in the repo.
- [ ] **Web UI in `aavaaz serve`** — only the Lambda and Modal deployments serve a page.
- [ ] **Multi-GPU** — one process serves one GPU; nothing spreads sessions across devices (the SCALING guide covers one node per GPU behind a load balancer).

### Exists on one path, advertised as general

- [ ] **Noise reduction on streaming** — batch only (Lambda/Modal). Streaming needs audio-input access in WhisperLive before `add_frames`.
- [ ] **Multichannel on Modal batch and streaming** — Lambda only.
- [ ] **Summarization, highlights, filler removal on `aavaaz serve`** — the streaming plugin does per-segment sentiment/topics/entities only; whole-transcript analysis has no streaming hook beyond `transcript_finalizer` (paragraphs use it, intelligence could too).
- [ ] **Profanity mode and custom words on `aavaaz serve`** — CLI flag gives partial masking with the default list; mode/extra words are per-request on Lambda/Modal only.
- [ ] **Known speaker matching over WebSocket** — REST `verbose_json` only; the WS handshake has no enrollment fields.
- [ ] **Webhooks from `aavaaz serve` and Modal live** — Lambda only.
- [ ] **Language code + probability on REST `json`/SSE responses** — batch responses have both, REST `json` returns text only, `verbose_json` has no probability, SSE events have neither.
- [ ] **Transcript search filters** — endpoints take `q`, `language`, `tag`; `TranscriptIndex.search` already supports user/model/start/end but nothing exposes them. "Full-text" is a substring match.
- [ ] **Usage API characters and per-model/per-language breakdown** — only minutes, requests, cost, daily rows are recorded; `UsageTracker` in `features/search.py` has the richer shape but no caller.
- [ ] **Smart formatting punctuation cleanup** — formatter does capitalization, numbers, dates/times/currency; nothing touches punctuation.
- [ ] **Modal batch `word_timestamps` and hotwords** — `deploy/modal/app.py` never sets them on `BatchRequest`.
- [ ] **Auto-reconnect "only on unexpected disconnects"** — WhisperLive client reconnects on any close unless `server_error`; default `max_retries=0`.

### Behaviour the docs now describe instead of hide

- [ ] **REST `/v1/audio/transcriptions` model selection** — the `model` form field is ignored and `--model` only applies when it is a path or HF repo; otherwise the endpoint loads `small`. Upstream WhisperLive.
- [ ] **`/docs`, `/redoc`, `/openapi.json` behind `--api-key`** — the REST middleware 401s them; exempt them upstream.
- [ ] **PyPI install cannot start `aavaaz serve`** — published `whisper-live` 0.9.0 lacks the hooks; docs point at `boxerab/WhisperLive@scaling-fixes` until a release includes collabora/WhisperLive#535.
- [ ] **Lambda demo keeps large-file transcripts** — uploads over 6 MB go through S3 and their transcript objects are never deleted; add cleanup after the status handler returns them.
