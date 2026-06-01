# Aavaaz SaaS — Manual QA Checklist

**Dashboard URL:** https://du7890u4mptc6.cloudfront.net  
**Date:** 2025-05-27  
**Tester:** _______________

---

## 🔴 Critical Path Tests

| # | Test | Steps | Expected Result | Pass? |
|---|------|-------|-----------------|-------|
| 1 | Live transcription E2E | Dashboard → Live Demo → Start Recording → speak 30s | Real-time text appears within 2-60s (cold start) | ☐ |
| 2 | Live with cold start banner | Start live when Modal GPU is cold | Amber "cold start" warning shows, then transcription begins | ☐ |
| 3 | Batch upload (JSON) | File Upload → drag .wav → select JSON format → Submit | JSON response with text + segments array | ☐ |
| 4 | Batch upload (SRT) | File Upload → select SRT format → Submit | Valid SRT subtitle file with timestamps | ☐ |
| 5 | Feature pipeline: PII | Settings → enable PII Redaction → Live Demo → say "my SSN is 123-45-6789" | Numbers masked in output (e.g. `[REDACTED]`) | ☐ |
| 6 | Feature pipeline: Profanity | Settings → enable Profanity Filter → Live Demo → say profanity | Word replaced with `****` or similar | ☐ |
| 7 | API health check | API Playground → Batch (Lambda) → Try it | Returns `{"status": "ok"}` | ☐ |
| 8 | API curl from terminal | Copy curl from Playground → run in terminal | Same result as browser | ☐ |

---

## 🟡 Page Smoke Tests

| # | Page | Steps | Expected Result | Pass? |
|---|------|-------|-----------------|-------|
| 9 | Overview | Navigate to /dashboard | Stats cards render, no errors in console | ☐ |
| 10 | API Keys | Create a key → verify it appears → delete it | Key lifecycle works, persists in localStorage | ☐ |
| 11 | Vocabulary | Add word "Aavaaz" with boost 8 → Import "kubernetes,terraform" | Words appear in list with correct boost values | ☐ |
| 12 | Features/Settings | Toggle all 9 feature cards on → check config preview JSON | All features show `true` in JSON preview | ☐ |
| 13 | Integrations | Click "Zapier" card → verify template → click Copy | Template shown, copied to clipboard | ☐ |
| 14 | Integrations filter | Click "Storage" category tab | Only S3 + GCS cards visible | ☐ |
| 15 | Team | Invite user → change role to admin → remove user | All actions reflect in table immediately | ☐ |
| 16 | Request Logs | After batch upload, navigate to Logs | Upload request appears with timestamp + status | ☐ |
| 17 | Request Logs clear | Click Clear button | All logs removed | ☐ |
| 18 | Usage | Navigate to /dashboard/usage | Usage chart/stats render | ☐ |
| 19 | Billing | Navigate to /dashboard/billing | Plan info and billing section render | ☐ |
| 20 | Transcripts | Navigate to /dashboard/transcripts | Transcript history renders | ☐ |
| 21 | Status page | Navigate to /dashboard/status | 3 services checked, latency shown | ☐ |
| 22 | Status refresh | Click Refresh button | Timestamps update, latencies re-measured | ☐ |

---

## 🟠 Edge Cases & Error Handling

| # | Test | Steps | Expected Result | Pass? |
|---|------|-------|-----------------|-------|
| 23 | No microphone | Deny mic permission when prompted | Clear error message, no crash | ☐ |
| 24 | Upload non-audio file | Upload .txt or .pdf | Error message (not silent failure) | ☐ |
| 25 | Upload 0-byte file | Upload empty file | Graceful error | ☐ |
| 26 | Toggle features during live | Start live → toggle PII on/off mid-stream | No crash, feature applies on next segment | ☐ |
| 27 | Rapid start/stop live | Click Start/Stop 5 times quickly | No zombie connections, UI stays consistent | ☐ |
| 28 | Large file upload | Upload 10+ minute audio file | Progress shown, result eventually returns (may hit 300s Lambda timeout) | ☐ |
| 29 | Network offline | Disable network mid-live-session | Graceful disconnect message | ☐ |
| 30 | LocalStorage full | Fill localStorage, try creating API key | Graceful error or warning | ☐ |

---

## 🔵 Cross-Browser & Responsive

| # | Test | Browser/Device | Expected Result | Pass? |
|---|------|----------------|-----------------|-------|
| 31 | Full flow | Chrome (latest) | All critical path tests pass | ☐ |
| 32 | Full flow | Firefox (latest) | All critical path tests pass | ☐ |
| 33 | Mobile viewport | Chrome DevTools 375×667 (iPhone SE) | Sidebar collapses, all pages readable | ☐ |
| 34 | Tablet viewport | Chrome DevTools 768×1024 (iPad) | Layout adjusts, no overflow | ☐ |
| 35 | Live on mobile | Mobile Chrome, real device | getUserMedia works, transcription flows | ☐ |

---

## 🟣 Performance & Latency

| # | Test | Steps | Expected Result | Pass? |
|---|------|-------|-----------------|-------|
| 36 | Dashboard load time | Hard refresh (Ctrl+Shift+R) | First meaningful paint < 2s | ☐ |
| 37 | Batch API latency | Upload 30s audio, measure response | < 15s for small model | ☐ |
| 38 | Live first-byte (warm) | Start live when Modal is warm | First transcript < 2s | ☐ |
| 39 | Live first-byte (cold) | Start live after 10+ min idle | First transcript < 60s, warning shown | ☐ |
| 40 | CloudFront caching | Check response headers | Static assets have Cache-Control headers | ☐ |

---

## 🔐 Security Checks

| # | Test | Steps | Expected Result | Pass? |
|---|------|-------|-----------------|-------|
| 41 | HTTPS enforced | Try http:// URL | Redirects to https:// or blocked | ☐ |
| 42 | API CORS | Call API from different origin | CORS headers present, no open redirect | ☐ |
| 43 | No secrets in source | View page source, check JS bundles | No API keys, tokens, or credentials exposed | ☐ |
| 44 | XSS in transcript | Upload audio saying `<script>alert(1)</script>` | Text rendered safely, not executed | ☐ |

---

## Notes

- **Modal cold start**: The live transcription GPU container scales to zero after ~5 min idle. First request takes 30-60s to spin up. This is expected behavior for the demo.
- **Lambda timeout**: 300s max. Files longer than ~10 minutes may timeout with the current small model.
- **localStorage**: All state (keys, vocab, features, logs) is stored client-side. Clearing browser data resets everything.
- **Auth disabled**: Login/signup pages exist but auth guard is disabled for demo purposes.

---

## Summary

| Category | Total | Passed | Failed | Blocked |
|----------|-------|--------|--------|---------|
| Critical Path | 8 | | | |
| Page Smoke | 14 | | | |
| Edge Cases | 8 | | | |
| Cross-Browser | 5 | | | |
| Performance | 5 | | | |
| Security | 4 | | | |
| **TOTAL** | **44** | | | |
