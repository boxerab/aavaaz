# Scaling findings

Phase 0, 2026-08-26, RTX 3060 laptop 6 GB, model `small`, `--batch-inference`, LibriSpeech tracks, ramp of 10 clients every 30 s to 200 then a 300 s hold. Lag is how far the transcript trails the audio already sent.

## Result

Old defaults (beam 5, temperature fallback on, batch 8, no admission control): p95 lag passed 3 s at 10 clients, transcripts stopped past 110 clients, 3,713 batch timeouts.

New defaults (beam 1, fallback off, batch 16, admission control): p95 2.6 s at 20 clients, 3.2 s at 30, admitted clients hold at 30 while the rest get WAIT, hold phase p50 2.9 s and p95 3.7 s, zero timeouts. About 25 clients stay under 3 s p95 on this GPU. Raw runs are in `results_run*/`, `ab/`, `profile/`.

## What limited it, in the order found

1. Concurrent first connections each loaded the model (`disabled_tqdm has no attribute '_lock'`) and each started a batch worker. Both creations now hold a lock.
2. A request that waited 30 s was resubmitted with a longer buffer, so overload fed itself. The timed out chunk is now dropped. Chunks are capped at 30 s so none fall to the serial path.
3. Nothing refused clients. New clients now get WAIT when the batch queue wait EMA exceeds `--batch-max-queue-wait` (0.5 s), and at most `--batch-max-admissions-per-s` (5) get in per second. Without the rate limit a queue that drains for a moment admitted 200 waiting clients at once.
4. The worker thread did VAD and mel extraction serially. It is now done in the session thread before submit.
5. py-spy: the worker spends 91% of its time in CTranslate2 `generate`, the GIL is held 5% of the time. Decode is the limit, not Python. Beam 1 decodes 2.5x faster than beam 5. The temperature fallback re-decodes 5 to 10% of chunks but each pass costs a full batch decode, which halved throughput at beam 1. Both are off by default now, `--batch-beam-size 5 --batch-temperature-fallback` restores the old behaviour.
6. Load test clients told to WAIT retried every 5 s, 20 handshakes per second at 170 waiting clients. The client now backs off, doubling to 60 s.

Threads per client are 4 (websocket handler, frame reader, keepalive, transcription loop). They cost little once the polling sleeps became event waits.

## Open

- The admission signal (queue wait) excludes batch processing time, so it understates lag. Full submit-to-result latency would track lag more closely.
- Accuracy of beam 1 without fallback is unmeasured. The LibriSpeech tracks have reference transcripts, a WER run over the four configurations is a short job.
- `openvino_backend.py` and `trt_backend.py` still have the unlocked single-model check.
- WAIT carries minutes and the client just retries. A load balancer should route a WAITed client to another node.

## Phase 1 plan (AWS)

1. Pick the production model first. All numbers above are for `small`.
2. One process on the chosen instance: ramp to find the client count where p95 stays under 2 s through the hold (agent assist target, 3 s outer bound).
3. Then 2 and 4 processes on the same GPU. Locally this was skipped because the GPU was already at 96%. On a 4 vCPU g5.xlarge the CPU will bind first, prefer instances with more vCPU per GPU.
4. Clients per instance = processes per GPU times the per-process knee, with 30% headroom. One call is two streams if both legs are transcribed separately.
5. Terraform: N processes per GPU behind one target group, load balancer honours WAIT.
