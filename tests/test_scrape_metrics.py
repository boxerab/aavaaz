import csv
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from loadtest import scrape_metrics

METRICS_TEXT = b"""# HELP whisperlive_connections_active Currently active WebSocket connections
# TYPE whisperlive_connections_active gauge
whisperlive_connections_active 7.0
whisperlive_connections_rejected_total{reason="full"} 2.0
whisperlive_transcription_latency_seconds_bucket{le="0.5"} 10.0
whisperlive_transcription_latency_seconds_sum 4.5
whisperlive_transcription_latency_seconds_count 12.0
python_gc_objects_collected_total{generation="0"} 100.0
"""


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(METRICS_TEXT)

    def log_message(self, *args):
        pass


def test_scrape_writes_selected_metrics(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), MetricsHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    target = f"127.0.0.1:{server.server_port}"
    out = tmp_path / "metrics.csv"
    try:
        scrape_metrics.main(["--targets", target, "--rounds", "1", "--out", str(out)])
    finally:
        server.shutdown()

    with open(out) as f:
        rows = {row["metric"]: float(row["value"]) for row in csv.DictReader(f)}
    assert rows["whisperlive_connections_active"] == 7.0
    assert rows['whisperlive_connections_rejected_total{reason="full"}'] == 2.0
    assert rows["whisperlive_transcription_latency_seconds_sum"] == 4.5
    assert 'python_gc_objects_collected_total{generation="0"}' not in rows
    assert not any(metric.endswith("_bucket") for metric in rows)
