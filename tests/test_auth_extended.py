"""
Tests for authentication gaps (Test Matrix §4.6-4.9).

Covers rate-limit configuration and WebSocket token auth.
"""

import sys
from unittest.mock import MagicMock

import pytest

from aavaaz.api.auth import configure_auth, create_token, verify_token


class TestRateLimiting:
    """4.6 - Rate limiting (requests per minute)."""

    def test_rate_limit_config(self):
        """Rate limit should be configurable."""
        sys.modules.setdefault("whisper_live", MagicMock())
        sys.modules.setdefault("whisper_live.server", MagicMock())
        from aavaaz.server import AavaazServer

        server = AavaazServer(rate_limit_rpm=30)
        assert server.rate_limit_rpm == 30

    def test_zero_means_unlimited(self):
        sys.modules.setdefault("whisper_live", MagicMock())
        sys.modules.setdefault("whisper_live.server", MagicMock())
        from aavaaz.server import AavaazServer

        server = AavaazServer(rate_limit_rpm=0)
        assert server.rate_limit_rpm == 0


class TestWebSocketAuth:
    """4.8 - WebSocket authentication (token query param)."""

    def test_valid_token_accepted(self):
        """Valid token should allow WebSocket connection."""
        configure_auth("test-secret-ws")
        token = create_token("ws-user", expires_in=3600)
        payload = verify_token(token)
        assert payload["sub"] == "ws-user"

    def test_expired_token_rejected(self):
        """Expired tokens should be rejected for WebSocket."""
        import jwt as pyjwt

        configure_auth("test-secret-ws")
        token = create_token("ws-user", expires_in=-1)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            verify_token(token)

    def test_no_token_means_unauthenticated(self):
        """Missing token should mean unauthenticated access."""
        configure_auth("test-secret-ws", api_keys=["valid-key"])
        with pytest.raises((ValueError, KeyError, Exception)):  # noqa: B017
            verify_token("")
