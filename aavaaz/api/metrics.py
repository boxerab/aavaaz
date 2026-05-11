"""
Prometheus metrics endpoint for Aavaaz.

Wraps WhisperLive's metrics module and adds Aavaaz-specific metrics.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()

# Aavaaz-level metrics
TRANSCRIPTION_REQUESTS = Counter(
    "aavaaz_transcription_requests_total",
    "Total transcription requests",
    ["method", "status"],
)
TRANSCRIPTION_DURATION = Histogram(
    "aavaaz_transcription_duration_seconds",
    "Time spent transcribing audio",
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120],
)
ACTIVE_CONNECTIONS = Gauge(
    "aavaaz_active_websocket_connections",
    "Currently active WebSocket connections",
)
PLUGIN_ERRORS = Counter(
    "aavaaz_plugin_errors_total",
    "Plugin processing errors",
    ["plugin_name"],
)


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
