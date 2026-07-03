# CodeAutopsy × Repponator — Phase 3 Pipeline & Execution

This document provides a guide on how the Phase 3 pipeline executes, details the output file specifications, and showcases real-world end-to-end validation results.

---

## 1. Pipeline Execution Flow

The `chunk_orchestrator.py` drives the end-to-end pipeline through 14 distinct sequential phases:

```
[Start Pipeline]
       │
       ▼
1. Verify Phase 2 parsed output directory exists
       │
       ▼
2. Check Cache (skips run if chunk_manifest.json & collection exist, unless --force)
       │
       ▼
3. Load Phase 2 outputs (parsed files, dependency maps, call graphs, patterns)
       │
       ▼
4. Create output data directory (data/repos/{owner}__{repo}/chunks/)
       │
       ▼
5. Initialize Chunker, Splitter, Enricher, and local SentenceTransformers Embedder
       │
       ▼
6. Run Chunker (transforms all files into initial semantic chunks)
       │
       ▼
7. Run Splitter (slices oversized chunks into overlapping sub-chunks)
       │
       ▼
8. Filter out tiny chunks (skips chunks with < MIN_CHUNK_TOKENS tokens)
       │
       ▼
9. Run Metadata Enricher (injects call graphs, entry points, dependencies, and used imports)
       │
       ▼
10. Build & Save qualified name index (chunk_index.json)
       │
       ▼
11. Save metadata-only chunk backup (chunks.jsonl)
       │
       ▼
12. Run Embedder (downloads all-MiniLM-L6-v2 on first run, computes unit embeddings)
       │
       ▼
13. Store in ChromaDB (deletes old collection if --force, creates persistent collection)
       │
       ▼
14. Save Chunk Manifest report (chunk_manifest.json)
       │
       ▼
[End Pipeline]
```

---

## 2. Output File Specifications

All chunk outputs reside at `data/repos/{owner}__{repo}/chunks/`.

### 2.1 qualified name index (`chunk_index.json`)
Maps every parsed class, method, or function qualified name to its corresponding central database chunk ID. If a function is split into multiple sub-chunks, this points to sub-chunk `0`.
```json
{
  "URLSafeSerializer": "2a9f4c3b-d183-4a0b-85cd-df5d2f6277c0",
  "URLSafeSerializer.loads": "4c9d7e6f-402a-45c1-90a1-7c5e2d6b38c2"
}
```

### 2.2 chunk backup list (`chunks.jsonl`)
A JSON Lines file containing the complete serialized state of all code chunks (excluding the raw float embedding arrays, which are stored inside ChromaDB). Provides an easy-to-read local backup.
```json
{
  "chunk_id": "d81f902f-f974-426f-a5ce-69a495230430",
  "repo_owner": "pallets",
  "repo_name": "itsdangerous",
  "chunk_type": "method",
  "file_path": "src/itsdangerous/serializer.py",
  "language": "Python",
  "start_line": 120,
  "end_line": 150,
  "sha": "a1b2c3d4",
  "content": "File: src/itsdangerous/serializer.py...",
  "token_count": 145,
  "name": "loads",
  "qualified_name": "Serializer.loads",
  "calls": ["itsdangerous.encoding.want_bytes"],
  "called_by": ["itsdangerous.serializer.Serializer.loads_unsafe"],
  "imports_used": ["itsdangerous.encoding"],
  "is_subchunk": false
}
```

### 2.3 chunk manifest (`chunk_manifest.json`)
The central summary of the chunking and embedding execution:
```json
{
  "codeautopsy_version": "1.0.0",
  "chunk_timestamp": "2026-05-31T13:08:09.123Z",
  "repo_owner": "pallets",
  "repo_name": "itsdangerous",
  "embedding_model": "all-MiniLM-L6-v2",
  "embedding_dimensions": 384,
  "total_chunks": 201,
  "chunks_by_type": {
    "method": 81,
    "function": 20,
    "class_summary": 29,
    "file_summary": 15,
    "import_context": 11,
    "function_subchunk": 45
  },
  "total_tokens": 22029,
  "average_tokens_per_chunk": 109,
  "largest_chunk_tokens": 198,
  "total_files_processed": 15,
  "total_functions_chunked": 101,
  "total_classes_chunked": 29,
  "functions_split_into_subchunks": 45,
  "chroma_collection_name": "codeautopsy__pallets__itsdangerous",
  "chunk_duration_seconds": 6.65,
  "embed_duration_seconds": 5.75,
  "total_duration_seconds": 12.40,
  "errors": []
}
```

---

## 3. End-to-End Validation Report (`itsdangerous`)

We verified the entire pipeline on the `pallets/itsdangerous` codebase (15 source files).

### 3.1 Terminal Output
```
$ python main.py embed https://github.com/pallets/itsdangerous

🧩  CodeAutopsy — embedding pallets/itsdangerous

[INFO] ChromaDB PersistentClient initialized at data/chroma_db
[INFO] Loading Phase 2 parsed data for pallets/itsdangerous …
[INFO] Loaded 15 parsed files
[INFO] Loading embedding model all-MiniLM-L6-v2 …
[INFO] Model loaded in 5.7s — embedding dimension: 384
[INFO] Chunking file 15/15 — 170 chunks so far
[INFO] Created 174 initial chunks from 15 files
[INFO] Split 18 large function chunks into sub-chunks
[INFO] After splitting: 201 chunks (45 sub-chunks created)
[INFO] Enriched 201 chunks with relational metadata
[INFO] Saved chunk index: 165 entries → chunks/chunk_index.json
[INFO] Saved 201 chunks to chunks/chunks.jsonl
[INFO] Starting embedding with all-MiniLM-L6-v2 …
[INFO] Embedded 201/201 chunks (5.8s elapsed)
[INFO] Stored 201/201 chunks in ChromaDB
[INFO] Phase 3 complete: 201 chunks | 22029 tokens | 12.4s total

╔════════════════════════════════════════════════════╗
║  CodeAutopsy — Embedding Complete                  ║
╠════════════════════════════════════════════════════╣
║  Repo            : pallets/itsdangerous            ║
║  Total Chunks    : 201                             ║
║  Functions       : 101                             ║
║  Classes         : 29                              ║
║  File Summaries  : 15                              ║
║  Import Context  : 11                              ║
║  Sub-chunks      : 45                              ║
║  Total Tokens    : 22,029                          ║
║  Avg Tokens      : 109 per chunk                   ║
║  Model           : all-MiniLM-L6-v2 (384-dim)      ║
║  ChromaDB        : codeautopsy__pallets__itsdangerous║
║  Embed Time      : 5.8 seconds                     ║
║  Saved to        : data/repos/pallets__itsdangerous/chunks/║
╚════════════════════════════════════════════════════╝
```

---

## 4. Semantic Search Query Examples

A semantic search check verifies that L2 normalized vectors and ChromaDB cosine retrieval provide high-quality results:

### Query 1: `"signing a token"`
* **Target Context**: Token signature generation and signing algorithms.
* **Top Results**:
  1. `[0.470]` `NoneAlgorithm.get_signature` (method chunk containing signature generation code)
  2. `[0.468]` `TestSigner.test_signer` (unit test function for signer instances)
  3. `[0.453]` `TestSigner.test_secret_keys` (test block checking secret signing keys)

### Query 2: `"timestamp verification"`
* **Target Context**: Validating expiration bounds on timed tokens.
* **Top Results**:
  1. `[0.565]` `TimestampSigner.unsign` (sub-chunk containing token signature validation with age checks)
  2. `[0.538]` `TimestampSigner.unsign` (overlapping sub-chunk displaying timing expiration comparisons)
  3. `[0.536]` `TimestampSigner.get_timestamp` (method extracting current epoch boundaries)

### Query 3: `"URL safe serializer"`
* **Target Context**: Serialization formats safe for web URLs.
* **Top Results**:
  1. `[0.635]` `URLSafeSerializer` (class summary block documenting base64 web serialization)
  2. `[0.601]` `TestURLSafeTimedSerializer.serializer_factory` (test utility building URL-safe serialization instances)
  3. `[0.587]` `TestURLSafeSerializer.serializer_factory` (method building web encoders)
