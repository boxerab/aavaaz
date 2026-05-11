"""Tests for webhook delivery."""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from aavaaz.api.webhooks import deliver_webhook


class _OKHandler(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _OKHandler.received.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_webhook_delivery():
    _OKHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _OKHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    ok = deliver_webhook(
        url=f"http://127.0.0.1:{port}/hook",
        event="transcription.complete",
        payload={"transcript_id": "abc"},
        timeout=5,
    )
    thread.join(timeout=5)
    server.server_close()

    assert ok
    assert len(_OKHandler.received) == 1
    assert _OKHandler.received[0]["event"] == "transcription.complete"
