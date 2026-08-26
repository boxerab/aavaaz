"""Stream speech to an Aavaaz server from many virtual clients and record transcript lag.

Every client streams a track in real time. A transcript message covering audio up to
second E that arrives at wall time W has lag (W - stream_start) - E. Rows go to
messages.csv, connection outcomes to events.csv. Read them with report.py.
"""

import argparse
import asyncio
import csv
import json
import pathlib
import random
import statistics
import time
import uuid

import numpy as np
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 4096
CHUNK_SECONDS = CHUNK_SAMPLES / SAMPLE_RATE
READY_TIMEOUT_SECONDS = 60
WAIT_RETRY_S = 5.0
DEFAULT_TRACKS = pathlib.Path.home() / ".cache/aavaaz-loadtest/tracks"
STOP_LAG_INTERVALS = 2

MESSAGE_FIELDS = ["client", "session", "active", "t", "audio_end", "lag", "segments", "completed"]
EVENT_FIELDS = ["client", "session", "active", "t", "event", "connect_ms", "detail"]


class Run:
    def __init__(self, args, messages_file, events_file):
        self.args = args
        self.started_at = time.time()
        self.active = 0
        self.tracks = [np.fromfile(p, dtype=np.float32) for p in sorted(args.tracks.glob("*.f32"))]
        if not self.tracks:
            raise SystemExit(f"no *.f32 tracks in {args.tracks}, run prepare_audio.py first")
        self.messages_file = messages_file
        self.events_file = events_file
        self.messages = csv.DictWriter(messages_file, MESSAGE_FIELDS)
        self.events = csv.DictWriter(events_file, EVENT_FIELDS)
        self.messages.writeheader()
        self.events.writeheader()
        self.interval_lags = []
        self.intervals_over_stop_lag = 0
        self.interval_events = {}
        self.stop = asyncio.Event()

    def now(self):
        return time.time() - self.started_at

    def record_message(self, client, session, audio_end, lag, segments, completed):
        self.interval_lags.append(lag)
        self.messages.writerow(
            {
                "client": client,
                "session": session,
                "active": self.active,
                "t": f"{self.now():.3f}",
                "audio_end": f"{audio_end:.3f}",
                "lag": f"{lag:.3f}",
                "segments": segments,
                "completed": int(completed),
            }
        )

    def record_event(self, client, session, event, connect_ms="", detail=""):
        self.interval_events[event] = self.interval_events.get(event, 0) + 1
        self.events.writerow(
            {
                "client": client,
                "session": session,
                "active": self.active,
                "t": f"{self.now():.3f}",
                "event": event,
                "connect_ms": connect_ms,
                "detail": detail,
            }
        )

    def handshake(self):
        return json.dumps(
            {
                "uid": str(uuid.uuid4()),
                "language": "en",
                "task": "transcribe",
                "model": self.args.model,
                "use_vad": True,
                "send_last_n_segments": 10,
                "no_speech_thresh": 0.45,
                "clip_audio": False,
                "same_output_threshold": 10,
            }
        )

    async def client(self, client_id):
        session = 0
        while not self.stop.is_set():
            session += 1
            outcome = await self.session(client_id, session)
            if outcome == "wait":
                await asyncio.sleep(WAIT_RETRY_S)
            else:
                await asyncio.sleep(random.uniform(0.5, 2.0))

    async def session(self, client_id, session):
        track = random.choice(self.tracks)
        offset = random.randrange(0, len(track) - CHUNK_SAMPLES)
        connect_started = time.time()
        try:
            async with connect(
                self.args.url, max_size=None, open_timeout=READY_TIMEOUT_SECONDS
            ) as ws:
                await ws.send(self.handshake())
                outcome = await asyncio.wait_for(self.wait_ready(ws), READY_TIMEOUT_SECONDS)
                connect_ms = f"{(time.time() - connect_started) * 1000:.0f}"
                self.record_event(client_id, session, outcome, connect_ms)
                if outcome != "ready":
                    return outcome
                stream_start = time.time()
                receiver = asyncio.create_task(self.receive(ws, client_id, session, stream_start))
                try:
                    await self.send_audio(ws, track, offset, stream_start)
                finally:
                    receiver.cancel()
                self.record_event(client_id, session, "closed")
        except TimeoutError:
            self.record_event(client_id, session, "timeout")
        except ConnectionClosed as error:
            self.record_event(client_id, session, "disconnect", detail=str(error.rcvd))
        except OSError as error:
            self.record_event(client_id, session, "error", detail=str(error))

    async def wait_ready(self, ws):
        while True:
            message = json.loads(await ws.recv())
            if message.get("message") == "SERVER_READY":
                return "ready"
            if message.get("status") == "WAIT":
                return "wait"

    async def send_audio(self, ws, track, offset, stream_start):
        position = offset
        sent_seconds = 0.0
        while not self.stop.is_set() and time.time() - stream_start < self.args.session:
            chunk = track[position : position + CHUNK_SAMPLES]
            if len(chunk) < CHUNK_SAMPLES:
                position = 0
                continue
            sent_seconds += CHUNK_SECONDS
            delay = stream_start + sent_seconds - time.time()
            if delay > 0:
                await asyncio.sleep(delay)
            await ws.send(chunk.tobytes())
            position += CHUNK_SAMPLES

    async def receive(self, ws, client_id, session, stream_start):
        async for raw in ws:
            message = json.loads(raw)
            segments = message.get("segments")
            if not segments:
                continue
            audio_end = max(float(segment["end"]) for segment in segments)
            lag = (time.time() - stream_start) - audio_end
            self.record_message(
                client_id,
                session,
                audio_end,
                lag,
                len(segments),
                segments[-1].get("completed", False),
            )

    async def ramp(self):
        tasks = []
        while self.active < self.args.clients and not self.stop.is_set():
            for _ in range(min(self.args.ramp_step, self.args.clients - self.active)):
                self.active += 1
                tasks.append(asyncio.create_task(self.client(self.active)))
            await asyncio.sleep(self.args.ramp_interval)
            self.report_interval()
        hold_until = time.time() + self.args.hold
        while time.time() < hold_until and not self.stop.is_set():
            await asyncio.sleep(self.args.ramp_interval)
            self.report_interval()
        self.stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def report_interval(self):
        lags = sorted(self.interval_lags)
        events = " ".join(f"{name}={count}" for name, count in sorted(self.interval_events.items()))
        if lags:
            p50 = statistics.quantiles(lags, n=100)[49] if len(lags) > 1 else lags[0]
            p95 = statistics.quantiles(lags, n=100)[94] if len(lags) > 1 else lags[0]
            print(
                f"t={self.now():6.0f}s active={self.active:5d} msgs={len(lags):6d} "
                f"lag p50={p50:.2f}s p95={p95:.2f}s {events}",
                flush=True,
            )
            over = self.args.stop_lag and p95 > self.args.stop_lag
            self.intervals_over_stop_lag = self.intervals_over_stop_lag + 1 if over else 0
            if self.intervals_over_stop_lag >= STOP_LAG_INTERVALS:
                print(f"p95 lag over {self.args.stop_lag}s for {STOP_LAG_INTERVALS} intervals, stopping", flush=True)
                self.stop.set()
        else:
            print(f"t={self.now():6.0f}s active={self.active:5d} msgs=0 {events}", flush=True)
        self.interval_lags = []
        self.interval_events = {}
        self.messages_file.flush()
        self.events_file.flush()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="ws://localhost:9090")
    parser.add_argument("--clients", type=int, default=50, help="target concurrent clients")
    parser.add_argument("--ramp-step", type=int, default=10, help="clients added per interval")
    parser.add_argument("--ramp-interval", type=float, default=30, help="seconds between steps")
    parser.add_argument("--hold", type=float, default=300, help="seconds to hold at target")
    parser.add_argument(
        "--session", type=float, default=480, help="seconds per session before reconnect"
    )
    parser.add_argument(
        "--stop-lag",
        type=float,
        default=0,
        help=f"stop when interval p95 lag exceeds this for {STOP_LAG_INTERVALS} intervals in a row (0=never)",
    )
    parser.add_argument("--model", default="small", help="model name sent in the handshake")
    parser.add_argument("--tracks", type=pathlib.Path, default=DEFAULT_TRACKS)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("loadtest/results"))
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    with (
        open(args.out / "messages.csv", "w", newline="") as messages_file,
        open(args.out / "events.csv", "w", newline="") as events_file,
    ):
        asyncio.run(Run(args, messages_file, events_file).ramp())


if __name__ == "__main__":
    main()
