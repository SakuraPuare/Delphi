"""Git 仓库缓存测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture()
def _patch_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))


@pytest.mark.usefixtures("_patch_data_dir")
class TestCloneOrFetch:
    async def test_first_clone(self):
        """First import should clone the repo."""
        with patch(
            "delphi.ingestion.git.clone_repo", new_callable=AsyncMock
        ) as mock_clone:
            from delphi.ingestion.git import clone_or_fetch

            result = await clone_or_fetch(
                "https://github.com/user/repo", "proj", "main", 1
            )
            mock_clone.assert_called_once()
            assert isinstance(result, Path)

    async def test_fetch_existing_repo(self):
        """Second import should fetch instead of clone."""
        from delphi.core.cache import get_repo_dir

        repo_dir = get_repo_dir("proj", "https://github.com/user/repo")
        (repo_dir / ".git").mkdir(parents=True)

        with (
            patch(
                "delphi.ingestion.git._git_fetch_reset", new_callable=AsyncMock
            ) as mock_fetch,
            patch(
                "delphi.ingestion.git.clone_repo", new_callable=AsyncMock
            ) as mock_clone,
        ):
            from delphi.ingestion.git import clone_or_fetch

            result = await clone_or_fetch(
                "https://github.com/user/repo", "proj", "main", 1
            )
            mock_fetch.assert_called_once()
            mock_clone.assert_not_called()
            assert result == repo_dir

    async def test_reclone_on_fetch_failure(self):
        """If fetch fails, should delete and re-clone."""
        from delphi.core.cache import get_repo_dir

        repo_dir = get_repo_dir("proj", "https://github.com/user/repo2")
        (repo_dir / ".git").mkdir(parents=True)

        with (
            patch(
                "delphi.ingestion.git._git_fetch_reset",
                new_callable=AsyncMock,
                side_effect=Exception("fetch failed"),
            ) as mock_fetch,
            patch(
                "delphi.ingestion.git.clone_repo", new_callable=AsyncMock
            ) as mock_clone,
        ):
            from delphi.ingestion.git import clone_or_fetch

            result = await clone_or_fetch(
                "https://github.com/user/repo2", "proj", "main", 1
            )
            mock_fetch.assert_called_once()
            mock_clone.assert_called_once()
            assert isinstance(result, Path)
