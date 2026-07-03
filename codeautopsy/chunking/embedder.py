"""
chunking/embedder.py — Phase 3 Embedding Engine

Converts CodeChunk content strings into dense vector embeddings using
sentence-transformers (all-MiniLM-L6-v2 by default).

Design decisions:
- L2-normalized embeddings → cosine similarity == dot product (faster search)
- Batched encoding for memory efficiency
- Automatic OOM recovery by halving batch size
- CPU-only by default; GPU picked up automatically if available
- Model loaded once (singleton via Embedder class) — never re-initialize
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

import config
from chunking import ChunkType, CodeChunk
from utils.logger import get_logger

logger = get_logger(__name__)


class Embedder:
    """Wraps a sentence-transformers model for batch embedding."""

    def __init__(self, model_name: str = config.EMBEDDING_MODEL_NAME) -> None:
        self._model_name = model_name
        self._model = None
        self._embedding_dim: Optional[int] = None
        self._load_model()

    # -----------------------------------------------------------------------
    # Model loading
    # -----------------------------------------------------------------------

    def _load_model(self) -> None:
        logger.info("Loading embedding model %s …", self._model_name)
        t0 = time.monotonic()

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            self._model = SentenceTransformer(self._model_name)
        except OSError as exc:
            if "corrupted" in str(exc).lower() or "safetensors" in str(exc).lower():
                raise RuntimeError(
                    f"Embedding model cache appears corrupted ({exc}).\n"
                    "Fix: rm -rf ~/.cache/huggingface/hub/models--sentence-transformers*"
                ) from exc
            raise RuntimeError(
                f"Cannot load embedding model. Check internet connection.\n"
                f"Or pre-download with: python -c 'from sentence_transformers import "
                f"SentenceTransformer; SentenceTransformer(\"{self._model_name}\")'"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Unexpected error loading model {self._model_name}: {exc}"
            ) from exc

        # Probe embedding dimension
        probe = self._model.encode(["dimension probe"], convert_to_numpy=True)
        self._embedding_dim = int(probe.shape[1])
        elapsed = time.monotonic() - t0

        logger.info(
            "Model loaded in %.1fs — embedding dimension: %d",
            elapsed, self._embedding_dim,
        )

        if self._embedding_dim != config.EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"CRITICAL: Model {self._model_name} returned dimension "
                f"{self._embedding_dim}, expected {config.EMBEDDING_DIMENSIONS}. "
                f"Check EMBEDDING_MODEL_NAME in config.py."
            )

        # Detect device
        try:
            import torch
            if not torch.cuda.is_available():
                logger.info("No GPU detected. Using CPU for embedding (slower but fine).")
        except ImportError:
            pass

    # -----------------------------------------------------------------------
    # Batch embedding
    # -----------------------------------------------------------------------

    def embed_chunks(
        self,
        chunks: list[CodeChunk],
        show_progress: bool = True,
    ) -> list[CodeChunk]:
        """
        Embed all chunks in batches. Returns the same list with .embedding
        and .embedding_model populated.

        Args:
            chunks:        List of CodeChunk objects to embed.
            show_progress: Log progress every 10 batches.

        Returns:
            The same list with embeddings populated.
        """
        if not chunks:
            return chunks

        total         = len(chunks)
        batch_size    = config.EMBEDDING_BATCH_SIZE
        t_start       = time.monotonic()
        embedded      = 0
        batch_num     = 0

        for start in range(0, total, batch_size):
            batch = chunks[start : start + batch_size]
            contents = [_prepare_content(c) for c in batch]

            # OOM-resilient encode
            embeddings = self._encode_with_retry(contents, batch_size)

            for chunk, emb in zip(batch, embeddings):
                chunk.embedding       = emb.tolist()
                chunk.embedding_model = self._model_name

            embedded  += len(batch)
            batch_num += 1

            if show_progress and (batch_num % 10 == 0 or embedded == total):
                elapsed = time.monotonic() - t_start
                logger.info(
                    "Embedded %d/%d chunks (%.1fs elapsed)",
                    embedded, total, elapsed,
                )

        return chunks

    def _encode_with_retry(
        self,
        contents: list[str],
        batch_size: int,
    ) -> np.ndarray:
        """Encode with OOM recovery: halves batch_size until it fits."""
        current_size = batch_size
        while True:
            try:
                vecs = self._model.encode(
                    contents,
                    batch_size=current_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                return vecs  # type: ignore[return-value]
            except (MemoryError, RuntimeError) as exc:
                if current_size == 1:
                    logger.error(
                        "OOM at batch_size=1 — cannot embed batch. "
                        "Returning zero vectors. Error: %s", exc,
                    )
                    # Return zero vectors so pipeline continues
                    return np.zeros((len(contents), self._embedding_dim or 384), dtype=np.float32)
                current_size = max(1, current_size // 2)
                logger.warning(
                    "OOM during embedding. Halving batch size to %d and retrying.",
                    current_size,
                )

    # -----------------------------------------------------------------------
    # Query embedding
    # -----------------------------------------------------------------------

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string for semantic search (Phase 4+).

        Returns:
            L2-normalized embedding as list[float].
        """
        vec = self._model.encode(
            [query],
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return vec[0].tolist()

    # -----------------------------------------------------------------------
    # Introspection
    # -----------------------------------------------------------------------

    def get_model_info(self) -> dict:
        """Return model metadata dict."""
        try:
            max_seq = self._model.max_seq_length
        except AttributeError:
            max_seq = None
        return {
            "model_name":          self._model_name,
            "embedding_dimensions": self._embedding_dim,
            "max_sequence_length":  max_seq,
        }


# ===========================================================================
# Private helpers
# ===========================================================================

def _prepare_content(chunk: CodeChunk) -> str:
    """
    Sanitize chunk content before passing to the embedding model.
    - Strip null bytes
    - Truncate at MAX_EMBEDDING_TOKENS characters (safety guard)
    """
    content = chunk.content.replace("\x00", "")

    # Roughly check token budget using character estimate
    # Proper token check already done during chunking — this is a safety net
    max_chars = config.MAX_EMBEDDING_TOKENS * 4
    if len(content) > max_chars:
        logger.warning(
            "Chunk %s content length %d exceeds safe limit (%d chars) — truncating",
            chunk.chunk_id, len(content), max_chars,
        )
        content = content[:max_chars]

    return content
