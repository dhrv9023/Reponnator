# Phase 1 Architecture & Design Decisions

## Table of Contents
1. [System Overview](#1-system-overview)
2. [Full Data Flow (Step by Step)](#2-full-data-flow-step-by-step)
3. [Module Dependency Graph](#3-module-dependency-graph)
4. [Key Design Decisions](#4-key-design-decisions)
5. [What Phase 1 Produces](#5-what-phase-1-produces)
6. [Failure Handling Strategy](#6-failure-handling-strategy)
7. [Rate Limit Architecture](#7-rate-limit-architecture)
8. [Caching Architecture](#8-caching-architecture)

---

## 1. System Overview

Phase 1 is a **pure ingestion pipeline**. It makes no assumptions about what will be done with the code it fetches. Its only job is to:

1. Accept any GitHub URL in any format
2. Fetch every relevant code file from that repository
3. Store everything locally in a clean, consistent structure
4. Produce a structured manifest describing exactly what was fetched and why

Everything downstream (AST parsing, chunking, embedding, diagram generation, narrative generation) reads from the output of Phase 1. Phase 1 is the foundation. If it produces incomplete or corrupt data, every subsequent phase will be wrong.

This is why Phase 1 is built to be:
- **Fault-tolerant**: errors on individual files never abort the run
- **Transparent**: every decision (skip, fetch, warn) is logged
- **Reproducible**: the manifest records exactly what was fetched and when
- **Resumable**: the caching system prevents redundant re-fetches

---

## 2. Full Data Flow (Step by Step)

### Step 0: CLI Entry (`main.py`)
```
python main.py https://github.com/pallets/flask --branch main
```
- argparse processes `repo_url`, `--branch`, `--force`, `--list`, `--debug`
- Loads `.env` for `GITHUB_TOKEN`
- Calls `url_parser.parse_github_url()` to validate and normalize the URL
- Checks the local cache via `storage.list_fetched_repos()`
- If cached and `--force` not set → prints cached stats, exits cleanly

### Step 1: URL Parsing (`ingestion/url_parser.py`)
```
Input:  "https://github.com/pallets/flask/tree/main"
Output: ParsedURL(owner="pallets", repo_name="flask", branch="main",
                  normalized_url="https://github.com/pallets/flask")
```
- Handles 10 different URL formats (HTTPS, HTTP, SSH, shorthand, blob, tree)
- Normalizes owner and repo name to lowercase
- Validates names against GitHub's character and length rules
- Raises `ValueError` with actionable messages on any invalid input

### Step 2: GitHub Client Init (`ingestion/github_client.py`)
```
Input:  GITHUB_TOKEN from .env (or None for anonymous)
Output: GitHubClient instance, rate limit verified and logged
```
- If token provided: verifies token with a lightweight `get_user()` call
- If no token: warns user about 60 req/hr limit, continues anyway
- Initializes `RateLimiter` with current quota state

### Step 3: Repo Fetch + Metadata (`ingestion/github_client.py`)
```
Input:  owner="pallets", repo_name="flask"
Output: Repository object + metadata dict
```
Metadata dict contains:
```json
{
  "name": "flask",
  "owner": "pallets",
  "description": "The Python micro framework for building web applications.",
  "primary_language": "Python",
  "stars": 68000,
  "forks": 16000,
  "default_branch": "main",
  "license": "BSD-3-Clause",
  "is_fork": false,
  "is_archived": false,
  "topics": ["flask", "python", "web", "wsgi"]
}
```

### Step 4: File Tree Fetch (`ingestion/github_client.py → get_file_tree`)
```
Input:  Repository object, branch="main"
Output: List of 236 entries [{"path": "...", "type": "blob", "size": N, "sha": "..."}]
```
- Calls GitHub's recursive Git Tree API (single request for entire tree)
- Detects truncation (repos > 100,000 files) and warns user
- Filters out `type="commit"` entries (git submodules)
- Returns only `type="blob"` and `type="tree"` entries

### Step 5: Pre-Filter (`ingestion/file_filter.py → should_fetch_file`)
```
Input:  236 blob entries
Output: 84 to_fetch, 152 skipped (before content is downloaded)
```
Applied in strict order (first failing check wins):
1. **Directory filter** — `node_modules`, `.git`, `__pycache__`, etc.
2. **Pattern filter** — `*.min.js`, `*.lock`, `*.map`, `*.pyc`, etc.
3. **Extension filter** — only known code extensions pass
4. **Size filter** — skip files > 500 KB (based on tree metadata, before download)

### Step 6: Content Fetch Loop (`ingestion/file_fetcher.py`)
```
For each of the 84 qualifying files:
  → github_client.get_file_content(repo, path, branch)
  → Decode base64 content
  → Normalize CRLF → LF
  → Strip BOM
  → Apply is_likely_binary() check
  → If binary: add to skipped_files
  → If ok: add to fetched_files
```
- Logs progress every 50 files: `"Progress: 50/84 files fetched (373.9 KB so far)"`
- Stops early if `total_bytes > 50 MB`
- Each file fetch has retry logic (up to 3 retries with exponential backoff)
- Non-fatal errors (single file failures) are recorded in `result.errors[]`
- Fatal errors (repo not found, private) raise immediately

### Step 7: Language Detection (`ingestion/language_detector.py`)
```
Input:  84 FetchedFile objects with path and size_bytes
Output: {
  "primary_language": "Python",
  "languages": {
    "Python": {"file_count": 61, "byte_count": 285000, "percentage": 84.2},
    "JavaScript": {"file_count": 8, "byte_count": 23000, "percentage": 6.8}
  },
  "is_monorepo": false,
  "has_multiple_primary_languages": false
}
```

### Step 8: Save to Disk (`ingestion/storage.py`)
```
Output structure:
  data/repos/pallets__flask/
    ├── manifest.json       ← Full structured summary
    ├── fetch.log           ← Complete run log
    └── files/              ← All code files
        ├── src/flask/app.py
        ├── src/flask/cli.py
        └── ...
```

### Step 9: Summary Display (`main.py`)
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

---

## 3. Module Dependency Graph

```
main.py
   │
   ├── config.py                    (imported by almost everyone)
   │
   ├── ingestion/url_parser.py      (no ingestion deps — pure logic)
   │
   ├── ingestion/github_client.py
   │       └── utils/rate_limiter.py
   │               └── utils/logger.py
   │
   └── ingestion/file_fetcher.py    (the orchestrator)
           ├── ingestion/github_client.py
           ├── ingestion/file_filter.py
           │       └── config.py
           └── ingestion/language_detector.py
                   └── ingestion/file_filter.py

ingestion/storage.py
   ├── ingestion/file_fetcher.py    (uses FetchResult dataclass)
   ├── config.py
   └── utils/logger.py

utils/logger.py                     (no project dependencies)
utils/rate_limiter.py
   └── utils/logger.py
```

**Rule enforced:** No circular imports. `config.py` and `utils/logger.py` have zero project-level dependencies.

---

## 4. Key Design Decisions

### Decision 1: GitHub API Tree Endpoint vs. Recursive Directory Walk

**Choice:** Use GitHub's `git/trees/{sha}?recursive=1` endpoint.

**Why:** This fetches the entire file tree in a **single API request**. The alternative — walking directories recursively via the Contents API — would require one API call per directory, burning through the rate limit quota extremely fast. For Flask's 50+ directories, the recursive tree approach uses 1 request vs. 50+ requests.

**Trade-off:** The tree API returns truncated results for repos with > 100,000 files. This is detected and warned.

---

### Decision 2: Pre-filter Before Downloading Content

**Choice:** Apply directory, pattern, and extension filters against tree metadata *before* making any content download calls.

**Why:** Downloading content costs 1 API request per file. If we downloaded `node_modules` (often 10,000+ files) before filtering, we would exhaust rate limits instantly. Pre-filtering on the free tree metadata eliminates >60% of files before spending any quota on content.

---

### Decision 3: Never Delete Old Fetch Data

**Choice:** When re-fetching a repo, rename the old folder with a timestamp suffix instead of deleting it.

**Why:** Silent deletion is dangerous. If a user is mid-analysis of a previous fetch and runs `--force`, they lose their work. The rotation approach (`pallets__flask__2024-01-15T10:30:00`) preserves all historical data. Users can always manually delete old backups.

---

### Decision 4: Non-fatal Error Collection

**Choice:** Individual file fetch failures are collected into `result.errors[]` and never abort the run.

**Why:** A single corrupted or missing file should not prevent analysis of the other 200 files in the repo. The manifest records every error so the user can investigate. Only truly fatal errors (repo not found, private repo, disk full) abort the run.

---

### Decision 5: Layered Binary Detection

**Choice:** Two-stage binary detection:
1. **Pre-fetch** (stage 1): Extension filter catches `.class`, `.pyc`, `.wasm`, etc.
2. **Post-fetch** (stage 2): `is_likely_binary()` inspects actual content for null bytes and non-printable character ratios.

**Why:** Stage 1 catches obvious binary files cheaply. Stage 2 is necessary because some files have "code" extensions but are actually binary (e.g. compiled Java `.class` files mistakenly committed with a `.java` extension, or auto-generated protobuf Go files).

---

### Decision 6: Language Detection by Byte Count, Not File Count

**Choice:** `primary_language` is determined by total **byte count**, not number of files.

**Why:** A repo might have 100 tiny `.sh` shell scripts and 10 large `.py` files. By file count, Shell would win. By byte count, Python wins — reflecting where the actual *work* of the codebase is. This matches how GitHub computes language percentages.

---

## 5. What Phase 1 Produces

### Output 1: Mirrored File Tree (`data/repos/{owner}__{repo}/files/`)

An exact mirror of the repository's code files at the fetched branch state. File paths are preserved exactly:

```
files/
├── src/
│   └── flask/
│       ├── app.py              ← 62 KB of Python
│       ├── cli.py              ← 28 KB of Python
│       ├── wrappers.py         ← 14 KB of Python
│       └── templating.py       ← 8 KB of Python
└── tests/
    ├── test_basic.py
    └── test_cli.py
```

### Output 2: `manifest.json`

A complete, machine-readable record of the entire ingestion run:

```json
{
  "codeautopsy_version": "1.0.0",
  "fetch_timestamp": "2024-01-15T10:30:00Z",
  "repo": {
    "owner": "pallets",
    "name": "flask",
    "full_name": "pallets/flask",
    "url": "https://github.com/pallets/flask",
    "branch": "main",
    "description": "The Python micro framework...",
    "stars": 68000,
    "primary_language": "Python",
    "topics": ["flask", "python", "web", "wsgi"],
    "license": "BSD-3-Clause"
  },
  "ingestion_stats": {
    "total_files_in_repo": 236,
    "total_files_fetched": 84,
    "total_files_skipped": 152,
    "total_bytes_fetched": 1258000,
    "fetch_duration_seconds": 13.4
  },
  "language_analysis": {
    "primary_language": "Python",
    "languages": {
      "Python": {"file_count": 61, "byte_count": 285000, "percentage": 84.2}
    },
    "is_monorepo": false,
    "has_multiple_primary_languages": false
  },
  "files": [
    {"path": "src/flask/app.py", "language": "Python", "size_bytes": 62000, "sha": "abc123..."}
  ],
  "skipped_files": [
    {"path": "node_modules/lodash/index.js", "reason": "ignored directory: node_modules", "size_bytes": 54000}
  ],
  "errors": [],
  "warnings": []
}
```

### Output 3: `fetch.log`

A complete timestamped log of every decision made during the run:

```
[2024-01-15T10:30:00] [INFO    ] [ingestion.file_fetcher] — Starting ingestion of github.com/pallets/flask
[2024-01-15T10:30:01] [INFO    ] [ingestion.file_fetcher] — File tree fetched: 236 total blobs in repo.
[2024-01-15T10:30:01] [DEBUG   ] [ingestion.file_filter] — SKIP "docs/conf.py" — unsupported extension: .rst
[2024-01-15T10:30:01] [DEBUG   ] [ingestion.file_filter] — SKIP "package-lock.json" — ignored pattern: package-lock.json
[2024-01-15T10:30:13] [INFO    ] [ingestion.file_fetcher] — Progress: 50/84 files fetched (373.9 KB so far)
[2024-01-15T10:30:22] [INFO    ] [ingestion.file_fetcher] — Ingestion complete: 84 files, 1.2 MB, 13.4 seconds
```

---

## 6. Failure Handling Strategy

| Failure Type | Severity | Behavior |
|-------------|----------|----------|
| Invalid URL | Fatal | `ValueError` → clean `❌ Error:` message to user, exit 1 |
| Non-GitHub URL | Fatal | `ValueError` → tells user only GitHub supported |
| Repo not found | Fatal | `RepoNotFoundError` → "Repository not found. Verify owner/name." |
| Private repo | Fatal | `RepoPrivateError` → "Add a GitHub token with repo scope." |
| Invalid token | Fatal | `GitHubClientError` → "Token invalid. Generate a new one at..." |
| No internet | Fatal | `GitHubClientError` → "Could not reach GitHub API." |
| Rate limit | Auto-recover | `RateLimiter` waits for reset window, resumes automatically |
| Single file 404 | Non-fatal | Logged to errors[], skipped, run continues |
| Single file binary | Non-fatal | Added to skipped_files[], run continues |
| Single file encoding fail | Non-fatal | Added to skipped_files[], run continues |
| Disk full | Fatal | Detected via `errno.ENOSPC`, clean message, stops writes |
| Manifest write fails | Non-fatal | Logged error but files already saved — no crash |
| Submodules in tree | Non-fatal | Warning logged, entries skipped silently |
| Truncated tree (>100K files) | Warning | Logged, continues with what API returned |

---

## 7. Rate Limit Architecture

GitHub API rate limits are the biggest operational constraint for Phase 1.

### Without a token (anonymous):
- **60 requests per hour**
- Shared globally by all anonymous users on your IP
- Flask repo (84 code files) needs ~86 requests (1 tree + 84 content + 1 rate check)
- Result: hits limit after ~56 files, waits ~17 minutes for reset

### With a token:
- **5,000 requests per hour**
- Flask repo completes in ~13 seconds
- Repos up to ~4,900 files can be ingested in a single hour window

### How the rate limiter works:

```
RateLimiter.__init__()
  → calls GitHub API to fetch initial quota state
  → stores: remaining=58, limit=60, reset_at=2024-01-15T11:00:00Z

Before every API call:
  check_and_wait()
    → if remaining <= 10 (RATE_LIMIT_BUFFER):
        wait_seconds = reset_at - now + 2s safety margin
        log warning with exact wait time and reset clock
        sleep in 15-second intervals with countdown logs
        after reset: refresh quota state and resume

After each set of 50 decrements:
  _refresh_if_stale()
    → re-sync with GitHub to get accurate remaining count
    → corrects for any requests made outside our counter
```

### Handling unexpected 403s:
If PyGithub itself raises a `RateLimitExceededException` mid-request (rate limit hit between our check and the actual call):
```python
except RateLimitExceededException as exc:
    limiter.update_from_exception(exc)  # refresh state and wait
    return func(*args, **kwargs)         # retry once after waiting
```

---

## 8. Caching Architecture

Phase 1 never re-fetches a repo that was already ingested (unless `--force` is used). This is important because fetching a large repo takes significant API quota.

### Cache Lookup Flow:
```
python main.py https://github.com/pallets/flask

1. parse URL → owner="pallets", repo_name="flask"
2. list_fetched_repos(DATA_DIR) → scan all data/repos/ subfolders
3. For each folder: read manifest.json → extract owner, repo_name, timestamp
4. Check if "pallets/flask" already in list
5a. Found + complete → print stats, ask user to use --force, exit
5b. Found + incomplete (previous crash) → re-fetch automatically
5c. Not found → proceed with full fetch
```

### Incomplete Fetch Detection:
A manifest is considered incomplete if it's missing any of these required keys:
```python
required_keys = {"codeautopsy_version", "fetch_timestamp", "repo",
                 "ingestion_stats", "language_analysis", "files"}
```

If a manifest is missing any of these (crash mid-write), the system treats it as incomplete and offers to re-fetch rather than silently using corrupt data.

### Old Fetch Rotation:
```
Before new fetch:                  After --force or incomplete detected:
data/repos/                        data/repos/
└── pallets__flask/                ├── pallets__flask/           ← new fetch
    ├── manifest.json              │   ├── manifest.json
    └── files/                     │   └── files/
                                   └── pallets__flask__2024-01-15T10-30-00/  ← backup
                                       ├── manifest.json
                                       └── files/
```
