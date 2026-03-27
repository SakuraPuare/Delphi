"""自举集成测试：用 Delphi 自身仓库走完 import → search 全链路。

使用 Qdrant 内存模式 + mock embedding（随机向量），不需要外部服务。
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from qdrant_client import AsyncQdrantClient

from delphi.core.clients import EmbeddingResult, SparseVector, VectorStore
from delphi.ingestion.chunker import chunk_file
from delphi.ingestion.doc_chunker import chunk_doc_file
from delphi.ingestion.doc_pipeline import run_doc_import
from delphi.ingestion.git import collect_files
from delphi.ingestion.pipeline import create_task, get_task, run_git_import
from delphi.retrieval.rag import ScoredChunk, build_prompt, retrieve

REPO_ROOT = Path(__file__).resolve().parent.parent
VECTOR_DIM = 1024


class FakeEmbedding:
    """Deterministic fake embedding: hash-based so same text → same vector."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for t in texts:
            rng = random.Random(hash(t))
            result.append([rng.gauss(0, 1) for _ in range(VECTOR_DIM)])
        return result

    async def embed_sparse(self, texts: list[str]) -> list[SparseVector]:
        result = []
        for t in texts:
            rng = random.Random(hash(t) ^ 0xDEAD)
            indices = sorted(rng.sample(range(30522), 10))
            values = [rng.random() for _ in range(10)]
            result.append(SparseVector(indices=indices, values=values))
        return result

    async def embed_all(self, texts: list[str]) -> EmbeddingResult:
        dense = await self.embed(texts)
        sparse = await self.embed_sparse(texts)
        return EmbeddingResult(dense=dense, sparse=sparse)

    async def close(self) -> None:
        pass


@pytest.fixture
async def vector_store():
    client = AsyncQdrantClient(location=":memory:")
    vs = VectorStore(client=client)
    yield vs
    await vs.close()


@pytest.fixture
def fake_embedding():
    return FakeEmbedding()


# --- File collection ---


class TestFileCollection:
    def test_collect_own_repo(self):
        """Delphi 仓库自身应该能收集到 .py 文件"""
        files = collect_files(REPO_ROOT)
        py_files = [f for f in files if f.suffix == ".py"]
        assert len(py_files) >= 5, f"Expected >=5 .py files, got {len(py_files)}"

    def test_collect_skips_venv_and_git(self):
        files = collect_files(REPO_ROOT)
        for f in files:
            rel = f.relative_to(REPO_ROOT)
            parts = rel.parts
            assert ".git" not in parts
            assert ".venv" not in parts
            assert "__pycache__" not in parts

    def test_collect_includes_docs(self):
        files = collect_files(REPO_ROOT)
        md_files = [f for f in files if f.suffix == ".md"]
        assert len(md_files) >= 3, f"Expected >=3 .md files, got {len(md_files)}"


# --- Chunking own code ---


class TestChunkOwnCode:
    def test_chunk_own_pipeline(self):
        """chunk_file on our own pipeline.py should produce chunks"""
        target = REPO_ROOT / "src" / "delphi" / "ingestion" / "pipeline.py"
        chunks = chunk_file(target, repo_url="self")
        assert len(chunks) >= 2
        # Should find run_git_import function
        texts = " ".join(c.text for c in chunks)
        assert "run_git_import" in texts

    def test_chunk_own_readme(self):
        """chunk_doc_file on our README should produce chunks"""
        readme = REPO_ROOT / "README.md"
        if readme.exists():
            chunks = chunk_doc_file(readme)
            assert len(chunks) >= 1

    def test_chunk_own_config(self):
        target = REPO_ROOT / "src" / "delphi" / "core" / "config.py"
        chunks = chunk_file(target)
        assert len(chunks) >= 1
        texts = " ".join(c.text for c in chunks)
        assert "Settings" in texts


# --- Full import pipeline (in-memory Qdrant) ---


class TestGitImportPipeline:
    @pytest.mark.asyncio
    async def test_import_own_src(self, vector_store: VectorStore, fake_embedding):
        """Import Delphi's own src/ directory as a local repo"""
        task_id = create_task()
        src_path = str(REPO_ROOT / "src")

        await run_git_import(
            task_id=task_id,
            url=src_path,
            project="test-self",
            embedding=fake_embedding,
            vector_store=vector_store,
        )

        task = get_task(task_id)
        assert task is not None
        assert task["status"] == "done"
        assert task["total"] >= 5  # at least 5 .py files in src/

        # Verify data in Qdrant
        count = await vector_store.count("test-self")
        assert count > 0, "Expected chunks in Qdrant"

    @pytest.mark.asyncio
    async def test_import_idempotent(self, vector_store: VectorStore, fake_embedding):
        """Importing twice should not double the data"""
        src_path = str(REPO_ROOT / "src")

        task1 = create_task()
        await run_git_import(
            task_id=task1,
            url=src_path,
            project="test-idem",
            embedding=fake_embedding,
            vector_store=vector_store,
        )
        count1 = await vector_store.count("test-idem")

        task2 = create_task()
        await run_git_import(
            task_id=task2,
            url=src_path,
            project="test-idem",
            embedding=fake_embedding,
            vector_store=vector_store,
        )
        count2 = await vector_store.count("test-idem")

        assert count1 == count2, f"Idempotency failed: {count1} vs {count2}"


class TestDocImportPipeline:
    @pytest.mark.asyncio
    async def test_import_own_docs(self, vector_store: VectorStore, fake_embedding):
        """Import Delphi's own docs/ directory"""
        docs_path = str(REPO_ROOT / "docs")

        task_id = create_task()
        await run_doc_import(
            task_id=task_id,
            path=docs_path,
            project="test-docs",
            file_types=["md"],
            embedding=fake_embedding,
            vector_store=vector_store,
        )

        task = get_task(task_id)
        assert task is not None
        assert task["status"] == "done"
        assert task["total"] >= 3

        count = await vector_store.count("test-docs")
        assert count > 0

    @pytest.mark.asyncio
    async def test_doc_import_idempotent(self, vector_store: VectorStore, fake_embedding):
        """Doc import twice should not double data"""
        docs_path = str(REPO_ROOT / "docs")

        task1 = create_task()
        await run_doc_import(
            task_id=task1,
            path=docs_path,
            project="test-docs-idem",
            file_types=["md"],
            embedding=fake_embedding,
            vector_store=vector_store,
        )
        count1 = await vector_store.count("test-docs-idem")

        task2 = create_task()
        await run_doc_import(
            task_id=task2,
            path=docs_path,
            project="test-docs-idem",
            file_types=["md"],
            embedding=fake_embedding,
            vector_store=vector_store,
        )
        count2 = await vector_store.count("test-docs-idem")

        assert count1 == count2


# --- Retrieval (search after import) ---


class TestRetrieval:
    @pytest.mark.asyncio
    async def test_search_after_import(self, vector_store: VectorStore, fake_embedding):
        """Import code, then search — should return relevant chunks"""
        src_path = str(REPO_ROOT / "src")
        task_id = create_task()
        await run_git_import(
            task_id=task_id,
            url=src_path,
            project="test-search",
            embedding=fake_embedding,
            vector_store=vector_store,
        )

        # Search for something that exists in our code
        results = await retrieve(
            question="EmbeddingClient",
            project="test-search",
            top_k=3,
            embedding_client=fake_embedding,
            vector_store=vector_store,
        )

        assert len(results) > 0
        assert all(isinstance(r, ScoredChunk) for r in results)

    @pytest.mark.asyncio
    async def test_build_prompt_with_real_chunks(self, vector_store: VectorStore, fake_embedding):
        """Build prompt from real retrieved chunks"""
        src_path = str(REPO_ROOT / "src")
        task_id = create_task()
        await run_git_import(
            task_id=task_id,
            url=src_path,
            project="test-prompt",
            embedding=fake_embedding,
            vector_store=vector_store,
        )

        results = await retrieve(
            question="如何配置 Delphi",
            project="test-prompt",
            top_k=3,
            embedding_client=fake_embedding,
            vector_store=vector_store,
        )

        messages = build_prompt("如何配置 Delphi", results)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "上下文开始" in messages[1]["content"]
        assert "如何配置 Delphi" in messages[1]["content"]
