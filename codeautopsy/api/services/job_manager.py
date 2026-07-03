"""
api/services/job_manager.py — Async job queue and status tracker

Lightweight in-memory job tracker with optional SQLite persistence.
"""

import uuid
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enum."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class Job:
    """Job data structure."""
    job_id: str
    phase: str
    repo_key: str
    status: JobStatus
    progress_percent: int = 0
    current_step: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert enums and datetimes to strings
        data['status'] = self.status.value
        for key in ['started_at', 'completed_at', 'created_at']:
            if data[key]:
                data[key] = data[key].isoformat()
        return data


class JobManager:
    """
    Async job manager for tracking background pipeline tasks.
    
    Features:
    - In-memory job storage
    - Progress tracking
    - Status updates
    - Job cleanup
    """
    
    def __init__(self):
        """Initialize job manager."""
        self.jobs: Dict[str, Job] = {}
        self._lock = asyncio.Lock()
    
    async def create_job(self, phase: str, repo_key: str) -> str:
        """
        Create a new job.
        
        Args:
            phase: Phase name (ingest, parse, chunk, qa, diagram, story)
            repo_key: Repository key (owner__repo)
        
        Returns:
            job_id: Unique job identifier
        """
        job_id = str(uuid.uuid4())
        
        async with self._lock:
            job = Job(
                job_id=job_id,
                phase=phase,
                repo_key=repo_key,
                status=JobStatus.QUEUED
            )
            self.jobs[job_id] = job
        
        logger.info(f"Created job {job_id} for {phase} on {repo_key}")
        return job_id
    
    async def start_job(self, job_id: str):
        """Mark job as running."""
        async with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].status = JobStatus.RUNNING
                self.jobs[job_id].started_at = datetime.now()
                logger.info(f"Started job {job_id}")
    
    async def update_progress(self, job_id: str, percent: int, step: str | None = None):
        """
        Update job progress.
        
        Args:
            job_id: Job identifier
            percent: Progress percentage (0-100)
            step: Current step description
        """
        async with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].progress_percent = max(0, min(100, percent))
                if step:
                    self.jobs[job_id].current_step = step
                logger.debug(f"Job {job_id} progress: {percent}% - {step}")
    
    async def mark_complete(self, job_id: str):
        """Mark job as complete."""
        async with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].status = JobStatus.COMPLETE
                self.jobs[job_id].progress_percent = 100
                self.jobs[job_id].completed_at = datetime.now()
                logger.info(f"Completed job {job_id}")
    
    async def mark_failed(self, job_id: str, error_message: str):
        """
        Mark job as failed.
        
        Args:
            job_id: Job identifier
            error_message: Error description
        """
        async with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].status = JobStatus.FAILED
                self.jobs[job_id].error = error_message
                self.jobs[job_id].completed_at = datetime.now()
                logger.error(f"Failed job {job_id}: {error_message}")
    
    async def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get job by ID.
        
        Args:
            job_id: Job identifier
        
        Returns:
            Job object or None if not found
        """
        async with self._lock:
            return self.jobs.get(job_id)
    
    async def list_jobs(
        self, 
        repo_key: Optional[str] = None, 
        status: Optional[JobStatus] = None
    ) -> List[Job]:
        """
        List jobs with optional filters.
        
        Args:
            repo_key: Filter by repository key
            status: Filter by status
        
        Returns:
            List of jobs matching filters
        """
        async with self._lock:
            jobs = list(self.jobs.values())
        
        # Apply filters
        if repo_key:
            jobs = [j for j in jobs if j.repo_key == repo_key]
        if status:
            jobs = [j for j in jobs if j.status == status]
        
        # Sort by created_at descending (newest first)
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        
        return jobs
    
    async def cleanup_old_jobs(self, max_age_hours: int = 24):
        """
        Remove jobs older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age in hours
        """
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        
        async with self._lock:
            old_job_ids = [
                job_id for job_id, job in self.jobs.items()
                if job.created_at < cutoff and job.status in [JobStatus.COMPLETE, JobStatus.FAILED]
            ]
            
            for job_id in old_job_ids:
                del self.jobs[job_id]
            
            if old_job_ids:
                logger.info(f"Cleaned up {len(old_job_ids)} old jobs")
    
    async def check_running_job(self, phase: str, repo_key: str) -> Optional[str]:
        """
        Check if there's already a running job for this phase and repo.
        
        Args:
            phase: Phase name
            repo_key: Repository key
        
        Returns:
            job_id if found, None otherwise
        """
        async with self._lock:
            for job in self.jobs.values():
                if (job.phase == phase and 
                    job.repo_key == repo_key and 
                    job.status in [JobStatus.QUEUED, JobStatus.RUNNING]):
                    return job.job_id
        return None


# Global singleton instance
job_manager = JobManager()
