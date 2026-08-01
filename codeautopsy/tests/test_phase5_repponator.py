"""
tests/test_phase5_repponator.py — Story Engine & Repponator Tests

Tests Phase 7 (story generation) and the job manager's new SQLite persistence.
No LLM calls are made — all LLM interactions are mocked.

Run:
    cd /home/ag2/Desktop/github_prj/codeautopsy
    venv/bin/python -m pytest tests/test_phase5_repponator.py -v

Coverage targets
----------------
* Repponator._generate_fallback_story()   — no LLM required, pure logic
* Repponator._parse_response()            — JSON extraction and validation
* Repponator._build_user_prompt()         — prompt construction, no network
* JobManager (SQLite)                     — persistence across re-instantiation
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — tests run from the repo root or the codeautopsy/ directory.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent.resolve()
_PKG  = _HERE.parent.resolve()   # codeautopsy/
sys.path.insert(0, str(_PKG))


# ===========================================================================
# Fixtures
# ===========================================================================

def _make_story_context(**overrides):
    """
    Return a minimal StoryContext that satisfies all fields without touching
    the filesystem. Values mirror what StoryContextBuilder.build() would produce
    for a small single-file repo.
    """
    from story import ModuleBrief, StoryContext

    defaults = dict(
        repo_name="testowner/testrepo",
        primary_language="Python",
        total_files=4,
        total_functions=12,
        total_classes=2,
        detected_pattern="REST API",
        entry_points=["main.py"],
        core_utilities=["utils.py"],
        top_modules=[
            ModuleBrief(
                filename="main.py",
                function_names=["run", "handle_request"],
                class_names=[],
                called_by_count=0,
                calls_count=5,
            ),
            ModuleBrief(
                filename="utils.py",
                function_names=["parse_args", "validate"],
                class_names=["Config"],
                called_by_count=3,
                calls_count=1,
            ),
        ],
        has_circular_deps=False,
        complexity_hotspots=["main.py::handle_request"],
        architectural_signals=["has_api_routes", "has_config"],
        repo_description="A test repository for unit testing.",
        languages_breakdown="Python (100%)",
        file_contents=[],
    )
    defaults.update(overrides)
    return StoryContext(**defaults)


def _make_repponator_no_llm(tmp_path: Path):
    """
    Construct a Repponator instance without triggering its __init__ LLM setup.
    Sets repo_folder and output_folder to a temp directory. llm_client is a
    MagicMock so any method call on it is safe and inspectable.
    """
    from story.repponator import Repponator

    r = object.__new__(Repponator)         # bypass __init__
    r.repo_folder   = tmp_path
    r.output_folder = tmp_path / "story"
    r.llm_client    = MagicMock()
    return r


# ===========================================================================
# 1. Repponator._generate_fallback_story()
# ===========================================================================

class TestRepponatorFallback:
    """
    The fallback story path is triggered for very small repos (< 5 files)
    when the main LLM call fails. It must return a valid ArchitecturalStory
    and StoryMetadata without making any LLM call.
    """

    def test_fallback_returns_architectural_story_type(self, tmp_path):
        from story import ArchitecturalStory, StoryMetadata
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context(total_files=3)

        story, meta = r._generate_fallback_story(context)

        assert isinstance(story, ArchitecturalStory), (
            "_generate_fallback_story must return an ArchitecturalStory"
        )
        assert isinstance(meta, StoryMetadata), (
            "_generate_fallback_story must return a StoryMetadata"
        )

    def test_fallback_story_has_all_required_fields(self, tmp_path):
        """Every field of ArchitecturalStory must be populated (non-empty)."""
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context(total_files=3)

        story, _ = r._generate_fallback_story(context)

        required_str_fields = [
            "primary_commitment", "origin_story", "how_it_flows",
            "design_tensions", "founding_metaphor", "verdict",
        ]
        for field_name in required_str_fields:
            value = getattr(story, field_name)
            assert value and value.strip(), (
                f"ArchitecturalStory.{field_name} must be non-empty in fallback"
            )

    def test_fallback_does_not_call_llm(self, tmp_path):
        """_generate_fallback_story must never invoke the LLM client."""
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context(total_files=2)

        r._generate_fallback_story(context)

        r.llm_client.generate.assert_not_called()

    def test_fallback_key_modules_built_from_context(self, tmp_path):
        """key_modules list should reflect the top_modules in the context."""
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context(total_files=3)

        story, _ = r._generate_fallback_story(context)

        # The fallback uses context.top_modules[:3] — we provided 2.
        assert len(story.key_modules) <= 3
        assert len(story.key_modules) >= 1

    def test_fallback_metadata_model_is_fallback(self, tmp_path):
        """StoryMetadata.model_used must indicate the fallback path."""
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context(total_files=2)

        _, meta = r._generate_fallback_story(context)

        assert "fallback" in meta.model_used.lower(), (
            "model_used must contain 'fallback' so callers can detect it"
        )

    def test_fallback_saves_story_file(self, tmp_path):
        """_generate_fallback_story must persist story_output.json to disk."""
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context(total_files=2)

        r._generate_fallback_story(context)

        story_file = tmp_path / "story" / "story_output.json"
        assert story_file.exists(), (
            "story_output.json must be written by _generate_fallback_story"
        )
        # File must be valid JSON
        with story_file.open() as f:
            data = json.load(f)
        assert "primary_commitment" in data


# ===========================================================================
# 2. Repponator._parse_response()
# ===========================================================================

class TestRepponatorParseResponse:
    """
    _parse_response() extracts JSON from the LLM text output and validates
    that all required story fields are present. It must handle:
    - Plain JSON strings
    - JSON wrapped in ```json ... ``` markdown fences
    - Missing required fields (raises ValueError)
    - Invalid JSON (raises ValueError)
    """

    _VALID_STORY_DICT = {
        "project_summary":    "A test project.",
        "tech_stack":         ["FastAPI"],
        "primary_commitment": "Commit to simplicity.",
        "origin_story":       "Built for testing.",
        "how_it_flows":       "Request → handler → response.",
        "key_modules": [
            {
                "module_id":   "main.py",
                "role_title":  "The Gateway",
                "explanation": "Entry point. Handles routing.",
            }
        ],
        "design_tensions":  "Speed vs. correctness.",
        "founding_metaphor": "A well-oiled machine.",
        "verdict":          "Solid but needs tests.",
    }

    def test_parse_plain_valid_json(self, tmp_path):
        from story.repponator import Repponator
        r = _make_repponator_no_llm(tmp_path)

        raw    = json.dumps(self._VALID_STORY_DICT)
        result = r._parse_response(raw)

        assert result["primary_commitment"] == "Commit to simplicity."

    def test_parse_json_in_markdown_fence(self, tmp_path):
        """LLMs often wrap JSON in ```json ... ``` — this must be stripped."""
        from story.repponator import Repponator
        r = _make_repponator_no_llm(tmp_path)

        raw    = f"```json\n{json.dumps(self._VALID_STORY_DICT)}\n```"
        result = r._parse_response(raw)

        assert "primary_commitment" in result

    def test_parse_json_in_bare_markdown_fence(self, tmp_path):
        """Some models use ``` without 'json' label."""
        from story.repponator import Repponator
        r = _make_repponator_no_llm(tmp_path)

        raw    = f"```\n{json.dumps(self._VALID_STORY_DICT)}\n```"
        result = r._parse_response(raw)

        assert "primary_commitment" in result

    def test_parse_missing_required_field_raises(self, tmp_path):
        """If any required field is absent, ValueError must be raised."""
        from story.repponator import Repponator
        r = _make_repponator_no_llm(tmp_path)

        incomplete = dict(self._VALID_STORY_DICT)
        incomplete.pop("verdict")  # remove a required field

        with pytest.raises(ValueError, match="Missing required field"):
            r._parse_response(json.dumps(incomplete))

    def test_parse_invalid_json_raises(self, tmp_path):
        """Completely malformed JSON must raise ValueError."""
        from story.repponator import Repponator
        r = _make_repponator_no_llm(tmp_path)

        with pytest.raises(ValueError):
            r._parse_response("{ this is not valid JSON }")

    def test_parse_all_required_fields_present(self, tmp_path):
        """All seven required fields must be present in a valid response."""
        from story.repponator import Repponator
        r = _make_repponator_no_llm(tmp_path)

        result = r._parse_response(json.dumps(self._VALID_STORY_DICT))

        required = [
            "primary_commitment", "origin_story", "how_it_flows",
            "key_modules", "design_tensions", "founding_metaphor", "verdict",
        ]
        for field_name in required:
            assert field_name in result, f"Field '{field_name}' missing from parsed result"


# ===========================================================================
# 3. Repponator._build_user_prompt()
# ===========================================================================

class TestRepponatorPromptBuilder:
    """
    _build_user_prompt() constructs the user prompt from a StoryContext.
    No network calls are made. Tests check structural properties of the
    output string.
    """

    def test_prompt_contains_repo_name(self, tmp_path):
        from story.repponator import Repponator
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context(repo_name="pallets/flask")

        prompt = r._build_user_prompt(context)

        assert "pallets/flask" in prompt

    def test_prompt_contains_detected_pattern(self, tmp_path):
        from story.repponator import Repponator
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context(detected_pattern="MVC")

        prompt = r._build_user_prompt(context)

        assert "MVC" in prompt

    def test_prompt_contains_json_schema_instruction(self, tmp_path):
        """The prompt must instruct the LLM to return JSON."""
        from story.repponator import Repponator
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context()

        prompt = r._build_user_prompt(context)

        assert "JSON" in prompt or "json" in prompt

    def test_prompt_contains_source_code_when_provided(self, tmp_path):
        """If file_contents is non-empty, the source must appear in the prompt."""
        from story.repponator import Repponator
        r = _make_repponator_no_llm(tmp_path)
        context = _make_story_context(
            file_contents=[
                {"path": "app.py", "language": "Python", "content": "def main(): pass"}
            ]
        )

        prompt = r._build_user_prompt(context)

        assert "app.py" in prompt
        assert "def main(): pass" in prompt

    def test_prompt_omits_source_section_when_no_files(self, tmp_path):
        """An empty file_contents list must not add a populated source code block."""
        from story.repponator import Repponator
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context(file_contents=[])

        prompt = r._build_user_prompt(context)

        # The template preamble mentions SOURCE CODE in the instruction text even
        # when no files are provided; but the actual file block ("=== path ===")
        # must be absent when file_contents is empty.
        assert "=== " not in prompt, (
            "No file blocks (=== path ===) should appear when file_contents==[]"
        )

    def test_prompt_is_nonempty_string(self, tmp_path):
        from story.repponator import Repponator
        r       = _make_repponator_no_llm(tmp_path)
        context = _make_story_context()

        prompt = r._build_user_prompt(context)

        assert isinstance(prompt, str) and len(prompt) > 100


# ===========================================================================
# 4. JobManager — SQLite persistence
# ===========================================================================

class TestJobManagerSQLite:
    """
    Verifies that the new SQLite-backed JobManager persists data across
    re-instantiation — the core correctness property that the old in-memory
    dict could not provide.

    Each test gets an isolated temp DB path. We inject it by importing the
    module via sys.modules (which gives the actual module object, not the
    singleton instance) and replacing _DB_PATH with monkeypatch.
    """

    @pytest.fixture(autouse=True)
    def _isolated_db(self, tmp_path, monkeypatch):
        """
        Redirect the SQLite DB to a fresh temp file for each test.

        We use sys.modules to get the actual module object — the `import X as Y`
        alias in the fixture body would also work, but sys.modules is unambiguous
        and avoids any confusion with the module-level `job_manager` singleton.
        """
        import importlib
        import sys

        # Ensure the module is imported
        import api.services.job_manager  # noqa: F401

        mod = sys.modules["api.services.job_manager"]
        monkeypatch.setattr(mod, "_DB_PATH", tmp_path / "test_jobs.db")
        yield

    def test_job_persists_across_re_instantiation(self):
        """
        The key invariant: a job created by one JobManager instance must be
        readable by a freshly-created second instance (simulating a server restart).
        """
        from api.services.job_manager import JobManager

        async def _run():
            mgr1   = JobManager()
            job_id = await mgr1.create_job(phase="ingest", repo_key="owner__repo")

            # Simulate server restart — new Python object, same DB file
            mgr2 = JobManager()
            job  = await mgr2.get_job(job_id)

            assert job is not None, "Job must survive re-instantiation"
            assert job.job_id == job_id
            assert job.repo_key == "owner__repo"
            assert job.phase == "ingest"

        asyncio.run(_run())

    def test_create_job_returns_unique_ids(self):
        from api.services.job_manager import JobManager

        async def _run():
            mgr = JobManager()
            id1 = await mgr.create_job(phase="parse", repo_key="a__b")
            id2 = await mgr.create_job(phase="parse", repo_key="a__b")
            assert id1 != id2

        asyncio.run(_run())

    def test_mark_complete_updates_status(self):
        from api.services.job_manager import JobManager, JobStatus

        async def _run():
            mgr    = JobManager()
            job_id = await mgr.create_job(phase="chunk", repo_key="x__y")
            await mgr.mark_complete(job_id)

            job = await mgr.get_job(job_id)
            assert job.status == JobStatus.COMPLETE
            assert job.progress_percent == 100
            assert job.completed_at is not None

        asyncio.run(_run())

    def test_mark_failed_stores_error_message(self):
        from api.services.job_manager import JobManager, JobStatus

        async def _run():
            mgr    = JobManager()
            job_id = await mgr.create_job(phase="qa", repo_key="err__repo")
            await mgr.mark_failed(job_id, "Out of memory during embedding")

            job = await mgr.get_job(job_id)
            assert job.status == JobStatus.FAILED
            assert "Out of memory" in job.error

        asyncio.run(_run())

    def test_update_progress_clamps_to_0_100(self):
        from api.services.job_manager import JobManager

        async def _run():
            mgr    = JobManager()
            job_id = await mgr.create_job(phase="story", repo_key="c__d")

            await mgr.update_progress(job_id, percent=150, step="overflow test")
            job = await mgr.get_job(job_id)
            assert job.progress_percent == 100

            await mgr.update_progress(job_id, percent=-10)
            job = await mgr.get_job(job_id)
            assert job.progress_percent == 0

        asyncio.run(_run())

    def test_list_jobs_filters_by_repo_key(self):
        from api.services.job_manager import JobManager

        async def _run():
            mgr = JobManager()
            await mgr.create_job(phase="ingest", repo_key="owner__repo_a")
            await mgr.create_job(phase="ingest", repo_key="owner__repo_a")
            await mgr.create_job(phase="ingest", repo_key="owner__repo_b")

            jobs_a = await mgr.list_jobs(repo_key="owner__repo_a")
            jobs_b = await mgr.list_jobs(repo_key="owner__repo_b")

            assert len(jobs_a) == 2
            assert len(jobs_b) == 1

        asyncio.run(_run())

    def test_check_running_job_detects_active_job(self):
        from api.services.job_manager import JobManager

        async def _run():
            mgr    = JobManager()
            job_id = await mgr.create_job(phase="parse", repo_key="owner__repo")
            await mgr.start_job(job_id)

            found = await mgr.check_running_job(phase="parse", repo_key="owner__repo")
            assert found == job_id

        asyncio.run(_run())

    def test_check_running_job_returns_none_after_completion(self):
        from api.services.job_manager import JobManager

        async def _run():
            mgr    = JobManager()
            job_id = await mgr.create_job(phase="parse", repo_key="owner__repo")
            await mgr.start_job(job_id)
            await mgr.mark_complete(job_id)

            found = await mgr.check_running_job(phase="parse", repo_key="owner__repo")
            assert found is None

        asyncio.run(_run())

    def test_get_job_returns_none_for_unknown_id(self):
        from api.services.job_manager import JobManager

        async def _run():
            mgr = JobManager()
            job = await mgr.get_job("00000000-0000-0000-0000-000000000000")
            assert job is None

        asyncio.run(_run())

    def test_cleanup_removes_old_completed_jobs(self):
        """Cleanup must not touch QUEUED/RUNNING jobs, only terminal states."""
        import sys
        import aiosqlite
        from datetime import datetime, timedelta
        from api.services.job_manager import JobManager, JobStatus

        # Get the actual module object (not the singleton) outside the async fn
        jm_mod = sys.modules["api.services.job_manager"]

        async def _run():
            mgr    = JobManager()
            job_id = await mgr.create_job(phase="ingest", repo_key="old__repo")
            await mgr.mark_complete(job_id)

            # Backdate created_at to 48 hours ago directly in SQLite
            old_ts  = (datetime.now() - timedelta(hours=48)).isoformat()
            db_path = jm_mod._DB_PATH
            async with aiosqlite.connect(db_path) as conn:
                await conn.execute(
                    "UPDATE jobs SET created_at=? WHERE job_id=?",
                    (old_ts, job_id),
                )
                await conn.commit()

            await mgr.cleanup_old_jobs(max_age_hours=24)

            job = await mgr.get_job(job_id)
            assert job is None, "Old completed job must be deleted by cleanup"

        asyncio.run(_run())


