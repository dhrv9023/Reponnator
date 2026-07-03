# Quick Start, Testing & Troubleshooting Guide

## Table of Contents
1. [Setup](#1-setup)
2. [Running the Ingestion Pipeline](#2-running-the-ingestion-pipeline)
3. [Understanding the Output](#3-understanding-the-output)
4. [Test Suite Reference](#4-test-suite-reference)
5. [Edge Cases Handled](#5-edge-cases-handled)
6. [Common Errors & Fixes](#6-common-errors--fixes)
7. [Rate Limit Strategy](#7-rate-limit-strategy)
8. [What Phase 2 Will Use](#8-what-phase-2-will-use)

---

## 1. Setup

### Prerequisites
- Python 3.10 or higher
- `git` (pre-installed on most systems)
- Internet access (to reach `api.github.com`)

### Install Dependencies
```bash
cd codeautopsy/

# Option A — using the run.sh bootstrap script (auto-installs if needed):
./run.sh https://github.com/pallets/flask

# Option B — manual install:
pip install -r requirements.txt
# or if externally-managed Python:
pip install -r requirements.txt --break-system-packages
```

### Configure GitHub Token (Strongly Recommended)
```bash
cp .env.example .env
```

Edit `.env` and add your token:
```
GITHUB_TOKEN=ghp_your_token_here
```

**Where to get a token:**
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scope: `public_repo` (for public repos only) or `repo` (for private repos too)
4. Copy the token into `.env`

**Without a token:** Limited to 60 API requests per hour. For Flask (84 code files), this means hitting the rate limit mid-fetch and waiting ~17 minutes for the window to reset. The system handles this automatically — it waits and resumes — but it's slow.

**With a token:** 5,000 requests per hour. Flask completes in ~13 seconds.

---

## 2. Running the Ingestion Pipeline

### Basic Usage
```bash
python main.py https://github.com/pallets/flask
```

### All CLI Options

| Command | Description |
|---------|-------------|
| `python main.py <url>` | Fetch repo using default branch |
| `python main.py <url> --branch develop` | Fetch specific branch |
| `python main.py <url> --force` | Re-fetch even if already cached |
| `python main.py --list` | List all previously fetched repos |
| `python main.py <url> --debug` | Enable verbose DEBUG logging |

### Supported URL Formats
```bash
# All of these work identically:
python main.py https://github.com/pallets/flask
python main.py https://github.com/pallets/flask/
python main.py https://github.com/pallets/flask.git
python main.py https://github.com/pallets/flask/tree/main
python main.py https://github.com/pallets/flask/blob/main/src/flask/app.py
python main.py http://github.com/pallets/flask
python main.py github.com/pallets/flask
python main.py git@github.com:pallets/flask.git
python main.py pallets/flask
```

### Using the run.sh Bootstrap Script
```bash
# First run: installs deps, creates .env from template, runs ingestion
./run.sh https://github.com/pallets/flask

# Subsequent runs: skips install, runs directly
./run.sh pallets/flask --branch 2.x
./run.sh --list
```

---

## 3. Understanding the Output

### Success Output

```
🔍  CodeAutopsy — analysing https://github.com/pallets/flask

[2024-01-15T10:30:00] [WARNING ] [ingestion.github_client] — No GitHub token configured...
[2024-01-15T10:30:00] [INFO    ] [ingestion.file_fetcher] — Starting ingestion of github.com/pallets/flask
[2024-01-15T10:30:01] [INFO    ] [ingestion.file_fetcher] — File tree fetched: 236 total blobs in repo.
[2024-01-15T10:30:01] [INFO    ] [ingestion.file_fetcher] — Found 236 total blobs, 84 code files after filtering.
[2024-01-15T10:30:01] [INFO    ] [ingestion.file_fetcher] — Progress: 0/84 files fetched (0.0 KB so far).
[2024-01-15T10:30:13] [INFO    ] [ingestion.file_fetcher] — Progress: 50/84 files fetched (373.9 KB so far).
[2024-01-15T10:30:22] [INFO    ] [ingestion.file_fetcher] — Ingestion complete: 84 files, 1.2 MB, 13.4 seconds.

╔══════════════════════════════════════════════════╗
║  CodeAutopsy — Ingestion Complete                ║
╠══════════════════════════════════════════════════╣
║  Repo        : pallets/flask                     ║
║  Branch      : main                              ║
║  Language    : Python (84.2%)                    ║
║  Files       : 84 fetched / 236 total            ║
║  Size        : 1.2 MB                            ║
║  Time        : 13.4 seconds                      ║
║  Saved to    : data/repos/pallets__flask/         ║
╚══════════════════════════════════════════════════╝
```

### Cache Hit Output (second run)

```
✅  Repository 'pallets/flask' was already fetched at 2024-01-15T10:30:00.
    Files fetched : 84
    Primary lang  : Python
    Saved at      : /path/to/data/repos/pallets__flask

    Use --force to re-fetch, or --list to see all fetched repos.
```

### Listing Repos

```bash
python main.py --list
```
```
Full Name                           Language        Files  Fetched At
────────────────────────────────────────────────────────────────────────────────
pallets/flask                       Python             84   2024-01-15T10:30:00
django/django                       Python            312   2024-01-14T08:15:22
```

### Directory Output Structure

```
data/repos/pallets__flask/
├── manifest.json          ← Machine-readable full summary (JSON)
├── fetch.log              ← Complete run log with timestamps
└── files/
    ├── src/
    │   └── flask/
    │       ├── app.py         ← Source code files
    │       ├── cli.py
    │       ├── wrappers.py
    │       └── ...
    └── tests/
        ├── test_basic.py
        └── ...
```

### Reading the Manifest

```python
import json
from pathlib import Path

manifest = json.loads(
    (Path("data/repos/pallets__flask/manifest.json")).read_text()
)

# Key fields:
print(manifest["repo"]["primary_language"])          # "Python"
print(manifest["ingestion_stats"]["total_files_fetched"])  # 84
print(manifest["language_analysis"]["is_monorepo"])  # False
print(len(manifest["files"]))                        # 84
print(len(manifest["skipped_files"]))                # 152
print(manifest["errors"])                            # []
```

---

## 4. Test Suite Reference

### Running Tests

```bash
cd codeautopsy/

# Run all unit tests (fast, no internet):
python -m pytest tests/test_phase1.py -v -m "not integration"

# Run with verbose output:
python -m pytest tests/test_phase1.py -v

# Run a specific test class:
python -m pytest tests/test_phase1.py::TestURLParser -v

# Run a specific test:
python -m pytest tests/test_phase1.py::TestFileFilter::test_node_modules_filtered -v

# Run integration tests (requires internet + optional token):
python -m pytest tests/test_phase1.py -v -m integration

# Run everything:
python -m pytest tests/test_phase1.py -v
```

### Test Classes and Coverage

#### `TestURLParser` (21 tests)
Tests all 10 input URL formats, error cases, branch extraction, and normalization.

| Test | What it validates |
|------|------------------|
| `test_https_basic` | Standard HTTPS URL parses correctly |
| `test_https_trailing_slash` | Trailing slash stripped |
| `test_https_git_suffix` | `.git` suffix stripped from repo name |
| `test_https_tree_branch` | Branch extracted from `/tree/main` |
| `test_https_tree_branch_subfolder` | Branch extracted even with subdirectory |
| `test_https_blob_file` | Branch extracted from `/blob/main/file.py` |
| `test_http_protocol` | `http://` (non-SSL) accepted |
| `test_no_protocol` | `github.com/owner/repo` (no scheme) accepted |
| `test_ssh_format` | `git@github.com:owner/repo.git` parsed |
| `test_shorthand_format` | `owner/repo` shorthand parsed |
| `test_uppercase_normalised` | `Pallets/Flask` → `pallets/flask` |
| `test_url_with_query_params` | `?tab=readme` stripped |
| `test_ssh_without_dotgit` | SSH URL without `.git` suffix |
| `test_empty_input_raises` | Empty string → `ValueError` with "No URL provided" |
| `test_whitespace_only_raises` | Whitespace-only → `ValueError` |
| `test_non_github_url_raises` | GitLab URL → `ValueError` mentioning "not GitHub" |
| `test_github_user_page_raises` | User page (no repo) → `ValueError` |
| `test_random_string_raises` | Garbage input → `ValueError` |
| `test_branch_extracted_correctly` | Branch name extracted accurately |
| `test_repo_with_dots_and_hyphens` | Repo names with dots/hyphens accepted |
| `test_original_url_preserved` | `original_url` field matches raw input |

#### `TestFileFilter` (21 tests)
Tests every filter function and the master `should_fetch_file` orchestrator.

| Test | What it validates |
|------|------------------|
| `test_node_modules_filtered` | `node_modules` in path → skipped |
| `test_nested_ignored_dir_filtered` | `__pycache__` nested inside `project/` → skipped |
| `test_python_file_accepted` | `.py` files → `(True, "ok")` |
| `test_min_js_rejected` | `*.min.js` → pattern rejection |
| `test_markdown_rejected` | `.md` → extension rejection |
| `test_file_over_limit_rejected` | > 500 KB → size rejection |
| `test_file_at_limit_accepted` | Exactly 500 KB → accepted |
| `test_typescript_accepted` | `.ts` → accepted |
| `test_tsx_accepted` | `.tsx` → accepted |
| `test_go_file_accepted` | `.go` → accepted |
| `test_lock_file_rejected` | `package-lock.json` → rejected |
| `test_binary_content_detected` | Null-byte-heavy content → `is_likely_binary=True` |
| `test_normal_python_not_binary` | Normal code → `is_likely_binary=False` |
| `test_empty_content_not_binary` | Empty string → `is_likely_binary=False` |
| `test_get_file_language_python` | `.py` → `"Python"` |
| `test_get_file_language_typescript` | `.ts` → `"TypeScript"` |
| `test_get_file_language_unknown` | `.md` → `None` |
| `test_case_insensitive_extension` | `.PY` matches `.py` |
| `test_is_ignored_directory_exact` | Deep venv path → rejected |
| `test_is_ignored_directory_false_for_clean` | Clean path → `False` |
| `test_yarn_lock_rejected` | `yarn.lock` → rejected |

#### `TestLanguageDetector` (10 tests)
Tests language statistics, detection thresholds, and edge cases.

| Test | What it validates |
|------|------------------|
| `test_primary_python` | Mostly Python files → `primary_language="Python"` |
| `test_empty_list` | Empty input → graceful empty result |
| `test_multiple_primary_when_close` | 50%/48% split → `has_multiple_primary_languages=True` |
| `test_no_multiple_primary_when_far_apart` | 91%/9% → `has_multiple=False` |
| `test_monorepo_detection` | 3 languages each ≥15% → `is_monorepo=True` |
| `test_not_monorepo_when_one_dominant` | One dominant language → `is_monorepo=False` |
| `test_percentages_sum_to_100` | All percentages sum to ~100% |
| `test_unrecognised_files_ignored` | `.md` files not included in stats |
| `test_total_bytes_correct` | `total_bytes` sums correctly |
| `test_total_files_correct` | `total_files` counts correctly |

#### `TestStorage` (6 tests)
Tests disk persistence, manifest structure, and caching behavior.

| Test | What it validates |
|------|------------------|
| `test_save_creates_manifest` | `manifest.json` created with correct fields |
| `test_save_creates_files` | Code files written to correct paths |
| `test_manifest_has_required_keys` | All required keys present |
| `test_rotate_old_folder` | Second save rotates first folder |
| `test_list_fetched_repos` | `list_fetched_repos()` returns saved repo |
| `test_load_manifest_missing_raises` | Missing manifest → `FileNotFoundError` |

#### `TestIntegration` (2 tests, marked `@pytest.mark.integration`)
Real network tests. Require internet and optionally a GitHub token.

| Test | What it validates |
|------|------------------|
| `test_fetch_small_public_repo` | Full end-to-end with `kennethreitz/records` |
| `test_invalid_repo_raises` | Non-existent repo raises `RepoNotFoundError` |

---

## 5. Edge Cases Handled

### URL Edge Cases
| Edge Case | Handling |
|-----------|----------|
| URL with trailing slash | Stripped during parsing |
| URL with `.git` suffix | Stripped from repo name |
| URL pointing to file or subfolder | Owner and repo extracted, path/blob ignored |
| URL with uppercase letters | Normalized to lowercase |
| SSH format URLs | Handled by dedicated `_try_ssh()` parser |
| Short format `owner/repo` | Handled by `_try_shorthand()` parser |
| URL with `?query=string` | Query string stripped before path parsing |
| Completely empty input | Raises `ValueError: "No URL provided"` |
| Non-GitHub URL | Raises `ValueError` with targeted message for GitLab/Bitbucket |
| GitHub user page (no repo) | Raises `ValueError` suggesting full repo URL |

### Repo Edge Cases
| Edge Case | Handling |
|-----------|----------|
| Repo doesn't exist | `RepoNotFoundError` with clear message |
| Private repo, no token | `RepoPrivateError` with instruction to add token |
| Empty repo (no files) | Returns `FetchResult` with empty `files[]`, warning logged |
| Archived repo | Warning logged, fetch continues |
| Fork repo | Noted in metadata, fetch continues normally |
| Repo with no code files | Warning: "No code files found", empty `files[]` returned |
| Repo renamed or deleted | GitHub returns 404 → `RepoNotFoundError` |

### File Tree Edge Cases
| Edge Case | Handling |
|-----------|----------|
| Tree truncated (>100K files) | Warning logged, partial tree processed |
| Files with unicode names | `PurePosixPath` handles unicode paths correctly |
| Symlinks in tree | Type appears as `blob` but content fetch returns None → skipped |
| Git submodules (`type="commit"`) | Counted and warned, skipped silently |
| Files at repo root (no subdirectory) | `PurePosixPath("file.py").parts = ("file.py",)` → no directory components to check → works |
| Files with spaces or special chars | `_sanitise_path_component()` replaces invalid chars with underscores |

### File Content Edge Cases
| Edge Case | Handling |
|-----------|----------|
| Binary file with code extension | `is_likely_binary()` post-fetch check → skipped |
| Empty file (0 bytes) | `get_file_content()` returns `None` → skipped |
| Windows CRLF line endings | Normalized to LF (`\r\n` → `\n`) during decode |
| BOM at start of file | `utf-8-sig` codec strips BOM automatically |
| UTF-8 decoding fails | Fallback to `latin-1`, log warning |
| Both encodings fail | Return `None`, skip with "encoding not supported" |
| File actually binary | `is_likely_binary()` catches it post-fetch |

### Storage Edge Cases
| Edge Case | Handling |
|-----------|----------|
| Disk full | `errno.ENOSPC` detected → `CRITICAL` log, exception re-raised to `main.py` |
| `data/repos/` doesn't exist | `mkdir(parents=True, exist_ok=True)` creates it automatically |
| Path component too long (>200 chars) | Truncated with MD5 hash suffix for uniqueness |
| Case collision between two files | Short MD5 hash appended to disambiguate |
| Previous fetch incomplete (crashed) | `_is_manifest_complete()` detects, system re-fetches |
| Manifest write fails | Error logged, no crash (files already saved) |

---

## 6. Common Errors & Fixes

### `❌ Error: No GitHub token configured...` (warning, not fatal)
**Cause:** You haven't added a `GITHUB_TOKEN` to `.env`.  
**Fix:** Add your token to `.env`. See Setup section above.  
**Impact:** Limited to 60 API requests/hour. For small repos, this is fine.

### `❌ Error: Repository not found on GitHub.`
**Cause:** The repo doesn't exist, was renamed, or was deleted.  
**Fix:** Verify the URL at `https://github.com/owner/repo`.

### `❌ Error: Repository is private.`
**Cause:** The repo is private. Anonymous access returns a 404 that looks like "not found" but is actually "forbidden".  
**Fix:** Add a `GITHUB_TOKEN` with `repo` scope to `.env`.

### `❌ Error: The GitHub token in your .env file is invalid.`
**Cause:** Token expired, revoked, or mistyped.  
**Fix:** Generate a new token at https://github.com/settings/tokens and update `.env`.

### `❌ Error: Missing dependency: No module named 'github'`
**Cause:** Dependencies not installed.  
**Fix:** Run `pip install -r requirements.txt --break-system-packages`

### Rate limit pausing (not an error)
```
[WARNING] Rate limit low (8/60 remaining). Waiting 847 seconds until reset at 11:00:00 UTC.
[INFO   ] Rate limit reset in ~847 seconds...
```
**Cause:** Anonymous API limit (60 req/hr) exhausted.  
**Fix:** Add `GITHUB_TOKEN` to `.env`, or wait for the window to reset automatically.  
**The system handles this automatically** — it will resume when the window resets.

---

## 7. Rate Limit Strategy

### Optimizing for Large Repos Without a Token
Phase 1 uses the Git Tree API (1 request for the full file tree) instead of the Contents API (1 request per directory). This is the single biggest rate-limit optimization.

For a repo with 84 code files, the total API calls are approximately:
```
1  → verify token (or check anonymous rate limit)
1  → get_repo() metadata
1  → get_file_tree() recursive
84 → get_file_content() × 84 files
1  → rate limit status refresh (every 50 requests)
─────────────────────────────────────────────
≈88 total requests
```

With a token (5,000 req/hr): completes in ~13 seconds  
Without a token (60 req/hr): hits limit at request 56, waits ~17 minutes, completes

### For very large repos (500+ code files)
Add a token. There is no alternative. 500 files + overhead = 502+ requests = 8.4× the anonymous limit.

---

## 8. What Phase 2 Will Use

Phase 2 (AST Parsing) reads the output of Phase 1. Here is the interface:

### Loading files for parsing:
```python
import json
from pathlib import Path

# Load manifest to get file list
manifest = json.loads(Path("data/repos/pallets__flask/manifest.json").read_text())
files = manifest["files"]  # list of {path, language, size_bytes, sha}

# Read actual file content
for file_info in files:
    content = (
        Path("data/repos/pallets__flask/files") / file_info["path"]
    ).read_text(encoding="utf-8")
    language = file_info["language"]  # "Python", "TypeScript", etc.
    # → Feed to tree-sitter parser
```

### Using the Python API:
```python
from ingestion import create_client_from_env, fetch_repository
from ingestion.storage import save_fetch_result, load_manifest

# Programmatic use (no CLI)
client = create_client_from_env()
result = fetch_repository(client, "pallets", "flask")
repo_folder = save_fetch_result(result)
manifest = load_manifest(repo_folder)
```

### Key fields Phase 2 needs:

| Field | Path in manifest | Phase 2 use |
|-------|-----------------|-------------|
| File content | `files/{file.path}` on disk | Feed to tree-sitter |
| Language | `manifest["files"][i]["language"]` | Select correct tree-sitter parser |
| SHA | `manifest["files"][i]["sha"]` | Cache invalidation — re-parse only if changed |
| Primary language | `manifest["language_analysis"]["primary_language"]` | Choose entry point detection strategy |
| Is monorepo | `manifest["language_analysis"]["is_monorepo"]` | Adjust chunking strategy |
| Repo metadata | `manifest["repo"]` | Include in chunk metadata |
