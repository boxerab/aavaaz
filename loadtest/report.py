"""Summarize a stream_clients.py run: lag percentiles per client count, and a chart."""

import argparse
import collections
import csv
import pathlib
import statistics


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * fraction))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "results", type=pathlib.Path, nargs="?", default=pathlib.Path("loadtest/results")
    )
    args = parser.parse_args()

    lags_by_active = collections.defaultdict(list)
    with open(args.results / "messages.csv") as f:
        for row in csv.DictReader(f):
            lags_by_active[int(row["active"])].append(float(row["lag"]))

    events_by_active = collections.defaultdict(collections.Counter)
    connect_by_active = collections.defaultdict(list)
    with open(args.results / "events.csv") as f:
        for row in csv.DictReader(f):
            active = int(row["active"])
            events_by_active[active][row["event"]] += 1
            if row["connect_ms"]:
                connect_by_active[active].append(float(row["connect_ms"]))

    print(
        f"{'clients':>7} {'msgs':>7} {'p50':>6} {'p95':>6} {'p99':>6} {'ready_p95ms':>11}  events"
    )
    rows = []
    for active in sorted(set(lags_by_active) | set(events_by_active)):
        lags = lags_by_active.get(active, [])
        connects = connect_by_active.get(active, [])
        p50 = p95 = p99 = float("nan")
        if lags:
            p50, p95, p99 = percentile(lags, 0.5), percentile(lags, 0.95), percentile(lags, 0.99)
            rows.append((active, p50, p95, p99))
        ready_p95 = percentile(connects, 0.95) if connects else float("nan")
        events = " ".join(f"{k}={v}" for k, v in sorted(events_by_active[active].items()))
        print(
            f"{active:7d} {len(lags):7d} {p50:6.2f} {p95:6.2f} {p99:6.2f}"
            f" {ready_p95:11.0f}  {events}"
        )

    if rows:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        clients = [r[0] for r in rows]
        figure, axis = plt.subplots(figsize=(8, 4.5))
        for index, label in ((1, "p50"), (2, "p95"), (3, "p99")):
            axis.plot(clients, [r[index] for r in rows], marker="o", label=label)
        axis.set_xlabel("concurrent clients")
        axis.set_ylabel("transcript lag (s)")
        axis.grid(alpha=0.3)
        axis.legend()
        figure.tight_layout()
        chart = args.results / "lag_vs_clients.png"
        figure.savefig(chart, dpi=150)
        print(f"chart: {chart}")

    all_lags = [lag for lags in lags_by_active.values() for lag in lags]
    print(f"median lag overall: {statistics.median(all_lags):.2f}s")


if __name__ == "__main__":
    main()
