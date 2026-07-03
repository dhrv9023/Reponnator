"""
tests/test_phase1.py — Phase 1 Unit and Integration Tests

Run fast tests only:
    cd codeautopsy && python -m pytest tests/test_phase1.py -v

Run including integration tests (requires internet + optional GitHub token):
    cd codeautopsy && python -m pytest tests/test_phase1.py -v -m integration
"""

import sys
from pathlib import Path

import pytest

# Ensure the package root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ===========================================================================
# url_parser tests
# ===========================================================================

class TestURLParser:
    """Tests for ingestion.url_parser.parse_github_url."""

    def test_https_basic(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("https://github.com/pallets/flask")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"
        assert r.branch is None
        assert r.normalized_url == "https://github.com/pallets/flask"

    def test_https_trailing_slash(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("https://github.com/pallets/flask/")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"

    def test_https_git_suffix(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("https://github.com/pallets/flask.git")
        assert r.repo_name == "flask"

    def test_https_tree_branch(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("https://github.com/pallets/flask/tree/main")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"
        assert r.branch == "main"

    def test_https_tree_branch_subfolder(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("https://github.com/pallets/flask/tree/main/src")
        assert r.branch == "main"
        assert r.repo_name == "flask"

    def test_https_blob_file(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("https://github.com/pallets/flask/blob/main/README.md")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"
        assert r.branch == "main"

    def test_http_protocol(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("http://github.com/pallets/flask")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"

    def test_no_protocol(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("github.com/pallets/flask")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"

    def test_ssh_format(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("git@github.com:pallets/flask.git")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"
        assert r.branch is None

    def test_shorthand_format(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("pallets/flask")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"

    def test_uppercase_normalised(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("https://github.com/Pallets/Flask")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"

    def test_url_with_query_params(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("https://github.com/pallets/flask?tab=readme")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"

    def test_ssh_without_dotgit(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("git@github.com:pallets/flask")
        assert r.owner == "pallets"
        assert r.repo_name == "flask"

    def test_empty_input_raises(self):
        from ingestion.url_parser import parse_github_url
        with pytest.raises(ValueError, match="No URL provided"):
            parse_github_url("")

    def test_whitespace_only_raises(self):
        from ingestion.url_parser import parse_github_url
        with pytest.raises(ValueError):
            parse_github_url("   ")

    def test_non_github_url_raises(self):
        from ingestion.url_parser import parse_github_url
        with pytest.raises(ValueError, match="not GitHub"):
            parse_github_url("https://gitlab.com/pallets/flask")

    def test_github_user_page_raises(self):
        from ingestion.url_parser import parse_github_url
        with pytest.raises(ValueError, match="not a repository"):
            parse_github_url("https://github.com/pallets")

    def test_random_string_raises(self):
        from ingestion.url_parser import parse_github_url
        with pytest.raises(ValueError):
            parse_github_url("not-a-valid-url-at-all!!!")

    def test_branch_extracted_correctly(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("https://github.com/owner/repo/tree/develop")
        assert r.branch == "develop"

    def test_repo_with_dots_and_hyphens(self):
        from ingestion.url_parser import parse_github_url
        r = parse_github_url("owner/my-repo.js")
        assert r.repo_name == "my-repo.js"

    def test_original_url_preserved(self):
        from ingestion.url_parser import parse_github_url
        raw = "https://github.com/pallets/flask/tree/main"
        r = parse_github_url(raw)
        assert r.original_url == raw


# ===========================================================================
# file_filter tests
# ===========================================================================

class TestFileFilter:
    """Tests for ingestion.file_filter."""

    def test_node_modules_filtered(self):
        from ingestion.file_filter import should_fetch_file
        ok, reason = should_fetch_file("src/node_modules/lodash/index.js", 1024)
        assert not ok
        assert "node_modules" in reason

    def test_nested_ignored_dir_filtered(self):
        from ingestion.file_filter import should_fetch_file
        ok, reason = should_fetch_file("project/__pycache__/module.pyc", 512)
        assert not ok

    def test_python_file_accepted(self):
        from ingestion.file_filter import should_fetch_file
        ok, reason = should_fetch_file("src/app.py", 1024)
        assert ok
        assert reason == "ok"

    def test_min_js_rejected(self):
        from ingestion.file_filter import should_fetch_file
        ok, reason = should_fetch_file("assets/bundle.min.js", 50000)
        assert not ok
        assert "min.js" in reason.lower() or "pattern" in reason.lower()

    def test_markdown_rejected(self):
        from ingestion.file_filter import should_fetch_file
        ok, reason = should_fetch_file("README.md", 2048)
        assert not ok
        assert "extension" in reason

    def test_file_over_limit_rejected(self):
        from ingestion.file_filter import should_fetch_file
        from config import MAX_FILE_SIZE_BYTES
        ok, reason = should_fetch_file("bigfile.py", MAX_FILE_SIZE_BYTES + 1)
        assert not ok
        assert "too large" in reason

    def test_file_at_limit_accepted(self):
        from ingestion.file_filter import should_fetch_file
        from config import MAX_FILE_SIZE_BYTES
        ok, _ = should_fetch_file("file.py", MAX_FILE_SIZE_BYTES)
        assert ok

    def test_typescript_accepted(self):
        from ingestion.file_filter import should_fetch_file
        ok, _ = should_fetch_file("src/index.ts", 4096)
        assert ok

    def test_tsx_accepted(self):
        from ingestion.file_filter import should_fetch_file
        ok, _ = should_fetch_file("components/App.tsx", 2048)
        assert ok

    def test_go_file_accepted(self):
        from ingestion.file_filter import should_fetch_file
        ok, _ = should_fetch_file("main.go", 3000)
        assert ok

    def test_lock_file_rejected(self):
        from ingestion.file_filter import should_fetch_file
        ok, reason = should_fetch_file("package-lock.json", 10000)
        assert not ok

    def test_binary_content_detected(self):
        from ingestion.file_filter import is_likely_binary
        # Null-byte-heavy content
        binary_content = "\x00" * 100 + "some text"
        assert is_likely_binary(binary_content)

    def test_normal_python_not_binary(self):
        from ingestion.file_filter import is_likely_binary
        python_code = "def hello():\n    print('hello world')\n"
        assert not is_likely_binary(python_code)

    def test_empty_content_not_binary(self):
        from ingestion.file_filter import is_likely_binary
        assert not is_likely_binary("")

    def test_get_file_language_python(self):
        from ingestion.file_filter import get_file_language
        assert get_file_language("src/app.py") == "Python"

    def test_get_file_language_typescript(self):
        from ingestion.file_filter import get_file_language
        assert get_file_language("src/index.ts") == "TypeScript"

    def test_get_file_language_unknown(self):
        from ingestion.file_filter import get_file_language
        assert get_file_language("README.md") is None

    def test_case_insensitive_extension(self):
        from ingestion.file_filter import is_supported_code_file
        assert is_supported_code_file("Script.PY")

    def test_is_ignored_directory_exact(self):
        from ingestion.file_filter import is_ignored_directory
        assert is_ignored_directory("venv/lib/python3.11/site-packages/flask/__init__.py")

    def test_is_ignored_directory_false_for_clean(self):
        from ingestion.file_filter import is_ignored_directory
        assert not is_ignored_directory("src/models/user.py")

    def test_yarn_lock_rejected(self):
        from ingestion.file_filter import should_fetch_file
        ok, reason = should_fetch_file("yarn.lock", 5000)
        assert not ok


# ===========================================================================
# language_detector tests
# ===========================================================================

class TestLanguageDetector:
    """Tests for ingestion.language_detector.detect_languages."""

    def _make_file_list(self, specs: list[tuple[str, int]]) -> list[dict]:
        return [{"path": p, "size": s} for p, s in specs]

    def test_primary_python(self):
        from ingestion.language_detector import detect_languages
        files = self._make_file_list([
            ("app.py", 10000),
            ("models.py", 8000),
            ("utils.py", 5000),
            ("index.js", 1000),
        ])
        result = detect_languages(files)
        assert result["primary_language"] == "Python"

    def test_empty_list(self):
        from ingestion.language_detector import detect_languages
        result = detect_languages([])
        assert result["primary_language"] == "Unknown"
        assert result["languages"] == {}
        assert not result["is_monorepo"]

    def test_multiple_primary_when_close(self):
        from ingestion.language_detector import detect_languages
        # Python 50%, JS 48% — should flag as multiple primary
        files = self._make_file_list([
            ("app.py", 5000),
            ("index.js", 4800),
        ])
        result = detect_languages(files)
        assert result["has_multiple_primary_languages"]

    def test_no_multiple_primary_when_far_apart(self):
        from ingestion.language_detector import detect_languages
        files = self._make_file_list([
            ("app.py", 10000),
            ("index.js", 1000),
        ])
        result = detect_languages(files)
        assert not result["has_multiple_primary_languages"]

    def test_monorepo_detection(self):
        from ingestion.language_detector import detect_languages
        # 3 languages each ≥ 15%
        files = self._make_file_list([
            ("app.py", 4000),
            ("server.go", 3500),
            ("frontend.ts", 3000),
        ])
        result = detect_languages(files)
        assert result["is_monorepo"]

    def test_not_monorepo_when_one_dominant(self):
        from ingestion.language_detector import detect_languages
        files = self._make_file_list([
            ("app.py", 9000),
            ("server.go", 500),
            ("util.ts", 500),
        ])
        result = detect_languages(files)
        assert not result["is_monorepo"]

    def test_percentages_sum_to_100(self):
        from ingestion.language_detector import detect_languages
        files = self._make_file_list([
            ("a.py", 3000),
            ("b.js", 3000),
            ("c.ts", 4000),
        ])
        result = detect_languages(files)
        total_pct = sum(v["percentage"] for v in result["languages"].values())
        assert abs(total_pct - 100.0) < 1.0  # allow minor float rounding

    def test_unrecognised_files_ignored(self):
        from ingestion.language_detector import detect_languages
        files = self._make_file_list([
            ("README.md", 5000),
            ("app.py", 3000),
        ])
        result = detect_languages(files)
        assert "Python" in result["languages"]
        assert len(result["languages"]) == 1

    def test_total_bytes_correct(self):
        from ingestion.language_detector import detect_languages
        files = self._make_file_list([
            ("app.py", 3000),
            ("utils.py", 2000),
        ])
        result = detect_languages(files)
        assert result["total_bytes"] == 5000

    def test_total_files_correct(self):
        from ingestion.language_detector import detect_languages
        files = self._make_file_list([
            ("a.py", 1000),
            ("b.py", 1000),
            ("c.go", 1000),
        ])
        result = detect_languages(files)
        assert result["total_files"] == 3


# ===========================================================================
# storage tests (in-memory / temp-dir)
# ===========================================================================

class TestStorage:
    """Tests for ingestion.storage using temporary directories."""

    def _make_result(self, tmp_path):
        from ingestion.file_fetcher import FetchResult, FetchedFile, SkippedFile
        return FetchResult(
            owner="testowner",
            repo_name="testrepo",
            branch="main",
            repo_metadata={
                "name": "testrepo", "owner": "testowner",
                "description": "Test", "stars": 0, "forks": 0,
                "primary_language": "Python", "topics": [],
                "license": "MIT", "created_at": None, "updated_at": None,
                "is_fork": False, "is_archived": False,
                "has_wiki": False, "open_issues_count": 0,
                "size_kb": 10, "homepage": "", "visibility": "public",
                "default_branch": "main",
            },
            files=[
                FetchedFile(
                    path="src/app.py",
                    language="Python",
                    content="print('hello')\n",
                    size_bytes=16,
                    sha="abc123",
                )
            ],
            skipped_files=[
                SkippedFile(
                    path="node_modules/lodash/index.js",
                    reason="ignored directory: node_modules",
                    size_bytes=54000,
                )
            ],
            language_analysis={
                "primary_language": "Python",
                "languages": {"Python": {"file_count": 1, "byte_count": 16, "percentage": 100.0}},
                "is_monorepo": False,
                "has_multiple_primary_languages": False,
                "total_files": 1,
                "total_bytes": 16,
            },
            total_files_in_repo=2,
            total_files_fetched=1,
            total_files_skipped=1,
            total_bytes_fetched=16,
            fetch_duration_seconds=1.23,
            fetch_timestamp="2024-01-01T00:00:00Z",
            errors=[],
            warnings=[],
        )

    def test_save_creates_manifest(self, tmp_path):
        from ingestion.storage import save_fetch_result, load_manifest
        result = self._make_result(tmp_path)
        repo_folder = save_fetch_result(result, data_dir=tmp_path)
        manifest = load_manifest(repo_folder)
        assert manifest["repo"]["owner"] == "testowner"
        assert manifest["repo"]["name"] == "testrepo"

    def test_save_creates_files(self, tmp_path):
        from ingestion.storage import save_fetch_result
        result = self._make_result(tmp_path)
        repo_folder = save_fetch_result(result, data_dir=tmp_path)
        expected = repo_folder / "files" / "src" / "app.py"
        assert expected.exists()
        assert expected.read_text() == "print('hello')\n"

    def test_manifest_has_required_keys(self, tmp_path):
        from ingestion.storage import save_fetch_result, load_manifest
        result = self._make_result(tmp_path)
        repo_folder = save_fetch_result(result, data_dir=tmp_path)
        manifest = load_manifest(repo_folder)
        required = {"codeautopsy_version", "fetch_timestamp", "repo",
                    "ingestion_stats", "language_analysis", "files", "skipped_files"}
        assert required.issubset(manifest.keys())

    def test_rotate_old_folder(self, tmp_path):
        from ingestion.storage import save_fetch_result
        result = self._make_result(tmp_path)
        # First save
        repo_folder = save_fetch_result(result, data_dir=tmp_path)
        # Second save should rotate the old one
        repo_folder2 = save_fetch_result(result, data_dir=tmp_path)
        # The original folder now has a backup sibling
        backups = [d for d in tmp_path.iterdir()
                   if d.is_dir() and "testowner__testrepo__" in d.name]
        assert len(backups) >= 1

    def test_list_fetched_repos(self, tmp_path):
        from ingestion.storage import save_fetch_result, list_fetched_repos
        result = self._make_result(tmp_path)
        save_fetch_result(result, data_dir=tmp_path)
        repos = list_fetched_repos(data_dir=tmp_path)
        assert len(repos) >= 1
        assert repos[0]["full_name"] == "testowner/testrepo"

    def test_load_manifest_missing_raises(self, tmp_path):
        from ingestion.storage import load_manifest
        with pytest.raises(FileNotFoundError):
            load_manifest(tmp_path / "nonexistent")


# ===========================================================================
# Integration tests (require internet; skipped in CI unless -m integration)
# ===========================================================================

@pytest.mark.integration
class TestIntegration:
    """
    End-to-end integration tests.

    These tests make real network calls to the GitHub API.
    Run with: pytest -m integration
    """

    def test_fetch_small_public_repo(self, tmp_path):
        """Fetch a small well-known repo and verify the manifest structure."""
        import os
        from dotenv import load_dotenv
        from pathlib import Path as P
        load_dotenv(P(__file__).parent.parent / ".env")

        from ingestion.github_client import GitHubClient
        from ingestion.file_fetcher import fetch_repository
        from ingestion.storage import save_fetch_result, load_manifest

        token  = os.getenv("GITHUB_TOKEN") or None
        client = GitHubClient(token=token)

        # kennethreitz/records is a small, stable Python repo
        result = fetch_repository(client, "kennethreitz", "records")

        assert result.owner == "kennethreitz"
        assert result.repo_name == "records"
        assert result.total_files_fetched > 0
        assert result.language_analysis["primary_language"] == "Python"

        repo_folder = save_fetch_result(result, data_dir=tmp_path)
        manifest    = load_manifest(repo_folder)

        # Structural checks
        assert manifest["repo"]["owner"] == "kennethreitz"
        assert len(manifest["files"]) > 0
        assert (repo_folder / "files").is_dir()

    def test_invalid_repo_raises(self):
        """Fetching a non-existent repo should raise RepoNotFoundError."""
        from ingestion.github_client import GitHubClient, RepoNotFoundError
        from ingestion.file_fetcher import fetch_repository

        client = GitHubClient(token=None)
        with pytest.raises(RepoNotFoundError):
            fetch_repository(client, "this-owner-definitely-does-not-exist-xyz",
                             "this-repo-does-not-exist-xyz")
