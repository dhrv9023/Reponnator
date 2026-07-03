"""
api/routers/chunk.py — Chunking and embedding endpoints (Phase 3)
"""

import logging
import json
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, status

from api.models import ChunkRequest, JobResponse, ChunkResponse
from api.services import job_manager
from api.middleware import RepoNotFoundError, PhaseNotCompleteError, JobAlreadyRunningError

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import DATA_DIR, PARSED_DIR_NAME, PARSE_MANIFEST_FILENAME
from chunking import chunk_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()


async def run_chunk_job(job_id: str, repo_key: str, force: bool):
    """Background task to run Phase 3 chunking."""
    try:
        await job_manager.start_job(job_id)
        await job_manager.update_progress(job_id, 10, "Starting chunking")
        
        repo_folder = DATA_DIR / repo_key
        
        # Run chunking
        manifest = chunk_orchestrator.chunk_and_embed_repository(
            repo_folder=repo_folder,
            force_rechunk=force
        )
        
        await job_manager.update_progress(job_id, 100, "Complete")
        await job_manager.mark_complete(job_id)
        
        logger.info(f"Chunking complete: {repo_key}")
        
    except Exception as e:
        logger.exception(f"Chunking failed: {e}")
        await job_manager.mark_failed(job_id, str(e))


@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def chunk_repo(request: ChunkRequest, background_tasks: BackgroundTasks):
    """Trigger Phase 3 - Chunk and embed a repository."""
    repo_folder = DATA_DIR / request.repo_key
    
    # Check Phase 2 complete
    if not (repo_folder / PARSED_DIR_NAME / PARSE_MANIFEST_FILENAME).exists():
        raise PhaseNotCompleteError("chunk", "parse")
    
    # Check if already running
    existing_job = await job_manager.check_running_job("chunk", request.repo_key)
    if existing_job:
        raise JobAlreadyRunningError("chunk", request.repo_key, existing_job)
    
    # Create job
    job_id = await job_manager.create_job("chunk", request.repo_key)
    
    # Start background task
    background_tasks.add_task(run_chunk_job, job_id, request.repo_key, request.force)
    
    return JobResponse(job_id=job_id, status="queued", repo_key=request.repo_key)


@router.get("/{repo_key}", response_model=ChunkResponse)
async def get_chunk_output(repo_key: str):
    """Get Phase 3 chunk output."""
    repo_folder = DATA_DIR / repo_key
    manifest_path = repo_folder / "chunks" / "chunk_manifest.json"
    
    if not manifest_path.exists():
        raise PhaseNotCompleteError("chunk", "chunk")
    
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    return ChunkResponse(
        repo_key=repo_key,
        total_chunks=manifest.get('total_chunks', 0),
        embedding_model=manifest.get('embedding_model', ''),
        embedding_dimensions=manifest.get('embedding_dimensions', 0),
        total_tokens=manifest.get('total_tokens', 0),
        average_tokens_per_chunk=manifest.get('average_tokens_per_chunk', 0),
        chroma_collection_name=manifest.get('chroma_collection_name', ''),
        embed_duration_seconds=manifest.get('embed_duration_seconds', 0)
    )
