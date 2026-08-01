"""
api/services/job_manager.py — Async job queue and status tracker

Persistent SQLite-backed job store. Jobs survive server restarts and
uvicorn --reload cycles. The database is auto-created at data/jobs.db
on first use; no migration step is needed.

Design decisions
----------------
* aiosqlite is used so every method stays ``async`` and never blocks
  the FastAPI event loop with a synchronous DB call.
* The public API (create_job, start_job, update_progress, mark_complete,
  mark_failed, get_job, list_jobs, check_running_job, cleanup_old_jobs)
  is identical to the previous in-memory implementation — no callers need
  to change.
* The Job dataclass and JobStatus enum are preserved as the application-
  layer data model; they are serialised to/from SQLite rows internally.
* WAL journal mode is enabled for better concurrent read performance
  (multiple readers, one writer) — important when the FastAPI app polls
  job status while a background pipeline task writes updates.

Industry context
----------------
This pattern (async SQLite via aiosqlite for lightweight persistence in
FastAPI services) is documented in the FastAPI official tutorials and
is production-appropriate for single-node deployments. For multi-node
or high-throughput scenarios, swap for PostgreSQL with asyncpg — the
interface is identical.
"""

from __future__ import annotations

import json
import uuid
import logging
import aiosqlite
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database path — inside the existing data/ directory (already gitignored).
# Resolved relative to this file: codeautopsy/api/services/ → codeautopsy/data/
# ---------------------------------------------------------------------------
_DB_PATH: Path = Path(__file__).parent.parent.parent / "data" / "jobs.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id           TEXT PRIMARY KEY,
    phase            TEXT NOT NULL,
    repo_key         TEXT NOT NULL,
    status           TEXT NOT NULL,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    current_step     TEXT,
    started_at       TEXT,
    completed_at     TEXT,
    error            TEXT,
    created_at       TEXT NOT NULL
)
"""

# Column order must match INSERT and SELECT * below.
_COLUMNS = (
    "job_id", "phase", "repo_key", "status",
    "progress_percent", "current_step",
    "started_at", "completed_at", "error", "created_at",
)


# ---------------------------------------------------------------------------
# Domain types (unchanged from previous implementation)
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    """Job status enum."""
    QUEUED   = "queued"
    RUNNING  = "running"
    COMPLETE = "complete"
    FAILED   = "failed"


@dataclass
class Job:
    """Job data structure."""
    job_id:           str
    phase:            str
    repo_key:         str
    status:           JobStatus
    progress_percent: int            = 0
    current_step:     str | None     = None
    started_at:       datetime | None = None
    completed_at:     datetime | None = None
    error:            str | None     = None
    created_at:       datetime       = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to JSON-serialisable dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        for key in ("started_at", "completed_at", "created_at"):
            if data[key]:
                data[key] = data[key].isoformat()
        return data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_to_job(row: tuple) -> Job:
    """Reconstruct a Job from a SQLite row (column order = _COLUMNS)."""
    d = dict(zip(_COLUMNS, row))

    def _parse_dt(val: str | None) -> datetime | None:
        if not val:
            return None
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None

    return Job(
        job_id=d["job_id"],
        phase=d["phase"],
        repo_key=d["repo_key"],
        status=JobStatus(d["status"]),
        progress_percent=d["progress_percent"] or 0,
        current_step=d["current_step"],
        started_at=_parse_dt(d["started_at"]),
        completed_at=_parse_dt(d["completed_at"]),
        error=d["error"],
        created_at=_parse_dt(d["created_at"]) or datetime.now(),
    )


async def _get_conn() -> aiosqlite.Connection:
    """
    Open (or create) the SQLite database and ensure the jobs table exists.

    Returns an aiosqlite Connection to be used as an async context manager:
        async with aiosqlite.connect(_DB_PATH) as conn: ...

    WAL mode is enabled for better concurrent read performance:
    multiple coroutines can read simultaneously while one writes.

    Note: In aiosqlite >= 0.19, aiosqlite.connect() returns an object that is
    BOTH awaitable and an async context manager. Always use it as:
        async with aiosqlite.connect(path) as conn: ...
    NOT as:
        async with await aiosqlite.connect(path) as conn: ...  # old 0.17 API
    """
    # This function is kept as a setup helper to ensure the table exists.
    # The actual connection must be opened inline in each method.
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(_CREATE_TABLE_SQL)
        await conn.commit()


async def _ensure_table() -> None:
    """Ensure the jobs table exists. Called before each DB operation."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(_CREATE_TABLE_SQL)
        await conn.commit()



# ---------------------------------------------------------------------------
# JobManager — public API unchanged from the in-memory implementation
# ---------------------------------------------------------------------------

class JobManager:
    """
    Async job manager for tracking background pipeline tasks.

    Backed by an SQLite database at ``data/jobs.db``. Jobs persist across
    server restarts. The public API is identical to the previous in-memory
    implementation — no callers need to change.

    Features
    --------
    - Persistent storage (survives uvicorn --reload and crashes)
    - Progress tracking with step descriptions
    - Status transitions (QUEUED → RUNNING → COMPLETE | FAILED)
    - Duplicate-job detection (check_running_job)
    - Automatic cleanup of old completed/failed jobs
    """

    async def create_job(self, phase: str, repo_key: str) -> str:
        """
        Create a new job and persist it to SQLite.

        Args:
            phase:    Phase name (ingest, parse, chunk, qa, diagram, story).
            repo_key: Repository key (owner__repo).

        Returns:
            job_id: Unique job identifier (UUID4 string).
        """
        job_id = str(uuid.uuid4())
        now    = datetime.now().isoformat()

        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(_DB_PATH) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(_CREATE_TABLE_SQL)
            await conn.execute(
                """INSERT INTO jobs
                   (job_id, phase, repo_key, status, progress_percent,
                    current_step, started_at, completed_at, error, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, phase, repo_key, JobStatus.QUEUED.value,
                 0, None, None, None, None, now),
            )
            await conn.commit()

        logger.info("Created job %s for %s on %s", job_id, phase, repo_key)
        return job_id

    async def start_job(self, job_id: str) -> None:
        """Mark a job as RUNNING and record its start time."""
        now = datetime.now().isoformat()
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(_DB_PATH) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(_CREATE_TABLE_SQL)
            await conn.execute(
                "UPDATE jobs SET status=?, started_at=? WHERE job_id=?",
                (JobStatus.RUNNING.value, now, job_id),
            )
            await conn.commit()
        logger.info("Started job %s", job_id)

    async def update_progress(
        self, job_id: str, percent: int, step: str | None = None
    ) -> None:
        """
        Update job progress percentage and optional step description.

        Args:
            job_id:  Job identifier.
            percent: Progress percentage (clamped to 0–100).
            step:    Human-readable description of the current step.
        """
        percent = max(0, min(100, percent))
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(_DB_PATH) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(_CREATE_TABLE_SQL)
            if step is not None:
                await conn.execute(
                    "UPDATE jobs SET progress_percent=?, current_step=? WHERE job_id=?",
                    (percent, step, job_id),
                )
            else:
                await conn.execute(
                    "UPDATE jobs SET progress_percent=? WHERE job_id=?",
                    (percent, job_id),
                )
            await conn.commit()
        logger.debug("Job %s progress: %d%% - %s", job_id, percent, step)

    async def mark_complete(self, job_id: str) -> None:
        """Mark a job as COMPLETE (progress set to 100)."""
        now = datetime.now().isoformat()
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(_DB_PATH) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(_CREATE_TABLE_SQL)
            await conn.execute(
                """UPDATE jobs
                   SET status=?, progress_percent=100, completed_at=?
                   WHERE job_id=?""",
                (JobStatus.COMPLETE.value, now, job_id),
            )
            await conn.commit()
        logger.info("Completed job %s", job_id)

    async def mark_failed(self, job_id: str, error_message: str) -> None:
        """
        Mark a job as FAILED and record the error message.

        Args:
            job_id:        Job identifier.
            error_message: Human-readable error description (stored verbatim).
        """
        now = datetime.now().isoformat()
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(_DB_PATH) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(_CREATE_TABLE_SQL)
            await conn.execute(
                """UPDATE jobs
                   SET status=?, completed_at=?, error=?
                   WHERE job_id=?""",
                (JobStatus.FAILED.value, now, error_message, job_id),
            )
            await conn.commit()
        logger.error("Failed job %s: %s", job_id, error_message)

    async def get_job(self, job_id: str) -> Optional[Job]:
        """
        Fetch a job by ID.

        Args:
            job_id: Job identifier.

        Returns:
            Job object, or None if not found.
        """
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(_DB_PATH) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(_CREATE_TABLE_SQL)
            async with conn.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ) as cursor:
                row = await cursor.fetchone()

        if row is None:
            return None
        return _row_to_job(row)

    async def list_jobs(
        self,
        repo_key: Optional[str] = None,
        status: Optional[JobStatus] = None,
    ) -> List[Job]:
        """
        List jobs with optional filters, ordered newest-first.

        Args:
            repo_key: Filter by repository key (exact match).
            status:   Filter by JobStatus.

        Returns:
            List of Job objects matching the filters.
        """
        conditions: list[str] = []
        params:     list[str] = []

        if repo_key:
            conditions.append("repo_key = ?")
            params.append(repo_key)
        if status:
            conditions.append("status = ?")
            params.append(status.value)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql   = f"SELECT * FROM jobs {where} ORDER BY created_at DESC"

        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(_DB_PATH) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(_CREATE_TABLE_SQL)
            async with conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()

        return [_row_to_job(row) for row in rows]

    async def cleanup_old_jobs(self, max_age_hours: int = 24) -> None:
        """
        Delete completed/failed jobs older than ``max_age_hours``.

        Only terminal-state jobs (COMPLETE, FAILED) are eligible for
        cleanup — active and queued jobs are never removed.

        Args:
            max_age_hours: Maximum age in hours before a terminal job is deleted.
        """
        cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        terminal_statuses = (JobStatus.COMPLETE.value, JobStatus.FAILED.value)

        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(_DB_PATH) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(_CREATE_TABLE_SQL)
            cursor = await conn.execute(
                f"""DELETE FROM jobs
                    WHERE status IN ({','.join('?' * len(terminal_statuses))})
                    AND created_at < ?""",
                (*terminal_statuses, cutoff),
            )
            await conn.commit()
            deleted = cursor.rowcount

        if deleted:
            logger.info("Cleaned up %d old jobs (older than %dh)", deleted, max_age_hours)

    async def check_running_job(
        self, phase: str, repo_key: str
    ) -> Optional[str]:
        """
        Check whether a QUEUED or RUNNING job already exists for this
        phase + repo combination. Used to prevent duplicate pipeline runs.

        Args:
            phase:    Phase name.
            repo_key: Repository key.

        Returns:
            job_id of the active job, or None if no active job exists.
        """
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(_DB_PATH) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(_CREATE_TABLE_SQL)
            async with conn.execute(
                """SELECT job_id FROM jobs
                   WHERE phase=? AND repo_key=?
                   AND status IN (?, ?)
                   LIMIT 1""",
                (phase, repo_key,
                 JobStatus.QUEUED.value, JobStatus.RUNNING.value),
            ) as cursor:
                row = await cursor.fetchone()

        return row[0] if row else None


# ---------------------------------------------------------------------------
# Global singleton — identical interface to the old in-memory singleton.
# Each method opens and closes its own aiosqlite connection, so there is
# no shared connection state to manage at module level.
# ---------------------------------------------------------------------------
job_manager = JobManager()
