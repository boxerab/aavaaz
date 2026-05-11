"""Tests for storage backends."""

import json
import tempfile
from pathlib import Path

from aavaaz.api.storage import LocalStorage


def test_local_storage_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalStorage(base_dir=tmpdir)
        data = {"segments": [{"text": "hello", "start": 0, "end": 1}]}
        store.save("test-001", data)

        loaded = store.load("test-001")
        assert loaded == data


def test_local_storage_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalStorage(base_dir=tmpdir)
        store.save("a", {"text": "a"})
        store.save("b", {"text": "b"})
        ids = store.list_ids()
        assert sorted(ids) == ["a", "b"]


def test_local_storage_delete():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalStorage(base_dir=tmpdir)
        store.save("del-me", {"text": "bye"})
        assert store.delete("del-me")
        assert store.load("del-me") is None


def test_local_storage_path_traversal():
    """Ensure path traversal attempts are sanitized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalStorage(base_dir=tmpdir)
        store.save("../../etc/passwd", {"text": "nope"})
        # Should be stored safely inside base_dir
        assert not Path("/etc/passwd.json").exists()
        assert store.load("../../etc/passwd") is not None
