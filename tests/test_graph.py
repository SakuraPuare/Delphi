"""代码关系图谱模块单元测试"""

from pathlib import Path
from textwrap import dedent

import pytest

from delphi.graph.extractor import (
    CodeGraph,
    Relation,
    Symbol,
    extract_from_directory,
    extract_graph,
)
from delphi.graph.store import GraphStore

# ---------------------------------------------------------------------------
# Python: symbols extraction
# ---------------------------------------------------------------------------


class TestPythonSymbols:
    def test_extract_function(self):
        source = dedent("""\
            def hello():
                print("hi")

            def world():
                return 42
        """).encode()

        graph = extract_graph(source, "app.py", "python")
        names = {s.name for s in graph.symbols.values()}
        assert "hello" in names
        assert "world" in names
        kinds = {s.name: s.kind for s in graph.symbols.values()}
        assert kinds["hello"] == "function"
        assert kinds["world"] == "function"

    def test_extract_class_and_methods(self):
        source = dedent("""\
            class Animal:
                def speak(self):
                    pass

                def eat(self):
                    pass
        """).encode()

        graph = extract_graph(source, "models.py", "python")
        names = {s.name for s in graph.symbols.values()}
        assert "Animal" in names
        assert "speak" in names
        assert "eat" in names
        # kind checks
        by_name = {s.name: s for s in graph.symbols.values()}
        assert by_name["Animal"].kind == "class"
        assert by_name["speak"].kind == "method"
        assert by_name["eat"].kind == "method"

    def test_symbol_qualified_name(self):
        source = dedent("""\
            class Foo:
                def bar(self):
                    pass
        """).encode()

        graph = extract_graph(source, "pkg/foo.py", "python")
        by_name = {s.name: s for s in graph.symbols.values()}
        assert by_name["Foo"].qualified_name == "pkg/foo.py::Foo"
        assert by_name["bar"].qualified_name == "pkg/foo.py::Foo::bar"

    def test_symbol_line_numbers(self):
        source = dedent("""\
            def first():
                pass

            def second():
                pass
        """).encode()

        graph = extract_graph(source, "lines.py", "python")
        by_name = {s.name: s for s in graph.symbols.values()}
        assert by_name["first"].start_line == 1
        assert by_name["second"].start_line == 4

    def test_symbol_language_field(self):
        source = b"def f(): pass\n"
        graph = extract_graph(source, "x.py", "python")
        for s in graph.symbols.values():
            assert s.language == "python"


# ---------------------------------------------------------------------------
# Python: imports
# ---------------------------------------------------------------------------


class TestPythonImports:
    def test_import_statement(self):
        source = dedent("""\
            import os
            import sys
        """).encode()

        graph = extract_graph(source, "main.py", "python")
        import_rels = [r for r in graph.relations if r.kind == "imports"]
        targets = [r.target for r in import_rels]
        assert any("os" in t for t in targets)
        assert any("sys" in t for t in targets)

    def test_from_import(self):
        source = dedent("""\
            from pathlib import Path
            from os.path import join
        """).encode()

        graph = extract_graph(source, "util.py", "python")
        import_rels = [r for r in graph.relations if r.kind == "imports"]
        targets = [r.target for r in import_rels]
        assert any("pathlib" in t for t in targets)
        assert any("os.path" in t for t in targets)

    def test_import_source_is_file(self):
        source = b"import json\n"
        graph = extract_graph(source, "app.py", "python")
        import_rels = [r for r in graph.relations if r.kind == "imports"]
        assert all(r.source == "app.py" for r in import_rels)


# ---------------------------------------------------------------------------
# Python: calls
# ---------------------------------------------------------------------------


class TestPythonCalls:
    def test_function_calls(self):
        source = dedent("""\
            def greet():
                print("hello")
                len([1, 2])
        """).encode()

        graph = extract_graph(source, "call.py", "python")
        call_rels = [r for r in graph.relations if r.kind == "calls"]
        targets = {r.target for r in call_rels}
        assert "print" in targets
        assert "len" in targets

    def test_call_source_is_qualified(self):
        source = dedent("""\
            def process():
                do_work()
        """).encode()

        graph = extract_graph(source, "job.py", "python")
        call_rels = [r for r in graph.relations if r.kind == "calls"]
        assert any(r.source == "job.py::process" for r in call_rels)

    def test_method_calls(self):
        source = dedent("""\
            class Service:
                def run(self):
                    self.setup()
        """).encode()

        graph = extract_graph(source, "svc.py", "python")
        call_rels = [r for r in graph.relations if r.kind == "calls"]
        targets = {r.target for r in call_rels}
        assert any("setup" in t for t in targets)


# ---------------------------------------------------------------------------
# Python: inherits
# ---------------------------------------------------------------------------


class TestPythonInherits:
    def test_single_inheritance(self):
        source = dedent("""\
            class Base:
                pass

            class Child(Base):
                pass
        """).encode()

        graph = extract_graph(source, "inh.py", "python")
        inh_rels = [r for r in graph.relations if r.kind == "inherits"]
        assert any(r.source == "inh.py::Child" and r.target == "Base" for r in inh_rels)

    def test_multiple_inheritance(self):
        source = dedent("""\
            class A:
                pass

            class B:
                pass

            class C(A, B):
                pass
        """).encode()

        graph = extract_graph(source, "multi.py", "python")
        inh_rels = [r for r in graph.relations if r.kind == "inherits"]
        c_parents = {r.target for r in inh_rels if r.source == "multi.py::C"}
        assert "A" in c_parents
        assert "B" in c_parents


# ---------------------------------------------------------------------------
# JavaScript / TypeScript extraction
# ---------------------------------------------------------------------------


class TestJavaScriptExtraction:
    def test_js_function_declaration(self):
        source = dedent("""\
            function greet(name) {
                return "Hello, " + name;
            }

            function add(a, b) {
                return a + b;
            }
        """).encode()

        graph = extract_graph(source, "util.js", "javascript")
        names = {s.name for s in graph.symbols.values()}
        assert "greet" in names
        assert "add" in names

    def test_js_import(self):
        source = dedent("""\
            import { readFile } from 'fs';

            function main() {
                readFile('test.txt');
            }
        """).encode()

        graph = extract_graph(source, "index.js", "javascript")
        import_rels = [r for r in graph.relations if r.kind == "imports"]
        assert len(import_rels) >= 1
        assert any("fs" in r.target for r in import_rels)

    def test_js_class(self):
        source = dedent("""\
            class Dog {
                bark() {
                    console.log("woof");
                }
            }
        """).encode()

        graph = extract_graph(source, "dog.js", "javascript")
        names = {s.name for s in graph.symbols.values()}
        assert "Dog" in names
        assert "bark" in names

    def test_ts_extraction(self):
        source = dedent("""\
            function hello(): string {
                return "hello";
            }
        """).encode()

        graph = extract_graph(source, "app.ts", "typescript")
        names = {s.name for s in graph.symbols.values()}
        assert "hello" in names


# ---------------------------------------------------------------------------
# CodeGraph.get_callers / get_callees
# ---------------------------------------------------------------------------


class TestCodeGraphQueries:
    def _make_graph(self) -> CodeGraph:
        graph = CodeGraph()
        graph.add_relation(Relation(source="a::foo", target="a::bar", kind="calls"))
        graph.add_relation(Relation(source="a::foo", target="a::baz", kind="calls"))
        graph.add_relation(Relation(source="b::qux", target="a::bar", kind="calls"))
        graph.add_relation(Relation(source="a::foo", target="os", kind="imports"))
        return graph

    def test_get_callers(self):
        graph = self._make_graph()
        callers = graph.get_callers("a::bar")
        assert len(callers) == 2
        sources = {r.source for r in callers}
        assert "a::foo" in sources
        assert "b::qux" in sources

    def test_get_callees(self):
        graph = self._make_graph()
        callees = graph.get_callees("a::foo")
        assert len(callees) == 2
        targets = {r.target for r in callees}
        assert "a::bar" in targets
        assert "a::baz" in targets

    def test_get_callers_empty(self):
        graph = self._make_graph()
        assert graph.get_callers("nonexistent") == []

    def test_get_callees_empty(self):
        graph = self._make_graph()
        assert graph.get_callees("nonexistent") == []

    def test_get_callees_excludes_imports(self):
        graph = self._make_graph()
        callees = graph.get_callees("a::foo")
        # imports relation should not appear in callees
        assert all(r.kind == "calls" for r in callees)


# ---------------------------------------------------------------------------
# CodeGraph.to_dict / from_dict serialization
# ---------------------------------------------------------------------------


class TestCodeGraphSerialization:
    def test_to_dict_structure(self):
        graph = CodeGraph()
        graph.add_symbol(Symbol(
            name="foo", qualified_name="a.py::foo", kind="function",
            file_path="a.py", start_line=1, end_line=3, language="python",
        ))
        graph.add_relation(Relation(source="a.py::foo", target="print", kind="calls"))

        d = graph.to_dict()
        assert "symbols" in d
        assert "relations" in d
        assert "a.py::foo" in d["symbols"]
        assert len(d["relations"]) == 1
        assert d["relations"][0]["kind"] == "calls"

    def test_roundtrip(self):
        graph = CodeGraph()
        graph.add_symbol(Symbol(
            name="Bar", qualified_name="b.py::Bar", kind="class",
            file_path="b.py", start_line=1, end_line=10, language="python",
        ))
        graph.add_relation(Relation(source="b.py::Bar", target="Base", kind="inherits"))

        restored = CodeGraph.from_dict(graph.to_dict())
        assert "b.py::Bar" in restored.symbols
        assert restored.symbols["b.py::Bar"].kind == "class"
        assert len(restored.relations) == 1
        assert restored.relations[0].kind == "inherits"

    def test_empty_graph_serialization(self):
        graph = CodeGraph()
        d = graph.to_dict()
        assert d == {"symbols": {}, "relations": []}
        restored = CodeGraph.from_dict(d)
        assert len(restored.symbols) == 0
        assert len(restored.relations) == 0


# ---------------------------------------------------------------------------
# GraphStore save / load / get / delete
# ---------------------------------------------------------------------------


class TestGraphStore:
    @pytest.fixture()
    def store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GraphStore:
        """Create a GraphStore that writes to tmp_path instead of ~/.delphi/graphs"""
        monkeypatch.setattr("delphi.graph.store.GRAPH_DIR", tmp_path)
        return GraphStore()

    def _sample_graph(self) -> CodeGraph:
        g = CodeGraph()
        g.add_symbol(Symbol(
            name="main", qualified_name="main.py::main", kind="function",
            file_path="main.py", start_line=1, end_line=5, language="python",
        ))
        g.add_relation(Relation(source="main.py::main", target="print", kind="calls"))
        return g

    def test_save_and_load(self, store: GraphStore, tmp_path: Path):
        graph = self._sample_graph()
        store.save("myproject", graph)

        # JSON file should exist
        assert (tmp_path / "myproject.json").exists()

        # load from file
        loaded = store.load("myproject")
        assert loaded is not None
        assert "main.py::main" in loaded.symbols
        assert len(loaded.relations) == 1

    def test_get_from_memory(self, store: GraphStore):
        graph = self._sample_graph()
        store.save("proj", graph)

        # get should return from memory cache
        result = store.get("proj")
        assert result is not None
        assert "main.py::main" in result.symbols

    def test_get_from_disk(self, store: GraphStore):
        graph = self._sample_graph()
        store.save("proj", graph)

        # clear memory cache, force disk read
        store._graphs.clear()
        result = store.get("proj")
        assert result is not None
        assert "main.py::main" in result.symbols

    def test_get_nonexistent(self, store: GraphStore):
        assert store.get("no_such_project") is None

    def test_delete(self, store: GraphStore, tmp_path: Path):
        graph = self._sample_graph()
        store.save("to_delete", graph)
        assert (tmp_path / "to_delete.json").exists()

        store.delete("to_delete")
        assert not (tmp_path / "to_delete.json").exists()
        assert store.get("to_delete") is None

    def test_delete_nonexistent(self, store: GraphStore):
        # should not raise
        store.delete("ghost")

    def test_list_projects(self, store: GraphStore):
        store.save("alpha", self._sample_graph())
        store.save("beta", self._sample_graph())
        projects = store.list_projects()
        assert "alpha" in projects
        assert "beta" in projects


# ---------------------------------------------------------------------------
# extract_from_directory integration
# ---------------------------------------------------------------------------


class TestExtractFromDirectory:
    def test_basic_directory(self, tmp_path: Path):
        (tmp_path / "hello.py").write_text(dedent("""\
            def hello():
                print("hi")
        """))
        (tmp_path / "world.py").write_text(dedent("""\
            def world():
                hello()
        """))

        graph = extract_from_directory(tmp_path)
        names = {s.name for s in graph.symbols.values()}
        assert "hello" in names
        assert "world" in names

    def test_include_filter(self, tmp_path: Path):
        (tmp_path / "keep.py").write_text("def keep(): pass\n")
        (tmp_path / "skip.py").write_text("def skip(): pass\n")

        graph = extract_from_directory(tmp_path, include=["keep.py"])
        names = {s.name for s in graph.symbols.values()}
        assert "keep" in names
        assert "skip" not in names

    def test_exclude_filter(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("def a(): pass\n")
        (tmp_path / "b.py").write_text("def b(): pass\n")

        graph = extract_from_directory(tmp_path, exclude=["b.py"])
        names = {s.name for s in graph.symbols.values()}
        assert "a" in names
        assert "b" not in names

    def test_ignores_non_code_files(self, tmp_path: Path):
        (tmp_path / "data.txt").write_text("not code")
        (tmp_path / "real.py").write_text("def real(): pass\n")

        graph = extract_from_directory(tmp_path)
        assert len(graph.symbols) == 1

    def test_nested_directory(self, tmp_path: Path):
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "mod.py").write_text(dedent("""\
            class Config:
                def load(self):
                    pass
        """))

        graph = extract_from_directory(tmp_path)
        names = {s.name for s in graph.symbols.values()}
        assert "Config" in names
        assert "load" in names
