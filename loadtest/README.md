# Load test

Streams real speech from many WebSocket clients and records transcript lag as the client count ramps up.

Lag for one transcript message is `(arrival - stream_start) - max(segment.end)`: how far the transcript trails the audio the client has already sent.

## One-time setup

```
curl -sSL -o ~/.cache/aavaaz-loadtest/test-clean.tar.gz https://www.openslr.org/resources/12/test-clean.tar.gz
tar xzf ~/.cache/aavaaz-loadtest/test-clean.tar.gz -C ~/.cache/aavaaz-loadtest
uv run loadtest/prepare_audio.py
```

`prepare_audio.py` writes 20 tracks of about 8 minutes each to `~/.cache/aavaaz-loadtest/tracks`.

## Run

Server, one shared model for all clients:

```
aavaaz serve --model small --batch-inference --max-clients 500 --max-connection-time 900 --metrics-port 9100
```

Clients, adding 10 every 30 s up to 200, stopping early once interval p95 lag passes 3 s for two intervals in a row:

```
uv run loadtest/stream_clients.py --clients 200 --ramp-step 10 --ramp-interval 30 --hold 300 --stop-lag 3
uv run loadtest/report.py
```

`report.py` prints lag percentiles per client count and writes `loadtest/results/lag_vs_clients.png`.

Server side counters, polled every 10 s into `loadtest/results/metrics.csv`:

```
uv run loadtest/scrape_metrics.py --targets 10.0.10.5:9100,10.0.10.6:9100
```

GPU load on a node: `nvidia-smi dmon -s u -d 5 > dmon.log`.

## AWS

`deploy/terraform` builds the servers and, with `loadgen_count`, the load generator hosts. `setup_loadgen.sh` prepares one host (repo, venv, tracks, file limits) and is what the instance runs on first boot.

One process handles about 2,000 clients. For more, run several with different `--out` directories.

Notes:
- `--session` (default 480 s) must stay under the server's `--max-connection-time`, or sessions end as server disconnects instead of client reconnects.
- The handshake `--model` must match a model the server can load.
- A client told to WAIT retries after 5 s, doubling up to 60 s, until it gets in.
- Server side metrics are at `http://localhost:9100/metrics`.
