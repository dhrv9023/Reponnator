"""
api/routers/parse.py — Code parsing endpoints (Phase 2)
"""

import logging
import json
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, status

from api.models import ParseRequest, JobResponse, ParseResponse
from api.services import job_manager
from api.middleware import RepoNotFoundError, PhaseNotCompleteError, JobAlreadyRunningError

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import DATA_DIR, PARSED_DIR_NAME, PARSE_MANIFEST_FILENAME
from parsing import parse_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()


async def run_parse_job(job_id: str, repo_key: str, force: bool):
    """Background task to run Phase 2 parsing."""
    try:
        await job_manager.start_job(job_id)
        await job_manager.update_progress(job_id, 10, "Starting parse")
        
        repo_folder = DATA_DIR / repo_key
        
        # Run parse
        manifest = parse_orchestrator.parse_repository(
            repo_folder=repo_folder,
            force_reparse=force
        )
        
        await job_manager.update_progress(job_id, 100, "Complete")
        await job_manager.mark_complete(job_id)
        
        logger.info(f"Parse complete: {repo_key}")
        
    except Exception as e:
        logger.exception(f"Parse failed: {e}")
        await job_manager.mark_failed(job_id, str(e))


@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def parse_repo(request: ParseRequest, background_tasks: BackgroundTasks):
    """Trigger Phase 2 - Parse a repository."""
    repo_folder = DATA_DIR / request.repo_key
    
    # Check Phase 1 complete
    if not (repo_folder / "manifest.json").exists():
        raise RepoNotFoundError(request.repo_key)
    
    # Check if already running
    existing_job = await job_manager.check_running_job("parse", request.repo_key)
    if existing_job:
        raise JobAlreadyRunningError("parse", request.repo_key, existing_job)
    
    # Create job
    job_id = await job_manager.create_job("parse", request.repo_key)
    
    # Start background task
    background_tasks.add_task(run_parse_job, job_id, request.repo_key, request.force)
    
    return JobResponse(job_id=job_id, status="queued", repo_key=request.repo_key)


@router.get("/{repo_key}", response_model=ParseResponse)
async def get_parse_output(repo_key: str):
    """Get Phase 2 parse output."""
    repo_folder = DATA_DIR / repo_key
    manifest_path = repo_folder / PARSED_DIR_NAME / PARSE_MANIFEST_FILENAME
    
    if not manifest_path.exists():
        raise PhaseNotCompleteError("parse", "parse")
    
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    # Load patterns
    patterns_path = repo_folder / PARSED_DIR_NAME / "patterns.json"
    patterns = []
    if patterns_path.exists():
        with open(patterns_path, 'r') as f:
            patterns_data = json.load(f)
            if isinstance(patterns_data, list):
                patterns = patterns_data
            elif isinstance(patterns_data, dict):
                patterns = patterns_data.get("detected_patterns", [])
    
    # Load entry points
    entry_points_path = repo_folder / PARSED_DIR_NAME / "entry_points.json"
    entry_points = []
    if entry_points_path.exists():
        with open(entry_points_path, 'r') as f:
            ep_data = json.load(f)
            if isinstance(ep_data, list) and ep_data:
                entry_points = [ep.get("file_path", "") for ep in ep_data[:3]]
    
    return ParseResponse(
        repo_key=repo_key,
        total_functions=manifest.get('total_functions_extracted', 0),
        total_classes=manifest.get('total_classes_extracted', 0),
        call_edges=manifest.get('total_call_edges', 0),
        detected_patterns=patterns,
        entry_points=entry_points,
        parse_duration_seconds=manifest.get('parse_duration_seconds', 0),
        files_parsed=manifest.get('total_files_parsed', 0),
        files_failed=manifest.get('total_files_failed', 0)
    )
