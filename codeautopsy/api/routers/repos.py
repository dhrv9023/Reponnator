"""
api/routers/repos.py — Repository management endpoints (Phase 1)

Endpoints:
- POST /api/repos/ingest - Trigger Phase 1 ingestion
- GET /api/repos - List all repositories
- GET /api/repos/{repo_key} - Get repository details
- DELETE /api/repos/{repo_key} - Delete repository
"""

import logging
import json
import shutil
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, status
from datetime import datetime

from api.models import IngestRequest, JobResponse, RepoListResponse, RepoDetailResponse, RepoSummary
from api.services import job_manager
from api.middleware import RepoNotFoundError, JobAlreadyRunningError

# Import Phase 1 modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import DATA_DIR
from ingestion import url_parser, github_client, file_fetcher, storage

logger = logging.getLogger(__name__)
router = APIRouter()


async def run_ingest_job(job_id: str, github_url: str, branch: str, force: bool):
    """Background task to run Phase 1 ingestion."""
    try:
        await job_manager.start_job(job_id)
        await job_manager.update_progress(job_id, 5, "Parsing GitHub URL")
        
        # Parse URL
        parsed = url_parser.parse_github_url(github_url)
        owner = parsed.owner
        repo_name = parsed.repo_name
        branch = branch or parsed.branch
        
        await job_manager.update_progress(job_id, 10, "Initializing GitHub client")
        
        # Initialize GitHub client
        from dotenv import load_dotenv
        import os
        load_dotenv(Path(__file__).parent.parent.parent / ".env")
        token = os.getenv("GITHUB_TOKEN")
        client = github_client.GitHubClient(token=token)
        
        # Check if already cached and force is False
        repo_key = f"{owner}__{repo_name}"
        repo_folder = DATA_DIR / repo_key
        manifest_path = repo_folder / "manifest.json"
        
        if manifest_path.exists() and not force:
            logger.info(f"Repository {owner}/{repo_name} already fetched on disk. Skipping GitHub fetch.")
            await job_manager.update_progress(job_id, 15, "Using cached files")
        else:
            await job_manager.update_progress(job_id, 15, "Fetching repository")
            
            # Fetch repository
            result = file_fetcher.fetch_repository(
                github_client=client,
                owner=owner,
                repo_name=repo_name,
                branch=branch
            )
            
            await job_manager.update_progress(job_id, 20, "Saving to disk")
            
            # Save results
            repo_folder = storage.save_fetch_result(result, DATA_DIR)
        
        await job_manager.update_progress(job_id, 25, "Ingestion complete")
        
        # Phase 2: Parse
        await job_manager.update_progress(job_id, 30, "Parsing code (Phase 2)")
        try:
            from parsing.parse_orchestrator import parse_repository
            parse_repository(repo_folder, force_reparse=force)
            await job_manager.update_progress(job_id, 45, "Parsing complete")
        except Exception as e:
            logger.error(f"Parse failed: {e}")
            await job_manager.update_progress(job_id, 45, f"Parse warning: {str(e)[:50]}")
        
        # Phase 3: Embed
        await job_manager.update_progress(job_id, 50, "Creating embeddings (Phase 3)")
        try:
            from chunking.chunk_orchestrator import chunk_and_embed_repository
            chunk_and_embed_repository(repo_folder, force_rechunk=force)
            await job_manager.update_progress(job_id, 65, "Embeddings complete")
        except Exception as e:
            logger.error(f"Embed failed: {e}")
            await job_manager.update_progress(job_id, 65, f"Embed warning: {str(e)[:50]}")
        
        # Phase 6: Diagram
        await job_manager.update_progress(job_id, 70, "Generating diagram (Phase 6)")
        try:
            from diagram.mermaid_generator import generate_mermaid_diagram
            generate_mermaid_diagram(repo_folder)
            await job_manager.update_progress(job_id, 85, "Diagram complete")
        except Exception as e:
            logger.error(f"Diagram failed: {e}")
            await job_manager.update_progress(job_id, 85, f"Diagram warning: {str(e)[:50]}")
        
        # Phase 7: Story
        await job_manager.update_progress(job_id, 90, "Generating story (Phase 7)")
        try:
            from story.repponator import generate_architectural_story
            generate_architectural_story(repo_folder, force=force)
            await job_manager.update_progress(job_id, 100, "All phases complete!")
        except Exception as e:
            logger.error(f"Story failed: {e}")
            await job_manager.update_progress(job_id, 100, f"Complete (story warning: {str(e)[:50]})")
        
        await job_manager.mark_complete(job_id)
        
        logger.info(f"Full pipeline complete: {owner}/{repo_name}")
        
    except Exception as e:
        logger.exception(f"Ingestion failed: {e}")
        await job_manager.mark_failed(job_id, str(e))


@router.post("/ingest", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_repo(request: IngestRequest, background_tasks: BackgroundTasks):
    """
    Trigger Phase 1 - Ingest a GitHub repository.
    
    Returns immediately with a job_id. Poll /api/jobs/{job_id} for status.
    """
    # Parse URL to get repo_key
    try:
        parsed = url_parser.parse_github_url(request.github_url)
        repo_key = f"{parsed.owner}__{parsed.repo_name}"
    except Exception as e:
        raise ValueError(f"Invalid GitHub URL: {e}")
    
    # Check if already running
    existing_job = await job_manager.check_running_job("ingest", repo_key)
    if existing_job:
        raise JobAlreadyRunningError("ingest", repo_key, existing_job)
    
    # Create job
    job_id = await job_manager.create_job("ingest", repo_key)
    
    # Start background task
    background_tasks.add_task(
        run_ingest_job,
        job_id,
        request.github_url,
        request.branch,
        request.force
    )
    
    return JobResponse(
        job_id=job_id,
        status="queued",
        repo_key=repo_key
    )


@router.get("", response_model=RepoListResponse)
async def list_repos():
    """
    List all ingested repositories.
    """
    repos = storage.list_fetched_repos(DATA_DIR)
    
    repo_summaries = []
    for repo in repos:
        # Check which phases are complete
        repo_folder = DATA_DIR / repo['repo_folder'].split('/')[-1]
        phases_complete = ["ingest"]
        
        if (repo_folder / "parsed" / "parse_manifest.json").exists():
            phases_complete.append("parse")
        if (repo_folder / "chunks" / "chunk_manifest.json").exists():
            phases_complete.append("chunk")
        if (repo_folder / "diagram" / "mermaid_diagram.mmd").exists():
            phases_complete.append("diagram")
        if (repo_folder / "story" / "story_output.json").exists():
            phases_complete.append("story")
        
        repo_summaries.append(RepoSummary(
            repo_key=repo['full_name'].replace('/', '__'),
            owner=repo['full_name'].split('/')[0],
            name=repo['full_name'].split('/')[1],
            total_files=repo['total_files_fetched'],
            primary_language=repo.get('primary_language', 'Unknown'),
            ingested_at=datetime.fromisoformat(repo['fetch_timestamp'].replace('Z', '+00:00')),
            phases_complete=phases_complete
        ))
    
    return RepoListResponse(repos=repo_summaries)


@router.get("/{repo_key}", response_model=RepoDetailResponse)
async def get_repo(repo_key: str):
    """
    Get detailed metadata for a repository.
    """
    # Find repo folder
    repo_folder = DATA_DIR / repo_key
    manifest_path = repo_folder / "manifest.json"
    
    if not manifest_path.exists():
        raise RepoNotFoundError(repo_key)
    
    # Load manifest
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    # Check which phases are complete
    phases_complete = ["ingest"]
    if (repo_folder / "parsed" / "parse_manifest.json").exists():
        phases_complete.append("parse")
    if (repo_folder / "chunks" / "chunk_manifest.json").exists():
        phases_complete.append("chunk")
    if (repo_folder / "diagram" / "mermaid_diagram.mmd").exists():
        phases_complete.append("diagram")
    if (repo_folder / "story" / "story_output.json").exists():
        phases_complete.append("story")
    
    return RepoDetailResponse(
        repo_key=repo_key,
        owner=manifest.get('repo_owner') or manifest.get('repo', {}).get('owner', repo_key.split('__')[0]),
        name=manifest.get('repo_name') or manifest.get('repo', {}).get('name', repo_key.split('__')[-1]),
        branch=manifest.get('branch') or manifest.get('repo', {}).get('branch', 'main'),
        total_files=manifest.get('total_files_fetched') or manifest.get('ingestion_stats', {}).get('total_files_fetched', 0),
        total_bytes=manifest.get('total_bytes_fetched') or manifest.get('ingestion_stats', {}).get('total_bytes_fetched', 0),
        primary_language=manifest.get('language_analysis', {}).get('primary_language', 'Unknown'),
        languages={
            lang: info if isinstance(info, (int, float)) else info.get('percentage', 0)
            for lang, info in manifest.get('language_analysis', {}).get('languages', {}).items()
        },
        ingested_at=datetime.fromisoformat(manifest['fetch_timestamp'].replace('Z', '+00:00')),
        phases_complete=phases_complete
    )


@router.delete("/{repo_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repo(repo_key: str):
    """
    Delete a repository and all its generated data.
    """
    repo_folder = DATA_DIR / repo_key
    
    if not repo_folder.exists():
        raise RepoNotFoundError(repo_key)
    
    # Delete folder
    shutil.rmtree(repo_folder)
    
    logger.info(f"Deleted repository: {repo_key}")
    
    return None
