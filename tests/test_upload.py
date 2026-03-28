"""上传会话管理测试"""

from __future__ import annotations

import hashlib
import json
import time

import pytest


@pytest.fixture()
def _patch_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))


@pytest.mark.usefixtures("_patch_data_dir")
class TestUploadSession:
    def test_create_and_load_session(self):
        from delphi.ingestion.upload import create_session, load_session

        session = create_session("proj", "test.pdf", 1024, "abc123", 2, "doc")
        assert session.upload_id
        assert session.project == "proj"
        assert session.file_name == "test.pdf"
        assert session.total_chunks == 2
        assert len(session.received_chunks) == 0
        # Load it back
        loaded = load_session(session.upload_id)
        assert loaded is not None
        assert loaded.upload_id == session.upload_id
        assert loaded.file_hash == "abc123"

    def test_save_chunk_updates_received(self):
        from delphi.ingestion.upload import create_session, load_session, save_chunk

        session = create_session("proj", "test.pdf", 100, "hash1", 3, "doc")
        save_chunk(session.upload_id, 0, b"chunk0")
        save_chunk(session.upload_id, 2, b"chunk2")
        loaded = load_session(session.upload_id)
        assert loaded is not None
        assert loaded.received_chunks == {0, 2}

    def test_find_session_by_hash(self):
        from delphi.ingestion.upload import create_session, find_session_by_hash

        session = create_session("proj", "test.pdf", 100, "unique_hash_xyz", 1, "doc")
        found = find_session_by_hash("unique_hash_xyz")
        assert found is not None
        assert found.upload_id == session.upload_id
        # Non-existent hash
        assert find_session_by_hash("nonexistent") is None

    def test_assemble_success(self):
        from delphi.ingestion.upload import assemble, create_session, save_chunk

        content = b"hello world from chunks"
        file_hash = hashlib.sha256(content).hexdigest()
        # Split into 2 chunks
        mid = len(content) // 2
        chunk0 = content[:mid]
        chunk1 = content[mid:]
        session = create_session("proj", "test.bin", len(content), file_hash, 2, "doc")
        save_chunk(session.upload_id, 0, chunk0)
        save_chunk(session.upload_id, 1, chunk1)
        result = assemble(session.upload_id)
        assert result.exists()
        assert result.read_bytes() == content

    def test_assemble_hash_mismatch(self):
        from delphi.ingestion.upload import (
            HashMismatchError,
            assemble,
            create_session,
            save_chunk,
        )

        session = create_session("proj", "bad.bin", 5, "wrong_hash", 1, "doc")
        save_chunk(session.upload_id, 0, b"hello")
        with pytest.raises(HashMismatchError):
            assemble(session.upload_id)

    def test_cleanup_stale(self):
        from delphi.core.cache import get_staging_dir
        from delphi.ingestion.upload import cleanup_stale, create_session, load_session

        session = create_session("proj", "old.bin", 100, "oldhash", 1, "doc")
        # Manually backdate the created_at in meta
        meta_path = get_staging_dir(session.upload_id) / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["created_at"] = time.time() - 25 * 3600  # 25 hours ago
        meta_path.write_text(json.dumps(meta))
        removed = cleanup_stale(max_age_hours=24)
        assert removed >= 1
        assert load_session(session.upload_id) is None
