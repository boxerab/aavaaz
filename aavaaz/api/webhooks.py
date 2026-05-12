"""
Webhook delivery for transcription events.

Wraps WhisperLive's webhook module with retry logic, HMAC signing,
and async delivery.
"""

import hashlib
import hmac
import json
import logging
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [1, 5, 30]  # seconds


def deliver_webhook(
    url: str,
    event: str,
    payload: dict,
    secret: str | None = None,
    timeout: int = 10,
) -> bool:
    """Deliver a webhook with retry and optional HMAC signing.

    Args:
        url: Webhook endpoint URL.
        event: Event type (e.g. "transcription.complete").
        payload: JSON-serializable event payload.
        secret: Optional HMAC secret for signing the payload.
        timeout: Request timeout in seconds.

    Returns:
        True if delivery succeeded, False after all retries exhausted.
    """
    body = json.dumps({"event": event, "data": payload, "timestamp": time.time()}).encode()
    headers = {"Content-Type": "application/json"}

    if secret:
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Aavaaz-Signature"] = f"sha256={sig}"

    for attempt, delay in enumerate(RETRY_DELAYS[:MAX_RETRIES]):
        try:
            req = Request(url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=timeout) as resp:
                if 200 <= resp.status < 300:
                    logger.info("Webhook delivered: %s -> %s (attempt %d)", event, url, attempt + 1)
                    return True
                logger.warning("Webhook %s returned %d", url, resp.status)
        except URLError as e:
            logger.warning("Webhook delivery failed (attempt %d): %s", attempt + 1, e)

        if attempt < MAX_RETRIES - 1:
            time.sleep(delay)

    logger.error("Webhook delivery exhausted retries: %s -> %s", event, url)
    return False
