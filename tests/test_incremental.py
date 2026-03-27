"""Tests for incremental update module."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from qdrant_client import AsyncQdrantClient

if TYPE_CHECKING:
    from pathlib import Path

from delphi.core.clients import VectorStore
from delphi.ingestion.incremental import (
    compute_file_hash,
    delete_file_chunks,
    get_existing_hashes,
)

DIM = VectorStore.VECTOR_SIZE


@pytest.fixture()
async def vs():
    client = AsyncQdrantClient(location=":memory:")
    store = VectorStore(client=client)
    yield store
    await client.close()


# ---------------------------------------------------------------------------
# compute_file_hash tests
# ---------------------------------------------------------------------------


class TestComputeFileHash:
    def test_returns_sha256(self, tmp_path: Path):
        f = tmp_path / "a.txt"
        f.write_text("hello")
        h = compute_file_hash(f)
        assert len(h) == 64  # SHA256 hex digest length
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_content_same_hash(self, tmp_path: Path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same content")
        f2.write_text("same content")
        assert compute_file_hash(f1) == compute_file_hash(f2)

    def test_different_content_different_hash(self, tmp_path: Path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content A")
        f2.write_text("content B")
        assert compute_file_hash(f1) != compute_file_hash(f2)


# ---------------------------------------------------------------------------
# get_existing_hashes tests
# ---------------------------------------------------------------------------


async def _insert_points(vs: VectorStore, collection: str, items: list[dict]) -> None:
    """Helper: insert points with file_path / file_hash payloads."""
    await vs.ensure_collection(collection)
    ids = [str(uuid.uuid4()) for _ in items]
    vecs = [[0.1] * DIM for _ in items]
    await vs.upsert(collection, ids, vecs, items)


class TestGetExistingHashes:
    @pytest.mark.asyncio
    async def test_returns_correct_mapping(self, vs):
        await _insert_points(
            vs,
            "inc",
            [
                {"file_path": "a.py", "file_hash": "aaa"},
                {"file_path": "a.py", "file_hash": "aaa"},
                {"file_path": "b.py", "file_hash": "bbb"},
            ],
        )
        result = await get_existing_hashes(vs, "inc")
        assert result == {
            "a.py": {"aaa"},
            "b.py": {"bbb"},
        }

    @pytest.mark.asyncio
    async def test_multiple_hashes_per_file(self, vs):
        await _insert_points(
            vs,
            "inc2",
            [
                {"file_path": "x.py", "file_hash": "h1"},
                {"file_path": "x.py", "file_hash": "h2"},
            ],
        )
        result = await get_existing_hashes(vs, "inc2")
        assert result == {"x.py": {"h1", "h2"}}

    @pytest.mark.asyncio
    async def test_empty_collection(self, vs):
        await vs.ensure_collection("empty")
        result = await get_existing_hashes(vs, "empty")
        assert result == {}

    @pytest.mark.asyncio
    async def test_nonexistent_collection(self, vs):
        result = await get_existing_hashes(vs, "does-not-exist")
        assert result == {}


# ---------------------------------------------------------------------------
# delete_file_chunks tests
# ---------------------------------------------------------------------------


class TestDeleteFileChunks:
    @pytest.mark.asyncio
    async def test_deletes_only_target_file(self, vs):
        await _insert_points(
            vs,
            "del",
            [
                {"file_path": "keep.py", "file_hash": "k1", "text": "keep"},
                {"file_path": "keep.py", "file_hash": "k1", "text": "keep2"},
                {"file_path": "remove.py", "file_hash": "r1", "text": "gone"},
                {"file_path": "remove.py", "file_hash": "r1", "text": "gone2"},
            ],
        )
        assert await vs.count("del") == 4

        await delete_file_chunks(vs, "del", "remove.py")
        assert await vs.count("del") == 2

        hashes = await get_existing_hashes(vs, "del")
        assert "keep.py" in hashes
        assert "remove.py" not in hashes

    @pytest.mark.asyncio
    async def test_noop_when_file_not_present(self, vs):
        await _insert_points(
            vs,
            "del2",
            [
                {"file_path": "a.py", "file_hash": "h1"},
            ],
        )
        await delete_file_chunks(vs, "del2", "nonexistent.py")
        assert await vs.count("del2") == 1
