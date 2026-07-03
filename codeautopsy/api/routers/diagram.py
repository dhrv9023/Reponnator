"""
api/routers/diagram.py — Diagram generation endpoints (Phase 6)
"""

import logging
import json
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, status

from api.models import DiagramRequest, JobResponse, DiagramResponse, NodeMetadata
from api.services import job_manager
from api.middleware import PhaseNotCompleteError, JobAlreadyRunningError

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import DATA_DIR, PARSED_DIR_NAME, PARSE_MANIFEST_FILENAME
from diagram.mermaid_generator import generate_mermaid_diagram

logger = logging.getLogger(__name__)
router = APIRouter()


async def run_diagram_job(job_id: str, repo_key: str, force: bool):
    """Background task to run Phase 6 diagram generation."""
    try:
        await job_manager.start_job(job_id)
        await job_manager.update_progress(job_id, 10, "Starting diagram generation")
        
        repo_folder = DATA_DIR / repo_key
        
        # Generate diagram
        mermaid_code, metadata = generate_mermaid_diagram(repo_folder)
        
        await job_manager.update_progress(job_id, 100, "Complete")
        await job_manager.mark_complete(job_id)
        
        logger.info(f"Diagram generation complete: {repo_key}")
        
    except Exception as e:
        logger.exception(f"Diagram generation failed: {e}")
        await job_manager.mark_failed(job_id, str(e))


@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_diagram(request: DiagramRequest, background_tasks: BackgroundTasks):
    """Trigger Phase 6 - Generate Mermaid diagram."""
    repo_folder = DATA_DIR / request.repo_key
    
    # Check Phase 2 complete
    if not (repo_folder / PARSED_DIR_NAME / PARSE_MANIFEST_FILENAME).exists():
        raise PhaseNotCompleteError("diagram", "parse")
    
    # Check if already running
    existing_job = await job_manager.check_running_job("diagram", request.repo_key)
    if existing_job:
        raise JobAlreadyRunningError("diagram", request.repo_key, existing_job)
    
    # Create job
    job_id = await job_manager.create_job("diagram", request.repo_key)
    
    # Start background task
    background_tasks.add_task(run_diagram_job, job_id, request.repo_key, request.force)
    
    return JobResponse(job_id=job_id, status="queued", repo_key=request.repo_key)


@router.get("/{repo_key}", response_model=DiagramResponse)
async def get_diagram(repo_key: str):
    """Get Phase 6 diagram output."""
    repo_folder = DATA_DIR / repo_key
    diagram_path = repo_folder / "diagram" / "mermaid_diagram.mmd"
    metadata_path = repo_folder / "diagram" / "diagram_metadata.json"
    
    if not diagram_path.exists():
        raise PhaseNotCompleteError("diagram", "diagram")
    
    # Load Mermaid syntax
    with open(diagram_path, 'r') as f:
        mermaid_syntax = f.read()
    
    # Load metadata
    metadata = {}
    if metadata_path.exists():
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
    
    # Build node metadata list
    node_metadata_list = []
    for node in metadata.get('nodes', []):
        node_metadata_list.append(NodeMetadata(
            id=node.get('id', ''),
            label=node.get('label', ''),
            type=node.get('type', 'module'),
            functions=node.get('functions', []),
            classes=node.get('classes', []),
            call_count=node.get('call_count', 0)
        ))
    
    return DiagramResponse(
        mermaid_syntax=mermaid_syntax,
        node_count=metadata.get('total_nodes', 0),
        edge_count=metadata.get('total_edges', 0),
        metadata=node_metadata_list
    )
