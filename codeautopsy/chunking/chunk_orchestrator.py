"""
chunking/chunk_orchestrator.py — Phase 3 Main Orchestration

Ties all Phase 3 modules (chunker → splitter → enricher → embedder →
vector_store) into a single pipeline.

Entry point: chunk_and_embed_repository(repo_folder, force_rechunk)

Reads from:  repo_folder/parsed/          (Phase 2 output — read-only)
Writes to:   repo_folder/chunks/          (Phase 3 output)
             data/chroma_db/              (shared ChromaDB store)
"""

from __future__ import annotations

import dataclasses
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config
from chunking import (
    ChunkManifest,
    ChunkType,
    CodeChunk,
    save_chunk_manifest,
    save_chunks_jsonl,
)
from chunking.chunker import Chunker
from chunking.embedder import Embedder
from chunking.metadata_enricher import MetadataEnricher
from chunking.splitter import Splitter
from chunking.vector_store import VectorStore
from parsing import (
    CallGraph,
    DependencyMap,
    ParsedFile,
    ParseManifest,
    load_json,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHUNKS_DIR_NAME   = "chunks"
CHUNKS_JSONL      = "chunks.jsonl"
CHUNK_INDEX_JSON  = "chunk_index.json"
CHUNK_MANIFEST_JSON = "chunk_manifest.json"


# ===========================================================================
# Public API
# ===========================================================================

def chunk_and_embed_repository(
    repo_folder: Path,
    force_rechunk: bool = False,
) -> ChunkManifest:
    """
    Run the full Phase 3 pipeline: chunk → split → enrich → embed → store.

    Args:
        repo_folder:   Path to the Phase 1/2 repo folder
                       (e.g. data/repos/pallets__flask).
        force_rechunk: If True, delete existing collection and rebuild.

    Returns:
        ChunkManifest summarising the run.

    Raises:
        FileNotFoundError: If Phase 2 output is missing.
        RuntimeError:      On fatal embedding or ChromaDB errors.
    """
    total_start = time.monotonic()

    # -----------------------------------------------------------------------
    # 1. Verify Phase 2 is complete
    # -----------------------------------------------------------------------
    parse_manifest_path = repo_folder / config.PARSED_DIR_NAME / config.PARSE_MANIFEST_FILENAME
    if not parse_manifest_path.exists():
        raise FileNotFoundError(
            f"Phase 2 output not found at {parse_manifest_path}.\n"
            f"Run:  python main.py parse <url>  first."
        )

    parse_meta = load_json(parse_manifest_path)
    owner     = parse_meta.get("repo_owner", "unknown")
    repo_name = parse_meta.get("repo_name", "unknown")

    # -----------------------------------------------------------------------
    # 2. Cache check
    # -----------------------------------------------------------------------
    chunks_dir      = repo_folder / CHUNKS_DIR_NAME
    manifest_path   = chunks_dir / CHUNK_MANIFEST_JSON
    vector_store    = VectorStore(config.CHROMA_DB_PATH)

    if (
        not force_rechunk
        and manifest_path.exists()
        and vector_store.collection_exists(owner, repo_name)
    ):
        logger.info(
            "Repository %s/%s already chunked and embedded. "
            "Use --force to redo.",
            owner, repo_name,
        )
        from chunking import load_chunk_manifest
        return load_chunk_manifest(manifest_path)

    # -----------------------------------------------------------------------
    # 3. Load all Phase 2 data
    # -----------------------------------------------------------------------
    logger.info("Loading Phase 2 parsed data for %s/%s …", owner, repo_name)
    parsed_dir = repo_folder / config.PARSED_DIR_NAME

    parsed_files = _load_parsed_files(parsed_dir / "files")
    logger.info("Loaded %d parsed files", len(parsed_files))

    dependency_map = _load_dependency_map(parsed_dir / "dependency_map.json")
    call_graph     = _load_call_graph(parsed_dir / "call_graph.json")
    entry_points   = _load_json_safe(parsed_dir / "entry_points.json", default=[])
    patterns       = _load_json_safe(parsed_dir / "patterns.json", default=[])

    # -----------------------------------------------------------------------
    # 4. Create output directory
    # -----------------------------------------------------------------------
    chunks_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # 5. Initialize components (Embedder loads model — takes ~2s first time)
    # -----------------------------------------------------------------------
    chunker    = Chunker()
    splitter   = Splitter()
    enricher   = MetadataEnricher()
    embedder   = Embedder(config.EMBEDDING_MODEL_NAME)
    # vector_store already initialized above

    # -----------------------------------------------------------------------
    # 6. Create chunks
    # -----------------------------------------------------------------------
    chunk_start = time.monotonic()
    all_chunks: list[CodeChunk] = []
    errors: list[str] = []

    for idx, pf in enumerate(parsed_files, start=1):
        if idx % 20 == 0 or idx == len(parsed_files):
            logger.info(
                "Chunking file %d/%d — %d chunks so far",
                idx, len(parsed_files), len(all_chunks),
            )
        try:
            file_chunks = chunker.create_chunks_from_file(pf, owner, repo_name)
            all_chunks.extend(file_chunks)
        except Exception as exc:  # noqa: BLE001
            msg = f"Chunking failed for {pf.file_path}: {exc}"
            logger.error(msg)
            errors.append(msg)

    logger.info(
        "Created %d initial chunks from %d files",
        len(all_chunks), len(parsed_files),
    )

    # -----------------------------------------------------------------------
    # 7. Split large chunks
    # -----------------------------------------------------------------------
    functions_before_split = sum(
        1 for c in all_chunks if c.chunk_type in (ChunkType.FUNCTION, ChunkType.METHOD)
    )
    all_chunks = splitter.split_large_chunks(all_chunks)
    functions_split = sum(
        1 for c in all_chunks if c.is_subchunk
    )
    logger.info(
        "After splitting: %d chunks (%d sub-chunks created)",
        len(all_chunks), functions_split,
    )

    # -----------------------------------------------------------------------
    # 8. Filter too-small chunks
    # -----------------------------------------------------------------------
    before_filter = len(all_chunks)
    all_chunks = [c for c in all_chunks if c.token_count >= config.MIN_CHUNK_TOKENS]
    removed = before_filter - len(all_chunks)
    if removed:
        logger.info(
            "Removed %d chunks below MIN_CHUNK_TOKENS (%d). Remaining: %d",
            removed, config.MIN_CHUNK_TOKENS, len(all_chunks),
        )

    # -----------------------------------------------------------------------
    # 9. Enrich metadata
    # -----------------------------------------------------------------------
    all_chunks = enricher.enrich_chunks(
        all_chunks, dependency_map, call_graph, entry_points, patterns
    )

    # -----------------------------------------------------------------------
    # 10. Build and save chunk index
    # -----------------------------------------------------------------------
    chunk_index = enricher.build_qualified_name_index(all_chunks)
    index_path  = chunks_dir / CHUNK_INDEX_JSON
    index_path.write_text(
        json.dumps(chunk_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Saved chunk index: %d entries → %s", len(chunk_index), index_path)

    # -----------------------------------------------------------------------
    # 11. Save chunks.jsonl (metadata backup without embeddings)
    # -----------------------------------------------------------------------
    jsonl_path = chunks_dir / CHUNKS_JSONL
    save_chunks_jsonl(all_chunks, jsonl_path)
    logger.info("Saved %d chunks to %s", len(all_chunks), jsonl_path)

    chunk_duration = time.monotonic() - chunk_start

    # -----------------------------------------------------------------------
    # 12. Embed chunks
    # -----------------------------------------------------------------------
    logger.info(
        "Starting embedding with %s …", config.EMBEDDING_MODEL_NAME
    )
    embed_start = time.monotonic()
    all_chunks  = embedder.embed_chunks(all_chunks, show_progress=True)
    embed_duration = time.monotonic() - embed_start
    logger.info("Embedding complete in %.1fs", embed_duration)

    # -----------------------------------------------------------------------
    # 13. Store in ChromaDB
    # -----------------------------------------------------------------------
    if force_rechunk:
        vector_store.delete_collection(owner, repo_name)

    collection = vector_store.get_or_create_collection(owner, repo_name)
    vector_store.add_chunks(collection, all_chunks)
    logger.info("Stored %d chunks in ChromaDB", len(all_chunks))

    # -----------------------------------------------------------------------
    # 14. Build and save ChunkManifest
    # -----------------------------------------------------------------------
    total_duration = time.monotonic() - total_start
    counts_by_type = _count_by_type(all_chunks)
    total_tokens   = sum(c.token_count for c in all_chunks)
    avg_tokens     = total_tokens // max(len(all_chunks), 1)
    max_tokens     = max((c.token_count for c in all_chunks), default=0)

    n_functions = len(parsed_files)  # already logged
    n_classes   = sum(len(pf.classes) for pf in parsed_files)
    n_funcs_raw = sum(len(pf.functions) for pf in parsed_files)

    manifest = ChunkManifest(
        codeautopsy_version         = config.CODEAUTOPSY_VERSION,
        chunk_timestamp             = datetime.now(timezone.utc).isoformat(),
        repo_owner                  = owner,
        repo_name                   = repo_name,
        embedding_model             = config.EMBEDDING_MODEL_NAME,
        embedding_dimensions        = config.EMBEDDING_DIMENSIONS,
        total_chunks                = len(all_chunks),
        chunks_by_type              = counts_by_type,
        total_tokens                = total_tokens,
        average_tokens_per_chunk    = avg_tokens,
        largest_chunk_tokens        = max_tokens,
        total_files_processed       = len(parsed_files),
        total_functions_chunked     = n_funcs_raw,
        total_classes_chunked       = n_classes,
        functions_split_into_subchunks = functions_split,
        chroma_collection_name      = collection.name,
        chunk_duration_seconds      = round(chunk_duration, 2),
        embed_duration_seconds      = round(embed_duration, 2),
        total_duration_seconds      = round(total_duration, 2),
        errors                      = errors,
    )

    save_chunk_manifest(manifest, manifest_path)
    logger.info(
        "Phase 3 complete: %d chunks | %d tokens | %.1fs total",
        len(all_chunks), total_tokens, total_duration,
    )
    return manifest


# ===========================================================================
# Private loaders
# ===========================================================================

def _load_parsed_files(files_dir: Path) -> list[ParsedFile]:
    """Load all ParsedFile objects from parsed/files/*.json."""
    from parsing import ParsedFile as PF, ParsedFunction, ParsedClass
    from parsing import ParsedImport, ParsedParameter

    parsed_files: list[ParsedFile] = []

    if not files_dir.exists():
        logger.warning("Parsed files directory not found: %s", files_dir)
        return []

    for json_path in sorted(files_dir.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            pf   = _dict_to_parsed_file(data)
            parsed_files.append(pf)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load parsed file %s: %s", json_path, exc)

    return parsed_files


def _dict_to_parsed_file(d: dict) -> ParsedFile:
    """Reconstruct a ParsedFile from a plain dict."""
    from parsing import ParsedFile, ParsedFunction, ParsedClass, ParsedImport, ParsedParameter

    def _param(p: dict):
        return ParsedParameter(
            name=p.get("name", ""),
            type_annotation=p.get("type_annotation"),
            default_value=p.get("default_value"),
            is_variadic=p.get("is_variadic", False),
        )

    def _func(f: dict):
        return ParsedFunction(
            name=f.get("name", ""),
            qualified_name=f.get("qualified_name", ""),
            file_path=f.get("file_path", ""),
            start_line=f.get("start_line", 0),
            end_line=f.get("end_line", 0),
            parameters=[_param(p) for p in f.get("parameters", [])],
            return_type=f.get("return_type"),
            docstring=f.get("docstring"),
            body_preview=f.get("body_preview", ""),
            full_body=f.get("full_body", ""),
            parent_class=f.get("parent_class"),
            is_method=f.get("is_method", False),
            is_constructor=f.get("is_constructor", False),
            is_private=f.get("is_private", False),
            is_static=f.get("is_static", False),
            is_async=f.get("is_async", False),
            decorators=f.get("decorators", []),
            calls=f.get("calls", []),
            complexity_score=f.get("complexity_score", 0),
        )

    def _cls(c: dict):
        return ParsedClass(
            name=c.get("name", ""),
            qualified_name=c.get("qualified_name", ""),
            file_path=c.get("file_path", ""),
            start_line=c.get("start_line", 0),
            end_line=c.get("end_line", 0),
            docstring=c.get("docstring"),
            base_classes=c.get("base_classes", []),
            implemented_interfaces=c.get("implemented_interfaces", []),
            methods=c.get("methods", []),
            class_variables=c.get("class_variables", []),
            instance_variables=c.get("instance_variables", []),
            is_abstract=c.get("is_abstract", False),
            is_interface=c.get("is_interface", False),
            decorators=c.get("decorators", []),
        )

    def _imp(i: dict):
        return ParsedImport(
            file_path=i.get("file_path", ""),
            line_number=i.get("line_number", 0),
            import_type=i.get("import_type", "absolute"),
            module=i.get("module", ""),
            imported_items=i.get("imported_items", []),
            aliases=i.get("aliases", {}),
            is_stdlib=i.get("is_stdlib", False),
            is_third_party=i.get("is_third_party", False),
            is_local=i.get("is_local", False),
            is_conditional=i.get("is_conditional", False),
        )

    return ParsedFile(
        file_path=d.get("file_path", ""),
        language=d.get("language", ""),
        sha=d.get("sha", ""),
        size_bytes=d.get("size_bytes", 0),
        total_lines=d.get("total_lines", 0),
        functions=[_func(f) for f in d.get("functions", [])],
        classes=[_cls(c) for c in d.get("classes", [])],
        imports=[_imp(i) for i in d.get("imports", [])],
        global_variables=d.get("global_variables", []),
        module_docstring=d.get("module_docstring"),
        is_entry_point=d.get("is_entry_point", False),
        has_main_block=d.get("has_main_block", False),
        has_exports=d.get("has_exports", False),
        parse_errors=d.get("parse_errors", []),
        parse_success=d.get("parse_success", True),
    )


def _load_dependency_map(path: Path) -> DependencyMap:
    """Load DependencyMap from dependency_map.json."""
    if not path.exists():
        logger.warning("dependency_map.json not found — using empty map")
        return DependencyMap(repo_owner="", repo_name="")

    d = json.loads(path.read_text(encoding="utf-8"))
    from parsing import DependencyEdge

    def _edge(e: dict):
        return DependencyEdge(
            from_file=e.get("from_file", ""),
            to_file=e.get("to_file"),
            to_module=e.get("to_module", ""),
            dependency_type=e.get("dependency_type", ""),
            imported_items=e.get("imported_items", []),
            line_number=e.get("line_number", 0),
        )

    return DependencyMap(
        repo_owner=d.get("repo_owner", ""),
        repo_name=d.get("repo_name", ""),
        edges=[_edge(e) for e in d.get("edges", [])],
        external_dependencies=d.get("external_dependencies", []),
        local_files=d.get("local_files", []),
        adjacency=d.get("adjacency", {}),
        reverse_adjacency=d.get("reverse_adjacency", {}),
    )


def _load_call_graph(path: Path) -> CallGraph:
    """Load CallGraph from call_graph.json."""
    if not path.exists():
        logger.warning("call_graph.json not found — using empty graph")
        return CallGraph(repo_owner="", repo_name="")

    d = json.loads(path.read_text(encoding="utf-8"))
    from parsing import CallEdge

    def _edge(e: dict):
        return CallEdge(
            caller_file=e.get("caller_file", ""),
            caller_function=e.get("caller_function", ""),
            caller_qualified=e.get("caller_qualified", ""),
            callee_name=e.get("callee_name", ""),
            callee_resolved=e.get("callee_resolved"),
            call_line=e.get("call_line", 0),
            is_resolved=e.get("is_resolved", False),
        )

    return CallGraph(
        repo_owner=d.get("repo_owner", ""),
        repo_name=d.get("repo_name", ""),
        edges=[_edge(e) for e in d.get("edges", [])],
        nodes=d.get("nodes", []),
        adjacency=d.get("adjacency", {}),
        reverse_adjacency=d.get("reverse_adjacency", {}),
    )


def _load_json_safe(path: Path, default):
    """Load JSON from path; return default on any error."""
    if not path.exists():
        logger.warning("%s not found — using default", path)
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load %s: %s", path, exc)
        return default


def _count_by_type(chunks: list[CodeChunk]) -> dict[str, int]:
    """Count chunks by ChunkType.value."""
    counts: dict[str, int] = {}
    for c in chunks:
        key = c.chunk_type.value if hasattr(c.chunk_type, "value") else str(c.chunk_type)
        counts[key] = counts.get(key, 0) + 1
    return counts
