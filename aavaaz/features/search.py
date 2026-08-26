"""
Transcript search and tagging for stored transcription results.

Provides:
- Full-text search across stored transcription results
- Tagging/metadata on transcription jobs
"""

import threading
import time
from dataclasses import asdict, dataclass, field


@dataclass
class TranscriptMetadata:
    """Metadata for a stored transcription job."""

    job_id: str
    user_id: str = ""
    created_at: float = field(default_factory=time.time)
    duration_seconds: float = 0.0
    language: str = ""
    model: str = ""
    tags: dict[str, str] = field(default_factory=dict)
    text: str = ""  # Full transcript text for search

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TranscriptMetadata":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class TranscriptIndex:
    """In-memory index for transcript search and tagging.

    Designed to work alongside the storage backend. The storage backend
    handles audio/result persistence; this index handles search and metadata.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._index: dict[str, TranscriptMetadata] = {}

    def add(self, metadata: TranscriptMetadata):
        """Add or update a transcript in the index."""
        with self._lock:
            self._index[metadata.job_id] = metadata

    def get(self, job_id: str) -> TranscriptMetadata | None:
        """Get metadata for a specific job."""
        with self._lock:
            return self._index.get(job_id)

    def delete(self, job_id: str) -> bool:
        """Remove a job from the index."""
        with self._lock:
            return self._index.pop(job_id, None) is not None

    def tag(self, job_id: str, tags: dict[str, str]) -> bool:
        """Add or update tags on a job.

        Args:
            job_id: The job ID.
            tags: Dict of tag key-value pairs to add/update.

        Returns:
            True if job exists and was tagged.
        """
        with self._lock:
            meta = self._index.get(job_id)
            if not meta:
                return False
            meta.tags.update(tags)
            return True

    def untag(self, job_id: str, keys: list[str]) -> bool:
        """Remove specific tags from a job."""
        with self._lock:
            meta = self._index.get(job_id)
            if not meta:
                return False
            for key in keys:
                meta.tags.pop(key, None)
            return True

    def search(
        self,
        query: str = "",
        user_id: str | None = None,
        tags: dict[str, str] | None = None,
        language: str | None = None,
        model: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TranscriptMetadata]:
        """Search transcripts by text content and/or metadata filters.

        Args:
            query: Full-text search query (case-insensitive substring match).
            user_id: Filter by user ID.
            tags: Filter by tags (all must match).
            language: Filter by detected language.
            model: Filter by model used.
            start_time: Filter by created_at >= start_time (epoch).
            end_time: Filter by created_at <= end_time (epoch).
            limit: Maximum results to return.
            offset: Pagination offset.

        Returns:
            List of matching TranscriptMetadata.
        """
        with self._lock:
            results = []
            query_lower = query.lower() if query else ""

            for meta in self._index.values():
                # Text search
                if query_lower and query_lower not in meta.text.lower():
                    continue

                # User filter
                if user_id and meta.user_id != user_id:
                    continue

                # Tag filter (all must match)
                if tags:
                    if not all(meta.tags.get(k) == v for k, v in tags.items()):
                        continue

                # Language filter
                if language and meta.language != language:
                    continue

                # Model filter
                if model and meta.model != model:
                    continue

                # Time range
                if start_time and meta.created_at < start_time:
                    continue
                if end_time and meta.created_at > end_time:
                    continue

                results.append(meta)

            # Sort by creation time, newest first
            results.sort(key=lambda m: m.created_at, reverse=True)
            return results[offset : offset + limit]

    def count(self, user_id: str | None = None) -> int:
        """Count total transcripts, optionally filtered by user."""
        with self._lock:
            if user_id:
                return sum(1 for m in self._index.values() if m.user_id == user_id)
            return len(self._index)

    def list_all(self, limit: int = 50, offset: int = 0) -> list[TranscriptMetadata]:
        """List all transcripts with pagination."""
        return self.search(limit=limit, offset=offset)
