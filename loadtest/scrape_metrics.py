"""Poll each server's Prometheus endpoint and append the counters that matter to a CSV."""

import argparse
import csv
import pathlib
import sys
import time
import urllib.error
import urllib.request

METRIC_PREFIXES = (
    "whisperlive_connections_active",
    "whisperlive_connections_total",
    "whisperlive_connections_rejected_total",
    "whisperlive_transcription_latency_seconds_sum",
    "whisperlive_transcription_latency_seconds_count",
    "whisperlive_batch_fallback_items_total",
    "whisperlive_audio_processed_seconds_total",
    "whisperlive_errors_total",
)
FIELDS = ["t", "target", "metric", "value"]


def parse_metrics(text):
    for line in text.splitlines():
        if not line.startswith(METRIC_PREFIXES):
            continue
        name, _, value = line.rpartition(" ")
        yield name, float(value)


def scrape(target, timeout=5):
    with urllib.request.urlopen(f"http://{target}/metrics", timeout=timeout) as response:
        return response.read().decode()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True, help="comma separated host:port list")
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument(
        "--rounds", type=int, default=0, help="stop after this many polls (0=forever)"
    )
    parser.add_argument(
        "--out", type=pathlib.Path, default=pathlib.Path("loadtest/results/metrics.csv")
    )
    args = parser.parse_args(argv)

    targets = args.targets.split(",")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    rounds = 0
    with open(args.out, "a", newline="") as out:
        writer = csv.DictWriter(out, FIELDS)
        if out.tell() == 0:
            writer.writeheader()
        while not args.rounds or rounds < args.rounds:
            now = f"{time.time() - started:.1f}"
            for target in targets:
                try:
                    text = scrape(target)
                except (urllib.error.URLError, OSError) as error:
                    print(f"{now}s {target}: {error}", file=sys.stderr)
                    continue
                for metric, value in parse_metrics(text):
                    writer.writerow({"t": now, "target": target, "metric": metric, "value": value})
            out.flush()
            rounds += 1
            if not args.rounds or rounds < args.rounds:
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
