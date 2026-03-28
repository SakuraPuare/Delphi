"""集成测试：导入流水线 git clone → parse → chunk → embed → store。

使用临时目录和 mock embedding，不需要外部服务。
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from qdrant_client import AsyncQdrantClient

from delphi.core.clients import VectorStore
from delphi.ingestion.chunker import chunk_file, detect_language
from delphi.ingestion.git import collect_files
from delphi.ingestion.incremental import get_existing_hashes
from delphi.ingestion.pipeline import create_task, get_task, run_git_import

from .conftest import FakeEmbedding

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def vs():
    client = AsyncQdrantClient(location=":memory:")
    store = VectorStore(client=client)
    yield store
    await store.close()


@pytest.fixture
def embedding():
    return FakeEmbedding()


def _create_repo(tmp_path: Path) -> Path:
    """创建一个模拟的代码仓库目录。"""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Python 文件
    (repo / "main.py").write_text(
        textwrap.dedent("""\
        def hello():
            print("hello world")

        def goodbye():
            print("goodbye")

        class Greeter:
            def greet(self, name):
                return f"Hello, {name}!"
        """)
    )

    # Markdown 文件
    (repo / "README.md").write_text("# My Project\n\nThis is a test project.\n")

    # JavaScript 文件
    (repo / "index.js").write_text(
        textwrap.dedent("""\
        function main() {
            console.log("hello");
        }
        """)
    )

    # 应被忽略的目录
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\x00")

    # 不支持的文件类型
    (repo / "image.png").write_bytes(b"\x89PNG\r\n")

    return repo


# ---------------------------------------------------------------------------
# 完整导入流程
# ---------------------------------------------------------------------------


class TestFullImportPipeline:
    """测试 git import 全链路：collect → chunk → embed → store。"""

    @pytest.mark.asyncio
    async def test_local_import_end_to_end(self, vs, embedding, tmp_path):
        """本地目录导入的完整流程。"""
        repo = _create_repo(tmp_path)
        task_id = create_task()

        await run_git_import(
            task_id=task_id,
            url=str(repo),
            project="test-import",
            embedding=embedding,
            vector_store=vs,
        )

        task = get_task(task_id)
        assert task["status"] == "done"
        assert task["total"] > 0

        count = await vs.count("test-import")
        assert count > 0

    @pytest.mark.asyncio
    async def test_import_nonexistent_path_fails(self, vs, embedding):
        """导入不存在的路径应标记任务失败。"""
        task_id = create_task()

        await run_git_import(
            task_id=task_id,
            url="/nonexistent/path/to/repo",
            project="fail-proj",
            embedding=embedding,
            vector_store=vs,
        )

        task = get_task(task_id)
        assert task["status"] == "failed"
        assert task["error"] is not None


# ---------------------------------------------------------------------------
# 增量更新
# ---------------------------------------------------------------------------


class TestIncrementalUpdate:
    """测试增量导入：只处理变更文件。"""

    @pytest.mark.asyncio
    async def test_no_change_skips_import(self, vs, embedding, tmp_path):
        """文件未变更时应跳过导入。"""
        repo = _create_repo(tmp_path)

        # 第一次导入
        t1 = create_task()
        await run_git_import(
            task_id=t1,
            url=str(repo),
            project="inc-proj",
            embedding=embedding,
            vector_store=vs,
        )
        count_after_first = await vs.count("inc-proj")
        assert count_after_first > 0

        # 第二次导入（无变更）
        t2 = create_task()
        await run_git_import(
            task_id=t2,
            url=str(repo),
            project="inc-proj",
            embedding=embedding,
            vector_store=vs,
        )
        task2 = get_task(t2)
        assert task2["status"] == "done"
        # 无变更文件
        assert task2["total"] == 0

    @pytest.mark.asyncio
    async def test_modified_file_re_imported(self, vs, embedding, tmp_path):
        """修改文件后应重新导入该文件的 chunks。"""
        repo = _create_repo(tmp_path)

        t1 = create_task()
        await run_git_import(
            task_id=t1,
            url=str(repo),
            project="mod-proj",
            embedding=embedding,
            vector_store=vs,
        )

        # 修改一个文件
        (repo / "main.py").write_text("def updated(): pass\n")

        t2 = create_task()
        await run_git_import(
            task_id=t2,
            url=str(repo),
            project="mod-proj",
            embedding=embedding,
            vector_store=vs,
        )
        task2 = get_task(t2)
        assert task2["status"] == "done"
        assert task2["total"] >= 1  # 至少 main.py 被重新处理

    @pytest.mark.asyncio
    async def test_deleted_file_chunks_removed(self, vs, embedding, tmp_path):
        """删除文件后其 chunks 应被清理。"""
        repo = _create_repo(tmp_path)

        t1 = create_task()
        await run_git_import(
            task_id=t1,
            url=str(repo),
            project="del-proj",
            embedding=embedding,
            vector_store=vs,
        )

        # 删除一个文件
        (repo / "index.js").unlink()

        t2 = create_task()
        await run_git_import(
            task_id=t2,
            url=str(repo),
            project="del-proj",
            embedding=embedding,
            vector_store=vs,
        )

        # 验证 index.js 的 chunks 已被删除
        hashes = await get_existing_hashes(vs, "del-proj")
        assert "index.js" not in hashes


# ---------------------------------------------------------------------------
# 文件类型处理
# ---------------------------------------------------------------------------


class TestFileTypeHandling:
    """测试不同文件类型的解析和切分。"""

    def test_python_file_chunking(self, tmp_path):
        """Python 文件应被 tree-sitter 正确解析。"""
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    return 42\n\nclass Bar:\n    pass\n")
        chunks = chunk_file(f)
        assert len(chunks) >= 2  # foo + Bar
        assert any("foo" in c.text for c in chunks)

    def test_javascript_file_chunking(self, tmp_path):
        """JavaScript 文件应被正确解析。"""
        f = tmp_path / "test.js"
        f.write_text("function hello() {\n  console.log('hi');\n}\n")
        chunks = chunk_file(f)
        assert len(chunks) >= 1
        assert any("hello" in c.text for c in chunks)

    def test_markdown_fallback_chunking(self, tmp_path):
        """Markdown 文件应使用 fallback 滑动窗口切分。"""
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nSome content here.\n\n## Section\n\nMore content.\n")
        chunks = chunk_file(f)
        assert len(chunks) >= 1

    def test_unsupported_extension_fallback(self, tmp_path):
        """不支持的扩展名应使用 fallback 切分。"""
        f = tmp_path / "data.txt"
        f.write_text("line 1\nline 2\nline 3\n")
        chunks = chunk_file(f)
        assert len(chunks) >= 1

    def test_detect_language(self, tmp_path):
        """语言检测应正确识别文件类型。"""
        assert detect_language(Path("test.py")) == "python"
        assert detect_language(Path("test.js")) == "javascript"
        assert detect_language(Path("test.ts")) == "typescript"
        assert detect_language(Path("test.go")) == "go"
        assert detect_language(Path("test.rs")) == "rust"
        assert detect_language(Path("test.unknown")) is None

    def test_collect_files_skips_pycache(self, tmp_path):
        """collect_files 应跳过 __pycache__ 目录。"""
        repo = _create_repo(tmp_path)
        files = collect_files(repo)
        assert not any("__pycache__" in str(f) for f in files)

    def test_collect_files_skips_unsupported(self, tmp_path):
        """collect_files 应跳过不支持的文件类型。"""
        repo = _create_repo(tmp_path)
        files = collect_files(repo)
        assert not any(f.suffix == ".png" for f in files)

    def test_collect_files_with_include_filter(self, tmp_path):
        """include 过滤器应只保留匹配的文件。"""
        repo = _create_repo(tmp_path)
        files = collect_files(repo, include=["*.py"])
        assert all(f.suffix == ".py" for f in files)
        assert len(files) >= 1
