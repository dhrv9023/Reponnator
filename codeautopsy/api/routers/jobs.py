"""
api/routers/jobs.py — Job status tracking endpoints
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Query

from api.models import JobStatusResponse
from api.services import job_manager, JobStatus

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Poll a background job for its current status."""
    job = await job_manager.get_job(job_id)
    
    if not job:
        from api.middleware import RepoNotFoundError
        raise RepoNotFoundError(f"job:{job_id}")
    
    return JobStatusResponse(
        job_id=job.job_id,
        phase=job.phase,
        repo_key=job.repo_key,
        status=job.status.value,
        progress_percent=job.progress_percent,
        current_step=job.current_step,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error=job.error
    )


@router.get("", response_model=List[JobStatusResponse])
async def list_jobs(
    repo_key: Optional[str] = Query(None, description="Filter by repository key"),
    status: Optional[str] = Query(None, description="Filter by status (queued, running, complete, failed)")
):
    """List all jobs with optional filters."""
    # Convert status string to enum
    status_enum = None
    if status:
        try:
            status_enum = JobStatus(status)
        except ValueError:
            pass
    
    jobs = await job_manager.list_jobs(repo_key=repo_key, status=status_enum)
    
    return [
        JobStatusResponse(
            job_id=job.job_id,
            phase=job.phase,
            repo_key=job.repo_key,
            status=job.status.value,
            progress_percent=job.progress_percent,
            current_step=job.current_step,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error=job.error
        )
        for job in jobs
    ]
