"""
api/routers/story.py — Story generation endpoints (Phase 7)
"""

import logging
import json
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, status

from api.models import StoryRequest, JobResponse, StoryResponse, KeyModule
from api.services import job_manager
from api.middleware import PhaseNotCompleteError, JobAlreadyRunningError

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import DATA_DIR, PARSED_DIR_NAME, PARSE_MANIFEST_FILENAME
from story.repponator import generate_architectural_story

logger = logging.getLogger(__name__)
router = APIRouter()


async def run_story_job(job_id: str, repo_key: str, force: bool):
    """Background task to run Phase 7 story generation."""
    try:
        await job_manager.start_job(job_id)
        await job_manager.update_progress(job_id, 10, "Starting story generation")
        
        repo_folder = DATA_DIR / repo_key
        
        # Generate story
        story, metadata = generate_architectural_story(repo_folder, force=force)
        
        await job_manager.update_progress(job_id, 100, "Complete")
        await job_manager.mark_complete(job_id)
        
        logger.info(f"Story generation complete: {repo_key}")
        
    except Exception as e:
        logger.exception(f"Story generation failed: {e}")
        await job_manager.mark_failed(job_id, str(e))


@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_story(request: StoryRequest, background_tasks: BackgroundTasks):
    """Trigger Phase 7 - Generate architectural story."""
    repo_folder = DATA_DIR / request.repo_key
    
    # Check Phase 2 complete
    if not (repo_folder / PARSED_DIR_NAME / PARSE_MANIFEST_FILENAME).exists():
        raise PhaseNotCompleteError("story", "parse")
    
    # Check if already running
    existing_job = await job_manager.check_running_job("story", request.repo_key)
    if existing_job:
        raise JobAlreadyRunningError("story", request.repo_key, existing_job)
    
    # Create job
    job_id = await job_manager.create_job("story", request.repo_key)
    
    # Start background task
    background_tasks.add_task(run_story_job, job_id, request.repo_key, request.force)
    
    return JobResponse(job_id=job_id, status="queued", repo_key=request.repo_key)


@router.get("/{repo_key}", response_model=StoryResponse)
async def get_story(repo_key: str):
    """Get Phase 7 architectural story output."""
    repo_folder = DATA_DIR / repo_key
    story_path = repo_folder / "story" / "story_output.json"
    meta_path = repo_folder / "story" / "story_meta.json"
    
    if not story_path.exists():
        raise PhaseNotCompleteError("story", "story")
    
    # Load story
    with open(story_path, 'r') as f:
        story_data = json.load(f)
    
    # Load metadata
    metadata = {}
    if meta_path.exists():
        with open(meta_path, 'r') as f:
            metadata = json.load(f)
    
    # Build key modules list
    key_modules = []
    for module in story_data.get('key_modules', []):
        key_modules.append(KeyModule(
            module_id=module.get('module_id', ''),
            role_title=module.get('role_title', ''),
            explanation=module.get('explanation', '')
        ))
    
    return StoryResponse(
        project_summary=story_data.get('project_summary', ''),
        tech_stack=story_data.get('tech_stack', []),
        primary_commitment=story_data.get('primary_commitment', ''),
        origin_story=story_data.get('origin_story', ''),
        how_it_flows=story_data.get('how_it_flows', ''),
        key_modules=key_modules,
        design_tensions=story_data.get('design_tensions', ''),
        founding_metaphor=story_data.get('founding_metaphor', ''),
        verdict=story_data.get('verdict', ''),
        model_used=metadata.get('model_used', ''),
        generation_duration_seconds=metadata.get('generation_duration_seconds', 0),
        tokens_used=metadata.get('prompt_tokens', 0) + metadata.get('completion_tokens', 0)
    )
