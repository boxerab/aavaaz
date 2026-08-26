"""The load generator against a fake WhisperLive server that answers with segments
covering all audio it has received, so lag is bounded by one chunk plus the reply.
"""

import csv
import json

import numpy as np
import pytest
from websockets.asyncio.server import serve

from loadtest import stream_clients

SAMPLE_RATE = 16000


async def fake_whisperlive(websocket):
    options = json.loads(await websocket.recv())
    await websocket.send(
        json.dumps({"uid": options["uid"], "message": "SERVER_READY", "backend": "fake"})
    )
    received_samples = 0
    async for frame in websocket:
        received_samples += len(frame) // 4
        end = received_samples / SAMPLE_RATE
        await websocket.send(
            json.dumps(
                {
                    "uid": options["uid"],
                    "segments": [{"start": 0.0, "end": end, "text": "hello", "completed": False}],
                }
            )
        )


@pytest.mark.asyncio
async def test_stream_clients_records_lag_and_events(tmp_path):
    tracks = tmp_path / "tracks"
    tracks.mkdir()
    np.zeros(SAMPLE_RATE * 5, dtype=np.float32).tofile(tracks / "silence.f32")
    out = tmp_path / "results"

    async with serve(fake_whisperlive, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        args = stream_clients.parse_args(
            [
                "--url",
                f"ws://127.0.0.1:{port}",
                "--clients",
                "3",
                "--ramp-step",
                "3",
                "--ramp-interval",
                "1",
                "--hold",
                "1",
                "--session",
                "2",
                "--tracks",
                str(tracks),
                "--out",
                str(out),
            ]
        )
        out.mkdir()
        with (
            open(out / "messages.csv", "w", newline="") as messages_file,
            open(out / "events.csv", "w", newline="") as events_file,
        ):
            await stream_clients.Run(args, messages_file, events_file).ramp()

    with open(out / "messages.csv") as f:
        messages = list(csv.DictReader(f))
    with open(out / "events.csv") as f:
        events = list(csv.DictReader(f))

    assert {row["client"] for row in messages} == {"1", "2", "3"}
    lags = [float(row["lag"]) for row in messages]
    assert all(0 <= lag < 1.0 for lag in lags), lags
    assert max(float(row["audio_end"]) for row in messages) > 1.0
    assert sum(row["event"] == "ready" for row in events) >= 3
    assert all(row["connect_ms"] for row in events if row["event"] == "ready")
