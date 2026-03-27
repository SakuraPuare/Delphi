"""Tree-sitter chunker 单元测试"""

from pathlib import Path
from textwrap import dedent

from delphi.ingestion.chunker import (
    chunk_file,
    detect_language,
    fallback_chunk,
    parse_code,
)


def test_detect_language():
    assert detect_language(Path("foo.py")) == "python"
    assert detect_language(Path("bar.ts")) == "typescript"
    assert detect_language(Path("baz.go")) == "go"
    assert detect_language(Path("readme.md")) is None
    assert detect_language(Path("data.json")) is None


def test_parse_python_functions():
    source = dedent("""\
        def hello():
            print("hello")

        def world():
            return 42

        class Foo:
            def bar(self):
                pass
    """).encode()

    chunks = parse_code(source, "python")
    assert len(chunks) >= 2
    # Should find hello, world, and Foo (class includes bar)
    texts = [c.text for c in chunks]
    assert any("hello" in t for t in texts)
    assert any("world" in t for t in texts)


def test_parse_javascript():
    source = dedent("""\
        function greet(name) {
            return `Hello, ${name}!`;
        }

        function add(a, b) {
            return a + b;
        }
    """).encode()

    chunks = parse_code(source, "javascript")
    assert len(chunks) >= 2


def test_parse_go():
    source = dedent("""\
        package main

        func main() {
            fmt.Println("hello")
        }

        func add(a, b int) int {
            return a + b
        }
    """).encode()

    chunks = parse_code(source, "go")
    assert len(chunks) >= 2


def test_fallback_chunk_basic():
    text = "\n".join(f"line {i}" for i in range(100))
    chunks = fallback_chunk(text, window=20, overlap=5)
    assert len(chunks) > 1
    # First chunk should start at line 1
    assert chunks[0].metadata.start_line == 1
    assert chunks[0].metadata.node_type == "fallback"


def test_fallback_chunk_small_file():
    text = "just one line"
    chunks = fallback_chunk(text)
    assert len(chunks) == 1


def test_parse_unknown_language_falls_back():
    source = b"some random text\nwith multiple lines\n"
    chunks = parse_code(source, "unknown_lang")
    assert chunks == []


def test_chunk_file_python(tmp_path: Path):
    py_file = tmp_path / "example.py"
    py_file.write_text(
        dedent("""\
        def foo():
            return 1

        def bar():
            return 2
    """)
    )

    chunks = chunk_file(py_file, repo_url="https://example.com/repo")
    assert len(chunks) >= 2
    for c in chunks:
        assert c.metadata.file_path == str(py_file)
        assert c.metadata.repo_url == "https://example.com/repo"
        assert c.metadata.language == "python"


def test_chunk_file_markdown(tmp_path: Path):
    md_file = tmp_path / "readme.md"
    md_file.write_text("# Hello\n\nSome content here.\n")

    chunks = chunk_file(md_file)
    assert len(chunks) >= 1
    assert chunks[0].metadata.language == ""  # markdown not in EXT_MAP as code
