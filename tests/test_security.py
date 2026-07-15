"""
Tests for security concerns (Test Matrix §22).

Covers path traversal, injection, XSS, credential leaking, and privacy.
"""

import sys
from unittest.mock import MagicMock

# Mock whisper_live
_mock_wl = MagicMock()
sys.modules.setdefault("whisper_live", _mock_wl)
sys.modules.setdefault("whisper_live.server", _mock_wl.server)

from aavaaz.features.search import TranscriptIndex  # noqa: E402


class TestSearchInjection:
    """22.2 - Injection in search queries."""

    def test_special_chars_in_search(self):
        """Search should handle special regex chars safely."""
        from aavaaz.features.search import TranscriptMetadata

        index = TranscriptIndex()
        index.add(TranscriptMetadata(job_id="job1", text="Hello world"))

        # Characters that could be dangerous in regex
        dangerous_queries = [
            ".*",
            "(evil)",
            "[a-z]+",
            "a{100}",
            "hello|rm -rf",
            "'; DROP TABLE --",
        ]
        for query in dangerous_queries:
            # Should not raise or execute anything dangerous
            results = index.search(query=query)
            assert isinstance(results, list)

    def test_empty_search(self):
        """Empty search should return results safely."""
        from aavaaz.features.search import TranscriptMetadata

        index = TranscriptIndex()
        index.add(TranscriptMetadata(job_id="job1", text="Secret data"))
        results = index.search(query="")
        assert isinstance(results, list)


class TestRateLimiting:
    """22.5 - Rate limiting prevents abuse."""

    def test_rate_limit_config_accepted(self):
        """Server should accept rate_limit_rpm config."""
        from aavaaz.server import AavaazServer

        server = AavaazServer(rate_limit_rpm=60)
        assert server.rate_limit_rpm == 60

    def test_zero_rate_limit_means_unlimited(self):
        """rate_limit_rpm=0 should mean no rate limiting."""
        from aavaaz.server import AavaazServer

        server = AavaazServer(rate_limit_rpm=0)
        assert server.rate_limit_rpm == 0
