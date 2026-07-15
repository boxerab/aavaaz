# Aavaaz Test Matrix

Comprehensive testing plan covering all features, deployment targets, and integration scenarios.

---

## Legend

| Priority | Meaning |
|----------|---------|
| P0 | Must pass before any release |
| P1 | Must pass before production deployment |
| P2 | Should pass, can ship with known issues |
| P3 | Nice to have, exploratory |

| Status | Meaning |
|--------|---------|
| ✅ | Covered by existing tests |
| ⚠️ | Partially covered |
| ❌ | Not yet covered |

---

## 1. Core Transcription

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 1.1 | Basic transcription (short audio < 10s) | P0 | ✅ | `test_smoke.py` |
| 1.2 | Long audio transcription (> 5 min) | P1 | ❌ | Needs real audio fixture |
| 1.3 | Multiple audio formats (WAV, MP3, FLAC, OGG, M4A) | P1 | ❌ | |
| 1.4 | Sample rate handling (8kHz, 16kHz, 44.1kHz, 48kHz) | P1 | ❌ | |
| 1.5 | Empty/silent audio | P1 | ❌ | Should return empty gracefully |
| 1.6 | Corrupted/invalid audio file | P1 | ❌ | Should return error, not crash |
| 1.7 | Model sizes (tiny, small, medium, large-v3, turbo) | P2 | ⚠️ | Only large-v3 smoke tested |
| 1.8 | Language detection (auto-detect) | P1 | ❌ | |
| 1.9 | Specific language transcription (en, es, fr, de, ja, zh) | P2 | ❌ | |
| 1.10 | Word timestamps accuracy | P2 | ❌ | |
| 1.11 | Hotwords/vocabulary boost | P2 | ❌ | |

---

## 2. Real-Time WebSocket Streaming

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 2.1 | WebSocket connection lifecycle (connect → stream → disconnect) | P0 | ⚠️ | `test_server.py` basic |
| 2.2 | Audio streaming at 16kHz float32 PCM | P0 | ❌ | |
| 2.3 | Incremental segment delivery (text appears progressively) | P0 | ❌ | |
| 2.4 | END_OF_AUDIO signal handling | P1 | ❌ | |
| 2.5 | Client reconnection after drop | P1 | ❌ | |
| 2.6 | Multiple concurrent clients (up to max_clients) | P1 | ❌ | |
| 2.7 | Client exceeding max_connection_time | P1 | ❌ | |
| 2.8 | Server full (WAIT status) | P1 | ❌ | |
| 2.9 | Raw PCM input mode | P2 | ❌ | |
| 2.10 | VAD filtering (silence between speech) | P1 | ❌ | |
| 2.11 | Very fast speech / overlapping words | P2 | ❌ | |
| 2.12 | Background noise handling during stream | P2 | ❌ | |

---

## 3. REST API

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 3.1 | POST /v1/audio/transcriptions (file upload) | P0 | ❌ | |
| 3.2 | POST /v1/audio/transcriptions (multipart form) | P0 | ❌ | |
| 3.3 | GET /health endpoint | P0 | ❌ | |
| 3.4 | GET /v1/models (list available models) | P1 | ❌ | |
| 3.5 | Response format: json | P0 | ❌ | |
| 3.6 | Response format: verbose_json (with timestamps) | P1 | ❌ | |
| 3.7 | Response format: srt | P1 | ❌ | |
| 3.8 | Response format: vtt | P1 | ❌ | |
| 3.9 | Response format: text (plain) | P1 | ❌ | |
| 3.10 | File size limit enforcement (25 MB) | P1 | ❌ | |
| 3.11 | Invalid file type rejection | P1 | ❌ | |
| 3.12 | OpenAPI spec serves at /openapi.json | P2 | ❌ | |

---

## 4. Authentication & Authorization

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 4.1 | API key authentication (valid key) | P0 | ✅ | `test_auth.py` |
| 4.2 | API key rejection (invalid key) | P0 | ✅ | `test_auth.py` |
| 4.3 | JWT token validation | P0 | ✅ | `test_auth.py` |
| 4.4 | Token expiration enforcement | P0 | ✅ | `test_auth.py` |
| 4.5 | Role-based access (admin/user/readonly) | P1 | ✅ | `test_acl.py` |
| 4.6 | Rate limiting (requests per minute) | P1 | ❌ | |
| 4.7 | Quota tracking and enforcement | P1 | ⚠️ | Unit tested, no integration |
| 4.8 | WebSocket authentication (token query param) | P1 | ❌ | |
| 4.9 | Unauthorized access returns 401/4001 | P1 | ❌ | |

---

## 5. Post-Processing Pipeline

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 5.1 | Smart formatting (capitalization) | P1 | ✅ | `test_formatting.py` |
| 5.2 | Spoken-to-numeric conversion ("twenty three" → "23") | P1 | ✅ | `test_formatting.py` |
| 5.3 | Punctuation normalization | P1 | ✅ | `test_formatting.py` |
| 5.4 | PII redaction: SSN | P0 | ⚠️ | `test_formatting.py` basic |
| 5.5 | PII redaction: credit card numbers | P0 | ❌ | |
| 5.6 | PII redaction: phone numbers | P0 | ❌ | |
| 5.7 | PII redaction: email addresses | P0 | ❌ | |
| 5.8 | PII redaction: IP addresses | P1 | ❌ | |
| 5.9 | Profanity filter (masking mode) | P2 | ❌ | |
| 5.10 | Pipeline ordering (format → PII → profanity) | P1 | ❌ | |
| 5.11 | Post-processor with empty/null segments | P1 | ❌ | |

---

## 6. Audio Intelligence

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 6.1 | Sentiment analysis (positive/negative/neutral) | P2 | ✅ | `test_intelligence.py` |
| 6.2 | Topic detection | P2 | ✅ | `test_intelligence.py` |
| 6.3 | Entity extraction (names, orgs, locations) | P2 | ✅ | `test_intelligence.py` |
| 6.4 | Text summarization | P2 | ✅ | `test_intelligence.py` |
| 6.5 | Intelligence on empty transcript | P2 | ❌ | |
| 6.6 | Intelligence on very long transcript | P2 | ❌ | |

---

## 7. Speaker Diarization

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 7.1 | Two-speaker identification | P1 | ⚠️ | `test_server.py` (flag passthrough; diarization behavior in WhisperLive) |
| 7.2 | Multi-speaker (3+) identification | P1 | ⚠️ | Unit tested |
| 7.3 | Max speakers limit enforcement | P1 | ⚠️ | `test_server.py` (flag passthrough; behavior in WhisperLive) |
| 7.4 | Speaker labels in output segments | P1 | ❌ | |
| 7.5 | Diarization with real audio (integration) | P1 | ❌ | |
| 7.6 | Single speaker (should not split) | P2 | ❌ | |

---

## 8. Multi-Channel Audio

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 8.1 | Stereo splitting (left/right) | P1 | ✅ | `test_multichannel.py` |
| 8.2 | Per-channel transcription merging | P1 | ✅ | `test_multichannel.py` |
| 8.3 | Channel labels in output | P1 | ✅ | `test_multichannel.py` |
| 8.4 | Mono audio (pass-through) | P1 | ❌ | |
| 8.5 | 4+ channel audio | P2 | ❌ | |

---

## 9. Ensemble Transcription

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 9.1 | Voting strategy (majority wins) | P1 | ❌ | Not implemented |
| 9.2 | Confidence strategy (highest confidence) | P1 | ❌ | Not implemented |
| 9.3 | Longest strategy | P1 | ❌ | Not implemented |
| 9.4 | Model registration and deregistration | P1 | ❌ | Not implemented |
| 9.5 | Ensemble with model failure (graceful degradation) | P1 | ❌ | |
| 9.6 | Real multi-model ensemble (integration) | P2 | ❌ | |

---

## 10. Batch Inference

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 10.1 | Single request processing | P0 | ⚠️ | `test_server.py` (flag passthrough; batching in WhisperLive) |
| 10.2 | Batch grouping (multiple clients) | P1 | ⚠️ | `test_server.py` (flag passthrough; batching in WhisperLive) |
| 10.3 | Queue timeout handling | P1 | ⚠️ | |
| 10.4 | Batch under concurrent load | P1 | ❌ | |
| 10.5 | Batch size limit enforcement | P1 | ❌ | |

---

## 11. Noise Reduction

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 11.1 | Near-field mode (stationary noise) | P1 | ✅ | `test_noise_reduction.py` |
| 11.2 | Far-field mode (non-stationary noise) | P1 | ✅ | `test_noise_reduction.py` |
| 11.3 | Audio shape preservation | P1 | ✅ | `test_noise_reduction.py` |
| 11.4 | Invalid mode rejection | P1 | ✅ | `test_noise_reduction.py` |
| 11.5 | Real noisy audio improvement (qualitative) | P2 | ❌ | |

---

## 12. Utterance Detection

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 12.1 | Pause-based segmentation | P1 | ✅ | `test_utterance.py` |
| 12.2 | Speaker change detection | P1 | ✅ | `test_utterance.py` |
| 12.3 | Paragraph grouping | P2 | ✅ | `test_utterance.py` |
| 12.4 | Custom pause threshold | P2 | ✅ | `test_utterance.py` |

---

## 13. Storage & Search

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 13.1 | Local storage save/load | P1 | ✅ | `test_security.py` |
| 13.2 | S3 storage backend | P1 | ❌ | Needs mock or localstack |
| 13.3 | Path traversal protection | P0 | ✅ | `test_security.py` |
| 13.4 | Transcript search (full-text) | P1 | ✅ | `test_search.py` |
| 13.5 | Search with tags | P2 | ✅ | `test_search.py` |
| 13.6 | Storage quota enforcement | P2 | ❌ | |

---

## 14. Webhooks

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 14.1 | Webhook delivery on transcription complete | P1 | ✅ | `test_serverless.py` |
| 14.2 | HMAC signature verification | P1 | ❌ | Not implemented |
| 14.3 | Exponential backoff retry on failure | P1 | ⚠️ | |
| 14.4 | Webhook timeout handling | P2 | ❌ | |
| 14.5 | Multiple webhook endpoints | P2 | ❌ | |

---

## 15. Plugin System

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 15.1 | Plugin registration | P1 | ✅ | `test_plugins.py` |
| 15.2 | Priority-based execution ordering | P1 | ✅ | `test_plugins.py` |
| 15.3 | Plugin failure isolation (one fails, others continue) | P1 | ❌ | |
| 15.4 | Plugin hot-reload | P2 | ❌ | |
| 15.5 | Custom plugin integration | P2 | ❌ | |

---

## 16. Model Cache

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 16.1 | Cache hit (same model) | P1 | ✅ | `test_model_cache.py` |
| 16.2 | LRU eviction when full | P1 | ✅ | `test_model_cache.py` |
| 16.3 | Cache size limit (max 3 models) | P1 | ✅ | `test_model_cache.py` |
| 16.4 | Concurrent model access (thread safety) | P1 | ❌ | |
| 16.5 | Cache with invalid model name | P1 | ❌ | |

---

## 17. Translation Relay

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 17.1 | Pub/sub message delivery | P1 | ✅ | `test_translation_relay.py` |
| 17.2 | Multi-language relay | P2 | ⚠️ | |
| 17.3 | Client subscribe/unsubscribe | P1 | ❌ | |
| 17.4 | Relay under load | P2 | ❌ | |

---

## 18. Deployment Targets

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 18.1 | Docker build (CPU) | P0 | ❌ | `docker build -f Dockerfile .` |
| 18.2 | Docker build (Lambda) | P0 | ❌ | `docker build -f Dockerfile.lambda .` |
| 18.3 | Modal deploy (batch) | P1 | ❌ | `modal deploy deploy/modal/app.py` |
| 18.4 | Modal deploy (live) | P1 | ❌ | `modal deploy deploy/modal/app_live.py` |
| 18.5 | Helm chart linting | P1 | ❌ | `helm lint deploy/helm/aavaaz` |
| 18.6 | Terraform plan (ECS) | P2 | ❌ | `terraform plan` |
| 18.7 | Terraform plan (Lambda) | P2 | ❌ | |
| 18.8 | Lambda handler (S3 trigger) | P1 | ⚠️ | `test_serverless.py` basic |
| 18.9 | Lambda handler (API Gateway) | P1 | ⚠️ | |
| 18.10 | Health endpoint on all deployments | P0 | ❌ | |

---

## 19. SDK Clients

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 19.1 | Python SDK: transcribe (file) | P1 | ❌ | |
| 19.2 | Python SDK: stream (WebSocket) | P1 | ❌ | |
| 19.3 | JavaScript SDK: transcribe (REST) | P1 | ❌ | |
| 19.4 | JavaScript SDK: transcribeStream (SSE) | P2 | ❌ | |
| 19.5 | Go SDK: Transcribe (REST) | P2 | ❌ | |
| 19.6 | Go SDK: Health check | P2 | ❌ | |
| 19.7 | SDK error handling (server down, timeout) | P1 | ❌ | |

---

## 20. Browser/UI

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 20.1 | Live transcription page loads | P0 | ❌ | Manual |
| 20.2 | Microphone capture and streaming | P0 | ❌ | Manual |
| 20.3 | Transcription text appears in real-time | P0 | ❌ | Manual |
| 20.4 | Copy button works | P2 | ❌ | Manual |
| 20.5 | Stop/disconnect clean (no error shown) | P1 | ❌ | Manual |
| 20.6 | Language selector works | P2 | ❌ | Manual |
| 20.7 | GitHub Pages demo (file upload) | P1 | ❌ | Manual |
| 20.8 | GitHub Pages demo (live streaming) | P1 | ❌ | Manual |
| 20.9 | Mobile browser support | P3 | ❌ | Manual |

---

## 21. Performance & Scale

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 21.1 | Transcription latency < 3s for 10s audio | P1 | ❌ | |
| 21.2 | 10 concurrent WebSocket clients | P1 | ❌ | |
| 21.3 | 100 concurrent REST requests | P2 | ❌ | |
| 21.4 | Memory usage under sustained load | P1 | ❌ | |
| 21.5 | GPU memory management (no OOM) | P1 | ❌ | |
| 21.6 | Cold start time (< 30s acceptable) | P1 | ❌ | |
| 21.7 | Model hot-swap latency | P2 | ❌ | |

---

## 22. Security

| # | Test Case | Priority | Status | Notes |
|---|-----------|----------|--------|-------|
| 22.1 | Path traversal blocked (storage) | P0 | ✅ | `test_security.py` |
| 22.2 | SQL/NoSQL injection in search | P0 | ❌ | |
| 22.3 | XSS in transcription output | P0 | ❌ | |
| 22.4 | CORS headers on REST API | P1 | ❌ | |
| 22.5 | Rate limiting prevents abuse | P1 | ❌ | |
| 22.6 | API key not leaked in logs | P0 | ❌ | |
| 22.7 | Webhook secret not exposed | P0 | ❌ | |
| 22.8 | Audio data not persisted (privacy) | P0 | ❌ | |

---

## Summary

| Category | Total Tests | Covered | Gaps |
|----------|-------------|---------|------|
| Core Transcription | 11 | 1 | 10 |
| WebSocket Streaming | 12 | 1 | 11 |
| REST API | 12 | 0 | 12 |
| Auth & ACL | 9 | 5 | 4 |
| Post-Processing | 11 | 4 | 7 |
| Audio Intelligence | 6 | 4 | 2 |
| Diarization | 6 | 3 | 3 |
| Multi-Channel | 5 | 3 | 2 |
| Ensemble | 6 | 4 | 2 |
| Batch Inference | 5 | 2 | 3 |
| Noise Reduction | 5 | 4 | 1 |
| Utterance | 4 | 4 | 0 |
| Storage & Search | 6 | 4 | 2 |
| Webhooks | 5 | 2 | 3 |
| Plugins | 5 | 2 | 3 |
| Model Cache | 5 | 3 | 2 |
| Translation Relay | 4 | 1 | 3 |
| Deployment | 10 | 1 | 9 |
| SDKs | 7 | 0 | 7 |
| Browser/UI | 9 | 0 | 9 |
| Performance | 7 | 0 | 7 |
| Security | 8 | 1 | 7 |
| **TOTAL** | **158** | **49** | **109** |

**Current coverage: ~31%** — Strong unit test coverage for individual features, but significant gaps in integration testing, deployment validation, SDK testing, and performance benchmarks.

---

## Recommended Test Execution Order

### Phase 1: Smoke Tests (CI/CD gate)
- 1.1, 2.1, 3.1, 3.3, 4.1, 4.2, 18.1, 18.2

### Phase 2: Feature Verification
- All P0 items not yet covered
- Post-processing pipeline end-to-end
- WebSocket streaming with real audio

### Phase 3: Integration & Deployment
- SDK tests against running server
- Deployment target validation
- Multi-feature pipeline (transcribe → format → PII → webhook)

### Phase 4: Performance & Security
- Load testing
- Security audit items
- Browser compatibility
