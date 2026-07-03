# Module Reference — Part 1: Foundation Modules

This document covers the three foundational modules that every other module in Phase 1 depends on. These have **zero project-level dependencies** between them — they are the bottom of the dependency chain.

## Table of Contents
1. [config.py — The Single Source of Truth](#1-configpy--the-single-source-of-truth)
2. [utils/logger.py — Centralized Logging](#2-utilsloggerpy--centralized-logging)
3. [utils/rate_limiter.py — API Quota Manager](#3-utilsrate_limiterpy--api-quota-manager)

---

## 1. `config.py` — The Single Source of Truth

**File:** `codeautopsy/config.py`  
**Role:** Defines every constant used across the entire codebase. No magic strings or hardcoded numbers are allowed anywhere else.  
**Dependencies:** None (pure Python constants)

### Why this module exists
Without a central constants file, values like `"node_modules"` or `500000` would be scattered across multiple files. When requirements change (e.g. raising the max file size to 1 MB, or adding a new language), you'd need to hunt for every occurrence. With `config.py`, you change one line and the change propagates everywhere.

---

### Constants Reference

#### `SUPPORTED_EXTENSIONS` (dict)
Maps language name → list of file extensions that belong to that language.

```python
SUPPORTED_EXTENSIONS: dict[str, list[str]] = {
    "Python":      [".py", ".pyi", ".pyw"],
    "JavaScript":  [".js", ".mjs", ".cjs", ".jsx"],
    "TypeScript":  [".ts", ".tsx"],
    "Java":        [".java"],
    "Go":          [".go"],
    "Rust":        [".rs"],
    "C":           [".c", ".h"],
    "C++":         [".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h++"],
    "Ruby":        [".rb", ".rake", ".gemspec"],
    "PHP":         [".php", ".php3", ".php4", ".php5", ".phtml"],
    "Swift":       [".swift"],
    "Kotlin":      [".kt", ".kts"],
    "Scala":       [".scala", ".sc"],
    "Shell":       [".sh", ".bash", ".zsh", ".fish", ".ksh"],
    # + 14 more: R, Elixir, Haskell, Lua, Perl, Dart, C#, F#, Clojure,
    #             Erlang, Julia, Nim, Zig, OCaml
}
```

**Used by:** `file_filter.py`, `language_detector.py`

#### `EXTENSION_TO_LANGUAGE` (dict)
Auto-generated reverse lookup: extension → language name. All keys are lowercase.

```python
# Auto-built at module load time from SUPPORTED_EXTENSIONS:
EXTENSION_TO_LANGUAGE = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    # ... all extensions from all languages
}
```

**Used by:** `file_filter.get_file_language()`, `language_detector.detect_languages()`

#### `IGNORED_DIRECTORIES` (frozenset)
Set of directory names that trigger automatic skipping. Matched against **every component** of a file path, not just the top level.

```
node_modules  .git  __pycache__  .pytest_cache  venv  env  .env  .venv
dist  build  target  out  bin  obj  _build  output
.next  .nuxt  .svelte-kit  bower_components
coverage  .coverage  htmlcoverage  .nyc_output
__mocks__  fixtures  snapshots  __fixtures__
.idea  .vscode  .vs  .DS_Store  .Trash
vendor  packages  .gradle  .m2  .cargo
tmp  temp  .cache  log  logs
eggs  wheels  .eggs  .tox
```

**Used by:** `file_filter.is_ignored_directory()`

#### `IGNORED_FILE_PATTERNS` (list of str)
Glob patterns matched against the filename only (not the full path), using `fnmatch`.

```
*.min.js    *.min.css    *.map       *.bundle.js   *.chunk.js
*.lock      package-lock.json        yarn.lock     poetry.lock
Pipfile.lock  composer.lock          Gemfile.lock  cargo.lock
*.sum       *.pyc        *.pyo       *.class       *.o
*.a         *.so         *.dll       *.dylib       *.exe
*.wasm      *.pb.go      *_gen.go    *.g.dart
.DS_Store   Thumbs.db    *.orig      *.rej
```

> **Note:** `go.mod` is intentionally NOT in this list. It is a critical Go module file that the AST parser needs.

**Used by:** `file_filter.is_ignored_pattern()`

#### Size and Volume Constants
```python
MAX_FILE_SIZE_BYTES  = 500_000    # 500 KB per individual file
MAX_REPO_FILES       = 5_000      # Soft warning threshold (not a hard stop)
MAX_TOTAL_SIZE_BYTES = 50_000_000 # 50 MB total across all files in one fetch
```

**Used by:** `file_filter.is_within_size_limit()`, `file_fetcher.fetch_repository()`

#### GitHub API Constants
```python
GITHUB_API_BASE_URL     = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES             = 3
RETRY_DELAY_SECONDS     = 2.0
RATE_LIMIT_BUFFER       = 10    # Pause if remaining quota <= this value
```

**Used by:** `github_client.py`, `rate_limiter.py`

#### Path Constants
```python
_PACKAGE_ROOT = Path(__file__).parent.resolve()  # codeautopsy/ directory
DATA_DIR      = _PACKAGE_ROOT / "data" / "repos" # where repos are saved
```

**Used by:** `storage.py`, `main.py`

#### Logging Constants
```python
LOG_FORMAT       = "[%(asctime)s] [%(levelname)-8s] [%(name)s] — %(message)s"
LOG_DATE_FORMAT  = "%Y-%m-%dT%H:%M:%S"
LOG_LEVEL_DEFAULT = "INFO"
```

**Used by:** `utils/logger.py`

#### Binary Detection Thresholds
```python
BINARY_DETECTION_SAMPLE_BYTES    = 8_000  # Inspect first 8 KB of content
BINARY_NULL_BYTE_THRESHOLD       = 0.01   # >1% null bytes  → binary
BINARY_NONPRINTABLE_THRESHOLD    = 0.30   # >30% non-printable chars → binary
```

**Used by:** `file_filter.is_likely_binary()`

---

## 2. `utils/logger.py` — Centralized Logging

**File:** `codeautopsy/utils/logger.py`  
**Role:** Factory for named loggers that simultaneously write to the console (with ANSI color) and to a per-repo `fetch.log` file.  
**Dependencies:** `config.py`

### Why this module exists
Python's `logging` module needs to be configured once and shared. Without centralization, each module would configure its own handler, resulting in duplicate log lines, inconsistent formats, and no unified log file. This module provides a single `get_logger(__name__)` call that any module can use to get a properly configured logger.

---

### Public API

#### `get_logger(name: str) → logging.Logger`
The primary function. Returns (or retrieves from cache) a named logger with:
- A colored console handler (colors disabled automatically if stdout is not a TTY)
- A file handler pointing to `fetch.log` (if `set_log_file()` or `configure_for_repo()` was called)

```python
# Usage in any module:
from utils.logger import get_logger
logger = get_logger(__name__)

logger.debug("Verbose internal detail")
logger.info("Normal progress update")
logger.warning("Something unexpected but not fatal")
logger.error("Something failed but run continues")
logger.critical("Run is aborting")
```

#### `set_log_file(log_path: Path) → None`
Configure a global log file path. All subsequent `get_logger()` calls will attach a `FileHandler` pointing to this path. The parent directory is created automatically.

#### `configure_for_repo(repo_folder: Path) → None`
Convenience function called once the repo output directory is created. Sets the log file to `{repo_folder}/fetch.log` and retroactively attaches the file handler to **all existing loggers** (so even loggers created before this call will start writing to the file).

```python
# Called from storage.save_fetch_result():
configure_for_repo(Path("data/repos/pallets__flask"))
# → Creates data/repos/pallets__flask/fetch.log
# → All subsequent log lines from all modules go to this file
```

---

### Log Format

```
[2024-01-15T10:30:00] [INFO    ] [ingestion.file_fetcher] — Starting ingestion of github.com/pallets/flask
[2024-01-15T10:30:01] [WARNING ] [ingestion.github_client] — No GitHub token configured. Anonymous API access is limited to 60 requests per hour.
[2024-01-15T10:30:01] [DEBUG   ] [ingestion.file_filter] — SKIP "docs/quickstart.rst" — unsupported extension: .rst
[2024-01-15T10:30:13] [INFO    ] [ingestion.file_fetcher] — Progress: 50/84 files fetched (373.9 KB so far)
```

**Components:**
- `[TIMESTAMP]` — ISO 8601 datetime to the second
- `[LEVEL]` — padded to 8 chars: DEBUG, INFO, WARNING, ERROR, CRITICAL
- `[module.name]` — Python module path (maps directly to the file that logged it)
- `— message` — the actual log message

### Console Colors (when stdout is a TTY)

| Level | Color |
|-------|-------|
| DEBUG | Cyan |
| INFO | Green |
| WARNING | Yellow |
| ERROR | Red |
| CRITICAL | Magenta |

Colors are automatically disabled when output is piped to a file or another process (`sys.stdout.isatty()` returns False).

---

### Implementation Notes

**Duplicate handler prevention:** `get_logger()` checks `logger.handlers` before adding new handlers. If a logger is retrieved twice, it gets the same handlers — not doubled-up handlers.

**Log propagation disabled:** All loggers have `propagate = False` to prevent messages from bubbling up to the root logger and being printed twice.

**Thread safety:** Python's `logging` module uses internal locks for thread-safe handler access. The `_file_handlers` dict is module-level shared state, but since loggers are typically initialized before threads start, race conditions are not a concern in Phase 1's single-threaded design.

---

## 3. `utils/rate_limiter.py` — API Quota Manager

**File:** `codeautopsy/utils/rate_limiter.py`  
**Role:** Tracks GitHub API rate limit state and automatically pauses execution when quota runs low, preventing failed API calls due to exhaustion.  
**Dependencies:** `utils/logger.py`, `PyGithub`

### Why this module exists
The GitHub API enforces hourly request limits. Without rate limit management, the application would fail mid-fetch with cryptic `403` errors whenever the quota is exhausted. The `RateLimiter` handles this transparently: it checks quota before each call, waits if needed, and retries if a limit is hit unexpectedly.

---

### `RateLimitStatus` Dataclass

```python
@dataclass
class RateLimitStatus:
    limit:     int       # Total requests allowed per hour (60 or 5000)
    remaining: int       # Requests left in current window
    reset_at:  datetime  # UTC time when window resets
    used:      int       # Requests consumed so far

    def seconds_until_reset(self) -> float:
        """How many seconds until the quota window resets."""
```

---

### `RateLimiter` Class

#### Constructor
```python
limiter = RateLimiter(github_client=github_obj, buffer=10)
```
- `github_client`: An authenticated `github.Github()` object
- `buffer`: Stop and wait when `remaining <= buffer` (default: 10)
- Immediately calls `_refresh()` to populate initial quota state

#### `check_and_wait() → None`
The primary method. Called before every API operation.

```
if remaining <= buffer (10):
  compute wait = reset_at - now + 2 seconds safety margin
  log warning: "Rate limit low (8/60 remaining). Waiting 847 seconds until reset at 11:00:00 UTC."
  sleep in 15-second intervals, logging countdown each time
  after reset: call _refresh() to verify quota restored
  log info: "Rate limit window has reset. Resuming."
```

#### `get_rate_limit_status() → dict`
Returns current state for display or logging:
```python
{
    "remaining": 42,
    "limit": 60,
    "used": 18,
    "reset_time": "2024-01-15T11:00:00+00:00",
    "seconds_until_reset": 847.0
}
```

#### `update_from_exception(exc: GithubException) → None`
Called when a `RateLimitExceededException` is raised unexpectedly mid-request. Refreshes state and calls `check_and_wait()` to recover automatically.

#### `rate_limited` (decorator factory)
```python
@limiter.rate_limited
def fetch_something():
    return github.get_repo("owner/repo")
```
Wraps any callable to automatically call `check_and_wait()` before each invocation and handle `RateLimitExceededException` with one automatic retry.

---

### PyGithub 2.x Compatibility Note

PyGithub 2.x changed the structure of `get_rate_limit()`:

| PyGithub version | Rate limit access |
|-----------------|-------------------|
| 1.x | `rl = gh.get_rate_limit()` → `rl.core.remaining` |
| 2.x | `rl = gh.get_rate_limit()` → `rl.resources.core.remaining` |

The `_refresh()` method handles both versions:
```python
rl = self._gh.get_rate_limit()
if hasattr(rl, "resources") and hasattr(rl.resources, "core"):
    core = rl.resources.core          # PyGithub 2.x
elif hasattr(rl, "core"):
    core = rl.core                    # PyGithub 1.x
```

---

### Internal Refresh Strategy

The rate limiter uses two refresh triggers:

1. **On initialization** — fetch fresh state so we start with accurate numbers
2. **Every 50 decrements** — after counting down 50 calls using internal tracking (`_refresh_if_stale()`), re-sync with the real GitHub API state. This corrects drift caused by requests made outside the RateLimiter's tracking scope.

The internal counter (`self._status.remaining -= 1`) is faster than a live API call but can drift. The periodic re-sync keeps it accurate without adding per-request overhead.
