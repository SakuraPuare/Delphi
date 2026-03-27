"""Git 文件收集测试"""

from pathlib import Path

from delphi.ingestion.git import collect_files


def test_collect_files_basic(tmp_path: Path):
    # Create a mini repo structure
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "lib.go").write_text("package main")
    (tmp_path / "readme.md").write_text("# Readme")
    (tmp_path / "data.json").write_text("{}")  # unsupported ext
    (tmp_path / "image.png").write_bytes(b"\x89PNG")  # unsupported

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "main.py" in names
    assert "lib.go" in names
    assert "readme.md" in names
    assert "data.json" not in names
    assert "image.png" not in names


def test_collect_files_skips_dirs(tmp_path: Path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("module.exports = {}")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "mod.cpython-312.pyc").write_bytes(b"")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("pass")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "dep.js" not in names
    assert "app.py" in names


def test_collect_files_gitignore(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("*.log\nsecret/\n")
    (tmp_path / "app.py").write_text("pass")
    (tmp_path / "debug.log").write_text("log")
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "key.py").write_text("KEY='xxx'")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "app.py" in names
    assert "debug.log" not in names
    assert "key.py" not in names


def test_collect_files_include_filter(tmp_path: Path):
    (tmp_path / "main.py").write_text("pass")
    (tmp_path / "lib.go").write_text("package main")
    (tmp_path / "readme.md").write_text("# Hi")

    files = collect_files(tmp_path, include=["*.py"])
    names = {f.name for f in files}
    assert "main.py" in names
    assert "lib.go" not in names
    assert "readme.md" not in names
