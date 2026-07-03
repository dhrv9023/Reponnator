"""
api/routers/qa.py — Q&A endpoints (Phase 4)

Fix: RAGPipeline is now cached per repo_key (singleton pattern via functools.lru_cache).
     The pipeline.ask() call is offloaded to a thread-pool executor so the synchronous
     LLM HTTP calls never block the Uvicorn async event loop.
"""

import asyncio
import logging
import functools
from pathlib import Path
from fastapi import APIRouter

from api.models import QARequest, QAResponse, Citation
from api.middleware import PhaseNotCompleteError

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import DATA_DIR
from rag.rag_pipeline import RAGPipeline

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Singleton cache — keyed by repo_key, built lazily on first request.
# Using functools.lru_cache keeps a single RAGPipeline (and therefore a single
# loaded Embedder + LLMClient) per repo rather than re-constructing on every call.
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=8)
def _get_pipeline(repo_key: str) -> RAGPipeline:
    """
    Return (or lazily create) a RAGPipeline for *repo_key*.

    Because lru_cache memoises the result, the Embedder model is loaded
    exactly once per repo across the lifetime of the server process.
    """
    parts = repo_key.split("__")
    if len(parts) != 2:
        raise ValueError(f"Invalid repo_key format: {repo_key!r}. Expected: owner__repo")
    owner, repo_name = parts
    logger.info("Creating RAGPipeline singleton for %s", repo_key)
    return RAGPipeline(owner, repo_name)


@router.post("", response_model=QAResponse)
async def ask_question(request: QARequest):
    """Ask a natural language question about a repository (Phase 4 RAG)."""
    repo_folder = DATA_DIR / request.repo_key

    # Check Phase 3 complete
    if not (repo_folder / "chunks" / "chunk_manifest.json").exists():
        raise PhaseNotCompleteError("qa", "chunk")

    # Retrieve (or create) the cached singleton pipeline
    try:
        pipeline = _get_pipeline(request.repo_key)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc))

    # Get or create session
    session_id = request.session_id or pipeline.new_session()

    # ---------------------------------------------------------------------------
    # Fix: run the synchronous pipeline.ask() in a thread-pool executor so the
    # blocking Groq/Gemini/Ollama HTTP calls never freeze the async event loop.
    # ---------------------------------------------------------------------------
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,  # use default ThreadPoolExecutor
        lambda: pipeline.ask(request.question, session_id)
    )

    # Extract citations
    citations = []
    if hasattr(response, "chunks_used") and response.chunks_used:
        for chunk in response.chunks_used[:5]:  # Top 5 citations
            citations.append(Citation(
                filename=chunk.get("filename", ""),
                line_start=chunk.get("line_start"),
                line_end=chunk.get("line_end"),
                snippet=chunk.get("content", "")[:200],
            ))

    # Rough token estimate
    tokens_used = len(request.question.split()) + len(response.answer.split())

    return QAResponse(
        answer=response.answer,
        citations=citations,
        session_id=session_id,
        tokens_used=tokens_used,
        confidence=response.confidence,
    )
