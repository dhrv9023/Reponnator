# CodeAutopsy × Repponator — Phase 3 Documentation Index

**Phase 3: Contextual Chunking & AST-Grounded Embeddings**

---

## What Phase 3 Does

Phase 2 parsed the repository into classes, functions, and import/call relationships, saving them as structured AST metadata. Phase 3 transforms those static AST parses into a **highly indexable semantic memory** stored inside a vector database.

It takes every parsed file and relationship graph from Phase 2, maps them to contextual code chunks, enriches them with graphs metadata, embeds them using a local model, and stores them in ChromaDB.

Key actions in Phase 3:
- **Intelligent Chunking**: Extracts 5 distinct types of chunks (`FUNCTION`, `METHOD`, `CLASS_SUMMARY`, `FILE_SUMMARY`, `IMPORT_CONTEXT`).
- **Token-Level Splitting**: Slices oversized functions into overlapping `FUNCTION_SUBCHUNK` nodes to fit the embedding model's input token window.
- **Relational Metadata Injection**: Re-links chunks with Phase 2 relational contexts (what functions are called, who calls them, which import statements are active in this snippet).
- **Batch Embedding**: Computes 384-dimensional dense vectors using a lightweight local `all-MiniLM-L6-v2` transformer model.
- **Vector Storage Persistence**: Persists all embeddings, text documents, and flat metadata in a local ChromaDB collection.

---

## Documentation Structure

| File | Contents |
|------|----------|
| [12_phase3_index.md](./12_phase3_index.md) | This file — Phase 3 overview, data flow, directory layout |
| [13_phase3_architecture.md](./13_phase3_architecture.md) | Chunker, splitter, metadata enricher design strategy, token calculation, and OOM recovery |
| [14_phase3_pipeline.md](./14_phase3_pipeline.md) | Complete execution pipeline, chunk manifest specifications, vector store query examples, and E2E validation reports |

---

## Phase 3 Data Flow

```
Phase 2 outputs (read-only):
data/repos/{owner}__{repo}/parsed/
├── files/*.json           ← per-file AST parses
├── dependency_map.json    ← cross-file import map
├── call_graph.json        ← inter-function calls map
├── entry_points.json      ← entry points score list
└── patterns.json          ← architectural pattern checklist
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                 chunk_orchestrator.py                       │
│                                                             │
│  1. Chunker Engine (chunker.py)                             │
│     Creates initial CodeChunks (FUNCTION, METHOD, summaries)│
│                                                             │
│  2. Chunker Splitter (splitter.py)                          │
│     Slices large functions into overlapping SUBCHUNKS        │
│                                                             │
│  3. Metadata Enricher (metadata_enricher.py)                │
│     Restores AST call graph edges & file import contexts    │
│     Saves metadata-only backup to chunks.jsonl              │
│                                                             │
│  4. Local Embedder (embedder.py)                            │
│     Generates L2-normalized 384-dim embeddings (batch)       │
│                                                             │
│  5. ChromaDB Client (vector_store.py)                       │
│     Persists embeddings + flat metadata to data/chroma_db/  │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
Phase 3 output:
data/repos/{owner}__{repo}/chunks/
├── chunk_manifest.json    ← statistics, timing, model specs
├── chunk_index.json       ← qualified_name → chunk_id mapping
└── chunks.jsonl           ← complete chunk backup (excluding vector)
```

---

## Directory Layout (Phase 3 additions)

```
codeautopsy/
├── main.py                     ← CLI entry point (updated with 'embed' and full 'run')
├── config.py                   ← Phase 3 constants appended (models, tokens, templates)
├── run_tests_p3.py             ← Phase 3 test runner script
│
├── chunking/                   ← NEW — entire Phase 3 package
│   ├── __init__.py             ← Dataclasses (CodeChunk, ChunkManifest) + JSON utils
│   ├── chunker.py              ← Creates initial chunks from AST ParsedFiles
│   ├── splitter.py             ← Handles oversized chunks & overlaps
│   ├── metadata_enricher.py    ← Restores call graphs & dependency mappings
│   ├── embedder.py             ← Local SentenceTransformers embedding controller
│   ├── vector_store.py         ← ChromaDB client operations
│   └── chunk_orchestrator.py   ← Main Phase 3 pipeline orchestrator
│
├── data/
│   ├── chroma_db/              ← NEW — Shared persistent vector storage
│   └── repos/{owner}__{repo}/
│       └── chunks/             ← NEW — Phase 3 manifest and data backups
│           ├── chunk_manifest.json
│           ├── chunk_index.json
│           └── chunks.jsonl
│
└── tests/
    └── test_phase3.py          ← NEW — Complete Phase 3 Pytest suite
```

---

## CLI Commands (Updated in Phase 3)

```bash
# Phase 3 only — chunk and embed a previously-parsed repository
python main.py embed  https://github.com/pallets/itsdangerous
python main.py embed  pallets/itsdangerous --force

# Full Phase 1 + 2 + 3 Pipeline
python main.py run    https://github.com/pallets/itsdangerous
python main.py run    pallets/itsdangerous --force
```

---

## Tech Stack (Phase 3)

| Component | Library / Tool | Version | Purpose |
|-----------|---------------|---------|---------|
| Local Embedding Model | `sentence-transformers` | 2.7.0 | Generates 384-dimensional dense vectors |
| Vector Database | `chromadb` | 0.5.x | Fast, local vector retrieval database |
| Token Estimation | `tiktoken` | 0.7.0 | Computes exact model tokens via `cl100k_base` |
| Deep Learning backend | `torch` | 2.3.0 (CPU) | Backend runtime for sentence-transformers |
| Numeric Operations | `numpy` | 1.26.x / 2.x | Computes vectors and parses dimensions |
| Progress Bar | `tqdm` | 4.66.4 | Visual tracking during large-batch embedding |

---

## Key Phase 3 Tuning Parameters (`config.py`)

* **`EMBEDDING_MODEL_NAME`**: `"all-MiniLM-L6-v2"` (cos-aligned 384 dimensions).
* **`EMBEDDING_BATCH_SIZE`**: `64` (number of chunks encoded concurrently).
* **`MAX_EMBEDDING_TOKENS`**: `256` (embedding model input limit).
* **`MAX_CHUNK_TOKENS`**: `200` (target token length for a code chunk).
* **`CHUNK_OVERLAP_TOKENS`**: `40` (sliding token overlap between sub-chunks).
* **`MIN_CHUNK_TOKENS`**: `10` (skips noise chunks like single pass statements).
