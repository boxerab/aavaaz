"""
Transcript storage backends.

Wraps WhisperLive's storage module and provides a unified interface for
local filesystem and S3-compatible storage.
"""

import json
import logging
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    def save(self, transcript_id: str, data: dict) -> str: ...
    def load(self, transcript_id: str) -> dict | None: ...
    def delete(self, transcript_id: str) -> bool: ...
    def list_ids(self) -> list[str]: ...


class LocalStorage:
    """Store transcripts as JSON files on local disk."""

    def __init__(self, base_dir: str = "transcripts"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, transcript_id: str) -> Path:
        safe_id = Path(transcript_id).name  # prevent path traversal
        return self.base_dir / f"{safe_id}.json"

    def save(self, transcript_id: str, data: dict) -> str:
        path = self._path(transcript_id)
        path.write_text(json.dumps(data, indent=2))
        return str(path)

    def load(self, transcript_id: str) -> dict | None:
        path = self._path(transcript_id)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def delete(self, transcript_id: str) -> bool:
        path = self._path(transcript_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_ids(self) -> list[str]:
        return [p.stem for p in self.base_dir.glob("*.json")]


class S3Storage:
    """Store transcripts in S3-compatible storage."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "transcripts/",
        endpoint_url: str | None = None,
    ):
        import boto3

        self.bucket = bucket
        self.prefix = prefix
        session = boto3.Session()
        self.s3 = session.client("s3", endpoint_url=endpoint_url)

    def _key(self, transcript_id: str) -> str:
        safe_id = transcript_id.replace("/", "_").replace("..", "_")
        return f"{self.prefix}{safe_id}.json"

    def save(self, transcript_id: str, data: dict) -> str:
        key = self._key(transcript_id)
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(data, indent=2),
            ContentType="application/json",
        )
        return f"s3://{self.bucket}/{key}"

    def load(self, transcript_id: str) -> dict | None:
        key = self._key(transcript_id)
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            return json.loads(resp["Body"].read())
        except self.s3.exceptions.NoSuchKey:
            return None

    def delete(self, transcript_id: str) -> bool:
        key = self._key(transcript_id)
        self.s3.delete_object(Bucket=self.bucket, Key=key)
        return True

    def list_ids(self) -> list[str]:
        paginator = self.s3.get_paginator("list_objects_v2")
        ids = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".json"):
                    name = key[len(self.prefix) : -5]
                    ids.append(name)
        return ids
