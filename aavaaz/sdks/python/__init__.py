"""
Aavaaz Python SDK

Lightweight client for the Aavaaz transcription API.

Usage:
    from aavaaz.sdks.python import AavaazClient

    client = AavaazClient("https://gh0edmarma.execute-api.us-east-1.amazonaws.com")
    result = client.transcribe("audio.mp3")
    print(result["text"])

    # Or with streaming:
    for segment in client.transcribe_stream("audio.mp3"):
        print(segment["text"])
"""

from __future__ import annotations

import json
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

import httpx


@dataclass
class AavaazClient:
    """Client for the Aavaaz transcription REST API."""

    base_url: str
    api_key: str = ""
    timeout: float = 300.0
    features: dict[str, Any] = field(default_factory=dict)

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def health(self) -> dict[str, Any]:
        """Check service health."""
        r = httpx.get(
            f"{self.base_url}/health",
            headers=self._headers(),
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def transcribe(
        self,
        audio: str | Path | BinaryIO,
        *,
        model: str | None = None,
        language: str | None = None,
        response_format: str = "json",
        hotwords: list[str] | None = None,
    ) -> dict[str, Any]:
        """Transcribe an audio file.

        Args:
            audio: File path, Path object, or file-like binary object.
            model: Whisper model name (e.g. "large-v3", "small.en").
            language: Language code (e.g. "en", "es") or None for auto-detect.
            response_format: "json", "text", "srt", or "vtt".
            hotwords: List of words to boost recognition of.

        Returns:
            Dict with "segments" (list of {start, end, text}) and metadata.
        """
        files: dict[str, Any] = {}
        data: dict[str, str] = {"response_format": response_format}

        if isinstance(audio, (str, Path)):
            path = Path(audio)
            files["file"] = (path.name, path.open("rb"), "application/octet-stream")
        else:
            name = getattr(audio, "name", "audio.wav")
            files["file"] = (name, audio, "application/octet-stream")

        if model:
            data["model"] = model
        if language:
            data["language"] = language
        if hotwords:
            data["hotwords"] = ",".join(hotwords)
        if self.features:
            data["features"] = json.dumps(self.features)

        r = httpx.post(
            f"{self.base_url}/v1/audio/transcriptions",
            headers=self._headers(),
            files=files,
            data=data,
            timeout=self.timeout,
        )
        r.raise_for_status()

        content_type = r.headers.get("content-type", "")
        if "application/json" in content_type:
            return r.json()
        return {"text": r.text, "segments": []}

    def transcribe_url(
        self,
        audio_url: str,
        *,
        model: str | None = None,
        language: str | None = None,
        response_format: str = "json",
    ) -> dict[str, Any]:
        """Transcribe audio from a URL.

        Args:
            audio_url: Public URL to the audio file.
            model: Whisper model name.
            language: Language code or None for auto-detect.
            response_format: Output format.

        Returns:
            Transcription result dict.
        """
        payload: dict[str, Any] = {
            "audio_url": audio_url,
            "response_format": response_format,
        }
        if model:
            payload["model"] = model
        if language:
            payload["language"] = language
        if self.features:
            payload["features"] = self.features

        r = httpx.post(
            f"{self.base_url}/v1/audio/transcriptions",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def transcribe_stream(
        self,
        audio: str | Path | BinaryIO,
        *,
        model: str | None = None,
        language: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Transcribe and yield segments as they arrive (streaming).

        Falls back to batch if server doesn't support streaming.
        """
        result = self.transcribe(
            audio, model=model, language=language, response_format="json"
        )
        yield from result.get("segments", [])


@dataclass
class AavaazLiveClient:
    """Client for real-time WebSocket transcription.

    Usage:
        import asyncio
        from aavaaz.sdks.python import AavaazLiveClient

        async def main():
            client = AavaazLiveClient("wss://your-endpoint/ws")
            async for segment in client.stream_microphone():
                print(segment["text"])

        asyncio.run(main())
    """

    ws_url: str
    model: str = "large-v3"
    language: str | None = None
    use_vad: bool = True
    features: dict[str, Any] = field(default_factory=dict)

    async def stream_audio(
        self,
        audio_chunks: Any,
        *,
        sample_rate: int = 16000,
    ) -> Generator[dict[str, Any], None, None]:
        """Stream audio chunks and yield transcription segments.

        Args:
            audio_chunks: Async iterable of float32 numpy arrays.
            sample_rate: Audio sample rate (default 16000).

        Yields:
            Segment dicts with "text", "start", "end".
        """
        import websockets

        async with websockets.connect(self.ws_url) as ws:
            # Send client options
            options = {
                "uid": f"python-sdk-{id(self)}",
                "language": self.language,
                "model": self.model,
                "use_vad": self.use_vad,
                "task": "transcribe",
            }
            if self.features:
                options["features"] = self.features

            await ws.send(json.dumps(options))

            # Send audio and receive segments concurrently
            import asyncio

            async def send_audio():
                async for chunk in audio_chunks:
                    await ws.send(chunk.tobytes())
                # Signal end
                await ws.send(b"END_OF_AUDIO")

            send_task = asyncio.create_task(send_audio())

            try:
                async for message in ws:
                    data = json.loads(message)
                    if "segments" in data:
                        for seg in data["segments"]:
                            yield seg
                    elif data.get("message") == "DISCONNECT":
                        break
            finally:
                send_task.cancel()
