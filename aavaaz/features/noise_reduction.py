"""
Audio noise reduction preprocessing for WhisperLive.

Uses the noisereduce library (stationary and non-stationary modes) to
clean up audio before transcription. Can be applied as a preprocessing
step on incoming audio frames.

Install: pip install noisereduce
"""

import logging
import os

import numpy as np

try:
    import noisereduce as nr

    _HAS_NOISEREDUCE = True
except ImportError:
    _HAS_NOISEREDUCE = False

logger = logging.getLogger(__name__)


class NoiseReducer:
    """Audio noise reduction using spectral gating.

    Args:
        mode: "near_field" for close-mic/headset audio (stationary noise),
              "far_field" for distant/speakerphone audio (non-stationary noise).
        sample_rate: Audio sample rate in Hz. Default 16000.
        prop_decrease: Amount of noise reduction (0.0 to 1.0). Default 0.8.
        stationary: Force stationary mode regardless of mode parameter.
            If None, determined by mode setting.
    """

    def __init__(
        self,
        mode: str = "near_field",
        sample_rate: int = 16000,
        prop_decrease: float = 0.8,
        stationary: bool | None = None,
    ):
        if not _HAS_NOISEREDUCE:
            raise ImportError(
                "noisereduce is required for audio noise reduction. "
                "Install it with: pip install noisereduce"
            )

        if mode not in ("near_field", "far_field"):
            raise ValueError(f"mode must be 'near_field' or 'far_field', got '{mode}'")

        self.mode = mode
        self.sample_rate = sample_rate
        self.prop_decrease = max(0.0, min(1.0, prop_decrease))

        if stationary is not None:
            self._stationary = stationary
        else:
            self._stationary = mode == "near_field"

    def reduce(self, audio: np.ndarray) -> np.ndarray:
        """Apply noise reduction to an audio array.

        Args:
            audio: 1-D float32 numpy array of audio samples.

        Returns:
            Noise-reduced audio array with same shape and dtype.
        """
        if audio.size == 0:
            return audio

        # noisereduce needs float data
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        reduced = nr.reduce_noise(
            y=audio,
            sr=self.sample_rate,
            stationary=self._stationary,
            prop_decrease=self.prop_decrease,
        )
        return reduced.astype(np.float32)

    def reduce_file(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Apply noise reduction to file audio (potentially different sample rate).

        Args:
            audio: Audio array (1-D or multi-channel).
            sample_rate: Sample rate of the audio.

        Returns:
            Noise-reduced audio array.
        """
        if audio.size == 0:
            return audio

        if audio.ndim == 1:
            return nr.reduce_noise(
                y=audio.astype(np.float32),
                sr=sample_rate,
                stationary=self._stationary,
                prop_decrease=self.prop_decrease,
            ).astype(np.float32)

        # Multi-channel: process each channel independently
        channels = []
        for ch in range(audio.shape[1]):
            reduced = nr.reduce_noise(
                y=audio[:, ch].astype(np.float32),
                sr=sample_rate,
                stationary=self._stationary,
                prop_decrease=self.prop_decrease,
            )
            channels.append(reduced)
        return np.stack(channels, axis=1).astype(np.float32)


def is_available() -> bool:
    """Check if noisereduce library is installed."""
    return _HAS_NOISEREDUCE


def _resolve(features: dict | None) -> tuple[bool, str, float]:
    """Resolve (enabled, mode, prop_decrease) from per-request features or env."""
    if features is None:
        enabled = os.environ.get("AAVAAZ_ENABLE_NOISE_REDUCTION", "0") == "1"
        mode = os.environ.get("AAVAAZ_NOISE_MODE", "near_field")
        prop = float(os.environ.get("AAVAAZ_NOISE_PROP_DECREASE", "0.8"))
    else:
        cfg = features.get("noiseReduction") or {}
        enabled = bool(cfg.get("enabled"))
        mode = cfg.get("mode", "near_field")
        prop = float(cfg.get("propDecrease", 0.8))
    return enabled, mode, prop


def is_enabled(features: dict | None = None) -> bool:
    """Whether noise reduction is requested (per-request features or env)."""
    return _resolve(features)[0]


def maybe_reduce_noise(
    audio: np.ndarray, features: dict | None = None, sample_rate: int = 16000
) -> np.ndarray:
    """Apply noise reduction if enabled, else return the audio unchanged.

    Gracefully returns the input when noisereduce isn't installed or reduction
    fails, so an optional dependency never breaks transcription.
    """
    enabled, mode, prop = _resolve(features)
    if not enabled:
        return audio
    if not is_available():
        logger.warning(
            "noise reduction requested but noisereduce is not installed; skipping"
        )
        return audio
    try:
        reducer = NoiseReducer(mode=mode, sample_rate=sample_rate, prop_decrease=prop)
        return reducer.reduce(audio)
    except Exception:
        logger.exception("noise reduction failed; using original audio")
        return audio
