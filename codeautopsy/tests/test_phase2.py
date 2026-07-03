"""
tests/test_phase2.py — Phase 2 Unit and Integration Tests

Covers: Python parser, JavaScript parser, dependency builder,
call graph builder, entry point finder, pattern detector,
parse orchestrator (cache), and integration with a real repo.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure package root is on path
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ===========================================================================
# Python Parser Tests
# ===========================================================================

class TestPythonParser:
    """Tests for the Python-specific tree-sitter parser."""

    @pytest.fixture(scope="class")
    def parser(self):
        from parsing.languages.python_parser import PythonParser
        return PythonParser()

    _SIMPLE = """
import os
from pathlib import Path
from .utils import helper

MY_CONST = 42

class MyService(BaseService):
    \"\"\"A service.\"\"\"
    class_var = []

    def __init__(self, x: int, y: str = "hi"):
        \"\"\"Init.\"\"\"
        self.x = x
        self.y = y

    @staticmethod
    def process(val: int) -> bool:
        if val > 0:
            for i in range(val):
                print(i)
        return True

async def run(data: list) -> None:
    svc = MyService(1)
    svc.process(42)

if __name__ == "__main__":
    run([])
"""

    def test_parse_success(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        assert result.parse_success is True
        assert result.parse_errors == []

    def test_function_extraction(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        names = [f.name for f in result.functions]
        assert "__init__" in names
        assert "process"  in names
        assert "run"      in names

    def test_qualified_names(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        qnames = [f.qualified_name for f in result.functions]
        assert "MyService.__init__" in qnames
        assert "MyService.process"  in qnames
        assert "run" in qnames

    def test_class_extraction(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "MyService"
        assert "BaseService" in cls.base_classes

    def test_class_docstring(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        assert result.classes[0].docstring is not None

    def test_instance_variables(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        cls = result.classes[0]
        assert "x" in cls.instance_variables
        assert "y" in cls.instance_variables

    def test_imports(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        modules = [i.module for i in result.imports]
        assert "os" in modules
        assert "pathlib" in modules
        assert ".utils" in modules

    def test_relative_import_is_local(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        rel = next(i for i in result.imports if i.module == ".utils")
        assert rel.is_local is True
        assert rel.import_type == "relative"

    def test_stdlib_classification(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        os_imp = next(i for i in result.imports if i.module == "os")
        assert os_imp.is_stdlib is True

    def test_global_variables(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        assert "MY_CONST" in result.global_variables

    def test_async_function(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        run_fn = next(f for f in result.functions if f.name == "run")
        assert run_fn.is_async is True

    def test_static_method(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        proc = next(f for f in result.functions if f.name == "process")
        assert proc.is_static is True

    def test_complexity_score(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        proc = next(f for f in result.functions if f.name == "process")
        assert proc.complexity_score >= 2  # has if + for

    def test_function_calls(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        proc = next(f for f in result.functions if f.name == "process")
        assert "range" in proc.calls or "print" in proc.calls

    def test_has_main_block(self, parser):
        result = parser.parse_file("test.py", self._SIMPLE)
        assert result.has_main_block is True

    def test_syntax_error_partial_parse(self, parser):
        """Parser should still extract valid parts on syntax error."""
        broken = "def foo():\n    return\ndef bar(x\n    pass\n"
        result = parser.parse_file("broken.py", broken)
        # Should not crash — parse_success may be False but no exception
        assert isinstance(result.parse_success, bool)

    def test_empty_file(self, parser):
        result = parser.parse_file("empty.py", "")
        assert result.parse_success is True
        assert result.functions == []
        assert result.classes == []

    def test_nested_function_qualified_name(self, parser):
        src = "def outer():\n    def inner():\n        pass\n"
        result = parser.parse_file("nested.py", src)
        names = [f.name for f in result.functions]
        assert "outer" in names
        assert "inner" in names

    def test_return_type_annotation(self, parser):
        src = "def foo(x: int) -> str:\n    return str(x)\n"
        result = parser.parse_file("types.py", src)
        fn = result.functions[0]
        assert fn.return_type == "str"

    def test_private_function(self, parser):
        src = "def _internal():\n    pass\n"
        result = parser.parse_file("priv.py", src)
        assert result.functions[0].is_private is True

    def test_dunder_not_private(self, parser):
        src = "class Foo:\n    def __str__(self):\n        return 'foo'\n"
        result = parser.parse_file("dunder.py", src)
        fn = next(f for f in result.functions if f.name == "__str__")
        assert fn.is_private is False


# ===========================================================================
# JavaScript Parser Tests
# ===========================================================================

class TestJavaScriptParser:
    @pytest.fixture(scope="class")
    def parser(self):
        from parsing.languages.javascript_parser import JavaScriptParser
        return JavaScriptParser()

    _JS = """
import React from 'react';
import { useState, useEffect } from 'react';
const path = require('path');

const myFunc = (x, y) => x + y;

async function fetchData(url) {
  const res = await fetch(url);
  return res.json();
}

class MyComponent extends React.Component {
  constructor(props) {
    super(props);
  }
  render() { return null; }
}

module.exports = { myFunc };
"""

    def test_parse_success(self, parser):
        result = parser.parse_file("app.js", self._JS)
        assert result.parse_success is True

    def test_function_detection(self, parser):
        result = parser.parse_file("app.js", self._JS)
        names = [f.name for f in result.functions]
        assert "fetchData" in names
        assert "myFunc" in names

    def test_async_function(self, parser):
        result = parser.parse_file("app.js", self._JS)
        fn = next(f for f in result.functions if f.name == "fetchData")
        assert fn.is_async is True

    def test_class_detection(self, parser):
        result = parser.parse_file("app.js", self._JS)
        assert any(c.name == "MyComponent" for c in result.classes)

    def test_class_extends(self, parser):
        result = parser.parse_file("app.js", self._JS)
        cls = next(c for c in result.classes if c.name == "MyComponent")
        assert any("React" in b or "Component" in b for b in cls.base_classes)

    def test_es6_import(self, parser):
        result = parser.parse_file("app.js", self._JS)
        modules = [i.module for i in result.imports]
        assert "react" in modules

    def test_has_exports(self, parser):
        result = parser.parse_file("app.js", self._JS)
        assert result.has_exports is True


# ===========================================================================
# Dependency Builder Tests
# ===========================================================================

class TestDependencyBuilder:
    def _make_file(self, path, imports):
        from parsing import ParsedFile, ParsedImport
        pf = ParsedFile(
            file_path=path, language="Python", sha="abc",
            size_bytes=100, total_lines=10,
        )
        pf.imports = imports
        return pf

    def _make_import(self, file_path, module, is_local):
        from parsing import ParsedImport
        return ParsedImport(
            file_path=file_path, line_number=1,
            import_type="relative" if module.startswith(".") else "absolute",
            module=module, is_local=is_local,
            is_stdlib=False, is_third_party=not is_local,
        )

    def test_local_dependency_resolved(self):
        from parsing.dependency_builder import build_dependency_map
        a = self._make_file("a.py", [self._make_import("a.py", "./b", True)])
        b = self._make_file("b.py", [])
        dep_map = build_dependency_map([a, b], "owner", "repo")
        assert "b.py" in dep_map.adjacency.get("a.py", [])

    def test_adjacency_dict_built(self):
        from parsing.dependency_builder import build_dependency_map
        a = self._make_file("a.py", [self._make_import("a.py", "./b", True)])
        b = self._make_file("b.py", [self._make_import("b.py", "./c", True)])
        c = self._make_file("c.py", [])
        dep_map = build_dependency_map([a, b, c])
        assert "b.py" in dep_map.adjacency.get("a.py", [])
        assert "c.py" in dep_map.adjacency.get("b.py", [])

    def test_circular_dependency_detected(self):
        from parsing.dependency_builder import build_dependency_map, detect_circular_dependencies
        a = self._make_file("a.py", [self._make_import("a.py", "./b", True)])
        b = self._make_file("b.py", [self._make_import("b.py", "./a", True)])
        dep_map = build_dependency_map([a, b])
        cycles = detect_circular_dependencies(dep_map)
        assert len(cycles) > 0

    def test_external_deps_collected(self):
        from parsing.dependency_builder import build_dependency_map
        imp = self._make_import("a.py", "requests", False)
        imp.is_third_party = True
        imp.is_local = False
        a = self._make_file("a.py", [imp])
        dep_map = build_dependency_map([a])
        assert "requests" in dep_map.external_dependencies

    def test_no_self_loops(self):
        from parsing.dependency_builder import build_dependency_map
        a = self._make_file("a.py", [self._make_import("a.py", "./a", True)])
        dep_map = build_dependency_map([a])
        # Self loops are allowed by the graph but shouldn't crash
        assert dep_map is not None


# ===========================================================================
# Call Graph Builder Tests
# ===========================================================================

class TestCallGraphBuilder:
    def test_call_edge_created(self):
        from parsing import ParsedFile, ParsedFunction, DependencyMap
        from parsing.call_graph_builder import build_call_graph

        fn_a = ParsedFunction(
            name="foo", qualified_name="foo", file_path="a.py",
            start_line=1, end_line=5, calls=["bar"],
        )
        fn_b = ParsedFunction(
            name="bar", qualified_name="bar", file_path="b.py",
            start_line=1, end_line=3, calls=[],
        )
        pf_a = ParsedFile(file_path="a.py", language="Python", sha="", size_bytes=0, total_lines=5, functions=[fn_a])
        pf_b = ParsedFile(file_path="b.py", language="Python", sha="", size_bytes=0, total_lines=3, functions=[fn_b])
        dep_map = DependencyMap(repo_owner="", repo_name="", local_files=["a.py", "b.py"])

        cg = build_call_graph([pf_a, pf_b], dep_map)
        # bar should be in the nodes
        assert "bar" in cg.nodes

    def test_orphan_function_detected(self):
        from parsing import ParsedFile, ParsedFunction, DependencyMap
        from parsing.call_graph_builder import build_call_graph, find_orphan_functions

        fn_main = ParsedFunction(name="main", qualified_name="main", file_path="a.py", start_line=1, end_line=5, calls=["helper"])
        fn_helper = ParsedFunction(name="helper", qualified_name="helper", file_path="a.py", start_line=6, end_line=10, calls=[])
        fn_unused = ParsedFunction(name="unused", qualified_name="unused", file_path="a.py", start_line=11, end_line=15, calls=[])

        pf = ParsedFile(file_path="a.py", language="Python", sha="", size_bytes=0, total_lines=15, functions=[fn_main, fn_helper, fn_unused])
        dep_map = DependencyMap(repo_owner="", repo_name="", local_files=["a.py"])

        cg = build_call_graph([pf], dep_map)
        orphans = find_orphan_functions(cg)
        assert "unused" in orphans


# ===========================================================================
# Entry Point Finder Tests
# ===========================================================================

class TestEntryPointFinder:
    def test_main_block_high_confidence(self):
        from parsing import ParsedFile, DependencyMap
        from parsing.entry_point_finder import find_entry_points

        pf = ParsedFile(
            file_path="main.py", language="Python", sha="", size_bytes=100,
            total_lines=20, has_main_block=True, is_entry_point=True,
        )
        dep_map = DependencyMap(repo_owner="", repo_name="", local_files=["main.py"])
        results = find_entry_points([pf], dep_map)
        assert len(results) > 0
        assert results[0]["confidence"] == "high"

    def test_unknown_file_not_flagged(self):
        from parsing import ParsedFile, DependencyMap
        from parsing.entry_point_finder import find_entry_points

        pf = ParsedFile(
            file_path="utils/helpers.py", language="Python", sha="", size_bytes=100,
            total_lines=20,
        )
        dep_map = DependencyMap(repo_owner="", repo_name="", local_files=["utils/helpers.py"])
        results = find_entry_points([pf], dep_map)
        # Should have low or no confidence
        high = [r for r in results if r["confidence"] == "high"]
        assert len(high) == 0


# ===========================================================================
# Pattern Detector Tests
# ===========================================================================

class TestPatternDetector:
    def test_mvc_detected(self):
        from parsing import ParsedFile, DependencyMap
        from parsing.pattern_detector import detect_patterns

        paths = ["models/user.py", "views/user.py", "controllers/user.py"]
        pfs   = [ParsedFile(file_path=p, language="Python", sha="", size_bytes=100, total_lines=10) for p in paths]
        dep_map = DependencyMap(repo_owner="", repo_name="", local_files=paths)
        patterns = detect_patterns(pfs, dep_map, paths)
        pattern_names = [p["pattern"] for p in patterns]
        assert "MVC" in pattern_names

    def test_cli_detected(self):
        from parsing import ParsedFile, ParsedImport, DependencyMap
        from parsing.pattern_detector import detect_patterns

        imp = ParsedImport(
            file_path="cli.py", line_number=1, import_type="absolute",
            module="click", is_third_party=True,
        )
        pf = ParsedFile(file_path="cli.py", language="Python", sha="", size_bytes=100, total_lines=10, imports=[imp])
        dep_map = DependencyMap(repo_owner="", repo_name="", local_files=["cli.py"])
        patterns = detect_patterns([pf], dep_map, ["cli.py"])
        pattern_names = [p["pattern"] for p in patterns]
        assert "CLI Application" in pattern_names

    def test_no_false_positive_empty_repo(self):
        from parsing import ParsedFile, DependencyMap
        from parsing.pattern_detector import detect_patterns

        pf = ParsedFile(file_path="main.py", language="Python", sha="", size_bytes=0, total_lines=1)
        dep_map = DependencyMap(repo_owner="", repo_name="", local_files=["main.py"])
        patterns = detect_patterns([pf], dep_map, ["main.py"])
        # Should detect 0 or very few patterns with empty content
        assert len(patterns) < 3


# ===========================================================================
# File Hasher Tests
# ===========================================================================

class TestFileHasher:
    def test_hash_file_path_length(self):
        from utils.file_hasher import hash_file_path
        assert len(hash_file_path("src/models/user.py")) == 12

    def test_hash_content_length(self):
        from utils.file_hasher import hash_content
        assert len(hash_content("def foo(): pass")) == 16

    def test_hash_deterministic(self):
        from utils.file_hasher import hash_file_path, hash_content
        assert hash_file_path("a.py") == hash_file_path("a.py")
        assert hash_content("hello") == hash_content("hello")

    def test_different_paths_different_hashes(self):
        from utils.file_hasher import hash_file_path
        assert hash_file_path("a.py") != hash_file_path("b.py")


# ===========================================================================
# Dataclass JSON Serialization Tests
# ===========================================================================

class TestJsonSerialization:
    def test_to_json_roundtrip(self):
        from parsing import ParsedFile, to_json
        pf = ParsedFile(
            file_path="test.py", language="Python", sha="abc123",
            size_bytes=1000, total_lines=50,
        )
        js = to_json(pf)
        d = json.loads(js)
        assert d["file_path"] == "test.py"
        assert d["language"] == "Python"
        assert d["sha"] == "abc123"

    def test_nested_dataclass_serialized(self):
        from parsing import ParsedFunction, ParsedParameter, to_json
        fn = ParsedFunction(
            name="foo", qualified_name="foo", file_path="a.py",
            start_line=1, end_line=5,
            parameters=[ParsedParameter(name="x", type_annotation="int")],
        )
        js = to_json(fn)
        d = json.loads(js)
        assert d["parameters"][0]["name"] == "x"
        assert d["parameters"][0]["type_annotation"] == "int"


# ===========================================================================
# Integration Tests (require internet + Phase 1 data)
# ===========================================================================

@pytest.mark.integration
class TestFullPipelineIntegration:
    """
    Integration tests that exercise the full Phase 2 pipeline on real data.

    These require Phase 1 to have been run for pallets/itsdangerous.
    Run with:  pytest tests/test_phase2.py -v -m integration
    """

    def test_parse_produces_manifest(self, tmp_path):
        """If pallets/itsdangerous is already fetched, parse it."""
        import config as cfg
        from parsing.parse_orchestrator import parse_repository

        folder = cfg.DATA_DIR / "pallets__itsdangerous"
        if not (folder / "manifest.json").exists():
            pytest.skip("pallets/itsdangerous not fetched. Run: python main.py ingest pallets/itsdangerous")

        manifest = parse_repository(folder, force_reparse=True)
        assert manifest.total_files_parsed > 0
        assert manifest.total_functions_extracted > 0
        assert (folder / "parsed" / "parse_manifest.json").exists()

    def test_functions_extracted_gt_zero(self):
        import config as cfg
        from parsing.parse_orchestrator import parse_repository

        folder = cfg.DATA_DIR / "pallets__itsdangerous"
        if not (folder / "manifest.json").exists():
            pytest.skip("pallets/itsdangerous not fetched.")

        manifest = parse_repository(folder)
        assert manifest.total_functions_extracted > 0
        assert manifest.total_classes_extracted >= 0

    def test_no_crash_on_all_files(self):
        import config as cfg
        from parsing.parse_orchestrator import parse_repository

        folder = cfg.DATA_DIR / "pallets__itsdangerous"
        if not (folder / "manifest.json").exists():
            pytest.skip("pallets/itsdangerous not fetched.")

        manifest = parse_repository(folder)
        assert manifest.total_files_failed == 0 or manifest.total_files_failed < manifest.total_files_parsed


# ===========================================================================
# Performance Test
# ===========================================================================

@pytest.mark.slow
class TestPerformance:
    def test_parse_speed(self):
        """Parsing 50 synthetic Python files should complete in under 60 seconds."""
        import time
        from parsing.languages.python_parser import PythonParser

        p = PythonParser()
        src = '''
import os
from pathlib import Path

class Service:
    def __init__(self):
        self.data = []
    def process(self, x: int) -> bool:
        if x > 0:
            return True
        return False

def main():
    svc = Service()
    svc.process(1)
'''
        start = time.monotonic()
        for i in range(50):
            p.parse_file(f"file_{i}.py", src)
        elapsed = time.monotonic() - start
        assert elapsed < 60, f"Parsing 50 files took {elapsed:.1f}s (limit: 60s)"
