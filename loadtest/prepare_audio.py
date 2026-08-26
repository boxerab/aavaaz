"""Build speech tracks for the load generator from LibriSpeech test-clean.

Each track is one speaker's utterances concatenated to about TRACK_SECONDS,
written as raw 16 kHz mono float32 so the streamer can slice it without decoding.
"""

import argparse
import pathlib

import numpy as np
import soundfile

SAMPLE_RATE = 16000
TRACK_SECONDS = 600
DEFAULT_CORPUS = pathlib.Path.home() / ".cache/aavaaz-loadtest/LibriSpeech/test-clean"
DEFAULT_TRACKS = pathlib.Path.home() / ".cache/aavaaz-loadtest/tracks"


def build_track(speaker_dir: pathlib.Path) -> np.ndarray:
    pieces = []
    total = 0
    for flac in sorted(speaker_dir.rglob("*.flac")):
        audio, rate = soundfile.read(flac, dtype="float32")
        assert rate == SAMPLE_RATE, f"{flac} is {rate} Hz"
        pieces.append(audio)
        total += len(audio)
        if total >= TRACK_SECONDS * SAMPLE_RATE:
            break
    return np.concatenate(pieces)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=pathlib.Path, default=DEFAULT_CORPUS)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_TRACKS)
    parser.add_argument("--max-tracks", type=int, default=20)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    speakers = sorted(p for p in args.corpus.iterdir() if p.is_dir())[: args.max_tracks]
    for speaker_dir in speakers:
        track = build_track(speaker_dir)
        path = args.out / f"{speaker_dir.name}.f32"
        track.tofile(path)
        print(f"{path} {len(track) / SAMPLE_RATE:.0f}s")


if __name__ == "__main__":
    main()
