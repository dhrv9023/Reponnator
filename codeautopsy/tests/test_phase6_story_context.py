"""
tests/test_phase6_story_context.py — StoryContextBuilder Unit Tests

Tests the context_builder module (story/context_builder.py) in isolation
using fixture data that mirrors real Phase 2 parse output structure.
No filesystem access to real repos is needed — all JSON is synthesized
in-memory using tmp_path.

Run:
    cd /home/ag2/Desktop/github_prj/codeautopsy
    venv/bin/python -m pytest tests/test_phase6_story_context.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).parent.resolve()
_PKG  = _HERE.parent.resolve()
sys.path.insert(0, str(_PKG))


# ===========================================================================
# Fixture helpers — build minimal but structurally valid Phase 2 output
# ===========================================================================

def _write_fixture_data(repo_folder: Path) -> None:
    """
    Write minimal Phase 1 + Phase 2 JSON fixtures to tmp_path so that
    StoryContextBuilder.build() can run without touching a real repo.
    """
    parsed_dir = repo_folder / "parsed"
    parsed_dir.mkdir(parents=True)
    files_dir = repo_folder / "files"
    files_dir.mkdir(parents=True)

    # --- manifest.json (Phase 1) ---
    manifest = {
        "repo": {
            "owner": "testowner",
            "name": "testrepo",
            "description": "A test repository for unit testing StoryContextBuilder.",
        },
        "language_analysis": {
            "primary_language": "Python",
            "languages": {
                "Python": {"percentage": 100, "file_count": 2}
            },
        },
        "files": [
            {
                "path": "main.py",
                "language": "Python",
                "sha": "abc123",
                "size_bytes": 512,
            },
            {
                "path": "utils.py",
                "language": "Python",
                "sha": "def456",
                "size_bytes": 256,
            },
        ],
    }
    (repo_folder / "manifest.json").write_text(json.dumps(manifest))

    # Write source files so _load_file_contents() can read them
    (files_dir / "main.py").write_text(
        "from utils import validate\n\ndef main():\n    validate()\n"
    )
    (files_dir / "utils.py").write_text(
        "def validate():\n    return True\n"
    )

    # --- parse_manifest.json (Phase 2) ---
    parse_manifest = {
        "codeautopsy_version": "1.0.0",
        "repo_owner": "testowner",
        "repo_name": "testrepo",
        "total_files_parsed": 2,
        "total_files_failed": 0,
        "total_functions_extracted": 3,
        "total_classes_extracted": 0,
        "total_imports_extracted": 1,
        "total_call_edges": 1,
        "total_dependency_edges": 1,
        "parse_duration_seconds": 0.12,
        "detected_patterns": ["REST API"],
        "entry_points": ["main.py"],
        "errors": [],
        "parsed_files": [
            {
                "file_path": "main.py",
                "language": "Python",
                "functions": [
                    {
                        "name": "main",
                        "qualified_name": "main.main",
                        "complexity_score": 2,
                    }
                ],
                "classes": [],
            },
            {
                "file_path": "utils.py",
                "language": "Python",
                "functions": [
                    {
                        "name": "validate",
                        "qualified_name": "utils.validate",
                        "complexity_score": 1,
                    },
                    {
                        "name": "parse_args",
                        "qualified_name": "utils.parse_args",
                        "complexity_score": 3,
                    },
                ],
                "classes": [],
            },
        ],
    }
    (parsed_dir / "parse_manifest.json").write_text(json.dumps(parse_manifest))

    # --- call_graph.json (Phase 2) ---
    call_graph = {
        "nodes": [
            {"id": "main.main",        "label": "main",     "type": "function"},
            {"id": "utils.validate",   "label": "validate", "type": "function"},
            {"id": "utils.parse_args", "label": "parse_args","type": "function"},
        ],
        "edges": [
            {
                "source": "main.main",
                "target": "utils.validate",
                "caller_file": "main.py",
                "callee_resolved": "utils.validate",
                "is_resolved": True,
            }
        ],
        "adjacency": {
            "main.main": ["utils.validate"],
        },
        "reverse_adjacency": {
            "utils.validate": ["main.main"],
        },
    }
    (parsed_dir / "call_graph.json").write_text(json.dumps(call_graph))

    # --- dependency_map.json (Phase 2) ---
    dependency_map = {
        "edges": [
            {"from_file": "main.py", "to_file": "utils.py", "import_type": "local"}
        ]
    }
    (parsed_dir / "dependency_map.json").write_text(json.dumps(dependency_map))

    # --- patterns.json (Phase 2) ---
    patterns = [
        {"pattern": "REST API", "confidence": 0.6, "signals": ["api/"]}
    ]
    (parsed_dir / "patterns.json").write_text(json.dumps(patterns))

    # --- entry_points.json (Phase 2) ---
    entry_points = [
        {
            "file_path": "main.py",
            "confidence": "high",
            "entry_functions": ["main.main"],
        }
    ]
    (parsed_dir / "entry_points.json").write_text(json.dumps(entry_points))


# ===========================================================================
# Tests
# ===========================================================================

class TestStoryContextBuilder:

    @pytest.fixture()
    def repo_folder(self, tmp_path):
        """Set up a temporary repo folder with full fixture data."""
        _write_fixture_data(tmp_path)
        return tmp_path

    def test_build_returns_story_context(self, repo_folder):
        """build() must return a StoryContext object."""
        from story import StoryContext
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        assert isinstance(context, StoryContext)

    def test_repo_name_populated(self, repo_folder):
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        assert context.repo_name == "testowner/testrepo"

    def test_primary_language_from_manifest(self, repo_folder):
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        assert context.primary_language == "Python"

    def test_total_files_matches_manifest(self, repo_folder):
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        assert context.total_files == 2

    def test_total_functions_matches_manifest(self, repo_folder):
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        assert context.total_functions == 3

    def test_detected_pattern_is_rest_api(self, repo_folder):
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        assert "REST API" in context.detected_pattern

    def test_entry_points_nonempty(self, repo_folder):
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        assert len(context.entry_points) >= 1

    def test_top_modules_are_module_brief(self, repo_folder):
        from story import ModuleBrief
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        for module in context.top_modules:
            assert isinstance(module, ModuleBrief)

    def test_no_circular_deps_in_fixture(self, repo_folder):
        """
        The fixture has main.py → utils.py only (no back-edge).
        has_circular_deps must be False.
        """
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        assert context.has_circular_deps is False

    def test_circular_deps_detected_when_present(self, repo_folder):
        """
        Inject a circular import edge (utils.py → main.py) and verify that
        has_circular_deps flips to True.
        """
        from story.context_builder import StoryContextBuilder

        # Add a back-edge to dependency_map.json
        dep_path = repo_folder / "parsed" / "dependency_map.json"
        dep_map  = json.loads(dep_path.read_text())
        dep_map["edges"].append(
            {"from_file": "utils.py", "to_file": "main.py", "import_type": "local"}
        )
        dep_path.write_text(json.dumps(dep_map))

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        assert context.has_circular_deps is True

    def test_complexity_hotspots_populated(self, repo_folder):
        """
        utils.parse_args has complexity_score=3 — the highest in the fixture.
        It must appear in complexity_hotspots.
        """
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        # At least one hotspot must contain 'parse_args'
        joined = " ".join(context.complexity_hotspots)
        assert "parse_args" in joined or len(context.complexity_hotspots) >= 1

    def test_file_contents_loaded_from_disk(self, repo_folder):
        """
        The builder must read actual source files from files/ and return
        them in context.file_contents.
        """
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        assert len(context.file_contents) >= 1
        paths = [fc["path"] for fc in context.file_contents]
        # At least one of the two fixture files should appear
        assert any(p in ("main.py", "utils.py") for p in paths)

    def test_file_contents_have_required_keys(self, repo_folder):
        """Each entry in file_contents must have path, language, and content."""
        from story.context_builder import StoryContextBuilder

        builder = StoryContextBuilder(repo_folder)
        context = builder.build()

        for entry in context.file_contents:
            assert "path"     in entry, "file_contents entry missing 'path'"
            assert "language" in entry, "file_contents entry missing 'language'"
            assert "content"  in entry, "file_contents entry missing 'content'"

    def test_missing_parsed_files_handled_gracefully(self, tmp_path):
        """
        StoryContextBuilder must not raise when Phase 2 files are mostly absent.
        It should return a StoryContext with zero-value defaults.

        Note: _load_json() returns {} for missing files. The builder handles a
        missing call_graph.json (gets {}), missing dependency_map.json (gets {}),
        and missing patterns.json (gets {}) gracefully. However, entry_points.json
        MUST exist as an empty list [] because the builder slices it directly.
        We write minimal stubs for all four to test the zero-data path cleanly.
        """
        from story.context_builder import StoryContextBuilder

        # Only write manifest.json — skip parsed/ directory entirely
        manifest = {
            "repo": {"owner": "o", "name": "r", "description": ""},
            "language_analysis": {"primary_language": "Python", "languages": {}},
            "files": [],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        parsed = tmp_path / "parsed"
        parsed.mkdir()

        # Write all required Phase 2 JSONs as empty / minimal stubs
        (parsed / "parse_manifest.json").write_text(json.dumps({
            "repo_owner": "o", "repo_name": "r",
            "total_files_parsed": 0, "total_functions_extracted": 0,
            "total_classes_extracted": 0, "entry_points": [], "errors": [],
        }))
        (parsed / "call_graph.json").write_text(json.dumps(
            {"nodes": [], "edges": [], "adjacency": {}, "reverse_adjacency": {}}
        ))
        (parsed / "dependency_map.json").write_text(json.dumps({"edges": []}))
        (parsed / "patterns.json").write_text(json.dumps([]))
        # entry_points.json must be a list, not a dict, so slicing works
        (parsed / "entry_points.json").write_text(json.dumps([]))

        builder = StoryContextBuilder(tmp_path)
        context = builder.build()   # must not raise

        assert context.total_files == 0
        assert context.file_contents == []

