# Module Reference — Part 3: Pipeline Modules

This document covers the four modules that form the execution backbone of Phase 1: the language analyser, the orchestration engine, the storage layer, and the CLI entry point.

## Table of Contents
1. [ingestion/language_detector.py — Language Statistics](#1-ingestionlanguage_detectorpy--language-statistics)
2. [ingestion/file_fetcher.py — Pipeline Orchestrator](#2-ingestionfile_fetcherpy--pipeline-orchestrator)
3. [ingestion/storage.py — Disk Persistence](#3-ingestionstorагepy--disk-persistence)
4. [main.py — CLI Entry Point](#4-mainpy--cli-entry-point)
5. [ingestion/__init__.py — Package Public API](#5-ingestion__init__py--package-public-api)

---

## 1. `ingestion/language_detector.py` — Language Statistics

**File:** `codeautopsy/ingestion/language_detector.py`  
**Role:** Analyses the list of successfully fetched code files to compute a statistical breakdown of language distribution. Identifies the primary language, detects monorepos, and flags co-dominant languages.  
**Dependencies:** `ingestion/file_filter.get_file_language()`, `utils/logger.py`

### Why this module exists
Language detection is more nuanced than checking the file extension of the first file. A repo might have 100 `.sh` shell scripts (tiny, a few lines each) and 5 `.py` Python files (each thousands of lines). Counting files would say "Shell" is primary. Counting bytes says "Python". Bytes is almost always the more meaningful metric for architectural analysis.

Additionally, downstream phases need to know if a repo is a polyglot monorepo (different languages for frontend, backend, data pipeline) because that changes how the architecture diagram and narrative are structured.

---

### `detect_languages(file_list) → dict`

The single public function. Accepts a list of file descriptors and returns a comprehensive statistics dict.

```python
# Input:
file_list = [
    {"path": "src/app.py",      "size": 62000},
    {"path": "src/cli.py",      "size": 28000},
    {"path": "static/app.js",   "size": 15000},
    {"path": "static/utils.js", "size": 8000},
    {"path": "Makefile.sh",     "size": 2000},
]

# Output:
{
    "primary_language": "Python",
    "languages": {
        "Python": {
            "file_count": 2,
            "byte_count": 90000,
            "percentage": 77.6
        },
        "JavaScript": {
            "file_count": 2,
            "byte_count": 23000,
            "percentage": 19.8
        },
        "Shell": {
            "file_count": 1,
            "byte_count": 2000,
            "percentage": 1.7
        }
    },
    "is_monorepo": False,        # Only Python qualifies at ≥15%
    "has_multiple_primary_languages": False,  # Python (77.6%) vs JS (19.8%) — gap > 10%
    "total_files": 5,
    "total_bytes": 115000
}
```

---

### Detection Thresholds

These are module-level constants (not in `config.py` because they are specific to this algorithm):

```python
_MONOREPO_THRESHOLD_PERCENT   = 15.0  # Each qualifying language must have ≥15%
_MONOREPO_LANGUAGE_COUNT      = 3     # Need at least 3 qualifying languages
_MULTI_PRIMARY_TOLERANCE_PERCENT = 10.0  # Top-2 within 10% = co-dominant
```

#### Monorepo Detection
```
is_monorepo = True when:
  - At least 3 different languages are found
  - AND each of those 3+ languages contributes ≥15% of total bytes

Example — Monorepo (True):
  Python: 40%   ← qualifies
  Go:     35%   ← qualifies
  TypeScript: 25%  ← qualifies
  → 3 qualifying languages → is_monorepo = True

Example — Not Monorepo (False):
  Python: 80%
  Go:     12%   ← does NOT qualify (<15%)
  Shell:  8%    ← does NOT qualify
  → Only 1 qualifying language → is_monorepo = False
```

#### Co-Dominant Language Detection
```
has_multiple_primary_languages = True when:
  |first_language_percentage - second_language_percentage| <= 10%

Example — Co-dominant (True):
  Python: 52%
  JavaScript: 48%
  → Gap = 4% ≤ 10% → True

Example — Clear winner (False):
  Python: 82%
  JavaScript: 18%
  → Gap = 64% > 10% → False
```

---

### Processing Pipeline

```
Input: list of {path, size} dicts (may include unrecognised files)
   │
   ├─ For each file:
   │    language = get_file_language(path)
   │    if language is None: skip (log debug)
   │    else: increment lang_stats[language][file_count, byte_count]
   │
   ├─ If no files produced stats: return _empty_result()
   │
   ├─ Compute percentages:
   │    pct = byte_count / total_bytes * 100
   │
   ├─ Sort by byte_count descending
   │    primary_language = sorted_langs[0][0]
   │
   ├─ Monorepo check:
   │    qualifying = [lang for lang, data in sorted_langs if data.pct >= 15%]
   │    is_monorepo = len(qualifying) >= 3
   │
   └─ Co-dominant check:
        has_multiple = abs(first_pct - second_pct) <= 10%
```

---

### Edge Cases

| Input | Behavior |
|-------|----------|
| Empty file list | Returns `_empty_result()` with `primary_language="Unknown"`, logs warning |
| All files unrecognised extensions | Returns `_empty_result()`, logs warning |
| Single file | Returns that language as primary, `is_monorepo=False`, `has_multiple=False` |
| Two equal-size files, same language | `is_monorepo=False`, `has_multiple=False` |
| Files with `size=0` | Contribute to file_count but not byte_count or percentage |

---

## 2. `ingestion/file_fetcher.py` — Pipeline Orchestrator

**File:** `codeautopsy/ingestion/file_fetcher.py`  
**Role:** The main orchestration module that wires together all other ingestion modules to execute the complete fetch pipeline for one repository. Returns a `FetchResult` dataclass.  
**Dependencies:** `config.py`, `ingestion/github_client.py`, `ingestion/file_filter.py`, `ingestion/language_detector.py`, `utils/logger.py`

### Why this module exists
No single module can do the complete job alone. `file_fetcher.py` is the conductor — it calls each module in the right order, handles state (running byte totals, file counts, error lists), enforces the total size limit, and assembles the final structured result.

---

### Dataclasses

#### `FetchedFile`
```python
@dataclass
class FetchedFile:
    path:       str   # "src/flask/app.py"
    language:   str   # "Python"
    content:    str   # Full decoded text content
    size_bytes: int   # Actual UTF-8 encoded byte count (may differ from tree size)
    sha:        str   # Git SHA-1 hash of this file version
```

> **Note on `size_bytes`:** The size reported in the GitHub tree is the raw blob size. `FetchedFile.size_bytes` is the byte count of the decoded, CRLF-normalized UTF-8 string. These can differ slightly due to BOM stripping and line ending normalization.

#### `SkippedFile`
```python
@dataclass
class SkippedFile:
    path:       str   # "node_modules/lodash/index.js"
    reason:     str   # "ignored directory: node_modules"
    size_bytes: int   # From tree metadata (not downloaded)
```

#### `FetchResult`
```python
@dataclass
class FetchResult:
    owner:                  str           # "pallets"
    repo_name:              str           # "flask"
    branch:                 str           # "main"
    repo_metadata:          dict          # Full metadata dict from get_repo_metadata()
    files:                  list[FetchedFile]
    skipped_files:          list[SkippedFile]
    language_analysis:      dict          # Full output from detect_languages()
    total_files_in_repo:    int           # All blobs in tree (236 for flask)
    total_files_fetched:    int           # Successfully fetched (84)
    total_files_skipped:    int           # Skipped for any reason (152)
    total_bytes_fetched:    int           # Sum of fetched file sizes
    fetch_duration_seconds: float         # Wall clock time for the entire run
    fetch_timestamp:        str           # ISO 8601 UTC timestamp of when fetch started
    errors:                 list[str]     # Non-fatal per-file errors
    warnings:               list[str]     # Non-fatal pipeline-level warnings
```

---

### `fetch_repository(github_client, owner, repo_name, branch) → FetchResult`

The single public function. Executes the full 7-step pipeline:

#### Step 1: Repo Validation
```python
repo = _get_validated_repo(client, owner, repo_name, warnings)
# Raises: RepoNotFoundError, RepoPrivateError, GitHubClientError
```
Wraps `client.get_repo()` with repo-specific error messages. Also:
- Appends warning to `warnings[]` if repo is archived
- Logs info note if repo is a fork

#### Step 2: Metadata + Branch Resolution
```python
metadata = github_client.get_repo_metadata(repo)
effective_branch = branch or metadata["default_branch"]
```
If the user didn't specify a branch, use the repo's default branch (typically `main` or `master`).

#### Step 3: File Tree Fetch
```python
tree_entries = github_client.get_file_tree(repo, branch=effective_branch)
blob_entries = [e for e in tree_entries if e["type"] == "blob"]
```
Also:
- Counts submodule entries (`type="commit"`) and warns about them
- Warns if `total_tree_blobs > MAX_REPO_FILES` (5,000)

#### Step 4: Pre-filter
```python
for entry in blob_entries:
    ok, reason = should_fetch_file(entry["path"], entry["size"])
    if ok:
        to_fetch.append(entry)
    else:
        skipped_files.append(SkippedFile(path, reason, size))
```
This loop is extremely fast — pure Python logic, no API calls.

After filtering, logs:
```
Found 236 total blobs, 84 code files after filtering (152 skipped by filter).
```

#### Step 5: Content Fetch Loop
```python
for idx, entry in enumerate(to_fetch, start=1):
    # Progress every 50 files:
    if idx % 50 == 0 or idx == 1:
        logger.info("Progress: %d/%d files fetched (%.1f KB so far)", ...)

    # Total size guard:
    if total_bytes_fetched + size_bytes > MAX_TOTAL_SIZE_BYTES:
        # Warn, mark remaining as skipped, break
        ...

    # Fetch content:
    content = _fetch_file_safe(client, repo, path, branch, sha, errors)

    # Post-fetch binary detection:
    if is_likely_binary(content):
        skipped_files.append(SkippedFile(path, "binary content detected", size))
        continue

    # Append to results:
    fetched_files.append(FetchedFile(path, language, content, actual_size, sha))
    total_bytes_fetched += actual_size
```

#### Step 6: Language Detection
```python
file_descriptors = [{"path": f.path, "size": f.size_bytes} for f in fetched_files]
language_analysis = detect_languages(file_descriptors)
```

#### Step 7: Assemble and Return
```python
return FetchResult(
    owner=owner,
    repo_name=repo_name,
    branch=effective_branch,
    ...
)
```

---

### `_fetch_file_safe()` — Non-fatal File Fetching

All individual file fetches go through this helper:

```python
def _fetch_file_safe(client, repo, path, branch, sha, errors) -> Optional[str]:
    try:
        return client.get_file_content(repo, path, branch)
    except GitHubClientError as exc:
        errors.append(f"Failed to fetch {path!r}: {exc}")
        return None
    except Exception as exc:
        errors.append(f"Unexpected error fetching {path!r}: {exc}")
        return None
```

**Critical design choice:** This function **never raises**. Any error on a single file is caught, recorded in `errors[]`, and returns `None`. The calling loop then adds the file to `skipped_files`. This ensures one bad file never aborts the ingestion of the remaining 200 files.

---

### Progress Logging

```
[INFO] [file_fetcher] — Starting ingestion of github.com/pallets/flask
[INFO] [file_fetcher] — Target branch: 'main'
[INFO] [file_fetcher] — File tree fetched: 236 total blobs in repo.
[INFO] [file_fetcher] — Found 236 total blobs, 84 code files after filtering (152 skipped by filter).
[INFO] [file_fetcher] — Progress: 0/84 files fetched (0.0 KB so far).
[INFO] [file_fetcher] — Progress: 50/84 files fetched (373.9 KB so far).
[INFO] [file_fetcher] — Progress: 84/84 files fetched (1,187.3 KB so far).
[INFO] [file_fetcher] — Ingestion complete: 84 files, 1.2 MB, 13.4 seconds.
```

---

## 3. `ingestion/storage.py` — Disk Persistence

**File:** `codeautopsy/ingestion/storage.py`  
**Role:** Takes the `FetchResult` dataclass and persists everything to disk — file contents, manifest.json, and fetch.log.  
**Dependencies:** `config.py`, `ingestion/file_fetcher.py` (for dataclass types), `utils/logger.py`

### Why this module exists
Separating persistence from orchestration follows the single-responsibility principle. `file_fetcher.py` knows how to fetch data. `storage.py` knows how to store it. Neither knows about the other's internals. This also makes it easy to change the storage format (e.g. switch to a database in a future phase) without touching the fetching logic.

---

### `save_fetch_result(result, data_dir) → Path`

The primary public function.

```python
repo_folder = save_fetch_result(result, data_dir=DATA_DIR)
# Returns: Path("data/repos/pallets__flask/")
```

**Execution steps:**
1. Compute folder name: `{owner}__{repo_name}` → `"pallets__flask"`
2. Call `_rotate_existing()` if folder already exists
3. Create `{repo_folder}/files/` directory tree
4. Call `configure_for_repo(repo_folder)` → attaches `fetch.log` to all loggers
5. Call `_save_code_files()` → write each file
6. Call `_write_manifest()` → serialize FetchResult to JSON

---

### `_rotate_existing(repo_folder)` — Safe Old-Data Rotation

```python
# Before new fetch:          After rotation:
pallets__flask/              pallets__flask__2024-01-15T10-30-00/
├── manifest.json            ├── manifest.json
└── files/                   └── files/

# New folder created fresh:
pallets__flask/
├── manifest.json
└── files/
```

The timestamp is extracted from the old manifest's `fetch_timestamp` field. If the manifest is corrupted/missing, falls back to the current time. The renamed folder name format is `{original}__{timestamp}` where colons in the timestamp are replaced with dashes (for filesystem compatibility).

---

### `_save_code_files(files, files_dir)` — File Writing

```python
for fetched_file in files:
    dest_path = _safe_destination(files_dir, fetched_file.path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(fetched_file.content, encoding="utf-8")
```

**Disk-full detection:**
```python
except OSError as exc:
    if exc.errno == 28:  # ENOSPC — disk full
        logger.critical("DISK FULL while saving %r. Stopping file writes.", path)
        raise  # Re-raise to bubble up to main.py for clean user message
    logger.error("Failed to save %r: %s", path, exc)
    # Other OS errors: log and continue (non-fatal)
```

---

### `_safe_destination(files_dir, repo_path)` — Path Safety

Handles edge cases that would break on real filesystems:

#### Invalid character sanitization
```python
sanitised = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", component)
```
Replaces characters invalid on Windows filesystems (`<>:"/\|?*` and control chars) with underscores. This makes the storage cross-platform.

#### Long path component truncation
```python
if len(sanitised) > 200:
    digest = hashlib.md5(sanitised.encode()).hexdigest()[:8]
    sanitised = sanitised[:191] + "_" + digest
```
Truncates to 200 characters and appends an 8-char MD5 hash suffix to ensure uniqueness despite truncation.

#### Case collision detection
```python
if dest.exists():
    path_hash = hashlib.md5(repo_path.encode()).hexdigest()[:6]
    name = dest.stem + f"_{path_hash}" + dest.suffix
    dest = dest.parent / name
```
If a file already exists at the computed destination (which can happen on case-insensitive filesystems like macOS when two paths differ only in case), appends a short hash to the filename to disambiguate.

---

### `_write_manifest(result, repo_folder)` — JSON Manifest

Calls `_build_manifest()` to convert the `FetchResult` dataclass into the canonical manifest dict, then writes it:

```python
with manifest_path.open("w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2, default=_json_serialiser)
```

**Custom JSON serializer** handles types the default encoder cannot:
```python
def _json_serialiser(obj):
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)  # Dataclass → dict
    if isinstance(obj, Path):
        return str(obj)                  # Path → string
    if isinstance(obj, datetime):
        return obj.isoformat()           # datetime → ISO string
    raise TypeError(...)
```

**Non-fatal manifest failure:** If the JSON write fails (e.g. mid-write disk full), it logs an error but does NOT raise. The code files are already safely written. The manifest is the index; losing it is bad but not catastrophic — it can be regenerated.

---

### `load_manifest(repo_folder) → dict`

```python
manifest = load_manifest(Path("data/repos/pallets__flask"))
```

Reads and parses `manifest.json`. Raises:
- `FileNotFoundError` if `manifest.json` doesn't exist
- `json.JSONDecodeError` if the file is corrupted

---

### `list_fetched_repos(data_dir) → list[dict]`

Scans all subfolders in `data_dir`, reads each `manifest.json`, and returns a lightweight summary list:

```python
repos = list_fetched_repos()
# Returns:
[
    {
        "owner":               "pallets",
        "repo_name":           "flask",
        "full_name":           "pallets/flask",
        "fetch_timestamp":     "2024-01-15T10:30:00Z",
        "total_files_fetched": 84,
        "primary_language":    "Python",
        "repo_folder":         "/path/to/data/repos/pallets__flask",
        "is_complete":         True
    }
]
```

**Backup folder exclusion:** Folders matching `__YYYY-MM-DDT` pattern are skipped (they are old rotated backups, not current fetches).

**Completeness check:** `is_complete` is `True` only if the manifest contains all required top-level keys. Incomplete manifests (from crashed runs) show `is_complete: False`, triggering automatic re-fetch next time.

---

## 4. `main.py` — CLI Entry Point

**File:** `codeautopsy/main.py`  
**Role:** Parses command-line arguments, orchestrates the full pipeline execution, handles all user-facing error presentation, and displays the final summary.  
**Dependencies:** All ingestion and utils modules (late-imported)

### Why this module exists
Separating the CLI layer from the pipeline logic is essential. `file_fetcher.py` knows nothing about command-line arguments. `main.py` knows nothing about GitHub API internals. This allows the pipeline to be used as a library (imported and called programmatically) without any CLI-specific code getting in the way.

---

### CLI Interface

```
usage: codeautopsy [-h] [--branch BRANCH] [--force] [--list] [--debug] [repo_url]

positional arguments:
  repo_url         GitHub repository URL (any supported format)

options:
  --branch BRANCH  Branch to fetch (default: repo's default branch)
  --force          Re-fetch even if this repo was already cached
  --list           List all previously fetched repos and exit
  --debug          Enable verbose DEBUG-level logging
```

**Examples:**
```bash
python main.py https://github.com/pallets/flask
python main.py pallets/flask --branch 2.x
python main.py git@github.com:pallets/flask.git --force
python main.py --list
python main.py https://github.com/pallets/flask --debug
```

---

### Execution Flow

```
main()
  │
  ├── parse args (argparse)
  │
  ├── if --list: _handle_list_command() → print table, return
  │
  ├── parse_github_url(repo_url)
  │   └── on ValueError: _fatal("...") → exit 1
  │
  ├── _check_cache(owner, repo_name, data_dir, --force)
  │   ├── cached + complete + no --force: print stats, return
  │   ├── cached + incomplete: print warning, proceed
  │   └── not cached: proceed
  │
  ├── load_dotenv(.env)
  ├── GitHubClient(GITHUB_TOKEN)
  │   └── on GitHubClientError: _fatal("...") → exit 1
  │
  ├── file_fetcher.fetch_repository(client, owner, repo, branch)
  │   ├── on RepoNotFoundError: _fatal("Repository not found...") → exit 1
  │   ├── on RepoPrivateError:  _fatal("Repository is private...") → exit 1
  │   ├── on GitHubClientError: _fatal("GitHub API error: ...") → exit 1
  │   ├── on KeyboardInterrupt: _fatal("Ingestion interrupted") → exit 1
  │   └── on Exception: log traceback to fetch.log, _fatal("Unexpected error...") → exit 1
  │
  ├── storage.save_fetch_result(result, data_dir)
  │   ├── on OSError(ENOSPC): _fatal("Disk is full...") → exit 1
  │   └── on Exception: _fatal("Failed to save results...") → exit 1
  │
  └── _print_summary(result, repo_folder)
```

---

### `_fatal(message)` — Clean Error Display

```python
def _fatal(message: str) -> None:
    print(f"\n❌  Error: {message}\n", file=sys.stderr)
    sys.exit(1)
```

This is the only place `sys.exit(1)` is called. **Raw Python tracebacks are never shown to users.** Full tracebacks are logged to `fetch.log` via:
```python
logging.getLogger(__name__).critical("Unexpected error during ingestion", exc_info=True)
```
The `exc_info=True` parameter causes Python to log the full stack trace to the file handler without printing it to the console.

---

### `_print_summary(result, repo_folder)`

```
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

Plus any warnings that were collected during the run:
```
⚠️  Warnings:
   • Repository 'django/django' is archived. Fetching anyway.
   • File tree is truncated by GitHub API (repo has >100,000 files).
```

---

### Cache Display (`--list`)

```
Full Name                           Language        Files  Fetched At
────────────────────────────────────────────────────────────────────────────────
pallets/flask                       Python             84   2024-01-15T10:30:00
django/django                       Python            312   2024-01-14T08:15:22
facebook/react                      JavaScript        198   2024-01-13T16:45:11
```

---

### Late Import Strategy

All project modules are imported inside `_import_modules()` which is called after argument parsing:

```python
def _import_modules():
    global config, logger_mod, url_parser, ...
    try:
        import config as _config
        ...
    except ImportError as exc:
        _fatal(f"Missing dependency: {exc}\nRun: pip install -r requirements.txt")
```

**Why:** This allows `python main.py --help` to display the help text even if dependencies are not installed, with a clear error message rather than an `ImportError` traceback.

---

## 5. `ingestion/__init__.py` — Package Public API

**File:** `codeautopsy/ingestion/__init__.py`  
**Role:** Defines the public API for the `ingestion` package. Downstream phases import from here rather than from individual sub-modules.

```python
from ingestion import (
    fetch_repository,
    FetchResult,
    FetchedFile,
    SkippedFile,
    ParsedURL,
    parse_github_url,
    GitHubClient,
    GitHubClientError,
    RepoNotFoundError,
    RepoPrivateError,
    RateLimitError,
    create_client_from_env,
)
```

**Why:** When Phase 2 (AST parsing) needs to read the files from a `FetchResult`, it should import from `ingestion`, not from `ingestion.file_fetcher`. If Phase 1 is ever refactored to reorganize its internal modules, the `__init__.py` provides a stable public interface that downstream phases don't need to change.
