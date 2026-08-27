"""Aavaaz CLI — entry point for the aavaaz command."""

import argparse
import logging
import sys


def _split_words(value: str | None) -> set[str] | None:
    """Parse a comma-separated CLI list into a set, or None when empty."""
    if not value:
        return None
    return {word.strip() for word in value.split(",") if word.strip()} or None


def main():
    parser = argparse.ArgumentParser(
        prog="aavaaz",
        description="Aavaaz — production-grade speech-to-text platform",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- serve ---
    serve_parser = subparsers.add_parser("serve", help="Start the Aavaaz server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    serve_parser.add_argument(
        "--port", type=int, default=9090, help="WebSocket port (default: 9090)"
    )
    serve_parser.add_argument(
        "--rest-port", type=int, default=8000, help="REST API port (default: 8000)"
    )
    serve_parser.add_argument("--model", default="large-v3", help="Whisper model name or path")
    serve_parser.add_argument(
        "--backend",
        default="faster_whisper",
        choices=["faster_whisper", "tensorrt", "openvino"],
        help="Transcription backend",
    )
    serve_parser.add_argument("--no-rest", action="store_true", help="Disable REST API")
    serve_parser.add_argument("--api-key", default=None, help="API key for auth (REST + WebSocket)")
    serve_parser.add_argument(
        "--rate-limit-rpm",
        type=int,
        default=0,
        help="Max REST requests per minute per IP (0=unlimited)",
    )
    serve_parser.add_argument(
        "--metrics-port",
        type=int,
        default=0,
        help="Prometheus metrics port (0=disabled)",
    )
    serve_parser.add_argument(
        "--single-model",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Build the model once and share it across clients (default: on). "
            "Off lets each client name its own model, at a fresh model load per "
            "connection"
        ),
    )
    serve_parser.add_argument(
        "--batch-inference",
        action="store_true",
        help="Enable cross-client GPU batching",
    )
    serve_parser.add_argument(
        "--batch-max-size",
        type=int,
        default=16,
        help="Max requests per GPU batch (default: 16)",
    )
    serve_parser.add_argument(
        "--batch-window-ms",
        type=int,
        default=50,
        help="Max ms to wait for batch to fill (default: 50)",
    )
    serve_parser.add_argument(
        "--batch-max-queue-wait",
        type=float,
        default=0.5,
        help="Seconds of batch queue wait before new clients are told to wait (default: 0.5)",
    )
    serve_parser.add_argument(
        "--batch-max-admissions-per-s",
        type=float,
        default=5.0,
        help="Most new clients admitted per second in batch mode, the rest get WAIT (default: 5.0)",
    )
    serve_parser.add_argument(
        "--batch-beam-size",
        type=int,
        default=1,
        help=(
            "Beam width for batched decoding, 1 is greedy, 5 costs about 2.5x "
            "the decode time (default: 1)"
        ),
    )
    serve_parser.add_argument(
        "--batch-temperature-fallback",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Re-decode batched chunks that fail the quality check at higher "
            "temperatures, halves throughput at beam 1 (default: off)"
        ),
    )
    serve_parser.add_argument(
        "--max-clients",
        type=int,
        default=4,
        help="Max concurrent WebSocket clients (default: 4)",
    )
    serve_parser.add_argument(
        "--max-connection-time",
        type=int,
        default=600,
        help="Seconds a client may stay connected (default: 600)",
    )
    serve_parser.add_argument(
        "--noise-reduction",
        choices=["near_field", "far_field"],
        default=None,
        help="Reduce noise on live audio before transcription (needs noisereduce)",
    )
    serve_parser.add_argument(
        "--word-timestamps",
        action="store_true",
        help="Enable word-level timestamps and confidence scores",
    )
    serve_parser.add_argument(
        "--hotwords",
        default=None,
        help="Comma-separated list of terms to boost recognition",
    )
    serve_parser.add_argument(
        "--enable-diarization", action="store_true", help="Enable speaker diarization"
    )
    serve_parser.add_argument(
        "--max-speakers",
        type=int,
        default=10,
        help="Max speakers for diarization (default: 10)",
    )
    serve_parser.add_argument(
        "--smart-format",
        action="store_true",
        help="Enable smart formatting post-processing",
    )
    serve_parser.add_argument("--pii-redaction", action="store_true", help="Enable PII redaction")
    serve_parser.add_argument(
        "--profanity-filter", action="store_true", help="Enable profanity filtering"
    )
    serve_parser.add_argument(
        "--profanity-mode",
        default="partial",
        choices=["partial", "full", "remove"],
        help="How to filter profanity: partial (f**k), full (****), remove",
    )
    serve_parser.add_argument(
        "--profanity-words",
        default=None,
        help="Comma-separated extra words to add to the profanity list",
    )
    serve_parser.add_argument(
        "--filler-removal",
        action="store_true",
        help="Remove filler words ('um', 'you know') from each segment",
    )
    serve_parser.add_argument(
        "--filler-aggressive",
        action="store_true",
        help="Also remove borderline fillers ('like', 'actually', 'right')",
    )
    serve_parser.add_argument(
        "--callback-url",
        default=None,
        help="POST the final transcript JSON to this URL at stream end",
    )
    serve_parser.add_argument(
        "--intelligence",
        action="store_true",
        help="Enable audio intelligence (sentiment, topics, entities)",
    )
    serve_parser.add_argument(
        "--paragraphs",
        action="store_true",
        help="Group the transcript into paragraphs, sent as a final message at stream end",
    )
    serve_parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")

    # --- transcribe ---
    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe an audio file")
    transcribe_parser.add_argument("file", help="Path to audio file")
    transcribe_parser.add_argument("--model", default="large-v3", help="Whisper model name or path")
    transcribe_parser.add_argument(
        "--format",
        default="text",
        choices=["text", "json", "srt", "vtt"],
        help="Output format",
    )
    transcribe_parser.add_argument(
        "--language", default=None, help="Language code (auto-detect if omitted)"
    )

    # --- version ---
    subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()

    level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    logging.basicConfig(level=level)

    if args.command == "version":
        from aavaaz import __version__

        print(f"aavaaz {__version__}")

    elif args.command == "serve":
        try:
            from aavaaz.server import AavaazServer
        except ImportError as e:
            if "whisper_live" in str(e):
                print(
                    "Error: whisper-live is required for 'aavaaz serve'.\n\n"
                    "Install from PyPI (Python 3.12/3.13 recommended):\n"
                    "  pip install whisper-live\n\n"
                    "Or install from source (for development / Python 3.14+):\n"
                    "  pip install --no-deps -e /path/to/WhisperLive\n"
                    "  pip install faster-whisper websockets scipy",
                    file=sys.stderr,
                )
                sys.exit(1)
            raise

        server = AavaazServer(
            host=args.host,
            port=args.port,
            rest_port=args.rest_port,
            backend=args.backend,
            model=args.model,
            enable_rest_api=not args.no_rest,
            api_key=args.api_key,
            rate_limit_rpm=args.rate_limit_rpm,
            metrics_port=args.metrics_port,
            single_model=args.single_model,
            batch_inference=args.batch_inference,
            batch_max_size=args.batch_max_size,
            batch_window_ms=args.batch_window_ms,
            batch_max_queue_wait_s=args.batch_max_queue_wait,
            batch_max_admissions_per_s=args.batch_max_admissions_per_s,
            batch_beam_size=args.batch_beam_size,
            batch_temperature_fallback=args.batch_temperature_fallback,
            max_clients=args.max_clients,
            max_connection_time=args.max_connection_time,
            noise_reduction=args.noise_reduction,
            word_timestamps=args.word_timestamps,
            hotwords=args.hotwords,
            enable_diarization=args.enable_diarization,
            max_speakers=args.max_speakers,
            enable_formatting=args.smart_format,
            enable_pii=args.pii_redaction,
            enable_profanity=args.profanity_filter,
            profanity_mode=args.profanity_mode,
            profanity_words=_split_words(args.profanity_words),
            enable_filler_removal=args.filler_removal,
            filler_aggressive=args.filler_aggressive,
            enable_intelligence=args.intelligence,
            enable_paragraphs=args.paragraphs,
            callback_url=args.callback_url,
        )
        server.run()

    elif args.command == "transcribe":
        from aavaaz.transcribe import transcribe_file

        transcribe_file(
            path=args.file,
            model=args.model,
            output_format=args.format,
            language=args.language,
        )


if __name__ == "__main__":
    main()
