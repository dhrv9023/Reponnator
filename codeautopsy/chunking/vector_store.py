"""
chunking/vector_store.py — Phase 3 ChromaDB Operations

All ChromaDB interactions are isolated here.  No other module imports
chromadb directly — everything goes through VectorStore.

Uses ChromaDB 0.5.x PersistentClient API.
Collection naming convention: codeautopsy__{owner}__{repo}

Fix (ChromaDB multi-client lock): A module-level singleton cache keyed by
db_path ensures only ONE PersistentClient per path is ever alive at a time.
Multiple VectorStore instances pointing to the same directory reuse the same
underlying client, eliminating SQLite "database is locked" races.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Optional

import config
from chunking import CodeChunk
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level singleton cache for ChromaDB PersistentClient instances.
# Keyed by the absolute db_path string.  A threading.Lock guards creation so
# concurrent first-time callers don't race to build two clients.
# ---------------------------------------------------------------------------
_CHROMA_CLIENT_CACHE: dict[str, object] = {}
_CHROMA_CACHE_LOCK = threading.Lock()


def _get_or_create_chroma_client(db_path: str):
    """Return a cached ChromaDB PersistentClient for *db_path*, creating it once."""
    if db_path in _CHROMA_CLIENT_CACHE:
        return _CHROMA_CLIENT_CACHE[db_path]

    with _CHROMA_CACHE_LOCK:
        # Double-check inside the lock in case another thread just created it.
        if db_path in _CHROMA_CLIENT_CACHE:
            return _CHROMA_CLIENT_CACHE[db_path]

        try:
            import chromadb  # type: ignore
            client = chromadb.PersistentClient(path=db_path)
            _CHROMA_CLIENT_CACHE[db_path] = client
            logger.info("ChromaDB PersistentClient created (singleton) at %s", db_path)
            return client
        except OSError as exc:
            if "corrupt" in str(exc).lower():
                raise RuntimeError(
                    f"ChromaDB database at {db_path!r} appears corrupted. "
                    f"Fix: rm -rf {db_path}  then rerun with --force."
                ) from exc
            raise RuntimeError(
                f"Disk full or permission error opening ChromaDB at {db_path!r}: {exc}"
            ) from exc


class VectorStore:
    """Manages a ChromaDB persistent store for CodeChunks."""

    def __init__(self, db_path: str = config.CHROMA_DB_PATH) -> None:
        import chromadb  # type: ignore
        self._chromadb = chromadb
        self._client = _get_or_create_chroma_client(db_path)
        logger.debug("VectorStore using shared ChromaDB client for %s", db_path)

    # -----------------------------------------------------------------------
    # Collection management
    # -----------------------------------------------------------------------

    def get_or_create_collection(
        self,
        owner: str,
        repo_name: str,
    ):
        """Return (or create) the ChromaDB collection for this repo."""
        name = self.sanitize_collection_name(
            f"{config.CHROMA_COLLECTION_PREFIX}__{owner}__{repo_name}"
        )
        collection = self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # we supply embeddings manually
        )
        logger.info("Using ChromaDB collection: %s", name)
        return collection

    def collection_exists(self, owner: str, repo_name: str) -> bool:
        """Return True if a collection for this repo already exists."""
        name = self.sanitize_collection_name(
            f"{config.CHROMA_COLLECTION_PREFIX}__{owner}__{repo_name}"
        )
        try:
            existing = [c.name for c in self._client.list_collections()]
            return name in existing
        except Exception:  # noqa: BLE001
            return False

    def delete_collection(self, owner: str, repo_name: str) -> None:
        """Delete the collection for this repo (used with --force)."""
        name = self.sanitize_collection_name(
            f"{config.CHROMA_COLLECTION_PREFIX}__{owner}__{repo_name}"
        )
        try:
            self._client.delete_collection(name=name)
            logger.info("Deleted existing ChromaDB collection: %s", name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not delete collection %s: %s", name, exc)

    def get_collection_stats(self, owner: str, repo_name: str) -> dict:
        """Return basic stats for the named collection."""
        name = self.sanitize_collection_name(
            f"{config.CHROMA_COLLECTION_PREFIX}__{owner}__{repo_name}"
        )
        try:
            col = self._client.get_collection(name=name)
            count = col.count()
            return {
                "collection_name": name,
                "total_chunks": count,
            }
        except Exception as exc:  # noqa: BLE001
            return {"collection_name": name, "total_chunks": 0, "error": str(exc)}

    # -----------------------------------------------------------------------
    # Writing
    # -----------------------------------------------------------------------

    def add_chunks(
        self,
        collection,
        chunks: list[CodeChunk],
        batch_size: int = 500,
    ) -> None:
        """
        Add CodeChunks to a ChromaDB collection in batches.

        Skips any chunk without an embedding (logs a warning).
        ChromaDB only accepts str/int/float/bool metadata values;
        list fields are JSON-serialized to strings.
        """
        total   = len(chunks)
        added   = 0
        skipped = 0

        for start in range(0, total, batch_size):
            batch = chunks[start : start + batch_size]

            ids:       list[str]        = []
            embeddings: list[list[float]] = []
            documents: list[str]        = []
            metadatas: list[dict]       = []

            for chunk in batch:
                if chunk.embedding is None or len(chunk.embedding) == 0:
                    logger.warning("Chunk %s has no embedding — skipping", chunk.chunk_id)
                    skipped += 1
                    continue

                ids.append(chunk.chunk_id)
                embeddings.append(chunk.embedding)
                documents.append(chunk.content)
                metadatas.append(_build_metadata(chunk))

            if ids:
                try:
                    collection.add(
                        ids=ids,
                        embeddings=embeddings,
                        documents=documents,
                        metadatas=metadatas,
                    )
                except OSError as exc:
                    if exc.errno == 28:  # ENOSPC
                        raise RuntimeError(
                            "CRITICAL: Disk full while writing to ChromaDB. "
                            "Free disk space and rerun with --force."
                        ) from exc
                    raise

                added += len(ids)

            logger.info("Stored %d/%d chunks in ChromaDB", added, total)

        if skipped:
            logger.warning("Skipped %d chunks with missing embeddings", skipped)

    # -----------------------------------------------------------------------
    # Querying
    # -----------------------------------------------------------------------

    def query(
        self,
        collection,
        query_embedding: list[float],
        n_results: int = 10,
        where_filter: Optional[dict] = None,
    ) -> list[dict]:
        """
        Semantic search over the collection.

        Returns a list of dicts sorted by similarity (highest first):
        {chunk_id, content, metadata, distance, similarity_score}
        """
        kwargs: dict = dict(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        if where_filter:
            kwargs["where"] = where_filter

        try:
            raw = collection.query(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error("ChromaDB query failed: %s", exc)
            return []

        results: list[dict] = []
        ids        = raw.get("ids", [[]])[0]
        docs       = raw.get("documents", [[]])[0]
        metas      = raw.get("metadatas", [[]])[0]
        distances  = raw.get("distances", [[]])[0]

        for cid, doc, meta, dist in zip(ids, docs, metas, distances):
            results.append({
                "chunk_id":        cid,
                "content":         doc,
                "metadata":        meta,
                "distance":        dist,
                "similarity_score": max(0.0, 1.0 - dist),
            })

        return results

    def get_chunk_by_id(self, collection, chunk_id: str) -> Optional[dict]:
        """Fetch a single chunk by its UUID."""
        try:
            raw = collection.get(
                ids=[chunk_id],
                include=["documents", "metadatas", "embeddings"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("get_chunk_by_id failed for %s: %s", chunk_id, exc)
            return None

        if not raw["ids"]:
            return None

        raw_embeddings = raw.get("embeddings")
        emb_value = None
        if raw_embeddings is not None:
            try:
                # raw_embeddings may be numpy array — handle safely
                first = raw_embeddings[0]
                if first is not None:
                    emb_value = first.tolist() if hasattr(first, "tolist") else list(first)
            except (IndexError, TypeError):
                emb_value = None

        return {
            "chunk_id":  raw["ids"][0],
            "content":   raw["documents"][0],
            "metadata":  raw["metadatas"][0],
            "embedding": emb_value,
        }

    def get_chunks_by_qualified_name(
        self,
        collection,
        qualified_name: str,
    ) -> list[dict]:
        """
        Fetch all chunks matching a qualified_name (could be multiple
        if a function was split into sub-chunks).
        """
        try:
            raw = collection.get(
                where={"qualified_name": {"$eq": qualified_name}},
                include=["documents", "metadatas"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "get_chunks_by_qualified_name failed for %s: %s", qualified_name, exc
            )
            return []

        results: list[dict] = []
        for cid, doc, meta in zip(
            raw.get("ids", []), raw.get("documents", []), raw.get("metadatas", [])
        ):
            results.append({"chunk_id": cid, "content": doc, "metadata": meta})
        return results

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    def sanitize_collection_name(self, name: str) -> str:
        """
        Make a string safe for ChromaDB collection names:
        - Only alphanumeric, underscores, hyphens
        - Must start with alphanumeric char
        - Max 63 characters
        """
        sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
        if sanitized and not sanitized[0].isalnum():
            sanitized = "c" + sanitized
        sanitized = sanitized[:63]
        return sanitized


# ===========================================================================
# Private helpers
# ===========================================================================

def _build_metadata(chunk: CodeChunk) -> dict:
    """
    Build a flat metadata dict for ChromaDB.

    ChromaDB only accepts str/int/float/bool values at the top level.
    Lists are JSON-serialized to strings.
    """
    return {
        # Identity
        "repo_owner":           chunk.repo_owner,
        "repo_name":            chunk.repo_name,
        "chunk_type":           chunk.chunk_type.value
                                if hasattr(chunk.chunk_type, "value")
                                else str(chunk.chunk_type),
        # Location
        "file_path":            chunk.file_path,
        "language":             chunk.language,
        "start_line":           chunk.start_line,
        "end_line":             chunk.end_line,
        "sha":                  chunk.sha,
        # Naming
        "name":                 chunk.name,
        "qualified_name":       chunk.qualified_name,
        "parent_class":         chunk.parent_class or "",
        "parent_function":      chunk.parent_function or "",
        # Semantic booleans
        "is_entry_point":       chunk.is_entry_point,
        "is_constructor":       chunk.is_constructor,
        "is_private":           chunk.is_private,
        "is_async":             chunk.is_async,
        "complexity_score":     chunk.complexity_score,
        "token_count":          chunk.token_count,
        # Sub-chunk tracking
        "is_subchunk":          chunk.is_subchunk,
        "subchunk_index":       chunk.subchunk_index if chunk.subchunk_index is not None else 0,
        "total_subchunks":      chunk.total_subchunks if chunk.total_subchunks is not None else 1,
        # Serialized lists
        "calls_count":          len(chunk.calls),
        "called_by_count":      len(chunk.called_by),
        "calls_serialized":     json.dumps(chunk.calls[:10]),
        "called_by_serialized": json.dumps(chunk.called_by[:10]),
        "decorators_serialized": json.dumps(chunk.decorators),
        "patterns_serialized":  json.dumps(chunk.architectural_patterns),
        "keywords_serialized":  json.dumps(chunk.search_keywords),
        "docstring_preview":    (chunk.docstring or "")[:200],
    }
