# Module Reference — Part 2: Ingestion Modules (Input & Filtering)

This document covers the three modules that handle input validation, GitHub API communication, and file filtering decisions.

## Table of Contents
1. [ingestion/url_parser.py — URL Validation & Normalization](#1-ingestionurl_parserpy--url-validation--normalization)
2. [ingestion/github_client.py — GitHub API Wrapper](#2-ingestiongithub_clientpy--github-api-wrapper)
3. [ingestion/file_filter.py — File Filtering Logic](#3-ingestionfile_filterpy--file-filtering-logic)

---

## 1. `ingestion/url_parser.py` — URL Validation & Normalization

**File:** `codeautopsy/ingestion/url_parser.py`  
**Role:** Accept any raw string a user might type as a GitHub repo reference and return a clean, validated, structured `ParsedURL` object.  
**Dependencies:** `utils/logger.py` (no other project dependencies)  
**Single Responsibility:** URL → (owner, repo_name, branch). Nothing else.

### Why this module exists
Users type GitHub URLs in many different ways. Before the application can make any API call, it needs clean, validated `owner` and `repo_name` strings. This module isolates all the messy string parsing in one place so no other module ever deals with raw URLs.

---

### `ParsedURL` Dataclass

```python
@dataclass(frozen=True)
class ParsedURL:
    owner:          str            # "pallets" (always lowercase)
    repo_name:      str            # "flask" (always lowercase, no .git suffix)
    branch:         Optional[str]  # "main" or None
    original_url:   str            # The raw input string, preserved unchanged
    normalized_url: str            # "https://github.com/pallets/flask"
```

`frozen=True` makes it immutable — a ParsedURL is a fact, not mutable state.

---

### `parse_github_url(raw_input: str) → ParsedURL`

The single public function. Tries three parsers in order:

```
1. _try_ssh(raw)       → handles git@github.com:owner/repo.git
2. _try_shorthand(raw) → handles owner/repo
3. _try_http_url(raw)  → handles all http/https/no-protocol variants
```

First parser that succeeds wins. If all three fail, raises `ValueError`.

After extraction:
1. Strips `.git` suffix from repo name if present
2. Validates owner against GitHub's naming rules
3. Validates repo name against GitHub's naming rules
4. Lowercases both owner and repo name
5. Builds normalized URL: `https://github.com/{owner}/{repo_name}`

---

### Supported Input Formats

| Input Format | Example | Extracted |
|-------------|---------|-----------|
| HTTPS basic | `https://github.com/pallets/flask` | owner=pallets, repo=flask |
| HTTPS with trailing slash | `https://github.com/pallets/flask/` | owner=pallets, repo=flask |
| HTTPS with .git | `https://github.com/pallets/flask.git` | owner=pallets, repo=flask |
| HTTPS tree (with branch) | `https://github.com/pallets/flask/tree/main` | branch=main |
| HTTPS tree (with subfolder) | `https://github.com/pallets/flask/tree/main/src` | branch=main |
| HTTPS blob (file URL) | `https://github.com/pallets/flask/blob/main/app.py` | branch=main |
| HTTP (non-SSL) | `http://github.com/pallets/flask` | owner=pallets, repo=flask |
| No protocol | `github.com/pallets/flask` | owner=pallets, repo=flask |
| SSH format | `git@github.com:pallets/flask.git` | owner=pallets, repo=flask |
| Shorthand | `pallets/flask` | owner=pallets, repo=flask |

---

### Error Cases

| Input | Error Message |
|-------|---------------|
| `""` (empty) | "No URL provided. Please supply a GitHub repository URL." |
| `"https://gitlab.com/user/repo"` | "The URL points to 'gitlab.com', which is not GitHub. CodeAutopsy currently supports GitHub repositories only." |
| `"https://github.com/pallets"` | "The URL appears to be a GitHub *user/org* page, not a repository URL." |
| `"not-a-url"` | "Unrecognised host 'not-a-url'. Only github.com URLs are supported." |
| Owner > 39 chars | "Owner name is 45 characters long; GitHub limits owner names to 39 characters." |
| Invalid owner chars | "Owner name contains invalid characters. GitHub owner names may only contain alphanumeric characters and hyphens." |

---

### Internal Parsers

#### `_try_ssh(raw: str)`
Uses a compiled regex:
```python
_SSH_RE = re.compile(
    r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    re.IGNORECASE,
)
```
Returns `(owner, repo, None)` on match, `(None, None, None)` otherwise. Branch is always `None` for SSH URLs (SSH doesn't encode branches).

#### `_try_shorthand(raw: str)`
Guards: must not start with `/`, `http`, or `git`. Uses:
```python
_SHORTHAND_RE = re.compile(
    r"^(?P<owner>[a-zA-Z0-9][a-zA-Z0-9\-]{0,38})/(?P<repo>[a-zA-Z0-9_.\-]+)$"
)
```

#### `_try_http_url(raw: str)`
- Prepends `https://` if no protocol present
- Parses with `urllib.parse.urlparse`
- Blocks non-GitHub hosts with targeted error messages for GitLab, Bitbucket, Codeberg, Gitea
- Strips `?query=string` from path
- Splits path into parts and extracts owner (part[0]), repo (part[1])
- Detects branch from `/tree/<branch>` or `/blob/<branch>` patterns (parts[2] and [3])

---

### Validation Rules

#### Owner Name Rules (GitHub's actual limits):
- Alphanumeric characters and hyphens only
- Cannot start or end with a hyphen
- Maximum 39 characters

```python
_OWNER_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,37}[a-zA-Z0-9])?$|^[a-zA-Z0-9]$"
)
```

#### Repo Name Rules:
- Alphanumeric, hyphens, underscores, and periods allowed
- Maximum 100 characters

```python
_REPO_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")
```

---

## 2. `ingestion/github_client.py` — GitHub API Wrapper

**File:** `codeautopsy/ingestion/github_client.py`  
**Role:** All GitHub API interactions flow through this module. Wraps PyGithub with retry logic, custom exception types, encoding handling, and rate-limit integration.  
**Dependencies:** `config.py`, `utils/logger.py`, `utils/rate_limiter.py`, `PyGithub`

### Why this module exists
Raw PyGithub calls can fail in many ways: rate limits, network errors, private repos, 500 errors, encoding issues. Without a wrapper, every call site would need its own try/except. This module centralizes all that complexity so callers get clean, typed errors and automatic retries without writing any error handling themselves.

---

### Custom Exception Hierarchy

```
Exception
└── GitHubClientError          ← Base for all GitHub errors
    ├── RepoNotFoundError      ← HTTP 404 — repo doesn't exist or was renamed
    ├── RepoPrivateError       ← HTTP 403 — private repo, need token
    └── RateLimitError         ← All retries exhausted due to rate limiting
```

**Design principle:** Callers catch specific exception types, not generic `Exception`. This allows `main.py` to show targeted error messages:
```python
except RepoNotFoundError:
    _fatal("Repository not found. Verify the owner and repo name.")
except RepoPrivateError:
    _fatal("Repository is private. Add a GitHub token to .env.")
```

---

### `GitHubClient` Class

#### Constructor
```python
client = GitHubClient(token="ghp_your_token_here")
# OR for anonymous:
client = GitHubClient(token=None)
```
- If `token` provided: calls `_verify_token()` → makes a `get_user()` call to validate
- If invalid token: raises `GitHubClientError` immediately with link to GitHub token settings
- If no token: logs warning about 60 req/hr limit
- Initializes `RateLimiter` with the authenticated `Github()` object

#### `get_repo(owner, repo_name) → Repository`
Fetches the PyGithub Repository object. Uses `_with_retry()` wrapper.

```python
repo = client.get_repo("pallets", "flask")
```

**Error mapping:**
- `UnknownObjectException(404)` → `RepoNotFoundError`
- `GithubException(403)` with "private"/"access" in message → `RepoPrivateError`
- `GithubException(401)` → `GitHubClientError` (invalid token)
- `GithubException(5xx)` → retry up to 3 times, then `GitHubClientError`

#### `get_repo_metadata(repo) → dict`
Extracts 17 metadata fields from a Repository object into a plain Python dict:

```python
metadata = client.get_repo_metadata(repo)
# Returns:
{
    "name": "flask",
    "owner": "pallets",
    "full_name": "pallets/flask",
    "description": "The Python micro framework...",
    "primary_language": "Python",      # GitHub's detected primary language
    "stars": 68000,
    "forks": 16000,
    "size_kb": 14200,
    "default_branch": "main",
    "topics": ["flask", "python", "web"],
    "created_at": "2010-04-06T21:22:00",
    "updated_at": "2024-01-15T09:00:00",
    "license": "BSD-3-Clause",
    "is_fork": False,
    "is_archived": False,
    "has_wiki": True,
    "open_issues_count": 42,
    "homepage": "https://flask.palletsprojects.com",
    "visibility": "public"
}
```

Topics are fetched via a separate `repo.get_topics()` call (wrapped in try/except in case it fails on some repo configurations).

#### `get_file_tree(repo, branch) → list[dict]`
Calls GitHub's **recursive Git Tree API** to get the complete file listing in one request.

```python
tree = client.get_file_tree(repo, branch="main")
# Returns list of:
{
    "path": "src/flask/app.py",
    "type": "blob",      # "blob"=file, "tree"=directory, "commit"=submodule
    "size": 62000,       # bytes (0 for tree entries)
    "sha": "abc123...",  # Git SHA of this version
    "url": "https://api.github.com/repos/..."
}
```

**Truncation detection:** If `tree.truncated == True`, the repo has > 100,000 files and GitHub only returned a subset. A warning is logged and the partial tree is processed.

**Submodule detection:** `type="commit"` entries are git submodules. They appear in the tree but have no fetchable content. These are counted and warned about.

#### `get_file_content(repo, file_path, branch) → Optional[str]`
Fetches and decodes the text content of a single file.

```python
content = client.get_file_content(repo, "src/flask/app.py", "main")
# Returns: decoded text string or None
```

**Decoding pipeline (`_decode_content`):**
1. Check for `encoding == "base64"` → base64 decode the raw bytes
2. Try `utf-8-sig` decode (handles UTF-8 BOM automatically)
3. Normalize `\r\n` → `\n` and `\r` → `\n` (Windows line endings)
4. On `UnicodeDecodeError`: fallback to `latin-1` (never fails, handles most Western encodings)
5. Log warning if latin-1 fallback was used
6. If both fail: log warning, return `None`

Returns `None` (does not raise) in these cases:
- File size > `MAX_FILE_SIZE_BYTES`
- File content is empty (0 bytes)
- GitHub returns unexpected format
- Both UTF-8 and latin-1 decoding fail

#### `check_repo_exists(owner, repo_name) → bool`
Quick existence check. Calls `get_repo()` and returns `True`/`False`. Used for pre-validation.

#### `create_client_from_env() → GitHubClient` (module-level factory)
Convenience function for creating a client using environment variables:
```python
from ingestion.github_client import create_client_from_env
client = create_client_from_env()  # reads GITHUB_TOKEN from .env automatically
```

---

### `_with_retry()` — Retry Logic

Every public method uses this internal helper for resilience:

```
for attempt in range(1, MAX_RETRIES + 1):   # MAX_RETRIES = 3
    try:
        return func()

    except RateLimitExceededException:
        # Tell rate limiter to wait for reset
        rate_limiter.update_from_exception(exc)
        # continue to next attempt

    except UnknownObjectException (404):
        # Never retried — repo either exists or it doesn't
        raise RepoNotFoundError(...)

    except GithubException(401):
        # Invalid token — never retried
        raise GitHubClientError("Token invalid...")

    except GithubException(403) with "private" in message:
        # Private repo — never retried
        raise RepoPrivateError(...)

    except GithubException(5xx):
        # Server error — retry with exponential backoff
        delay = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
        # attempt 1: wait 2s, attempt 2: wait 4s, attempt 3: wait 8s
        sleep(delay)

# All retries exhausted:
raise GitHubClientError("All 3 attempts failed...")
```

---

## 3. `ingestion/file_filter.py` — File Filtering Logic

**File:** `codeautopsy/ingestion/file_filter.py`  
**Role:** Decides which files in a repository tree should be fetched and which should be skipped. Applied before downloading content to preserve rate limit quota.  
**Dependencies:** `config.py`, `utils/logger.py`

### Why this module exists
Not every file in a GitHub repo is code. A typical JavaScript project has `node_modules` with 50,000 files, minified bundles, source maps, lock files, and binary assets — none of which are useful for architectural analysis. This module filters them out before any content is downloaded.

---

### Filter Functions

All filters are pure functions with no side effects. They take a file path and/or size, return a boolean.

#### `is_ignored_directory(path: str) → bool`

Checks if any **directory component** of the path is in `IGNORED_DIRECTORIES`.

```python
is_ignored_directory("src/node_modules/lodash/index.js")  # True
is_ignored_directory("src/__pycache__/module.cpython312.pyc")  # True
is_ignored_directory("venv/lib/python3.12/site-packages/flask/__init__.py")  # True
is_ignored_directory("src/models/user.py")  # False
```

**Implementation detail:** Uses `PurePosixPath(path).parts` to split the path, then checks each part (except the filename) against the `IGNORED_DIRECTORIES` frozenset. Comparison is case-insensitive (handles `Node_Modules` on case-sensitive filesystems).

#### `is_ignored_pattern(filename: str) → bool`

Checks if the **bare filename** matches any pattern in `IGNORED_FILE_PATTERNS`.

```python
is_ignored_pattern("app.min.js")      # True  (matches *.min.js)
is_ignored_pattern("app.js")          # False
is_ignored_pattern("package-lock.json")  # True (exact match)
is_ignored_pattern("go.mod")          # False (intentionally NOT in patterns)
```

Uses `fnmatch.fnmatch()` with lowercase comparison on both sides for case-insensitive matching.

#### `is_supported_code_file(path: str) → bool`

Checks if the file extension is in `EXTENSION_TO_LANGUAGE`.

```python
is_supported_code_file("src/app.py")     # True  (.py → Python)
is_supported_code_file("src/index.ts")   # True  (.ts → TypeScript)
is_supported_code_file("README.md")      # False (.md not in list)
is_supported_code_file("Script.PY")      # True  (case-insensitive: .PY = .py)
is_supported_code_file("noextension")    # False (no extension)
```

#### `is_within_size_limit(size_bytes: int) → bool`

Simple threshold check against `MAX_FILE_SIZE_BYTES` (500,000 bytes).

```python
is_within_size_limit(499_999)   # True
is_within_size_limit(500_000)   # True  (at limit = allowed)
is_within_size_limit(500_001)   # False (over limit)
```

This check uses the **tree metadata** (available before downloading), so oversized files never cost an API call.

#### `is_likely_binary(content: str) → bool`

Post-download heuristic check. Called on decoded content to catch files that have code extensions but are actually binary.

```python
# Binary (>1% null bytes):
is_likely_binary("\x00" * 100 + "some text")  # True

# Binary (>30% non-printable chars):
is_likely_binary("\x01\x02\x03" * 50 + "abc")  # True

# Normal code:
is_likely_binary("def hello():\n    print('world')\n")  # False

# Empty:
is_likely_binary("")  # False
```

**Algorithm:**
1. Sample the first `BINARY_DETECTION_SAMPLE_BYTES` (8,000) characters
2. Count null bytes (`\x00`). If > 1% of sample → binary
3. Count non-printable chars (excluding `\n`, `\r`, `\t`). If > 30% → binary

This detects:
- Compiled Java `.class` files accidentally committed
- Binary data files with code-like extensions
- Corrupted files
- Protobuf compiled outputs

---

### `should_fetch_file(path, size_bytes) → tuple[bool, str]`

The **master filter** that combines all individual predicates in strict order.

```python
# Signature
def should_fetch_file(path: str, size_bytes: int) -> tuple[bool, str]:
    ...
    return (True, "ok")       # fetch this file
    # OR
    return (False, "reason")  # skip this file
```

**Filter order (first failing check wins):**

```
1. is_ignored_directory(path)
   → False: "ignored directory: node_modules"

2. is_ignored_pattern(filename)
   → False: "ignored pattern: *.min.js"

3. is_supported_code_file(path)
   → False: "unsupported extension: .md"

4. is_within_size_limit(size_bytes)
   → False: "file too large: 623,000 bytes (limit: 500,000 bytes)"

→ All checks passed:
   True: "ok"
```

**Examples:**
```python
should_fetch_file("src/node_modules/lodash/index.js", 54000)
# → (False, "ignored directory: node_modules")

should_fetch_file("dist/bundle.min.js", 200000)
# → (False, "ignored directory: dist")
# (dist is caught first — directory check runs before pattern check)

should_fetch_file("assets/app.min.js", 80000)
# → (False, "ignored pattern: *.min.js")

should_fetch_file("README.md", 5000)
# → (False, "unsupported extension: .md")

should_fetch_file("bigfile.py", 600000)
# → (False, "file too large: 600,000 bytes (limit: 500,000 bytes)")

should_fetch_file("src/models/user.py", 8000)
# → (True, "ok")
```

Every skip reason is logged at DEBUG level:
```
[DEBUG] [ingestion.file_filter] — SKIP "src/node_modules/lodash/index.js" — ignored directory: node_modules
```

---

### `get_file_language(path: str) → Optional[str]`

Returns the language name for a file, or `None` if unrecognized.

```python
get_file_language("src/app.py")       # "Python"
get_file_language("index.ts")         # "TypeScript"
get_file_language("Makefile")         # None
get_file_language("main.rs")          # "Rust"
```

Used by:
- `file_fetcher.py` — to set the `language` field on each `FetchedFile`
- `language_detector.py` — to accumulate per-language file counts
