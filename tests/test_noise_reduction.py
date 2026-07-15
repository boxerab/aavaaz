"""Integration tests for the noise reduction module."""

from unittest.mock import patch

import numpy as np
import pytest


class TestNoiseReducer:
    def test_import_error_when_missing(self):
        """NoiseReducer raises ImportError if noisereduce not installed."""
        import aavaaz.features.noise_reduction as nr_mod

        with patch.object(nr_mod, "_HAS_NOISEREDUCE", False):
            assert nr_mod.is_available() is False
            with pytest.raises(ImportError, match="noisereduce is required"):
                nr_mod.NoiseReducer(mode="near_field")

    def test_is_available(self):
        from aavaaz.features.noise_reduction import is_available

        # Just ensure it returns a bool
        assert isinstance(is_available(), bool)

    def test_invalid_mode(self):
        try:
            from aavaaz.features.noise_reduction import NoiseReducer

            with pytest.raises(ValueError, match="mode must be"):
                NoiseReducer(mode="invalid")
        except ImportError:
            pytest.skip("noisereduce not installed")

    def test_empty_audio(self):
        try:
            from aavaaz.features.noise_reduction import NoiseReducer

            nr = NoiseReducer(mode="near_field")
            result = nr.reduce(np.array([], dtype=np.float32))
            assert result.size == 0
        except ImportError:
            pytest.skip("noisereduce not installed")

    def test_reduce_basic(self):
        """Test that reduce returns audio of same shape."""
        try:
            from aavaaz.features.noise_reduction import NoiseReducer

            nr = NoiseReducer(mode="near_field")
            # Generate some noisy audio
            rng = np.random.default_rng(42)
            audio = rng.standard_normal(16000).astype(np.float32)
            result = nr.reduce(audio)
            assert result.shape == audio.shape
            assert result.dtype == np.float32
        except ImportError:
            pytest.skip("noisereduce not installed")

    def test_far_field_mode(self):
        try:
            from aavaaz.features.noise_reduction import NoiseReducer

            nr = NoiseReducer(mode="far_field")
            assert nr._stationary is False
        except ImportError:
            pytest.skip("noisereduce not installed")

    def test_prop_decrease_clamped(self):
        try:
            from aavaaz.features.noise_reduction import NoiseReducer

            nr = NoiseReducer(mode="near_field", prop_decrease=2.0)
            assert nr.prop_decrease == 1.0
            nr2 = NoiseReducer(mode="near_field", prop_decrease=-0.5)
            assert nr2.prop_decrease == 0.0
        except ImportError:
            pytest.skip("noisereduce not installed")


class TestMaybeReduceNoise:
    """The wiring helpers used by the batch paths (no noisereduce needed)."""

    def test_is_enabled_from_features(self):
        from aavaaz.features.noise_reduction import is_enabled

        assert is_enabled({"noiseReduction": {"enabled": True}}) is True
        assert is_enabled({"noiseReduction": {"enabled": False}}) is False
        assert is_enabled({}) is False

    def test_is_enabled_from_env(self, monkeypatch):
        from aavaaz.features.noise_reduction import is_enabled

        monkeypatch.delenv("AAVAAZ_ENABLE_NOISE_REDUCTION", raising=False)
        assert is_enabled(None) is False
        monkeypatch.setenv("AAVAAZ_ENABLE_NOISE_REDUCTION", "1")
        assert is_enabled(None) is True

    def test_disabled_returns_input_unchanged(self):
        from aavaaz.features import noise_reduction

        audio = np.ones(100, dtype=np.float32)
        out = noise_reduction.maybe_reduce_noise(audio, {"noiseReduction": {"enabled": False}})
        assert out is audio

    def test_enabled_but_unavailable_skips_gracefully(self):
        from aavaaz.features import noise_reduction

        audio = np.ones(100, dtype=np.float32)
        with patch.object(noise_reduction, "_HAS_NOISEREDUCE", False):
            out = noise_reduction.maybe_reduce_noise(
                audio, {"noiseReduction": {"enabled": True}}
            )
        assert out is audio  # unchanged when the dep is missing

    def test_enabled_and_available_reduces(self):
        from aavaaz.features import noise_reduction

        audio = np.ones(100, dtype=np.float32)
        fake = type("FakeReducer", (), {"reduce": lambda self, a: a * 0.5})()
        with (
            patch.object(noise_reduction, "_HAS_NOISEREDUCE", True),
            patch.object(noise_reduction, "NoiseReducer", lambda **kw: fake),
        ):
            out = noise_reduction.maybe_reduce_noise(
                audio, {"noiseReduction": {"enabled": True}}
            )
        assert np.allclose(out, audio * 0.5)
