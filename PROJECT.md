# CodeAutopsy × Repponator

> **Reverse-engineer any public GitHub repository.** Drop a URL, get the architecture back — as an interactive diagram, a cinematic editorial story, and a live RAG Q&A assistant.

---

## 🚀 Quick Start

**Two terminals. Two commands.**

```bash
# Terminal 1 — Python Backend
cd ~/Desktop/github_prj/codeautopsy
source venv/bin/activate
python3 -m uvicorn api.main:app --reload --port 8000

# Terminal 2 — React Frontend
cd ~/Desktop/github_prj/codeautopsy-web
npm run dev
```

Then open **http://localhost:5173**

Or use the one-click script:
```bash
cd ~/Desktop/github_prj
./start.sh
```

---

## 🗂 Project Structure

```
github_prj/
├── codeautopsy/          ← Python backend (FastAPI + all pipeline phases)
│   ├── api/              ← Phase 8: REST API layer
│   ├── ingestion/        ← Phase 1: GitHub ingestion
│   ├── parsing/          ← Phase 2: Tree-sitter code parsing
│   ├── chunking/         ← Phase 3: Chunking + ChromaDB embeddings
│   ├── rag/              ← Phase 4: RAG Q&A (BM25 + vector search)
│   ├── agent/            ← Phase 5: LangGraph call-graph traversal agent
│   ├── diagram/          ← Phase 6: Mermaid architecture diagram generator
│   ├── story/            ← Phase 7: Repponator editorial story engine
│   ├── data/repos/       ← Generated output per repository
│   ├── main.py           ← CLI entry point
│   └── requirements.txt
│
└── codeautopsy-web/      ← React + TypeScript frontend (Vite + Tailwind)
    └── src/
        ├── api/client.ts         ← Typed REST API client
        ├── components/
        │   ├── HeroSection.tsx   ← Landing page + repo input
        │   ├── IngestionConsole  ← Real-time pipeline progress
        │   ├── Workspace.tsx     ← Workspace with Diagram + Q&A + Stack
        │   ├── Diagram/          ← Interactive Mermaid diagram viewer
        │   ├── Story/            ← Cinematic story page
        │   └── HelpChat/         ← RAG Q&A chat widget
        └── hooks/                ← useJobPoller, etc.
```

---

## 📦 What's Implemented — All Phases

### Phase 1 — GitHub Ingestion
- Clones any public GitHub repository via the GitHub API
- Extracts all source files, directory tree, and file metadata
- Detects primary language, file counts, and byte sizes
- Writes a `manifest.json` per repository to `data/repos/{owner}__{name}/`
- **API**: `POST /api/repos/ingest` → background job → `GET /api/repos/{repo_key}`

---

### Phase 2 — Code Parsing (Tree-sitter)
- Parses Python, JavaScript, TypeScript, Go, Rust, Java, C/C++ using Tree-sitter
- Extracts: functions, classes, call edges, parameters, decorators, docstrings
- Detects architectural patterns: MVC, Repository, Factory, Observer, etc.
- Identifies entry points (main functions, CLI handlers, route handlers)
- Writes `parsed_functions.json` and `call_graph.json`
- **API**: `POST /api/parse` → `GET /api/parse/{repo_key}`

---

### Phase 3 — Chunking + Embedding (ChromaDB)
- Splits parsed functions into semantic chunks with context headers
- Enriches each chunk with metadata: file path, function name, complexity, calls
- Embeds using `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim)
- Stores in a local ChromaDB collection per repository
- **API**: `POST /api/chunk` → `GET /api/chunk/{repo_key}`

---

### Phase 4 — RAG Q&A Layer
- Answers natural language questions about the codebase
- **Hybrid retrieval**: BM25 keyword search + ChromaDB vector search (fused with RRF)
- **LLM answering**: Groq (`llama-3.3-70b-versatile`) or Gemini (`gemini-2.5-pro`)
- Returns answers with source citations (file, line range, snippet)
- Maintains multi-turn conversation session
- **API**: `POST /api/qa` → synchronous response with `{ answer, citations, confidence }`
- **Frontend**: HelpChat widget (floating assistant on Workspace page)

---

### Phase 5 — LangGraph Call-Graph Traversal Agent
- LangGraph `StateGraph` agent that traverses the call graph from entry points
- Tools: `get_function_info`, `get_callers`, `get_callees`, `get_file_summary`
- Multi-hop reasoning: follows call chains to understand dependencies
- Summarises architecture from a traversal perspective
- Used internally to improve story and diagram quality

---

### Phase 6 — Architecture Diagram Generator
- Generates a **Mermaid** `flowchart TD` diagram from Phase 2 call graph
- Node types: Entry Point (green), Core Utility (purple), Module (blue), Class (teal)
- Edges represent import/call relationships
- **Interactive frontend**: pan, zoom, search to highlight nodes
- Node click → sidebar with function list, class list, call count
- **API**: `POST /api/diagram` → `GET /api/diagram/{repo_key}`

---

### Phase 7 — Repponator Architectural Story Engine
- Generates a 7-section editorial narrative from Phase 2 structural data
- Uses `story/context_builder.py` to compress the codebase into <3000 tokens
- Calls Groq LLM to produce:
  1. **Primary Commitment** — the guiding architectural decision
  2. **Origin Story** — why the project was built this way
  3. **How It Flows** — data/control flow in plain English
  4. **Key Modules** — top 5 files with poetic role titles ("The Signatory", "The Gateway")
  5. **Design Tensions** — trade-offs baked into the architecture
  6. **Founding Metaphor** — a vivid analogy for the whole system
  7. **Verdict** — one-paragraph architectural assessment
- **API**: `POST /api/story` → `GET /api/story/{repo_key}`
- **Frontend**: Cinematic story page with typewriter hero, parallax, particle field, 3D-tilt module cards, scroll-driven chapter entrances

---

### Phase 8 — FastAPI REST API Layer
- Wraps all phases (1–7) behind clean, versioned HTTP endpoints
- **Async background jobs**: all long-running phases run as tasks, return `job_id` immediately
- **Job Manager**: in-memory queue with `QUEUED → RUNNING → COMPLETE/FAILED` lifecycle
- **Phase dependency enforcement**: 409 Conflict if prerequisites not met
- **Pydantic v2** request + response validation
- **Global error handler**: `RepoNotFoundError`, `PhaseNotCompleteError`, `JobAlreadyRunningError`
- **CORS** configured for React dev server (localhost:5173)
- **Auto-docs**: Swagger UI at `http://localhost:8000/docs`, ReDoc at `/redoc`

#### All API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/repos/ingest` | Trigger Phase 1 ingestion |
| GET | `/api/repos` | List all ingested repos |
| GET | `/api/repos/{repo_key}` | Repo metadata |
| DELETE | `/api/repos/{repo_key}` | Delete repo + data |
| POST | `/api/parse` | Trigger Phase 2 parsing |
| GET | `/api/parse/{repo_key}` | Parse results |
| POST | `/api/chunk` | Trigger Phase 3 embedding |
| GET | `/api/chunk/{repo_key}` | Chunk results |
| POST | `/api/qa` | Ask a question (Phase 4) |
| POST | `/api/diagram` | Trigger Phase 6 diagram |
| GET | `/api/diagram/{repo_key}` | Diagram + node metadata |
| POST | `/api/story` | Trigger Phase 7 story |
| GET | `/api/story/{repo_key}` | Architectural story |
| GET | `/api/jobs/{job_id}` | Poll job status |
| GET | `/api/jobs` | List all jobs |

---

## 🔑 Environment Variables

Set in `codeautopsy/.env`:

```env
# LLM Provider (required for Phase 4 + 7)
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# GitHub (optional — increases API rate limit for Phase 1)
GITHUB_TOKEN=your_github_token_here
```

---

## 🖥 CLI Reference

```bash
cd codeautopsy && source venv/bin/activate

python3 main.py ingest  https://github.com/pallets/flask   # Phase 1
python3 main.py parse   pallets__flask                      # Phase 2
python3 main.py embed   pallets__flask                      # Phase 3
python3 main.py chat    pallets__flask                      # Phase 4 (interactive)
python3 main.py traverse pallets__flask                     # Phase 5
python3 main.py diagram pallets__flask                      # Phase 6
python3 main.py story   pallets__flask                      # Phase 7
python3 main.py run     https://github.com/pallets/flask    # Full pipeline (1→7)
python3 main.py list                                        # List ingested repos
```

---

## 🧰 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend language | Python 3.12 |
| Web framework | FastAPI + Uvicorn |
| Code parsing | Tree-sitter + tree-sitter-languages |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Vector store | ChromaDB |
| Keyword search | BM25 (rank-bm25) |
| LLM | Groq (`llama-3.3-70b-versatile`) / Gemini |
| Agent framework | LangGraph |
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS |
| Diagram rendering | Mermaid.js |
| Data validation | Pydantic v2 |
