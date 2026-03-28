"""Git 仓库克隆与文件收集"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pathspec

from delphi.ingestion.chunker import EXT_MAP

if TYPE_CHECKING:
    from pathlib import Path

from loguru import logger

# Directories to always skip
SKIP_DIRS: set[str] = {
    ".git",
    "node_modules",
    "vendor",
    "third_party",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "out",
    "target",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
}

# File patterns to always skip
SKIP_PATTERNS: list[str] = [
    "*.pb.cc",
    "*.pb.h",
    "*_generated.*",
    "*.min.js",
    "*.min.css",
    "*.lock",
    "*.sum",
]

# Supported file extensions (code + common text)
SUPPORTED_EXTS: set[str] = set(EXT_MAP.keys()) | {".md", ".mdx", ".txt", ".rst", ".html"}


async def clone_repo(
    url: str,
    dest: Path,
    branch: str = "main",
    depth: int = 1,
) -> None:
    cmd = ["git", "clone", "--single-branch", f"--branch={branch}"]
    if depth > 0:
        cmd.append(f"--depth={depth}")
    cmd.extend([url, str(dest)])

    logger.info("开始克隆仓库, url={}, branch={}, depth={}", url, branch, depth)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("仓库克隆失败, url={}, stderr={}", url, stderr.decode().strip())
        raise RuntimeError(f"git clone failed: {stderr.decode().strip()}")
    logger.info("仓库克隆完成, url={}, 目标路径={}", url, dest)


def _load_gitignore(repo_root: Path) -> pathspec.PathSpec | None:
    gitignore = repo_root / ".gitignore"
    if gitignore.exists():
        logger.debug("加载 .gitignore 规则, repo={}", repo_root)
        return pathspec.PathSpec.from_lines("gitignore", gitignore.read_text().splitlines())
    logger.debug("未找到 .gitignore, repo={}", repo_root)
    return None


def collect_files(
    repo_path: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[Path]:
    """Walk repo and return files to process, respecting filters."""
    logger.info("开始收集仓库文件, repo={}, include={}, exclude={}", repo_path, include, exclude)
    gitignore_spec = _load_gitignore(repo_path)
    skip_spec = pathspec.PathSpec.from_lines("gitignore", SKIP_PATTERNS)

    include_spec = pathspec.PathSpec.from_lines("gitignore", include) if include else None
    exclude_spec = pathspec.PathSpec.from_lines("gitignore", exclude) if exclude else None

    result: list[Path] = []

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue

        # Check if any parent dir should be skipped
        if any(part in SKIP_DIRS for part in path.relative_to(repo_path).parts):
            continue

        rel = str(path.relative_to(repo_path))

        # .gitignore
        if gitignore_spec and gitignore_spec.match_file(rel):
            continue

        # Built-in skip patterns
        if skip_spec.match_file(rel):
            continue

        # User include filter
        if include_spec and not include_spec.match_file(rel):
            continue

        # User exclude filter
        if exclude_spec and exclude_spec.match_file(rel):
            continue

        # Only process supported extensions
        if path.suffix.lower() not in SUPPORTED_EXTS:
            continue

        result.append(path)

    logger.info("文件收集完成, repo={}, 文件数={}", repo_path, len(result))
    return sorted(result)
