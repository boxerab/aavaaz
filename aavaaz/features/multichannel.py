"""
Multi-channel audio utilities.

Splits stereo/multi-channel audio files into per-channel mono streams
and provides helpers for merging per-channel transcription results.
"""

import logging
import os

import numpy as np


def resolve(features: dict | None) -> tuple[bool, list[str] | None]:
    """Resolve (enabled, channel_labels) from per-request features or env."""
    if features is None:
        enabled = os.environ.get("AAVAAZ_ENABLE_MULTICHANNEL", "0") == "1"
        raw_labels = os.environ.get("AAVAAZ_CHANNEL_LABELS", "")
        labels = [x.strip() for x in raw_labels.split(",") if x.strip()] or None
    else:
        cfg = features.get("multichannel") or {}
        enabled = bool(cfg.get("enabled"))
        labels = cfg.get("labels") or None
    return enabled, labels


def split_channels(audio_np: np.ndarray, channels: int = 2) -> list[np.ndarray]:
    """Split interleaved multi-channel audio into a list of mono arrays.

    Args:
        audio_np: 1-D numpy array of interleaved samples (float32 or int16).
        channels: Number of channels in the interleaved data.

    Returns:
        List of 1-D numpy arrays, one per channel.
    """
    if channels < 2:
        return [audio_np]
    total = len(audio_np)
    # Trim to a multiple of channel count
    usable = total - (total % channels)
    if usable == 0:
        return [np.array([], dtype=audio_np.dtype) for _ in range(channels)]
    interleaved = audio_np[:usable].reshape(-1, channels)
    return [interleaved[:, ch].copy() for ch in range(channels)]


def merge_channel_segments(
    channel_segments: list[list[dict]],
    channel_labels: list[str] | None = None,
) -> list[dict]:
    """Merge per-channel segment lists into a single timeline sorted by start time.

    Each segment gets a 'channel' field added.

    Args:
        channel_segments: List of segment lists, one per channel.
        channel_labels: Optional labels for each channel (e.g. ["agent", "customer"]).
            Defaults to "ch0", "ch1", etc.

    Returns:
        Merged list of segments sorted by start time.
    """
    if channel_labels is None:
        channel_labels = [f"ch{i}" for i in range(len(channel_segments))]

    merged = []
    for ch_idx, segments in enumerate(channel_segments):
        label = (
            channel_labels[ch_idx] if ch_idx < len(channel_labels) else f"ch{ch_idx}"
        )
        for seg in segments:
            seg_copy = dict(seg)
            seg_copy["channel"] = label
            merged.append(seg_copy)

    # Sort by start time (handle both string and numeric)
    merged.sort(key=lambda s: float(s.get("start", 0)))
    return merged


def detect_channels_from_wav(file_path: str) -> int:
    """Read channel count from a WAV file header.

    Args:
        file_path: Path to a .wav file.

    Returns:
        Number of channels, or 1 if detection fails.
    """
    try:
        import wave

        with wave.open(file_path, "rb") as wf:
            return wf.getnchannels()
    except Exception as e:
        logging.warning(f"Could not detect channels from {file_path}: {e}")
        return 1
