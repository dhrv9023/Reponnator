"""
chunking/metadata_enricher.py — Phase 3 Relational Metadata Enrichment

Adds relational metadata to chunks using the Phase 2 graph data:
  - call graph (calls / called_by)
  - dependency map (file-level dependencies)
  - entry points
  - architectural patterns
  - import usage per chunk

Called after chunker + splitter, before embedding.
"""

from __future__ import annotations

from typing import Optional

from parsing import DependencyMap, CallGraph
from chunking import ChunkType, CodeChunk
from utils.logger import get_logger

logger = get_logger(__name__)

# Maximum number of callers/callees stored (some utility functions have 500+)
_MAX_CALLS_STORED = 20


class MetadataEnricher:
    """Enriches CodeChunks with relational data from Phase 2 graphs."""

    def enrich_chunks(
        self,
        chunks: list[CodeChunk],
        dependency_map: DependencyMap,
        call_graph: CallGraph,
        entry_points: list[dict],
        patterns: list[dict],
    ) -> list[CodeChunk]:
        """
        Add relational metadata to every chunk in-place.

        Args:
            chunks:         Chunks from chunker + splitter.
            dependency_map: From parsed/dependency_map.json.
            call_graph:     From parsed/call_graph.json.
            entry_points:   From parsed/entry_points.json.
            patterns:       From parsed/patterns.json.

        Returns:
            Same list with enriched fields.
        """
        # Pre-build lookup sets for fast O(1) checks
        entry_point_files: set[str] = {
            ep["file_path"] for ep in entry_points
            if isinstance(ep, dict) and "file_path" in ep
        }
        entry_point_funcs: set[str] = {
            ep.get("function", "") for ep in entry_points
            if isinstance(ep, dict) and ep.get("function")
        }

        # Pattern signals: pattern_name → list of file path substrings
        pattern_signals: dict[str, list[str]] = {}
        for p in patterns:
            if isinstance(p, dict):
                pname = p.get("pattern", "")
                sigs  = p.get("file_signals", []) or p.get("signals", []) or []
                if pname:
                    pattern_signals[pname] = sigs

        for chunk in chunks:
            self._enrich_call_graph(chunk, call_graph)
            self._enrich_dependency_map(chunk, dependency_map)
            self._enrich_entry_point(chunk, entry_point_files, entry_point_funcs)
            self._enrich_patterns(chunk, pattern_signals)
            self._enrich_imports_used(chunk)

        logger.info("Enriched %d chunks with relational metadata", len(chunks))
        return chunks

    # -----------------------------------------------------------------------
    # Private enrichment helpers
    # -----------------------------------------------------------------------

    def _enrich_call_graph(self, chunk: CodeChunk, call_graph: CallGraph) -> None:
        """Populate calls / called_by from the call graph adjacency maps."""
        qn = chunk.qualified_name

        # calls: what this function calls
        if chunk.chunk_type in (ChunkType.FUNCTION, ChunkType.METHOD):
            raw_calls = call_graph.adjacency.get(qn, [])
            chunk.calls = list(raw_calls)[:_MAX_CALLS_STORED]

        # called_by: who calls this function
        raw_callers = call_graph.reverse_adjacency.get(qn, [])
        chunk.called_by = list(raw_callers)[:_MAX_CALLS_STORED]

    def _enrich_dependency_map(
        self, chunk: CodeChunk, dependency_map: DependencyMap
    ) -> None:
        """Populate file-level import dependency lists."""
        fp = chunk.file_path
        chunk.files_this_depends_on   = list(dependency_map.adjacency.get(fp, []))
        chunk.files_depending_on_this = list(dependency_map.reverse_adjacency.get(fp, []))

    def _enrich_entry_point(
        self,
        chunk: CodeChunk,
        entry_files: set[str],
        entry_funcs: set[str],
    ) -> None:
        """Mark chunk as entry point if its file or qualified name is one."""
        if chunk.file_path in entry_files:
            chunk.is_entry_point = True
        if chunk.qualified_name in entry_funcs:
            chunk.is_entry_point = True

    def _enrich_patterns(
        self,
        chunk: CodeChunk,
        pattern_signals: dict[str, list[str]],
    ) -> None:
        """Add architectural pattern names if this chunk's file matches signals."""
        matched: list[str] = []
        for pattern_name, signals in pattern_signals.items():
            for sig in signals:
                if sig and sig.lower() in chunk.file_path.lower():
                    matched.append(pattern_name)
                    break  # one signal match is enough per pattern
        chunk.architectural_patterns = matched

    def _enrich_imports_used(self, chunk: CodeChunk) -> None:
        """
        Identify which imported modules are actually referenced in this chunk's
        content.  Cross-references chunk.file_imports with content text.
        """
        if not chunk.file_imports:
            return

        content_lower = chunk.content.lower()
        used: list[str] = []
        for module in chunk.file_imports:
            # Match the leaf name of the module (e.g. "os" from "os.path")
            leaf = module.split(".")[-1].lower()
            if leaf and leaf in content_lower:
                used.append(module)

        chunk.imports_used = used

    # -----------------------------------------------------------------------
    # Chunk index builder
    # -----------------------------------------------------------------------

    def build_qualified_name_index(
        self, chunks: list[CodeChunk]
    ) -> dict[str, str]:
        """
        Build a qualified_name → chunk_id mapping.

        If a qualified name has multiple chunks (sub-chunks), the index maps
        to the FIRST sub-chunk (index 0) or the original unsplit chunk.

        Returns:
            dict mapping qualified_name → chunk_id
        """
        index: dict[str, str] = {}
        for chunk in chunks:
            qn = chunk.qualified_name
            if qn not in index:
                index[qn] = chunk.chunk_id
            elif chunk.is_subchunk and chunk.subchunk_index == 0:
                index[qn] = chunk.chunk_id  # prefer first sub-chunk
        return index
