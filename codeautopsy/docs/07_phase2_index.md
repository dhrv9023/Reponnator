# CodeAutopsy × Repponator — Phase 2 Documentation Index

**Phase 2: Code Parsing & Structural Analysis System**

---

## What Phase 2 Does

Phase 1 gave us raw code files on disk. Phase 2 makes those files *understandable* to a machine.

It reads every code file fetched by Phase 1, runs it through a language-specific Tree-sitter parser, and extracts:

- Every **function** and **method** (name, parameters, return type, docstring, complexity, calls it makes)
- Every **class** (inheritance, interface implementation, methods, instance variables)
- Every **import** statement (classified as stdlib / third-party / local, with resolved file targets)
- Every **call relationship** across functions and files (the call graph)
- Every **cross-file dependency** (the import dependency map)
- **Entry points** — where execution starts
- **Architectural patterns** — MVC, REST API, Layered, CLI, Event-driven, etc.

The output of Phase 2 is a structured JSON representation of the entire codebase, ready for Phase 3 (chunking + embedding) and Phase 4 (RAG + diagram generation).

---

## Documentation Structure

| File | Contents |
|------|----------|
| [07_phase2_index.md](./07_phase2_index.md) | This file — Phase 2 overview, data flow, directory layout |
| [08_phase2_architecture.md](./08_phase2_architecture.md) | Design decisions, parser architecture, AST strategy, data contract |
| [09_phase2_modules_parsers.md](./09_phase2_modules_parsers.md) | All language parsers — what each extracts and how |
| [10_phase2_modules_pipeline.md](./10_phase2_modules_pipeline.md) | Dependency builder, call graph, entry points, pattern detector, orchestrator |

---

## Phase 2 Data Flow

```
Phase 1 output (read-only):
data/repos/{owner}__{repo}/
├── manifest.json          ← file list, language stats, SHAs
└── files/                 ← raw source code files
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│               parse_orchestrator.py                      │
│                                                          │
│  For every file in manifest.json:                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │ parser_registry → language-specific parser        │   │
│  │                                                    │   │
│  │  PythonParser / JavaScriptParser / GoParser / … │   │
│  │                                                    │   │
│  │  ┌─────────────────────────────────────────────┐  │   │
│  │  │ BaseParser.parse_file()                      │  │   │
│  │  │  • Encode to bytes                            │  │   │
│  │  │  • tree-sitter parse (with SIGALRM timeout)  │  │   │
│  │  │  • extract_functions()                       │  │   │
│  │  │  • extract_classes()                         │  │   │
│  │  │  • extract_imports()                         │  │   │
│  │  │  • detect_entry_point()                      │  │   │
│  │  │  → ParsedFile dataclass                      │  │   │
│  │  └─────────────────────────────────────────────┘  │   │
│  │                                                    │   │
│  │  Save: parsed/files/{sha}.json                    │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  After all files:                                        │
│  ┌────────────────────┐  ┌────────────────────────────┐ │
│  │ dependency_builder │  │    call_graph_builder       │ │
│  └────────┬───────────┘  └────────────┬───────────────┘ │
│           │                           │                  │
│  ┌────────▼───────────┐  ┌────────────▼───────────────┐ │
│  │ entry_point_finder │  │     pattern_detector        │ │
│  └────────┬───────────┘  └────────────┬───────────────┘ │
│           └───────────────┬───────────┘                  │
│                           ▼                              │
│                   ParseManifest                          │
└─────────────────────────────────────────────────────────┘
        │
        ▼
Phase 2 output:
data/repos/{owner}__{repo}/parsed/
├── parse_manifest.json    ← summary: counts, patterns, entry points
├── dependency_map.json    ← cross-file import graph
├── call_graph.json        ← function-level call graph
├── entry_points.json      ← detected entry points with confidence
├── patterns.json          ← detected architectural patterns
└── files/
    └── {sha}.json         ← per-file ParsedFile (one per source file)
```

---

## Directory Layout (Phase 2 additions)

```
codeautopsy/
├── main.py                     ← CLI entry point (updated with subcommands)
├── config.py                   ← Phase 2 constants appended
│
├── parsing/                    ← NEW — entire Phase 2 package
│   ├── __init__.py             ← All shared dataclasses + JSON serialization
│   ├── base_parser.py          ← Abstract base class for all parsers
│   ├── parser_registry.py      ← Language label → parser instance mapping
│   ├── dependency_builder.py   ← Cross-file import graph builder
│   ├── call_graph_builder.py   ← Function-level call graph builder
│   ├── entry_point_finder.py   ← Entry point detection (multi-signal)
│   ├── pattern_detector.py     ← Architectural pattern detection
│   ├── parse_orchestrator.py   ← Main Phase 2 pipeline orchestrator
│   │
│   └── languages/              ← Language-specific parsers
│       ├── __init__.py
│       ├── python_parser.py    ← Python (.py, .pyi, .pyw)
│       ├── javascript_parser.py ← JavaScript (.js, .mjs, .cjs, .jsx)
│       ├── typescript_parser.py ← TypeScript (.ts, .tsx)
│       ├── java_parser.py      ← Java (.java)
│       ├── go_parser.py        ← Go (.go)
│       ├── rust_parser.py      ← Rust (.rs)
│       ├── cpp_parser.py       ← C and C++ (.c, .h, .cpp, .cc, .hpp, …)
│       └── generic_parser.py   ← Regex fallback for unsupported languages
│
├── utils/
│   ├── logger.py               ← Unchanged from Phase 1
│   ├── rate_limiter.py         ← Unchanged from Phase 1
│   └── file_hasher.py          ← NEW — MD5/SHA-256 cache key helpers
│
├── data/repos/{owner}__{repo}/
│   ├── manifest.json           ← Phase 1 output (read-only in Phase 2)
│   ├── fetch.log               ← Phase 1 output (read-only in Phase 2)
│   ├── files/                  ← Phase 1 output (read-only in Phase 2)
│   └── parsed/                 ← NEW — Phase 2 output
│       ├── parse_manifest.json
│       ├── dependency_map.json
│       ├── call_graph.json
│       ├── entry_points.json
│       ├── patterns.json
│       └── files/
│           └── {sha}.json      ← One per successfully parsed source file
│
└── tests/
    ├── test_phase1.py          ← 60 passing tests (unchanged)
    └── test_phase2.py          ← NEW — 46 unit tests for Phase 2
```

---

## CLI Commands (Updated in Phase 2)

Phase 2 adds a full subcommand structure to `main.py` while keeping backward compatibility.

```bash
# Phase 1 only — fetch a repository
python main.py ingest https://github.com/pallets/flask
python main.py ingest pallets/flask --branch develop --force

# Phase 2 only — parse a previously-fetched repository
python main.py parse  https://github.com/pallets/flask
python main.py parse  pallets/flask --force

# Full pipeline — Phase 1 then Phase 2 back-to-back
python main.py run    https://github.com/pallets/flask
python main.py run    pallets/flask --branch main --force

# List all fetched repositories
python main.py list

# Backward-compatible (no subcommand = ingest, same as Phase 1 usage)
python main.py https://github.com/pallets/flask
```

---

## Tech Stack (Phase 2)

| Component | Library / Tool | Version | Purpose |
|-----------|---------------|---------|---------|
| AST Parsing | `tree-sitter` | 0.21.3 | Core parser engine |
| Language Grammars | `tree-sitter-languages` | 1.10.2 | Bundled grammars for 100+ languages |
| Data Format | `dataclasses` + `json` | stdlib | Serialization via custom encoder |
| Timeout | `signal.SIGALRM` | stdlib | Per-file parse timeout (30 seconds) |
| Hashing | `hashlib` | stdlib | Cache keys for parsed file output |
| Testing | `pytest` | 8.3.5 | 46 unit tests |

> **Note on tree-sitter-languages:** Individual `tree-sitter-{language}` packages are **not pip-installable** at tree-sitter 0.21.x. The `tree-sitter-languages` bundle is the correct approach and provides grammars for Python, JavaScript, TypeScript, Java, Go, Rust, C, C++ (and 90+ more).

---

## Key Numbers (Phase 2)

| Metric | Value |
|--------|-------|
| Languages with dedicated AST parsers | 8 (Python, JS, TS, Java, Go, Rust, C, C++) |
| Languages with regex fallback | All others (Generic parser) |
| Architectural patterns detected | 8 (MVC, Layered, REST API, Event-driven, Microservices, CLI, Plugin, Frontend) |
| Parse timeout per file | 30 seconds (SIGALRM) |
| Max function body stored | 50,000 chars (truncated beyond this) |
| Minified file threshold | Lines > 10,000 chars → skipped |
| Unit tests | 46 passing |
| Phase 1 tests (regression check) | 60 passing (unchanged) |
| Real repo verified | `pallets/itsdangerous` — 15 files → 119 functions, 29 classes, 259 call edges in 0.4s |

---

## What Phase 2 Does NOT Do

Phase 2 is **analysis only** — it never:
- Modifies Phase 1 output (`files/` and `manifest.json` are read-only)
- Makes network requests
- Runs the code it's analyzing
- Stores embeddings (that is Phase 3)
- Generate diagrams or narratives (that is Phase 4+)

---

## Phase 2 Output Contract for Phase 3

Every downstream phase reads from `parsed/` in this exact format:

```python
# Load the summary
import json
manifest = json.load(open("parsed/parse_manifest.json"))
# manifest["total_functions_extracted"] → int
# manifest["detected_patterns"]         → list[str]
# manifest["entry_points"]              → list[str]

# Load per-file parsed data
file_data = json.load(open("parsed/files/{sha}.json"))
# file_data["functions"]  → list of ParsedFunction dicts
# file_data["classes"]    → list of ParsedClass dicts
# file_data["imports"]    → list of ParsedImport dicts

# Load graphs
dep_map    = json.load(open("parsed/dependency_map.json"))
call_graph = json.load(open("parsed/call_graph.json"))
```

All keys, types, and field names are guaranteed stable — they are generated from `@dataclass` definitions in `parsing/__init__.py` and will not change between runs unless a `--force` reparse is requested.
