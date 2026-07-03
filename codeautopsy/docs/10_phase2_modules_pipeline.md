# Phase 2 — Pipeline Modules

The pipeline modules take the `list[ParsedFile]` produced by the parsers and build the higher-level intelligence: dependency graphs, call graphs, entry point detection, and architectural pattern analysis. All pipeline modules are orchestrated by `parse_orchestrator.py`.

---

## `parsing/dependency_builder.py` — Cross-file Dependency Map

**Role:** Resolves every import in every file to its actual target file (if local), then builds a directed graph of which files depend on which.

**Input:** `list[ParsedFile]`, `repo_owner`, `repo_name`
**Output:** `DependencyMap`

### `build_dependency_map(parsed_files, repo_owner, repo_name)` → `DependencyMap`

**Step-by-step:**

1. **Build lookup structures** — `path_set` for O(1) lookup, `path_by_stem` index mapping filename stems to full paths (used for extension-agnostic resolution)

2. **Classify each import** — `is_local` → attempt resolution, `is_third_party` → add to external deps, `is_stdlib` → record but don't resolve

3. **Resolve local imports** — call `_resolve_local_import()` which tries 10+ candidate paths

4. **Build adjacency dicts** — `adjacency[from] = [to1, to2, …]`, `reverse_adjacency[to] = [from1, from2, …]`

5. **Detect cycles** — call `detect_circular_dependencies()` and log warnings for any found

6. **Return DependencyMap**

### Local Import Resolution Algorithm

For a file at `services/user_service.py` importing `from .models import User`:

```
from_file = "services/user_service.py"
from_dir  = "services"   (normalized — "." becomes "")

module = ".models"
dots   = 1  (one dot = same directory)
rel_part = "models"
base_dir = "services"  (no upward navigation for 1 dot)

candidate_base = "services/models"

Candidates tried (in order):
  "services/models"
  "services/models.py"     ← FOUND ✓
  "services/models.js"
  "services/models.ts"
  "services/models.tsx"
  "services/models.go"
  "services/models.rs"
  "services/models/__init__.py"
  "services/models/index.js"
  "services/models/index.ts"
```

For `from pathlib import Path` (absolute stdlib import):
- `is_stdlib=True` → skip resolution
- Add edge with `to_file=None`, `dependency_type="stdlib"`

For `import requests` (absolute third-party):
- `is_third_party=True` → add `"requests"` to `external_dependencies`
- Add edge with `to_file=None`, `dependency_type="third_party"`

### `detect_circular_dependencies(dep_map)` → `list[list[str]]`

Uses iterative DFS with a visited set and an in-stack set:

```
For each unvisited file:
  DFS: mark visited + in-stack
  For each neighbour:
    if not visited → recurse
    if in_stack → CYCLE FOUND (slice stack from neighbour to current)
  Pop from stack
```

Returns list of cycles. Each cycle is a list of file paths forming a closed loop:
```python
["services/a.py", "services/b.py", "services/a.py"]
```

### `get_most_imported_files(dep_map, top_n=10)` → `list[tuple[str, int]]`

Returns the files with the highest **in-degree** (imported by the most other files). These are the "core" files — utilities, models, config modules that the rest of the codebase depends on.

---

## `parsing/call_graph_builder.py` — Function Call Graph

**Role:** Builds a directed graph where nodes are functions (qualified names) and edges are "function A calls function B". Uses import context to resolve cross-file call targets.

**Input:** `list[ParsedFile]`, `DependencyMap`, `repo_owner`, `repo_name`
**Output:** `CallGraph`

### `build_call_graph(parsed_files, dependency_map, …)` → `CallGraph`

**Step-by-step:**

1. **Build name index** — `name_index[raw_name] = [(qualified_name, file_path), …]` for every function in every file. Both the bare name and qualified name are indexed.

2. **Build per-file import maps** — for each file, resolve locally-imported names to their qualified forms. If `from services.user import UserService` is found, `local_imports["UserService"] = "UserService"`.

3. **Resolve each call** — for every `fn.calls` entry, call `_resolve_callee()`.

4. **Build adjacency dicts** — `adjacency[caller_qname] = [callee_qname, …]`, `reverse_adjacency[callee_qname] = [caller_qnames]`.

5. **Return CallGraph**.

### Callee Resolution Priority

```
For callee_name "process_user":

Priority 1: Local import map
  "from services.user import process_user"
  → local_imports["process_user"] = "UserService.process_user"
  → RESOLVED ✓

Priority 2: Same-file functions
  name_index["process_user"] filtered to current file
  → RESOLVED ✓ (if found)

Priority 3: Global index, unambiguous match
  name_index["process_user"] has exactly one entry across all files
  → RESOLVED ✓

Priority 4: Method call decomposition
  "svc.process" → look up "process" in name index
  → RESOLVED ✓ (if unambiguous)

Priority 5: Unresolvable
  → CallEdge with is_resolved=False, callee_resolved=None
```

### Builtin Filtering

Before any edge is created, callee names are checked against a combined builtin set:
- **~50 Python builtins:** `print`, `len`, `range`, `str`, `int`, `isinstance`, `Exception`, etc.
- **~30 JS builtins:** `console`, `setTimeout`, `fetch`, `Promise`, `JSON`, `Math`, etc.

Builtins are skipped — they would add thousands of edges to universally-called names and dilute the graph.

### `find_orphan_functions(call_graph)` → `list[str]`

Returns all functions that have zero in-edges (never called by anything).
These could be: entry points, dead code, or utility functions only called from outside the repo.

### `find_hub_functions(call_graph, top_n=10)` → `list[str]`

Returns the functions with the most callers (highest in-degree). These are the "hub" utilities — things like `validate()`, `get_db()`, `logger.error()` that appear throughout the codebase.

### `get_call_depth(call_graph, start_function)` → `dict[str, int]`

BFS from a starting function. Returns depth of every reachable function:
```python
{"main": 0, "fetch_data": 1, "parse_response": 2, "validate_item": 3}
```

---

## `parsing/entry_point_finder.py` — Entry Point Detection

**Role:** Identify which files are the "start" of execution using a multi-signal weighted scoring system.

**Input:** `list[ParsedFile]`, `DependencyMap`
**Output:** `list[dict]` sorted by confidence (HIGH → MEDIUM → LOW)

### `find_entry_points(parsed_files, dependency_map)` → `list[dict]`

Each returned dict:
```python
{
    "file_path":        "src/main.py",
    "confidence":       "high",         # "high" | "medium" | "low"
    "confidence_score": 8,              # raw score (not exposed to user)
    "signals":          ["has_main_block", "filename_is_main.py", ...],
    "entry_functions":  ["main"],       # qualified function names if found
}
```

### Scoring Signals

| Signal | Score | Notes |
|--------|-------|-------|
| `has_main_block` | +3 | `if __name__` + `__main__` in source |
| Filename in HIGH_FILENAMES set | +3 | `main.py`, `index.js`, `main.go`, `main.rs`, etc. |
| Parser flagged as entry point | +2 | Parser's `detect_entry_point()` returned True |
| Not imported by anyone, but imports others | +2 | Top of dependency tree |
| Java `main` method (static) | +3 | `public static void main` with `is_static=True` |
| Has bare `main` function | +2 | Any language |
| Filename in MEDIUM_FILENAMES set | +2 | `app.py`, `server.py`, `run.py`, `cli.ts`, etc. |
| Root-level file | +1 | No `/` in file path |
| Web framework instantiation | +2 | `Flask(`, `FastAPI()`, `express()`, `gin.New()`, etc. |
| CLI setup | +2 | `argparse`, `click`, `typer`, `cobra`, etc. in body |
| No exports (JS/TS) | +1 | No `module.exports` or `export` → likely a script |

**Confidence tiers:**
- Score ≥ 5 → `"high"`
- Score 3–4 → `"medium"`
- Score 1–2 → `"low"`
- Score 0 → not included

Files with zero signals are excluded from results entirely.

---

## `parsing/pattern_detector.py` — Architectural Pattern Detection

**Role:** Detect high-level software architecture patterns by analyzing file paths, import names, function names, and directory structure.

**Input:** `list[ParsedFile]`, `DependencyMap`, `list[str]` (all repo file paths)
**Output:** `list[dict]` sorted by confidence descending (only patterns ≥ 20% confidence)

Each returned dict:
```python
{
    "pattern":    "REST API",
    "confidence": 0.75,         # 0.0 – 1.0
    "evidence":   [
        "Found 'api/' directory",
        "REST framework import detected: flask",
        "3 route decorator(s) found",
    ]
}
```

### Detected Patterns

| Pattern | Key Signals |
|---------|------------|
| **MVC** | `models/`, `views/`, `controllers/` directories; Django: `models.py` + `views.py` + `urls.py`; Rails: `app/models` + `app/views` |
| **Layered Architecture** | `services/`, `repositories/`, `handlers/` directories; service file importing from repository; service/usecase/handler function names |
| **REST API** | `routes/`, `endpoints/`, `api/` directories; Flask/FastAPI/Express/Spring imports; route decorators (`@app.get`, `@GetMapping`); serializers |
| **Event-driven** | `events/`, `handlers/`, `listeners/` directories; Celery/Kafka/RabbitMQ imports; `on_`, `handle_`, `emit`, `publish` function names |
| **Microservices** | `docker-compose` file present; Kubernetes/Helm configs; multiple independent `main.*` files in subdirectories; HTTP client imports |
| **CLI Application** | `cli/`, `commands/` directories; Click/Argparse/Typer/Cobra/Commander imports |
| **Plugin/Extension** | `plugins/`, `extensions/` directories; `register_plugin`, `add_extension` function names |
| **Frontend Component** | `components/`, `pages/` directories; `.jsx`/`.tsx` files present; React/Vue/Angular imports |

### Confidence Calculation

Each detector accumulates signal scores and divides by a maximum expected score to produce a 0.0–1.0 value. Scores are capped at 1.0. A threshold of 0.20 (20% confidence) is required for a pattern to appear in results.

Example — REST API detector:
```
Signals:
  "routes/" found in paths  → +1   (max 1 per path signal)
  Flask import found        → +2
  15 route decorators       → +min(15/5, 2) = +2

Total: 5 / max(6) = 0.83 → 83% confidence
```

---

## `parsing/parse_orchestrator.py` — Main Orchestrator

**Role:** Ties everything together. Reads Phase 1 output, runs all parsers, runs all pipeline modules, and writes Phase 2 output. The Phase 2 equivalent of `ingestion/file_fetcher.py`.

**Entry point:** `parse_repository(repo_folder, force_reparse=False)` → `ParseManifest`

### `parse_repository(repo_folder, force_reparse)` → `ParseManifest`

**Step-by-step execution:**

```
1. Load Phase 1 manifest.json
   → Extract: owner, repo_name, files list, language stats

2. Cache check
   → If parsed/parse_manifest.json exists and force_reparse=False:
      Return cached ParseManifest immediately (zero re-work)

3. Create output directories
   → parsed/
   → parsed/files/

4. For each file in manifest["files"]:
   a. Read source from files/{path}
   b. get_parser_for_language(language, file_path)
   c. parser.parse_file(file_path, source_code)
   d. Stamp SHA from manifest into ParsedFile.sha
   e. Append to parsed_files list
   f. Save as parsed/files/{sha}.json
   g. Accumulate function/class/import counts for progress logging

5. build_dependency_map(parsed_files)
   → Save parsed/dependency_map.json

6. build_call_graph(parsed_files, dep_map)
   → Save parsed/call_graph.json

7. find_entry_points(parsed_files, dep_map)
   → Save parsed/entry_points.json

8. detect_patterns(parsed_files, dep_map, repo_all_paths)
   → Save parsed/patterns.json

9. Assemble ParseManifest
   → Save parsed/parse_manifest.json

10. Return ParseManifest
```

### Error Handling

| Error | Handling |
|-------|---------|
| `manifest.json` missing | `FileNotFoundError` raised (caller shows clean message) |
| `manifest.json` malformed | `ValueError` raised |
| Source file missing on disk | Logged + counted in `total_files_failed`, pipeline continues |
| Source file read error | Logged + counted, pipeline continues |
| Parser crash (unexpected) | Creates `ParsedFile` with `parse_success=False`, pipeline continues |
| JSON write failure | Logged, pipeline continues |
| `KeyboardInterrupt` | Propagated to `main.py` for clean exit message |

### Progress Logging

The orchestrator logs progress every 25 files (and at start/end):
```
[INFO] Parsed 0/156 files | 0 functions | 0 classes found so far
[INFO] Parsed 25/156 files | 312 functions | 47 classes found so far
[INFO] Parsed 50/156 files | 678 functions | 103 classes found so far
```

### Output Files Summary

| File | Size (typical) | Contents |
|------|---------------|----------|
| `parse_manifest.json` | 1–2 KB | Summary counts, patterns, entry points |
| `dependency_map.json` | 10–200 KB | All import edges + adjacency dicts |
| `call_graph.json` | 50–500 KB | All call edges + adjacency dicts |
| `entry_points.json` | 1–10 KB | Entry point candidates with signals |
| `patterns.json` | 1–5 KB | Detected patterns with evidence |
| `files/{sha}.json` | 2–500 KB each | One per source file |

---

## `main.py` — Updated CLI (Phase 2 Additions)

**Role:** Adds `parse` and `run` subcommands to the existing `ingest` and `list` commands.

### Subcommand Dispatch

```
main()
├── args.command == "ingest"  → _cmd_ingest(args)
├── args.command == "parse"   → _cmd_parse(args)
├── args.command == "run"     → _cmd_run(args)  → _cmd_ingest → _cmd_parse
├── args.command == "list"    → _cmd_list()
└── args.command is None      → backward-compat → "ingest"
```

### `_cmd_parse(args)` — Phase 2 CLI Handler

1. Parse and normalize the URL (same as ingest, for repo folder lookup)
2. Check `data/repos/{owner}__{repo}/manifest.json` exists — if not, exit with helpful message
3. Call `parse_orchestrator.parse_repository(repo_folder, force_reparse=args.force)`
4. Print Phase 2 summary box

### Phase 2 Summary Box

```
╔════════════════════════════════════════════════════╗
║  CodeAutopsy — Parse Complete                      ║
╠════════════════════════════════════════════════════╣
║  Repo        : pallets/itsdangerous                ║
║  Files       : 15 parsed / 0 failed                ║
║  Functions   : 119 extracted                       ║
║  Classes     : 29 extracted                        ║
║  Imports     : 120 extracted                       ║
║  Call Edges  : 259 mapped                          ║
║  Patterns    : None detected                       ║
║  Entry Point : None detected                       ║
║  Time        : 0.4 seconds                         ║
║  Saved to    : data/repos/pallets__itsdangerous/parsed/║
╚════════════════════════════════════════════════════╝
```

### Backward Compatibility

The original Phase 1 usage still works unchanged:
```bash
# These still work exactly as before
python main.py https://github.com/pallets/flask
python main.py pallets/flask --branch 2.x
python main.py pallets/flask --force
python main.py --list
```

The `--list` flag is mapped to the new `list` subcommand. Positional URLs without a subcommand route to `ingest`.

---

## `config.py` — Phase 2 Constants

The following constants were appended to the existing `config.py` for Phase 2:

| Constant | Type | Value | Purpose |
|----------|------|-------|---------|
| `STDLIB_MODULES_PYTHON` | `frozenset[str]` | ~80 names | Python stdlib classification |
| `STDLIB_MODULES_NODE` | `frozenset[str]` | ~30 names | Node.js stdlib classification |
| `MAX_FUNCTION_BODY_CHARS` | `int` | 50,000 | Truncation threshold for `full_body` |
| `MAX_FILE_PARSE_TIMEOUT_SECONDS` | `int` | 30 | SIGALRM timeout per file |
| `MINIFIED_LINE_LENGTH_THRESHOLD` | `int` | 10,000 | Skip files with lines this long |
| `COMPLEXITY_KEYWORDS` | `dict[str, list[str]]` | 12 languages | Per-language branching keywords |
| `ENTRY_POINT_PATTERNS` | `dict[str, list[str]]` | 8 languages | Known entry point filename/content patterns |
| `ARCHITECTURAL_PATTERN_SIGNALS` | `dict[str, list[str]]` | 8 patterns | Path/content signals per pattern |
| `PARSED_DIR_NAME` | `str` | `"parsed"` | Output directory name |
| `PARSE_MANIFEST_FILENAME` | `str` | `"parse_manifest.json"` | Summary file name |

---

## `tests/test_phase2.py` — Phase 2 Test Suite

**46 unit tests**, organized by module:

| Test Class | Tests | What it tests |
|------------|-------|--------------|
| `TestPythonParser` | 20 | Functions, classes, imports, annotations, async, static, dunder, complexity, calls, main block, syntax errors, empty files, nested functions, return types, private/public |
| `TestJavaScriptParser` | 7 | ES6 imports, arrow functions, async functions, class detection, class heritage, exports |
| `TestDependencyBuilder` | 5 | Local dependency resolved, adjacency dict, circular dependency detection, external deps, no self-loops |
| `TestCallGraphBuilder` | 2 | Call edge creation, orphan function detection |
| `TestEntryPointFinder` | 2 | Main block → high confidence, utility file → not flagged |
| `TestPatternDetector` | 3 | MVC path signals, CLI imports, no false positives on empty repo |
| `TestFileHasher` | 4 | Hash length, determinism, different paths → different hashes |
| `TestJsonSerialization` | 2 | Dataclass roundtrip, nested dataclass with parameters |

**Additional test classes** (skipped unless data is present):
- `TestFullPipelineIntegration` — marked `@pytest.mark.integration`, requires `pallets/itsdangerous` to be fetched
- `TestPerformance` — marked `@pytest.mark.slow`, verifies 50 files parse in under 60 seconds

### Running Tests

```bash
# All Phase 2 unit tests (fast, no network required)
python3 -m pytest tests/test_phase2.py -v -m "not integration and not slow"

# All tests (Phase 1 + Phase 2)
python3 -m pytest tests/ -v -m "not integration and not slow"

# Integration test (requires pallets/itsdangerous to be fetched)
python3 -m pytest tests/test_phase2.py -v -m integration

# Performance test
python3 -m pytest tests/test_phase2.py -v -m slow
```

---

## End-to-End Verification Results

Tested on `pallets/itsdangerous` (pure Python library, 15 code files):

| Metric | Result |
|--------|--------|
| Files parsed | 15 / 15 |
| Files failed | 0 |
| Functions extracted | 119 |
| Classes extracted | 29 |
| Imports extracted | 120 |
| Call edges mapped | 259 |
| Dependency edges | varies |
| Parse time | 0.4 seconds |
| Patterns detected | 0 (expected — small utility library) |
| Entry points | Low confidence (no explicit main block in library) |
| Regex fallback files | 1 (Shell script `.sh`) |
