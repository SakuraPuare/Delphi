"""Tree-sitter chunker 单元测试"""

from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock

from delphi.ingestion.chunker import (
    MAX_CHUNK_LINES,
    _get_parent_symbol,
    _get_symbol_name,
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


# ---------------------------------------------------------------------------
# Symbol extraction (metadata enrichment) tests
# ---------------------------------------------------------------------------


class TestSymbolExtraction:
    def test_python_function_name(self):
        code = b"def hello_world():\n    pass\n"
        chunks = parse_code(code, "python")
        assert len(chunks) >= 1
        assert chunks[0].metadata.symbol_name == "hello_world"

    def test_python_class_name(self):
        code = b"class MyClass:\n    pass\n"
        chunks = parse_code(code, "python")
        assert len(chunks) >= 1
        assert chunks[0].metadata.symbol_name == "MyClass"

    def test_python_method_parent(self):
        code = b"class Foo:\n    def bar(self):\n        pass\n"
        chunks = parse_code(code, "python")
        # class 为容器节点：展开子方法，方法的 parent_symbol 为类名
        assert any(c.metadata.symbol_name == "bar" and c.metadata.parent_symbol == "Foo" for c in chunks)

    def test_javascript_function_name(self):
        code = b"function greet(name) {\n  return 'hello ' + name;\n}\n"
        chunks = parse_code(code, "javascript")
        assert len(chunks) >= 1
        assert chunks[0].metadata.symbol_name == "greet"

    def test_no_symbol_fallback(self):
        code = b"x = 1\ny = 2\n"
        chunks = parse_code(code, "python")
        # 没有函数/类定义，走 fallback
        for c in chunks:
            assert c.metadata.symbol_name == ""


# ---------------------------------------------------------------------------
# C++ symbol extraction tests (lines 130-150, 158)
# ---------------------------------------------------------------------------


def test_parse_cpp_function_symbol():
    """qualified_identifier path: void MyClass::MyMethod() { ... }"""
    source = dedent("""\
        void MyClass::MyMethod() {
            int x = 1;
        }
    """).encode()
    chunks = parse_code(source, "cpp")
    assert len(chunks) >= 1
    assert any(c.metadata.symbol_name == "MyClass::MyMethod" for c in chunks)


def test_parse_cpp_simple_function_symbol():
    """function_declarator -> identifier path: int add(int a, int b)"""
    source = dedent("""\
        int add(int a, int b) {
            return a + b;
        }
    """).encode()
    chunks = parse_code(source, "cpp")
    assert len(chunks) >= 1
    assert any(c.metadata.symbol_name == "add" for c in chunks)


def test_parse_cpp_pointer_return_symbol():
    """pointer_declarator at top level: symbol extraction returns empty (line 158)."""
    source = dedent("""\
        int* create() {
            return nullptr;
        }
    """).encode()
    chunks = parse_code(source, "cpp")
    assert len(chunks) >= 1
    # pointer_declarator is a direct child of function_definition, not nested
    # inside function_declarator, so _get_symbol_name falls through to return ""
    assert chunks[0].metadata.symbol_name == ""


def test_parse_cpp_class_specifier():
    source = dedent("""\
        class Foo {
        public:
            int x;
        };
    """).encode()
    chunks = parse_code(source, "cpp")
    assert any(c.metadata.node_type == "class_specifier" for c in chunks)


def test_parse_cpp_struct_specifier():
    source = dedent("""\
        struct Bar {
            int x;
            int y;
        };
    """).encode()
    chunks = parse_code(source, "cpp")
    assert any(c.metadata.node_type == "struct_specifier" for c in chunks)


def test_parse_cpp_namespace():
    source = dedent("""\
        namespace ns {
            void f() {}
        }
    """).encode()
    chunks = parse_code(source, "cpp")
    # namespace 为容器节点：展开内部函数，不再单独产出 namespace_definition 块
    assert any(c.metadata.node_type == "function_definition" and c.metadata.symbol_name == "f" for c in chunks)


def test_parse_cpp_enum_specifier():
    source = dedent("""\
        enum Color { RED, GREEN, BLUE };
    """).encode()
    chunks = parse_code(source, "cpp")
    assert any(c.metadata.node_type == "enum_specifier" for c in chunks)


# ---------------------------------------------------------------------------
# Large node splitting tests (lines 168-237, 242-251, 274-275)
# ---------------------------------------------------------------------------


def test_split_large_function_semantic():
    """A C++ function with >100 lines should be split into multiple chunks."""
    lines = ["void big_func() {"]
    for i in range(120):
        lines.append(f"    int x{i} = {i};")
    lines.append("}")
    source = "\n".join(lines).encode()

    chunks = parse_code(source, "cpp")
    # Must produce more than one chunk
    assert len(chunks) > 1
    for c in chunks:
        assert c.metadata.symbol_name == "big_func"
        assert c.metadata.node_type == "function_definition"
        chunk_lines = c.text.count("\n") + 1
        assert chunk_lines <= MAX_CHUNK_LINES


# PLACEHOLDER_APPEND_2


def test_split_large_function_fallback():
    """When the function body has too few direct children, fall back to sliding window."""
    # Build a function with >100 lines but only ONE compound child (a single if block)
    inner_lines = []
    for i in range(120):
        inner_lines.append(f"        int y{i} = {i};")
    inner_body = "\n".join(inner_lines)
    source = dedent(f"""\
        void big_single() {{
            if (true) {{
        {inner_body}
            }}
        }}
    """).encode()

    chunks = parse_code(source, "cpp")
    # Should still produce multiple chunks via fallback
    assert len(chunks) > 1
    for c in chunks:
        assert c.metadata.symbol_name == "big_single"


# ---------------------------------------------------------------------------
# Miscellaneous coverage tests (lines 158, 290-291)
# ---------------------------------------------------------------------------


def test_h_file_uses_cpp_parser():
    assert detect_language(Path("foo.h")) == "cpp"


def test_trivial_chunk_filtered():
    """Trivially small chunks (e.g. lone semicolons) should be filtered out."""
    # A semicolon at top level in C is a declaration, but trivially small
    source = b";\n;\n"
    chunks = parse_code(source, "c")
    # Either no chunks or all remaining chunks have meaningful text
    for c in chunks:
        assert len(c.text.strip()) > 1


def test_parse_go_type_declaration():
    source = dedent("""\
        package main

        type MyStruct struct {
            X int
        }
    """).encode()
    chunks = parse_code(source, "go")
    assert any(c.metadata.node_type == "type_declaration" for c in chunks)


# ---------------------------------------------------------------------------
# Deeply nested declarator chain (lines 142-148)
# ---------------------------------------------------------------------------


def _make_mock_node(node_type: str, children=None, text=None):
    """Helper to build a mock tree-sitter Node."""
    node = MagicMock()
    node.type = node_type
    node.children = children or []
    node.text = text
    node.parent = None
    return node


def test_get_symbol_name_nested_pointer_declarator_identifier():
    """Lines 142-148: function_declarator -> pointer_declarator -> identifier."""
    ident = _make_mock_node("identifier", text=b"create")
    star = _make_mock_node("*", text=b"*")
    ptr_decl = _make_mock_node("pointer_declarator", children=[star, ident])
    param_list = _make_mock_node("parameter_list")
    func_decl = _make_mock_node("function_declarator", children=[ptr_decl, param_list])
    func_def = _make_mock_node("function_definition", children=[func_decl])

    assert _get_symbol_name(func_def) == "create"


def test_get_symbol_name_field_identifier_in_declarator():
    """Line 139-140: function_declarator -> field_identifier (C++ inline method)."""
    field_id = _make_mock_node("field_identifier", text=b"bar")
    param_list = _make_mock_node("parameter_list")
    func_decl = _make_mock_node("function_declarator", children=[field_id, param_list])
    func_def = _make_mock_node("function_definition", children=[func_decl])

    assert _get_symbol_name(func_def) == "bar"


def test_get_symbol_name_nested_reference_declarator_qualified():
    """Lines 142-148: function_declarator -> reference_declarator -> qualified_identifier."""
    qual_id = _make_mock_node("qualified_identifier", text=b"Foo::bar")
    amp = _make_mock_node("&", text=b"&")
    ref_decl = _make_mock_node("reference_declarator", children=[amp, qual_id])
    param_list = _make_mock_node("parameter_list")
    func_decl = _make_mock_node("function_declarator", children=[ref_decl, param_list])
    func_def = _make_mock_node("function_definition", children=[func_decl])

    assert _get_symbol_name(func_def) == "Foo::bar"


def test_get_symbol_name_nested_function_declarator_scoped():
    """Lines 142-148: init_declarator -> function_declarator -> scoped_identifier."""
    scoped_id = _make_mock_node("scoped_identifier", text=b"ns::func")
    param_list = _make_mock_node("parameter_list")
    inner_func_decl = _make_mock_node("function_declarator", children=[scoped_id, param_list])
    outer_init_decl = _make_mock_node("init_declarator", children=[inner_func_decl])
    node = _make_mock_node("function_definition", children=[outer_init_decl])

    assert _get_symbol_name(node) == "ns::func"


# ---------------------------------------------------------------------------
# _get_parent_symbol returning _get_symbol_name(parent) (line 158)
# ---------------------------------------------------------------------------


def test_get_parent_symbol_finds_chunk_parent():
    """Line 158: _get_parent_symbol returns the symbol name of a chunk-type parent."""
    # Build: class_specifier (parent) -> ... -> function_definition (child)
    parent_name = _make_mock_node("type_identifier", text=b"MyClass")
    parent_node = _make_mock_node("class_specifier", children=[parent_name])
    parent_node.parent = None

    child_node = _make_mock_node("function_definition")
    child_node.parent = parent_node

    assert _get_parent_symbol(child_node) == "MyClass"


# ---------------------------------------------------------------------------
# Large node with no compound_statement body (line 181)
# ---------------------------------------------------------------------------


def test_split_large_namespace_no_compound_statement():
    """Line 181: large namespace has declaration_list body, not compound_statement.

    _split_large_node can't find a compound_statement/block/statement_block child,
    so it falls back to _fallback_split.
    """
    funcs = []
    for i in range(110):
        funcs.append(f"void func_{i}() {{ int x = {i}; }}")
    source = ("namespace big_ns {\n" + "\n".join(funcs) + "\n}").encode()

    chunks = parse_code(source, "cpp")
    assert len(chunks) > 1


# ---------------------------------------------------------------------------
# fallback_chunk empty text (lines 290-291)
# ---------------------------------------------------------------------------


def test_fallback_chunk_empty_text():
    """Lines 290-291: empty text returns empty list immediately."""
    assert fallback_chunk("") == []
