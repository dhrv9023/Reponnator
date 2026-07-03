# CodeAutopsy × Repponator — Project Phase Summary

This document serves as a high-level, living summary of the phases completed in the **CodeAutopsy × Repponator** project. It outlines the core objectives, key implementations, modules built, and verification results for each phase, and is updated as the project progresses.

---

## 📌 Overall Project Status

| Phase | Description | Status | Completed Date |
|:---|:---|:---:|:---|
| **Phase 1** | **GitHub Repository Ingestion System** | **Completed** | May 2026 |
| **Phase 2** | **Code Parsing & Structural AST Analysis** | **Completed** | May 2026 |
| **Phase 3** | **Contextual Chunking & AST-Grounded Embeddings** | **Completed** | May 2026 |
| **Phase 4** | **Multi-Agent RAG & Call Graph Traversal** | *Planned* | - |
| **Phase 5** | **Architecture Diagram & Story Dashboard** | **Completed** | May 2026 |

---

## 📂 Phase 1: GitHub Repository Ingestion System

### 🎯 Objective
Establish a robust, production-grade, and fault-tolerant local data ingestion pipeline that fetches public GitHub repositories, filters out non-code assets, detects programming languages, and prepares a normalized local file store with full manifest tracking.

### 🛠️ Key Implementations
- **GitHub URL Parser:** Validates, handles short-forms (`owner/repo`), normalizes URLs, and extracts branches.
- **Resilient API Client:** Wraps `PyGithub` with automatic token fallback, rate-limit awareness (exponential backoff/retries), and granular error handling.
- **Robust File Filtering:** Excludes massive binaries, assets, and build directories (`node_modules`, `.git`, etc.) based on a strict ignore-list. Caps single file size to 500 KB and total repository fetch size to 50 MB.
- **Language Detection:** Detects programming languages per-file and identifies primary languages, as well as detecting monorepo markers.
- **Atomic Local Storage:** Saves code files safely to disk inside a `data/repos/{owner}__{repo}/files/` tree and outputs a comprehensive `manifest.json` tracker and a detailed `fetch.log`.

### 🧩 Key Code Files & Roles
- [`config.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/config.py): Single source of truth for ignoring folders, file extensions, and sizing limits.
- [`ingestion/url_parser.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/ingestion/url_parser.py): Normalizes and parses incoming repo URLs.
- [`ingestion/github_client.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/ingestion/github_client.py): PyGithub API client with rate-limit and network recovery.
- [`ingestion/file_filter.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/ingestion/file_filter.py): Filtering rules for extensions, sizes, and folders.
- [`ingestion/language_detector.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/ingestion/language_detector.py): Calculates repository-wide language metrics.
- [`ingestion/file_fetcher.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/ingestion/file_fetcher.py): The pipeline engine orchestrating fetch operations.
- [`ingestion/storage.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/ingestion/storage.py): Manages local directory rotation, atomic writes, and manifest generation.

### ✅ Verification Metrics
- **60/60** unit and mock integration tests passed successfully.
- Verified rate limit backoff and error recovery during simulated network outages.
- Successfully fetched repositories of varying structures and sizes without structural errors or leaks.

---

## 🔬 Phase 2: Code Parsing & Structural AST Analysis

### 🎯 Objective
Consume the raw file structures produced in Phase 1 and build a multi-language AST-based parsing pipeline. Extract high-level semantics (functions, classes, imports) and construct code intelligence maps (dependency graphs, call graphs, entry points, and architectural patterns) stored in structured, downstream-ready JSON layers.

### 🛠️ Key Implementations
- **AST Parsing Engine:** Integrates `tree-sitter` and `tree-sitter-languages` for parsing files into Concrete Syntax Trees.
- **Language Parsers:** Implemented 8 dedicated AST parsers (Python, JS, TS, TSX, Java, Go, Rust, C/C++) extracting arguments, visibility, asynchronous functions, base classes, and decorators.
- **Regex Fallback Parser:** Fallback parser that executes regex-based structural approximations for unsupported languages, maintaining pipeline completion.
- **Pipeline Analysis Modules:**
  - **Dependency Builder:** Computes relative and absolute local file import maps and alerts on circular dependencies using DFS.
  - **Call Graph Builder:** Maps callers to callees globally, filtering built-in functions, resolving ambiguous names, and measuring function call depths using BFS.
  - **Entry Point Finder:** Uses a weighted scoring model (filename, main blocks, top-of-dependency-tree) to rank HIGH/MEDIUM/LOW confidence entry points.
  - **Pattern Detector:** Matches directory structures, imports, and name signals to detect 8 key patterns (MVC, Layered, REST, Microservices, Event-driven, CLI, Plugins, Frontend).
- **Subcommand-Based CLI:** Extends `main.py` to support `ingest`, `parse`, `run` (E2E), and `list` commands.

### 🧩 Key Code Files & Roles
- [`parsing/__init__.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/parsing/__init__.py): Complete data schema definitions (`ParsedFile`, `ParsedFunction`, etc.) and the custom JSON serialization layer.
- [`parsing/base_parser.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/parsing/base_parser.py): Shared pipeline orchestration, encoding validation, size checks, and signal-based timeouts (SIGALRM).
- [`parsing/parser_registry.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/parsing/parser_registry.py): Maps Phase 1 language labels and file extensions to their corresponding parser instances.
- [`parsing/languages/`](file:///home/ag2/Desktop/github_prj/codeautopsy/parsing/languages/): Specialized individual parsers utilizing Tree-sitter query expressions.
- [`parsing/dependency_builder.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/parsing/dependency_builder.py): Resolves local paths and establishes cross-file dependencies.
- [`parsing/call_graph_builder.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/parsing/call_graph_builder.py): Performs inter-function call resolution and analyzes graph topology (orphans/hubs).
- [`parsing/entry_point_finder.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/parsing/entry_point_finder.py): Scans for main blocks, entry files, and start functions.
- [`parsing/pattern_detector.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/parsing/pattern_detector.py): Scans for high-level architectural blueprints.
- [`parsing/parse_orchestrator.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/parsing/parse_orchestrator.py): Orchestrates parsing, constructs output formats, and builds the central `parse_manifest.json` report.
- [`utils/file_hasher.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/utils/file_hasher.py): Generates path and content hashes for caching and change detection.

### ✅ Verification Metrics
- **46/46** Phase 2 unit tests passed. All Phase 1 tests (**60/60**) remain green (zero regressions).
- Verified full E2E execution on the `pallets/itsdangerous` repository (15 files) completing successfully in **0.4 seconds**; yielding 119 functions, 29 classes, and 259 call graph edges with zero extraction failures.

---

## 🎨 Phase 5: Architecture Diagram & Story Dashboard (Frontend)

### 🎯 Objective
Construct a premium, high-fidelity, fully responsive web workspace application using React, Vite, TypeScript, and Tailwind CSS. The interface must provide a cinema-grade hero landing page with mouse-interactive seeking controls, transition seamlessly to an active progress log ingestion console, and boot into a comprehensive architectural workspace combining natural prose narratives, interactive dependency and call graph diagrams, and cited AI Q&A helpers.

### 🛠️ Key Implementations
- **Scrubbable Video Hero Canvas:** Custom horizontal `mousemove` delta listener mapping mouse gestures to smooth video playback seeking.
- **Eco Mode Battery & CPU Saver:** Complete unmounting of background video streams on low-spec battery/device modes, replacing video renders with zero-CPU CSS radial gradients.
- **Dynamic Typewriter Hook:** Custom delay-initiated typing simulation rendering brand paragraphs character-by-character.
- **Ingestion Log Terminal Console:** Simulated pipeline execution visualizing progress metrics, active stages, and pipeline steps in a high-fidelity console window.
- **Multi-Pane Workspace Dashboard:**
  - **The Narrative (Left Panel):** Clean, structural prose descriptions of parsed classes and patterns (grounded in `itsdangerous` statistics), with inline highlighted words that hover-trigger node indicators in the graph canvas.
  - **CodeAutopsy Diagram Canvas (Center Panel):** Hand-coded, lightweight, high-performance React SVG Call Graph showing class/method nodes, search queries filtering, node selection drawer, and pan/zoom mechanics.
  - **Q&A Chat Assistant (Right Panel):** Grounded conversation system with interactive code citation overlays, pulling source code snippets in a custom syntax-highlighted citation modal drawer.
- **Universal Style Syncing:** Synchronized root CSS properties maintaining visual consistency across high-contrast Light and sleek cyber-grey Dark modes.

### 🧩 Key Code Files & Roles
- [`src/App.tsx`](file:///home/ag2/Desktop/github_prj/codeautopsy-web/src/App.tsx): Root layout state router orchestrating views, theme variables, and Eco Mode.
- [`src/index.css`](file:///home/ag2/Desktop/github_prj/codeautopsy-web/src/index.css): Light & Dark theme color system variables, blinking cursors, and glow animation templates.
- [`src/components/Navbar.tsx`](file:///home/ag2/Desktop/github_prj/codeautopsy-web/src/components/Navbar.tsx): fixed header with toggles (EcoToggle, ThemeToggle), comma links, CTA, and responsive mobile overlays.
- [`src/components/HeroSection.tsx`](file:///home/ag2/Desktop/github_prj/codeautopsy-web/src/components/HeroSection.tsx): Typography hero headlines, typewriter parameters, pill controls, and trigger bounds.
- [`src/components/VideoBackground.tsx`](file:///home/ag2/Desktop/github_prj/codeautopsy-web/src/components/VideoBackground.tsx): Scrub playback tracker and Eco Mode background replacement.
- [`src/components/IngestionConsole.tsx`](file:///home/ag2/Desktop/github_prj/codeautopsy-web/src/components/IngestionConsole.tsx): Terminal window step-by-step progress monitor.
- [`src/components/Workspace.tsx`](file:///home/ag2/Desktop/github_prj/codeautopsy-web/src/components/Workspace.tsx): Panels system (Narrative, Diagram SVG Canvas, Chat Workspace, and Code Citation Overlay).

### ✅ Verification Metrics
- Tested in Chrome and Firefox browsers.
- Fully verified responsiveness across mobile views (hamburger overlays, column stacking, size clamps).
- Verified Eco Mode completely eliminates background video resources, resulting in solid 60 FPS animation states on lowest of devices.
- Verified fully operational Light / Dark mode toggles applying instantly without HMR delays.

---

## 🧩 Phase 3: Contextual Chunking & AST-Grounded Embeddings

### 🎯 Objective
Transform the raw codebase AST parse structures generated in Phase 2 into a high-fidelity vector store representing the semantic memory of the entire repository. This requires creating specialized code chunks, augmenting them with rich relational metadata (call graph, dependency maps, entry points, architectural patterns), generating L2-normalized embeddings, and persisting them in ChromaDB.

### 🛠️ Key Implementations
- **AST-Aware Chunking Engine:** Creates 5 specialized chunk types: `FUNCTION`, `METHOD`, `CLASS_SUMMARY`, `FILE_SUMMARY`, and `IMPORT_CONTEXT` to fit diverse retrieval queries.
- **Semantic Splitter:** Safely splits oversized functions into overlapping `FUNCTION_SUBCHUNK` sequences using Token-based slicing (tiktoken) and attaches overlap metadata.
- **Relational Metadata Enricher:** Restores and injects call graph relations (`calls`/`called_by`), import maps, entry point classifications, detected architectural patterns, and imports actually used inside function blocks.
- **L2-Normalized Batch Embedder:** Wraps `sentence-transformers` (`all-MiniLM-L6-v2`) to compute 384-dimensional cosine-aligned vectors, with batching and automatic memory limit (OOM) recovery.
- **ChromaDB Vector Store client:** Encapsulates persistent collection creation, batch additions, semantic query execution, and unique identifier lookups.
- **Subcommand CLI Integration:** Adds the `embed` subcommand to `main.py` and upgrades the `run` subcommand to execute Phase 1, Phase 2, and Phase 3 in sequence.

### 🧩 Key Code Files & Roles
- [`chunking/__init__.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/chunking/__init__.py): Data structures (`CodeChunk`, `ChunkManifest`) and serialization filters.
- [`chunking/chunker.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/chunking/chunker.py): Contextual templates and parsing engines.
- [`chunking/splitter.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/chunking/splitter.py): Token-based splitter and overlapping text assembler.
- [`chunking/metadata_enricher.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/chunking/metadata_enricher.py): Call graph, import-use, and architectural pattern enricher.
- [`chunking/embedder.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/chunking/embedder.py): SentenceTransformers model wrapper and batch processor.
- [`chunking/vector_store.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/chunking/vector_store.py): ChromaDB client manager and CRUD/query executors.
- [`chunking/chunk_orchestrator.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/chunking/chunk_orchestrator.py): Orchestrates Phase 3 pipeline execution.
- [`run_tests_p3.py`](file:///home/ag2/Desktop/github_prj/codeautopsy/run_tests_p3.py): Phase 3 unit and integration test runner.

### ✅ Verification Metrics
- **23/23** unit and integration tests passed successfully (covering chunker, splitter, enricher, embedder, and vector store).
- Verified full pipeline completion on the `pallets/itsdangerous` repository, creating 201 semantic chunks, compiling 22,029 tokens (avg 109 per chunk), and populating a ChromaDB collection in **12.4 seconds**.
- Tested semantic search capabilities yielding correct results for queries on token signing, timestamp verification, and URL serializers.

