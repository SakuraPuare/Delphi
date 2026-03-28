"""缓存模块测试"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def _patch_data_dir(tmp_path, monkeypatch):
    """Redirect settings.data_dir to a temp directory."""
    monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))


@pytest.mark.usefixtures("_patch_data_dir")
class TestCache:
    def test_get_upload_dir_creates_directory(self):
        from delphi.core.cache import get_upload_dir

        d = get_upload_dir("test-project")
        assert d.exists()
        assert d.is_dir()
        assert "uploads" in str(d)
        assert "test-project" in str(d)

    def test_get_staging_dir_creates_chunks_subdir(self):
        from delphi.core.cache import get_staging_dir

        d = get_staging_dir("abc123")
        assert d.exists()
        assert (d / "chunks").exists()

    def test_get_repo_dir_deterministic(self):
        from delphi.core.cache import get_repo_dir

        d1 = get_repo_dir("proj", "https://github.com/user/repo")
        d2 = get_repo_dir("proj", "https://github.com/user/repo")
        assert d1 == d2
        assert d1.exists()

    def test_get_repo_dir_different_urls(self):
        from delphi.core.cache import get_repo_dir

        d1 = get_repo_dir("proj", "https://github.com/user/repo1")
        d2 = get_repo_dir("proj", "https://github.com/user/repo2")
        assert d1 != d2

    def test_check_cache_returns_none_when_missing(self):
        from delphi.core.cache import check_cache

        assert check_cache("proj", "deadbeef") is None

    def test_save_and_check_cache(self, tmp_path):
        from delphi.core.cache import check_cache, save_to_cache

        # Create a source file
        src = tmp_path / "source.pdf"
        src.write_bytes(b"hello world")
        result = save_to_cache("proj", "abc123hash", src, "document.pdf")
        assert result.exists()
        assert result.read_bytes() == b"hello world"
        # Check cache should find it
        cached = check_cache("proj", "abc123hash")
        assert cached is not None
        assert cached == result

    def test_save_to_cache_writes_meta(self, tmp_path):
        from delphi.core.cache import get_upload_dir, save_to_cache

        src = tmp_path / "test.txt"
        src.write_bytes(b"data")
        save_to_cache("proj", "hash123", src, "test.txt")
        meta_path = get_upload_dir("proj") / "hash123.meta"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["name"] == "test.txt"
        assert meta["size"] == 4

    def test_list_cached_files(self, tmp_path):
        from delphi.core.cache import list_cached_files, save_to_cache

        src1 = tmp_path / "a.txt"
        src1.write_bytes(b"aaa")
        src2 = tmp_path / "b.txt"
        src2.write_bytes(b"bbb")
        save_to_cache("proj", "hash_a", src1, "a.txt")
        save_to_cache("proj", "hash_b", src2, "b.txt")
        files = list_cached_files("proj")
        assert len(files) == 2
        names = {f["name"] for f in files}
        assert names == {"a.txt", "b.txt"}
