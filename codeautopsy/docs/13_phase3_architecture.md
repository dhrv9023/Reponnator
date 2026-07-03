# CodeAutopsy × Repponator — Phase 3 Architecture & Design

This document details the architectural decisions, structural patterns, and mitigation strategies implemented for the **Phase 3 Chunking & Embedding Pipeline**.

---

## 1. Contextual AST-Aware Chunking Strategy

Standard RAG systems rely on character-count text chunking (e.g. slicing every 1000 characters). For codebases, this strategy is highly destructive as it cuts functions in half, separates classes from their attributes, and destroys local semantic context.

CodeAutopsy implements **AST-Aware Contextual Chunking** using the parses generated in Phase 2. We extract 5 distinct chunk types, each filled with specialized templates to preserve structure:

```
                  ┌──────────────────────┐
                  │ AST ParsedFile Input │
                  └──────────┬───────────┘
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
     [Function/Method]    [Class summaries]  [File-level Context]
     Full body code       Attributes list    Import summary
     Decorators line      Method names list  Class/Func lists
     Signature line       Docstrings         Module docstring
```

### 1.1 Chunk Types & Templates (`config.py`)

* **`FUNCTION` / `METHOD`**: Represents individual executable code blocks. Includes full body, decorators, arguments, start/end lines, and complexity.
  ```
  File: {file_path}
  Language: {language}
  Function: {qualified_name}
  {decorators_line}
  {signature_line}

  {docstring_block}

  {body}
  ```
* **`CLASS_SUMMARY`**: A high-level semantic blueprint of a class. Helps the AI quickly understand class definitions without getting lost in full method bodies.
  ```
  File: {file_path}
  Language: {language}
  Class: {qualified_name}
  {base_classes_line}

  {docstring_block}

  Methods: {methods_list}
  Attributes: {attributes_list}
  ```
* **`FILE_SUMMARY`**: Module-level overview containing top-level docstrings, imports summaries, and structural contents of the module.
  ```
  File: {file_path}
  Language: {language}
  Module Summary for: {qualified_name}

  Imports: {imports_summary}
  Classes defined: {classes_list}
  Functions defined: {functions_list}
  Entry point: {is_entry_point}
  {module_docstring_block}
  ```
* **`IMPORT_CONTEXT`**: Aggregates all external, local, and standard library import lines. Exposes third-party libraries and local modules that this file depends on.
  ```
  File: {file_path}
  Import dependencies for: {file_path}

  External libraries used: {third_party_imports}
  Local modules imported: {local_imports}
  Standard library used: {stdlib_imports}
  ```

---

## 2. Token Estimation & Splitting Architecture

Embedding models have strict input token limits (e.g. 256 or 512 wordpiece tokens). If input text exceeds this limit, the model silently truncates the end of the text, losing critical parts of the code.

```
       [Oversized Function Chunk] — 600 tokens
                    │
                    ▼
          (Splitter Engine)
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
[Sub-chunk 0] — 200 tokens  [Sub-chunk 1] — 200 tokens (overlapping)
Headers: File, Signature    Headers: File, Signature, [Overlap flag]
```

### 2.1 Token Calculation (`chunker.py`)
To prevent truncation, we estimate tokens using the `tiktoken` library with `cl100k_base` (GPT-4 encoding), which approximates code token density extremely well. If `tiktoken` is missing or fails, we fall back to a safe character-based approximation (`len(text) // 4`).

### 2.2 Semantic Splitting (`splitter.py`)
If a `FUNCTION` or `METHOD` chunk exceeds `config.MAX_CHUNK_TOKENS` (200 tokens):
1. The **Splitter** slices the function's body into sub-blocks with a sliding window overlay of `config.CHUNK_OVERLAP_TOKENS` (40 tokens).
2. For each sub-block, the Splitter dynamically re-attaches the chunk's contextual header (File, Language, Function name, Class parent, and signature).
3. The resulting chunk is marked as `is_subchunk = True`, with a `subchunk_index` and `total_subchunks` tracker.
4. Second and subsequent sub-chunks receive a header indicator: `[This block overlaps with the previous chunk for continuity]`.

*Non-function summaries (`CLASS_SUMMARY`, `FILE_SUMMARY`) are not split. Instead, they are truncated at word boundaries to keep class signatures intact.*

---

## 3. Relational Metadata Enrichment

Before embedding, chunks are enriched with local relationship mappings from the Phase 2 AST graphs. This builds a **semantic link** between chunks:

- **Call Graph Context**: Inject caller lists (`called_by`) and callee lists (`calls`) up to a maximum of 20 elements per chunk.
- **Dependency Map Context**: Injects file-level import adjacency lists (files that this chunk's module depends on, and files depending on this module).
- **Entry Point Tracking**: Chunks located inside entry point files are automatically flagged (`is_entry_point = True`).
- **Architectural Patterns**: Chunks in files signaling structural patterns (e.g. `views.py` matching MVC, `controllers/` matching layered architectures) inherit the pattern tag.
- **Imports In-Use**: Standard code blocks import dozens of modules, but a specific function may only use `os` or `json`. The enricher parses the chunk body and records the subset of imports actually used in that snippet.

---

## 4. Robust Embedding & OOM Mitigation Strategy

Generating dense embeddings can be resource-intensive, potentially exhausting available CPU/GPU memory (Out-Of-Memory / OOM errors) on large codebases.

### 4.1 L2 Normalization (`embedder.py`)
All embedding vectors generated by `all-MiniLM-L6-v2` are normalized to a unit length ($L_2$ norm = 1.0) before insertion. This ensures that downstream vector retrieval can use simple cosine distance or dot product comparisons, which are fast and highly accurate.

### 4.2 Dynamic OOM Mitigation (`embedder.py`)
The `Embedder` features a self-healing fallback mechanism for low-resource hardware:
* By default, it processes chunks in batches of `64`.
* If a batch run encounters a CUDA OOM or generic MemoryError, the embedder automatically catches the exception, **halves the batch size** (e.g. to 32, then 16), frees CPU/GPU cache, and retries the failed batch.
* This ensures that execution completes successfully even on restricted single-core VMs or micro-environments.

---

## 5. ChromaDB Vector Store Operations

All vector operations are isolated in `VectorStore`, wrapping the persistent client of ChromaDB 0.5.x.

### 5.1 Collection Sanitization
ChromaDB has strict naming requirements (must be alphanumeric or `_`/`-`, max 63 characters, must start with alnum). `VectorStore` sanitizes repository names (e.g. `codeautopsy__pallets__itsdangerous`) automatically to comply with these rules.

### 5.2 Cosine Space Insertion
Collections are initialized with `{"hnsw:space": "cosine"}` metadata. Since all embeddings are L2 normalized, cosine similarity is computed as a simple dot product:

$$\text{Similarity Score} = 1.0 - \text{Cosine Distance}$$

This ensures that scores are cleanly normalized between `0.0` (dissimilar) and `1.0` (identical).
