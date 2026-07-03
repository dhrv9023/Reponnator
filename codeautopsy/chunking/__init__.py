"""
chunking/__init__.py — Phase 3 Shared Dataclasses and Serialization

All Phase 3 data structures are defined here so every module imports
from a single location.  Serialization helpers handle dataclasses,
Enum values, numpy arrays, and other non-standard types.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np


# ===========================================================================
# Enumerations
# ===========================================================================

class ChunkType(Enum):
    FUNCTION         = "function"
    METHOD           = "method"
    CLASS_SUMMARY    = "class_summary"
    FILE_SUMMARY     = "file_summary"
    IMPORT_CONTEXT   = "import_context"
    FUNCTION_SUBCHUNK = "function_subchunk"
    MODULE_CONTEXT   = "module_context"


# ===========================================================================
# Core data structures
# ===========================================================================

@dataclasses.dataclass
class CodeChunk:
    """A single semantic unit extracted from a parsed source file."""

    # Identity
    chunk_id:   str       # UUID — unique across all repos
    repo_owner: str
    repo_name:  str
    chunk_type: ChunkType

    # Source location
    file_path:  str       # relative to repo root
    language:   str
    start_line: int
    end_line:   int
    sha:        str       # sha of source file from Phase 1

    # Content
    content:         str  # actual text to embed and search
    content_preview: str  # first 200 chars for display
    token_count:     int  # tiktoken count of content

    # Naming
    name:            str            # function name, class name, or file name
    qualified_name:  str            # e.g. "UserService.get_user" or file path
    parent_class:    Optional[str]  # set if chunk_type is METHOD
    parent_function: Optional[str]  # set if this is a FUNCTION_SUBCHUNK

    # Relational metadata (from call graph + dependency map)
    calls:                   list[str]  # qualified names this calls
    called_by:               list[str]  # qualified names that call this
    imports_used:            list[str]  # import module names referenced here
    file_imports:            list[str]  # all imports in the file
    files_this_depends_on:   list[str]  # files this chunk's file imports
    files_depending_on_this: list[str]  # files that import this chunk's file

    # Semantic metadata
    complexity_score:       int
    is_entry_point:         bool
    is_constructor:         bool
    is_private:             bool
    is_async:               bool
    decorators:             list[str]
    architectural_patterns: list[str]  # patterns this chunk participates in

    # Search optimization
    search_keywords: list[str]       # extracted keywords for hybrid search
    docstring:       Optional[str]   # if available from Phase 2

    # Sub-chunk tracking
    is_subchunk:            bool          = False
    subchunk_index:         Optional[int] = None   # 0, 1, 2…
    total_subchunks:        Optional[int] = None
    overlap_with_previous:  bool          = False

    # Embedding (populated by embedder)
    embedding:       Optional[list[float]] = None
    embedding_model: Optional[str]         = None


@dataclasses.dataclass
class ChunkManifest:
    """Summary of a complete Phase 3 chunk-and-embed run."""

    codeautopsy_version:         str
    chunk_timestamp:             str
    repo_owner:                  str
    repo_name:                   str
    embedding_model:             str
    embedding_dimensions:        int
    total_chunks:                int
    chunks_by_type:              dict[str, int]  # ChunkType.value → count
    total_tokens:                int
    average_tokens_per_chunk:    int
    largest_chunk_tokens:        int
    total_files_processed:       int
    total_functions_chunked:     int
    total_classes_chunked:       int
    functions_split_into_subchunks: int
    chroma_collection_name:      str
    chunk_duration_seconds:      float
    embed_duration_seconds:      float
    total_duration_seconds:      float
    errors:                      list[str]


# ===========================================================================
# JSON serialization helpers
# ===========================================================================

class _ChunkEncoder(json.JSONEncoder):
    """Custom encoder that handles dataclasses, Enum, datetime, Path, numpy."""

    def default(self, obj: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            d = dataclasses.asdict(obj)
            # Convert ChunkType enum values inside the dict
            if "chunk_type" in d and isinstance(d["chunk_type"], str):
                pass  # asdict already converts to value via __dict__
            return d
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, (set, frozenset)):
            return sorted(obj)
        # numpy arrays → plain lists
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        # numpy scalars
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        return super().default(obj)


def _chunk_asdict(chunk: CodeChunk) -> dict:
    """Convert CodeChunk to a plain dict, resolving Enum values."""
    d = dataclasses.asdict(chunk)
    # dataclasses.asdict recurses but Enum stays as-is in some Python versions
    if isinstance(d.get("chunk_type"), Enum):
        d["chunk_type"] = d["chunk_type"].value
    elif isinstance(d.get("chunk_type"), str):
        pass  # already resolved
    return d


def chunk_to_json(chunk: CodeChunk, *, include_embedding: bool = False,
                  indent: int = 2) -> str:
    """Serialize a CodeChunk to JSON string.

    Args:
        chunk:             The chunk to serialize.
        include_embedding: If False (default) the embedding field is dropped.
        indent:            JSON indentation.

    Returns:
        JSON string.
    """
    d = _chunk_asdict(chunk)
    if not include_embedding:
        d.pop("embedding", None)
    return json.dumps(d, cls=_ChunkEncoder, indent=indent, ensure_ascii=False)


def chunk_to_dict(chunk: CodeChunk, *, include_embedding: bool = False) -> dict:
    """Convert a CodeChunk to a plain dict (for ChromaDB metadata etc.)."""
    d = _chunk_asdict(chunk)
    if not include_embedding:
        d.pop("embedding", None)
    return d


def manifest_to_json(manifest: ChunkManifest, indent: int = 2) -> str:
    """Serialize a ChunkManifest to JSON string."""
    return json.dumps(dataclasses.asdict(manifest), cls=_ChunkEncoder,
                      indent=indent, ensure_ascii=False)


def save_chunk_manifest(manifest: ChunkManifest, path: Path) -> None:
    """Write ChunkManifest to *path*, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest_to_json(manifest), encoding="utf-8")


def load_chunk_manifest(path: Path) -> ChunkManifest:
    """Load a ChunkManifest from disk."""
    d = json.loads(path.read_text(encoding="utf-8"))
    return ChunkManifest(**d)


def save_chunks_jsonl(chunks: list[CodeChunk], path: Path) -> None:
    """Write all chunks as JSON Lines (one per line, no embeddings)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            line = chunk_to_json(chunk, include_embedding=False, indent=None)
            # chunk_to_json with indent=None produces compact JSON
            fh.write(line + "\n")


def _compact_chunk_json(chunk: CodeChunk) -> str:
    """Compact (no-indent) JSON of a chunk without embedding."""
    d = _chunk_asdict(chunk)
    d.pop("embedding", None)
    return json.dumps(d, cls=_ChunkEncoder, ensure_ascii=False)


# Override save_chunks_jsonl to use compact helper
def save_chunks_jsonl(chunks: list[CodeChunk], path: Path) -> None:  # noqa: F811
    """Write all chunks as JSON Lines (one per line, no embeddings)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(_compact_chunk_json(chunk) + "\n")


__all__ = [
    "ChunkType",
    "CodeChunk",
    "ChunkManifest",
    "chunk_to_json",
    "chunk_to_dict",
    "manifest_to_json",
    "save_chunk_manifest",
    "load_chunk_manifest",
    "save_chunks_jsonl",
]
