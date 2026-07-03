"""
chunking/splitter.py — Phase 3 Large Chunk Splitter

Handles chunks that exceed MAX_CHUNK_TOKENS by splitting them into
overlapping sub-chunks so the embedding model receives text within its
window limits.

Rules:
- Only FUNCTION and METHOD chunks are split into sub-chunks.
- CLASS_SUMMARY, FILE_SUMMARY, and IMPORT_CONTEXT chunks are truncated
  at MAX_CHUNK_TOKENS (never split — they must stay atomic).
- Each sub-chunk inherits all metadata from its parent.
- Sub-chunks 1+ include a context header AND an overlap tail from the
  previous sub-chunk for embedding continuity.
"""

from __future__ import annotations

import re
import uuid
from copy import deepcopy
from typing import Optional

import config
from chunking import ChunkType, CodeChunk
from utils.logger import get_logger

logger = get_logger(__name__)

# Chunk types that CAN be split into sub-chunks
_SPLITTABLE_TYPES: frozenset[ChunkType] = frozenset({
    ChunkType.FUNCTION,
    ChunkType.METHOD,
})


# ===========================================================================
# Public API
# ===========================================================================

class Splitter:
    """Splits large CodeChunks into overlapping sub-chunks."""

    def split_large_chunks(self, chunks: list[CodeChunk]) -> list[CodeChunk]:
        """
        Process all chunks and replace oversized ones with sub-chunks.

        For splittable chunk types: split into overlapping sub-chunks.
        For non-splittable types: truncate content to MAX_CHUNK_TOKENS.

        Args:
            chunks: Input list (may be mutated — always work from return value).

        Returns:
            New list where large splittable chunks are replaced by sub-chunks,
            and large non-splittable chunks have truncated content.
        """
        result: list[CodeChunk] = []
        split_count = 0

        for chunk in chunks:
            if chunk.token_count <= config.MAX_CHUNK_TOKENS:
                result.append(chunk)
                continue

            if chunk.chunk_type in _SPLITTABLE_TYPES:
                sub_chunks = self._split_single_chunk(chunk)
                if len(sub_chunks) > 1:
                    split_count += 1
                result.extend(sub_chunks)
            else:
                # Truncate non-splittable chunk
                truncated = _truncate_chunk(chunk)
                result.append(truncated)

        if split_count:
            logger.info("Split %d large function chunks into sub-chunks", split_count)

        return result

    def _split_single_chunk(self, chunk: CodeChunk) -> list[CodeChunk]:
        """
        Split one oversized FUNCTION/METHOD chunk into overlapping sub-chunks.

        Strategy:
        1. Split content into lines.
        2. Build sub-chunks greedily line by line.
        3. When token budget (MAX_CHUNK_TOKENS) is reached, start a new
           sub-chunk with CHUNK_OVERLAP_TOKENS of tail from the previous one.
        4. Each sub-chunk has a context header prepended.
        5. Each sub-chunk gets a fresh UUID.
        """
        lines = chunk.content.splitlines(keepends=True)

        if not lines:
            return [chunk]

        # ---- pass 1: segment lines into groups ----
        groups: list[list[str]] = []
        current_lines: list[str] = []
        current_tokens = 0

        for line in lines:
            line_tokens = _count_tokens_fast(line)
            if current_tokens + line_tokens > config.MAX_CHUNK_TOKENS and current_lines:
                groups.append(current_lines)
                # Overlap: keep last N tokens worth of lines
                overlap_lines = _tail_lines(current_lines, config.CHUNK_OVERLAP_TOKENS)
                current_lines = overlap_lines + [line]
                current_tokens = _count_tokens_fast("".join(current_lines))
            else:
                current_lines.append(line)
                current_tokens += line_tokens

        if current_lines:
            groups.append(current_lines)

        # If somehow only 1 group — edge case where single line > max
        if len(groups) == 1:
            if chunk.token_count > config.MAX_CHUNK_TOKENS:
                logger.warning(
                    "Chunk %s is %d tokens (limit %d) but cannot be split further — truncating",
                    chunk.chunk_id, chunk.token_count, config.MAX_CHUNK_TOKENS,
                )
                return [_truncate_chunk(chunk)]
            return [chunk]

        total = len(groups)
        sub_chunks: list[CodeChunk] = []

        for idx, group_lines in enumerate(groups):
            sub_content = _build_subchunk_content(
                chunk.qualified_name, idx, total, group_lines
            )
            sub_tokens = _count_tokens_fast(sub_content)

            sub = deepcopy(chunk)
            sub.chunk_id            = str(uuid.uuid4())
            sub.content             = sub_content
            sub.content_preview     = sub_content[:config.MAX_CONTENT_PREVIEW_CHARS]
            sub.token_count         = sub_tokens
            sub.name                = f"{chunk.name} [part {idx + 1}/{total}]"
            sub.chunk_type          = ChunkType.FUNCTION_SUBCHUNK
            sub.is_subchunk         = True
            sub.subchunk_index      = idx
            sub.total_subchunks     = total
            sub.parent_function     = chunk.qualified_name
            sub.overlap_with_previous = idx > 0
            sub_chunks.append(sub)

        return sub_chunks


# ===========================================================================
# Private helpers
# ===========================================================================

def _build_subchunk_content(
    qualified_name: str,
    idx: int,
    total: int,
    lines: list[str],
) -> str:
    """Prepend a context header to sub-chunk content."""
    header = f"# Continuation of {qualified_name} (part {idx + 1}/{total})\n\n"
    body   = "".join(lines)
    return header + body


def _tail_lines(lines: list[str], target_tokens: int) -> list[str]:
    """Return the last lines of *lines* that fit within *target_tokens*."""
    result: list[str] = []
    accumulated = 0
    for line in reversed(lines):
        t = _count_tokens_fast(line)
        if accumulated + t > target_tokens:
            break
        result.insert(0, line)
        accumulated += t
    return result


def _truncate_chunk(chunk: CodeChunk) -> CodeChunk:
    """Truncate a non-splittable chunk to MAX_CHUNK_TOKENS."""
    from copy import deepcopy
    truncated = deepcopy(chunk)
    # Rough character limit: 4 chars per token
    char_limit = config.MAX_CHUNK_TOKENS * 4
    if len(chunk.content) > char_limit:
        truncated.content = chunk.content[:char_limit] + "\n... [truncated]"
    truncated.token_count = _count_tokens_fast(truncated.content)
    return truncated


def _count_tokens_fast(text: str) -> int:
    """Fast token count using tiktoken; falls back to character estimate."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:  # noqa: BLE001
        return len(text) // 4
