<div align="center">

# CodeAutopsy × Repponator

### Reverse-engineer any public GitHub repository.
### Drop a URL. Get the architecture back.

**Most tools answer _"What does this code do?"_ — this one answers _"Why was it built this way?"_**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.1-FF6B35?style=flat)](https://langchain-ai.github.io/langgraph)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-0.5-E85D04?style=flat)](https://trychroma.com)

</div>

---

## What is this?

CodeAutopsy is a **full-stack code intelligence platform** that statically analyses any public GitHub repository and produces three outputs simultaneously:

| Output | What it is |
|--------|-----------|
| 🗺️ **Interactive Architecture Diagram** | Mermaid flowchart built from a real AST call graph — pan, zoom, search, click any node for details |
| 📖 **Repponator Architectural Story** | A 7-section editorial narrative: founding metaphor, design decisions, data flow, key modules with poetic role titles, trade-offs, and a verdict |
| 💬 **RAG Q&A Assistant** | A chat widget that answers architecture questions using hybrid semantic + keyword retrieval over the indexed codebase |

---

## What makes this technically interesting

> This is not a GPT wrapper. The LLM is the last step. The hard part is the structured knowledge layer built before it.

### 1. Real AST Call Graph — Not Text Similarity

The pipeline uses **Tree-sitter** (the same parser used by GitHub, Neovim, and VS Code) to build a genuine call graph across **7 languages** simultaneously. Every function's callers, callees, decorators, parameters, complexity score, and entry-point status are extracted as structured data — not inferred from embeddings.

```
Signer.__init__  ──calls──▶  hmac.new
                 ──calls──▶  base64.b64encode
                 ◀─called──  TimestampSigner.__init__
```

### 2. Architecture-Aware Hybrid RAG

When you ask *"how does authentication work?"*, most RAG systems find the auth function via text similarity. This system does something different:

1. **Entity extraction** — identifies `Signer`, `TimestampSigner` as named entities
2. **Direct chunk lookup** — fetches those exact chunks from ChromaDB (O(1), not similarity search)
3. **Graph expansion** — uses the in-memory **KnowledgeGraph** (NetworkX DiGraph loaded from the call graph) to BFS-traverse callers and callees within 2 hops
4. **Hybrid scoring** — fuses BM25 keyword scores + semantic similarity scores via **Reciprocal Rank Fusion**
5. **LLM answering** — sends the graph-aware context to Groq / Gemini

The KnowledgeGraph replaces N×ChromaDB round-trips (≈200ms each) with a single in-memory BFS traversal (~5ms), then one batched fetch.

**RAG retrieval configuration:**
- Semantic search top-K: **15 chunks**
- BM25 keyword search top-K: **10 chunks**
- HyDE (hypothetical document embedding): **8 chunks**
- Final reranked context: **12 chunks** sent to LLM
- Semantic weight: **0.65** · Keyword weight: **0.35**

### 3. LangGraph Call-Graph Traversal Agent

A `StateGraph` agent (Phase 5) traverses the call graph from entry points using tools:
- `get_function_info` — fetch AST metadata for a function
- `get_callers` / `get_callees` — traverse the graph
- `get_file_summary` — summarise a module

The agent uses a configurable LLM budget (default: **30 LLM calls per traversal**) and hub-node detection (a function called by ≥ 5 others is a hub node and gets deep analysis). This traversal output feeds both the diagram and the Repponator story with higher-quality structural context than a flat parse could provide.

### 4. 8-Phase Async Pipeline with Job Lifecycle

Every long-running phase (ingest → parse → embed → diagram → story) is dispatched as an **async background task** via FastAPI's `BackgroundTasks`. An in-memory job manager tracks:

```
QUEUED → RUNNING → COMPLETE / FAILED
```

Phase dependency is enforced at the API layer — you can't trigger Phase 3 (embedding) without Phase 2 (parsing) complete, with a `409 Conflict` response. All 16 REST endpoints are fully typed with Pydantic v2.

### 5. Repponator Story Engine

The story generator compresses the full codebase structure into a `<3000 token` context (via `story/context_builder.py`) and generates a 7-section architectural narrative using an LLM:

1. **Primary Commitment** — the guiding architectural decision
2. **Origin Story** — why the project exists structurally
3. **How It Flows** — data/control flow in plain English
4. **Key Modules** — top 5 files with poetic role titles (*"The Signatory"*, *"The Gateway"*)
5. **Design Tensions** — trade-offs baked into the architecture
6. **Founding Metaphor** — a vivid analogy for the whole system
7. **Verdict** — one-paragraph architectural assessment

No other tool produces this output format.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        React Frontend                           │
│   HeroSection → IngestionConsole → Workspace → StoryPage        │
│        (Vite + TypeScript + Tailwind + Mermaid.js)              │
└─────────────────────┬───────────────────────────────────────────┘
                      │  HTTP (REST)
┌─────────────────────▼───────────────────────────────────────────┐
│                    FastAPI REST API (Phase 8)                    │
│         16 endpoints · Pydantic v2 · Async background jobs      │
└──┬──────────┬──────────┬──────────┬───────────┬────────────────┘
   │          │          │          │           │
   ▼          ▼          ▼          ▼           ▼
Phase 1    Phase 2    Phase 3    Phase 4     Phase 5-7
GitHub     Tree-      ChromaDB   Hybrid      LangGraph
Ingestion  sitter     Embedding  RAG Q&A     Agent +
           AST        + BM25     + KnowGraph Diagram +
           Parsing    Index      traversal   Story
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Code Parsing | **Tree-sitter 0.21** + tree-sitter-languages | Grammar-based AST, not regex — handles all edge cases |
| Embeddings | **sentence-transformers** `all-MiniLM-L6-v2` (384-dim) | Fast, local, no API cost for embedding |
| Vector Store | **ChromaDB 0.5** | Local-first, persistent, no infrastructure needed |
| Keyword Search | **BM25Okapi** (rank-bm25) | Exact-match recall that pure vector search misses |
| Graph Traversal | **NetworkX** DiGraph | In-memory BFS — microsecond latency vs ChromaDB round-trips |
| LLM | **Groq** (`llama-3.3-70b`) / **Gemini** (`gemini-flash`) | Groq for speed; Gemini as fallback |
| Agent Framework | **LangGraph 0.1** StateGraph | Structured multi-step reasoning with tool use |
| Backend | **FastAPI 0.115** + Uvicorn | Async, typed, auto-docs at `/docs` |
| Data Validation | **Pydantic v2** | Request/response contracts enforced at the boundary |
| Frontend | **React 18** + TypeScript + Vite | Type-safe, fast dev cycle |
| Diagram Rendering | **Mermaid.js** | Browser-native, interactive, no extra dependencies |
| Containerisation | **Docker** + docker-compose | One-command full-stack deployment |

---

## Supported Languages

AST-level parsing (Tree-sitter grammars) for **7 languages:**

`Python` · `JavaScript` · `TypeScript` · `Java` · `Go` · `Rust` · `C/C++`

File detection for **26 languages** (everything from Ruby to Zig).

---

## Detected Architectural Patterns

The pattern detector (`parsing/pattern_detector.py`) identifies:

`MVC` · `Layered (Service/Repository)` · `Microservices` · `Event-driven` · `REST API` · `CLI` · `Plugin/Extension` · `Frontend Component`

---

## Quick Start

**Two terminals. Two commands.**

```bash
# Terminal 1 — Python backend
cd codeautopsy
python -m venv venv && source venv/activate
pip install torch==2.3.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
cp .env.example .env          # add your GROQ_API_KEY or GEMINI_API_KEY
python -m uvicorn api.main:app --reload --port 8000

# Terminal 2 — React frontend
cd codeautopsy-web
npm install
npm run dev
```

Open **http://localhost:5173**

Or use the one-click script:
```bash
./start.sh
```

### Environment Variables

```env
# codeautopsy/.env

# LLM provider — pick one
LLM_PROVIDER=groq                        # or "gemini"
GROQ_API_KEY=your_key_here               # from console.groq.com (free)
GEMINI_API_KEY=your_key_here             # from aistudio.google.com (free)

# GitHub (optional — 5000 req/hr vs 60 req/hr unauthenticated)
GITHUB_TOKEN=your_github_pat
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/repos/ingest` | Trigger Phase 1 — GitHub ingestion |
| `GET` | `/api/repos` | List all ingested repositories |
| `GET` | `/api/repos/{repo_key}` | Repository metadata + file stats |
| `DELETE` | `/api/repos/{repo_key}` | Delete repository + all generated data |
| `POST` | `/api/parse` | Trigger Phase 2 — AST parsing |
| `GET` | `/api/parse/{repo_key}` | Parse results (functions, call graph) |
| `POST` | `/api/chunk` | Trigger Phase 3 — embedding |
| `GET` | `/api/chunk/{repo_key}` | Chunk manifest + stats |
| `POST` | `/api/qa` | Ask a question (hybrid RAG, Phase 4) |
| `POST` | `/api/diagram` | Trigger Phase 6 — Mermaid diagram |
| `GET` | `/api/diagram/{repo_key}` | Diagram + node metadata |
| `POST` | `/api/story` | Trigger Phase 7 — Repponator story |
| `GET` | `/api/story/{repo_key}` | 7-section architectural story |
| `GET` | `/api/jobs/{job_id}` | Poll job status |
| `GET` | `/api/jobs` | List all background jobs |

Interactive Swagger UI at `http://localhost:8000/docs`

---

## CLI Reference

```bash
cd codeautopsy && source venv/bin/activate

python main.py run     https://github.com/pallets/flask     # Full pipeline (all phases)
python main.py ingest  https://github.com/pallets/flask     # Phase 1 only
python main.py parse   pallets__flask                       # Phase 2
python main.py embed   pallets__flask                       # Phase 3
python main.py chat    pallets__flask                       # Phase 4 — interactive Q&A
python main.py traverse pallets__flask                      # Phase 5 — agent traversal
python main.py diagram pallets__flask                       # Phase 6
python main.py story   pallets__flask                       # Phase 7
python main.py list                                         # List ingested repos
```

---

## Project Structure

```
github_prj/
├── codeautopsy/                    ← Python backend
│   ├── api/                        ← Phase 8: FastAPI REST layer
│   │   ├── main.py                 ← App entrypoint + router registration
│   │   ├── routers/                ← One router per domain (repos, qa, diagram…)
│   │   ├── models/                 ← Pydantic v2 request/response schemas
│   │   ├── services/job_manager.py ← Async job lifecycle (QUEUED→RUNNING→DONE)
│   │   └── middleware/             ← Global error handler
│   ├── ingestion/                  ← Phase 1: GitHub API client + file fetcher
│   ├── parsing/                    ← Phase 2: Tree-sitter AST parsers (7 languages)
│   │   └── languages/              ← One parser class per language
│   ├── chunking/                   ← Phase 3: Semantic chunker + ChromaDB + embedder
│   ├── rag/                        ← Phase 4: Hybrid RAG pipeline
│   │   ├── retriever.py            ← BM25 + semantic + graph expansion
│   │   ├── query_processor.py      ← Query classification + HyDE + expansion
│   │   ├── context_builder.py      ← Token-budget-aware context assembly
│   │   └── llm_client.py           ← Groq / Gemini unified client
│   ├── graph/                      ← KnowledgeGraph: in-memory NetworkX DiGraph
│   ├── agent/                      ← Phase 5: LangGraph StateGraph traversal agent
│   ├── diagram/                    ← Phase 6: Mermaid flowchart generator
│   ├── story/                      ← Phase 7: Repponator editorial story engine
│   ├── prompts/                    ← All LLM prompt templates (centralised)
│   ├── config.py                   ← Single source of truth for all constants
│   └── requirements.txt
│
└── codeautopsy-web/                ← React + TypeScript frontend
    └── src/
        ├── api/client.ts           ← Typed REST API client (all endpoints)
        ├── components/
        │   ├── HeroSection.tsx     ← Landing + typewriter + pipeline stages
        │   ├── IngestionConsole.tsx ← Real-time job polling + progress display
        │   ├── Workspace.tsx       ← Main workspace: diagram + Q&A + stack tabs
        │   ├── Diagram/            ← Interactive Mermaid viewer (pan/zoom/search)
        │   ├── Story/              ← Cinematic story page (parallax + particles)
        │   └── HelpChat/           ← Floating RAG Q&A chat widget
        └── hooks/
            ├── useJobPoller.ts     ← Polls /api/jobs/{id} until COMPLETE/FAILED
            └── useTypewriter.ts    ← Typewriter animation hook
```

---

## Design Decisions

### Why Tree-sitter over regex or `ast` module?

Regex-based parsers break on multiline expressions, string interpolation, and nested constructs. Python's `ast` module only handles Python. Tree-sitter provides a single, consistent, battle-tested parser for every language with error recovery — it keeps parsing even through syntax errors.

### Why hybrid BM25 + vector search instead of pure vector search?

Pure vector search misses exact keyword matches. If you search for `authenticate_user` (an exact function name), BM25 will score it at rank 1 while vector search might rank it 7th because it's looking at semantic similarity in embedding space. The weighted fusion (65% semantic, 35% BM25) handles both conceptual questions and exact-name lookups. RRF deduplication ensures a chunk found by both methods is surfaced at the top.

### Why a KnowledgeGraph on top of ChromaDB?

ChromaDB is optimised for similarity lookups, not graph traversal. Fetching 10 graph neighbours required 10 separate ChromaDB calls (≈200ms each = 2s total). Loading the call graph into a NetworkX DiGraph once at startup turns that into a single BFS traversal (~5ms) plus one batched fetch. Graph traversal is fundamentally an adjacency problem, not a similarity problem.

### Why LangGraph for the agent instead of a raw loop?

A raw loop can't express conditional routing, early termination, or typed shared state without growing into spaghetti. LangGraph's `StateGraph` makes the agent's decision tree explicit — each node is a typed function, edges are conditions. The hub-node detection and LLM budget logic are clean, testable, and easy to extend.

---

## Acknowledgements

- [Tree-sitter](https://tree-sitter.github.io) — the parser that makes multi-language AST analysis practical
- [LangGraph](https://langchain-ai.github.io/langgraph) — structured agent orchestration
- [Groq](https://groq.com) — fast LLM inference (free tier)
- [ChromaDB](https://trychroma.com) — local-first vector store

---

<div align="center">
Built by <a href="https://github.com/dhrv9023">dhrv9023</a>
</div>
