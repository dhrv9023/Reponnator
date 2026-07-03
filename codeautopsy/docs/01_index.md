# CodeAutopsy × Repponator — Documentation Index

**Phase 1: GitHub Repository Ingestion Pipeline**

---

## What is this project?

**CodeAutopsy × Repponator** is a code intelligence system that takes any public GitHub repository URL and produces:

1. **A visual, interactive architecture diagram** (CodeAutopsy) — showing every function, class, module, and their relationships
2. **An architectural narrative story** (Repponator) — explaining *why* the codebase is built the way it is, in flowing prose
3. **A grounded Q&A interface** — natural language questions answered using actual code as evidence

This documentation covers **Phase 1 only** — the ingestion pipeline that fetches, filters, and stores raw code from any GitHub repository. All downstream phases (AST parsing, embedding, diagram generation, narrative generation) depend on the quality of what Phase 1 produces.

---

## Documentation Structure

### Phase Summary

| File | Contents |
|------|----------|
| [00_phase_summary.md](./00_phase_summary.md) | Living project summary — tracks completed phases, objectives, and files |

### Phase 1 — GitHub Repository Ingestion

| File | Contents |
|------|----------|
| [01_index.md](./01_index.md) | This file — project overview and doc map |
| [02_architecture.md](./02_architecture.md) | System architecture, data flow, design decisions |
| [03_modules_foundation.md](./03_modules_foundation.md) | `config.py`, `utils/logger.py`, `utils/rate_limiter.py` |
| [04_modules_ingestion.md](./04_modules_ingestion.md) | `ingestion/url_parser.py`, `ingestion/github_client.py`, `ingestion/file_filter.py` |
| [05_modules_pipeline.md](./05_modules_pipeline.md) | `ingestion/language_detector.py`, `ingestion/file_fetcher.py`, `ingestion/storage.py`, `main.py` |
| [06_quickstart_and_testing.md](./06_quickstart_and_testing.md) | Setup, usage examples, test suite, edge cases, FAQ |

### Phase 2 — Code Parsing & Structural Analysis

| File | Contents |
|------|----------|
| [07_phase2_index.md](./07_phase2_index.md) | Phase 2 overview, data flow, directory layout, CLI, tech stack |
| [08_phase2_architecture.md](./08_phase2_architecture.md) | Tree-sitter design, parser ABC, dataclass contract, fault tolerance, caching |
| [09_phase2_modules_parsers.md](./09_phase2_modules_parsers.md) | All 8 language parsers + generic fallback + parser registry |
| [10_phase2_modules_pipeline.md](./10_phase2_modules_pipeline.md) | Dependency builder, call graph, entry points, pattern detector, orchestrator |

### Phase 3 — Contextual Chunking & AST-Grounded Embeddings

| File | Contents |
|------|----------|
| [12_phase3_index.md](./12_phase3_index.md) | Phase 3 overview, data flow, directory layout, tech stack, key numbers |
| [13_phase3_architecture.md](./13_phase3_architecture.md) | Chunker, splitter, metadata enricher design strategy, token calculation, and OOM recovery |
| [14_phase3_pipeline.md](./14_phase3_pipeline.md) | Complete execution pipeline, chunk manifest specifications, vector store query examples, and E2E validation reports |

### Phase 5 — High-Fidelity Interactive Workspace (Frontend)

| File | Contents |
|------|----------|
| [11_website_specification.md](./11_website_specification.md) | Premium UI/UX blueprints, interactive sections, page mockups, and recommended tech stack |

---

## Phase 1 at a Glance

```
User runs:  python main.py https://github.com/pallets/flask
                                    │
                            ┌───────▼────────┐
                            │  url_parser.py  │   Validate & normalize URL
                            └───────┬────────┘
                                    │ owner="pallets", repo="flask"
                            ┌───────▼────────┐
                            │ github_client  │   Connect to GitHub API
                            └───────┬────────┘
                                    │ Repository object + metadata
                            ┌───────▼────────┐
                            │  file_filter   │   Keep only code files
                            └───────┬────────┘
                                    │ 84 code files (of 236 total)
                            ┌───────▼────────┐
                            │ file_fetcher   │   Fetch content, detect binary
                            └───────┬────────┘
                                    │ FetchResult with all file contents
                        ┌───────────┴───────────┐
                        │                       │
               ┌────────▼────────┐   ┌──────────▼──────────┐
               │language_detector│   │     storage.py       │
               └────────┬────────┘   └──────────┬──────────┘
                        │                       │
                   Language stats          manifest.json
                   primary=Python          files/ tree
                   monorepo=False          fetch.log
```

---

## Tech Stack (Phase 1 Only)

| Component | Library / Tool | Purpose |
|-----------|---------------|---------|
| GitHub API | `PyGithub 2.9.1` | Fetch repo metadata, file trees, file content |
| Environment | `python-dotenv 1.2.2` | Load `GITHUB_TOKEN` from `.env` file |
| HTTP client | `requests 2.31.0` | Used transitively by PyGithub |
| Testing | `pytest 8.3.5` | Unit and integration test runner |
| Standard library | `pathlib`, `json`, `re`, `fnmatch`, `hashlib`, `logging`, `dataclasses` | No third-party dependencies needed for core logic |

> **No ML libraries in Phase 1.** No LangChain, ChromaDB, sentence-transformers, or PyTorch. Phase 1 is pure Python + one API client.

---

## Directory Layout (Phase 1)

```
codeautopsy/
├── .env                        ← Your GitHub token (not committed)
├── .env.example                ← Template — copy this to .env
├── requirements.txt            ← Pinned dependencies
├── run.sh                      ← One-command startup script
├── main.py                     ← CLI entry point
├── config.py                   ← All constants — the single source of truth
│
├── ingestion/                  ← Core pipeline modules
│   ├── __init__.py             ← Public package API
│   ├── url_parser.py           ← GitHub URL validation and normalization
│   ├── github_client.py        ← PyGithub wrapper with retry and error handling
│   ├── file_filter.py          ← Decides which files to fetch
│   ├── language_detector.py    ← Computes language statistics
│   ├── file_fetcher.py         ← Orchestrator — runs the full pipeline
│   └── storage.py              ← Writes results to disk + manifest
│
├── utils/                      ← Shared utilities
│   ├── __init__.py
│   ├── logger.py               ← Centralized logger (console + file)
│   └── rate_limiter.py         ← GitHub API rate limit management
│
├── data/                       ← All fetched repos stored here (gitignored)
│   └── repos/
│       └── {owner}__{repo}/
│           ├── manifest.json
│           ├── fetch.log
│           └── files/          ← Full mirrored repo file tree
│
├── tests/
│   ├── __init__.py
│   └── test_phase1.py          ← 60 tests (58 unit + 2 integration)
│
└── docs/                       ← You are here
    ├── 01_index.md
    ├── 02_architecture.md
    ├── 03_modules_foundation.md
    ├── 04_modules_ingestion.md
    ├── 05_modules_pipeline.md
    └── 06_quickstart_and_testing.md
```

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Supported languages | 27 (Python, JS, TS, Java, Go, Rust, C, C++, Ruby, PHP, Swift, Kotlin, Scala, Shell, R, Elixir, Haskell, Lua, Perl, Dart, C#, F#, Clojure, Erlang, Julia, Nim, Zig, OCaml) |
| Ignored directory names | 37 (node_modules, __pycache__, .git, venv, dist, build, etc.) |
| Ignored file patterns | 18 (*.min.js, *.lock, *.map, *.pyc, *.class, etc.) |
| Max file size | 500 KB per file |
| Max total size | 50 MB per repo |
| Unit tests | 58 passing |
| Integration tests | 2 (require GitHub API, run with `-m integration`) |
| API rate limit (no token) | 60 requests/hour |
| API rate limit (with token) | 5,000 requests/hour |
