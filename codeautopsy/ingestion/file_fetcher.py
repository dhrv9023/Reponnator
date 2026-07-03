"""
ingestion/file_fetcher.py — Core Ingestion Orchestrator

Ties together all ingestion sub-modules to execute the full fetch pipeline
for a single GitHub repository.  Returns a structured :class:`FetchResult`
that is then persisted to disk by ``ingestion.storage``.

The public API surface is intentionally minimal:
    result = fetch_repository(client, owner, repo_name, branch)
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from github.Repository import Repository

from config import MAX_REPO_FILES, MAX_TOTAL_SIZE_BYTES
from ingestion.file_filter import get_file_language, is_likely_binary, should_fetch_file
from ingestion.github_client import (
    GitHubClient,
    GitHubClientError,
    RepoNotFoundError,
    RepoPrivateError,
)
from ingestion.language_detector import detect_languages
from utils.logger import get_logger

logger = get_logger(__name__)

_PROGRESS_INTERVAL: int = 50  # log progress every N files


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FetchedFile:
    """Represents a successfully fetched and decoded code file."""

    path: str
    """Relative path within the repository (e.g. ``src/models/user.py``)."""

    language: str
    """Detected programming language (e.g. ``"Python"``))."""

    content: str
    """Full decoded text content of the file."""

    size_bytes: int
    """Original file size in bytes (from GitHub tree metadata)."""

    sha: str
    """GitHub's SHA-1 hash for this file version."""


@dataclass
class SkippedFile:
    """Represents a file that was present in the tree but not fetched."""

    path: str
    """Relative path within the repository."""

    reason: str
    """Human-readable explanation of why the file was skipped."""

    size_bytes: int
    """File size in bytes as reported by the tree (0 for directories)."""


@dataclass
class FetchResult:
    """Complete result of a repository ingestion run."""

    owner: str
    repo_name: str
    branch: str
    repo_metadata: dict[str, Any]
    files: list[FetchedFile]
    skipped_files: list[SkippedFile]
    language_analysis: dict[str, Any]
    total_files_in_repo: int
    total_files_fetched: int
    total_files_skipped: int
    total_bytes_fetched: int
    fetch_duration_seconds: float
    fetch_timestamp: str               # ISO 8601
    errors: list[str]                  # non-fatal errors encountered
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_repository(
    github_client: GitHubClient,
    owner: str,
    repo_name: str,
    branch: Optional[str] = None,
) -> FetchResult:
    """
    Execute the complete ingestion pipeline for a single GitHub repository.

    Pipeline steps:
        1. Validate repo existence and accessibility.
        2. Fetch rich repository metadata.
        3. Retrieve the recursive file tree.
        4. Apply :func:`~ingestion.file_filter.should_fetch_file` to every entry.
        5. Fetch content for each passing file, with binary detection.
        6. Respect ``MAX_TOTAL_SIZE_BYTES`` — stop early if exceeded.
        7. Detect language composition of fetched files.
        8. Return a fully populated :class:`FetchResult`.

    Args:
        github_client: An initialised :class:`~ingestion.github_client.GitHubClient`.
        owner:         Repository owner (user or organisation).
        repo_name:     Repository name.
        branch:        Branch to fetch; ``None`` uses the default branch.

    Returns:
        A :class:`FetchResult` dataclass.

    Raises:
        RepoNotFoundError: If the repository does not exist on GitHub.
        RepoPrivateError:  If the repository is private and inaccessible.
        GitHubClientError: For unrecoverable API errors.
    """
    start_time = time.monotonic()
    fetch_timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    errors: list[str] = []
    warnings: list[str] = []

    full_name = f"{owner}/{repo_name}"
    logger.info("═" * 60)
    logger.info("Starting ingestion of github.com/%s", full_name)
    logger.info("═" * 60)

    # -----------------------------------------------------------------------
    # Step 1: Fetch repo object and metadata
    # -----------------------------------------------------------------------
    repo = _get_validated_repo(github_client, owner, repo_name, warnings)
    metadata = github_client.get_repo_metadata(repo)

    if metadata.get("is_archived"):
        msg = f"Repository {full_name!r} is archived. Fetching anyway."
        logger.warning(msg)
        warnings.append(msg)

    if metadata.get("is_fork"):
        logger.info("Note: %r is a fork.", full_name)

    effective_branch = branch or metadata["default_branch"]
    logger.info("Target branch: %r", effective_branch)

    # -----------------------------------------------------------------------
    # Step 2: Fetch file tree
    # -----------------------------------------------------------------------
    tree_entries = github_client.get_file_tree(repo, branch=effective_branch)
    blob_entries = [e for e in tree_entries if e["type"] == "blob"]
    submodule_entries = [e for e in tree_entries if e["type"] == "commit"]
    total_tree_blobs = len(blob_entries)

    if submodule_entries:
        msg = (
            f"Repository contains {len(submodule_entries)} git submodule(s). "
            "Submodules are not fetched."
        )
        logger.warning(msg)
        warnings.append(msg)

    logger.info("File tree fetched: %d total blobs in repo.", total_tree_blobs)

    if total_tree_blobs > MAX_REPO_FILES:
        msg = (
            f"Repository has {total_tree_blobs:,} files, which exceeds the "
            f"soft warning threshold of {MAX_REPO_FILES:,}. Continuing but "
            "this may take a while."
        )
        logger.warning(msg)
        warnings.append(msg)

    # -----------------------------------------------------------------------
    # Step 3: Pre-filter — decide which files to attempt fetching
    # -----------------------------------------------------------------------
    to_fetch: list[dict[str, Any]] = []
    skipped_files: list[SkippedFile] = []

    for entry in blob_entries:
        path       = entry["path"]
        size_bytes = entry["size"]

        ok, reason = should_fetch_file(path, size_bytes)
        if ok:
            to_fetch.append(entry)
        else:
            skipped_files.append(SkippedFile(path=path, reason=reason, size_bytes=size_bytes))

    logger.info(
        "Found %d total blobs, %d code files after filtering (%d skipped by filter).",
        total_tree_blobs,
        len(to_fetch),
        len(skipped_files),
    )

    # -----------------------------------------------------------------------
    # Step 4: Fetch file contents  — parallelised with ThreadPoolExecutor
    # Fix: previously each file was downloaded sequentially; on a 250-file
    # repo that meant 250 sequential API round-trips.  We now fetch in
    # parallel batches of up to _FETCH_WORKERS threads, reducing wall-clock
    # time by ~6–8x while staying within GitHub's per-IP connection limits.
    # -----------------------------------------------------------------------
    _FETCH_WORKERS = 8

    fetched_files: list[FetchedFile] = []
    total_bytes_fetched: int = 0
    total_limit_reached: bool = False
    _lock = threading.Lock()

    def _fetch_one(entry: dict) -> Optional[FetchedFile | SkippedFile]:
        """Fetch a single file; returns FetchedFile, SkippedFile, or None on skip."""
        path       = entry["path"]
        size_bytes = entry["size"]
        sha        = entry["sha"]

        content = _fetch_file_safe(
            github_client, repo, path, effective_branch, sha, errors
        )

        if content is None:
            return SkippedFile(
                path=path,
                reason="content fetch returned None (binary, empty, or API error)",
                size_bytes=size_bytes,
            )

        if is_likely_binary(content):
            logger.warning("Skipping %r — detected as binary content after fetch.", path)
            return SkippedFile(
                path=path,
                reason="binary content detected after fetch",
                size_bytes=size_bytes,
            )

        language   = get_file_language(path) or "Unknown"
        actual_size = len(content.encode("utf-8"))
        return FetchedFile(
            path=path,
            language=language,
            content=content,
            size_bytes=actual_size,
            sha=sha,
        )

    logger.info(
        "Fetching %d files in parallel (max %d workers)…",
        len(to_fetch), _FETCH_WORKERS,
    )

    with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
        future_map = {pool.submit(_fetch_one, entry): entry for entry in to_fetch}

        done_count = 0
        for future in as_completed(future_map):
            done_count += 1
            if done_count % _PROGRESS_INTERVAL == 0 or done_count == len(to_fetch):
                logger.info(
                    "Progress: %d/%d files processed (%.1f KB so far).",
                    done_count, len(to_fetch), total_bytes_fetched / 1024,
                )

            try:
                result = future.result()
            except Exception as exc:
                entry = future_map[future]
                logger.error("Worker exception for %r: %s", entry["path"], exc)
                with _lock:
                    skipped_files.append(SkippedFile(
                        path=entry["path"],
                        reason=f"worker exception: {exc}",
                        size_bytes=entry["size"],
                    ))
                continue

            if result is None:
                continue

            with _lock:
                if isinstance(result, SkippedFile):
                    skipped_files.append(result)
                elif isinstance(result, FetchedFile):
                    # Total size guard (thread-safe check)
                    if total_bytes_fetched + result.size_bytes > MAX_TOTAL_SIZE_BYTES:
                        if not total_limit_reached:
                            msg = (
                                f"Total size limit ({MAX_TOTAL_SIZE_BYTES / 1_000_000:.0f} MB) "
                                f"reached after {len(fetched_files)} files. "
                                "Remaining files will be skipped."
                            )
                            logger.warning(msg)
                            warnings.append(msg)
                            total_limit_reached = True
                        skipped_files.append(SkippedFile(
                            path=result.path,
                            reason="total size limit reached",
                            size_bytes=result.size_bytes,
                        ))
                    else:
                        fetched_files.append(result)
                        total_bytes_fetched += result.size_bytes

    # -----------------------------------------------------------------------
    # Step 5: Language detection
    # -----------------------------------------------------------------------
    file_descriptors = [
        {"path": f.path, "size": f.size_bytes} for f in fetched_files
    ]
    language_analysis = detect_languages(file_descriptors)

    if not fetched_files:
        msg = (
            f"No code files were successfully fetched from {full_name!r}. "
            "The repository may contain only non-code assets."
        )
        logger.warning(msg)
        warnings.append(msg)

    # -----------------------------------------------------------------------
    # Finalise
    # -----------------------------------------------------------------------
    duration = time.monotonic() - start_time

    logger.info("═" * 60)
    logger.info(
        "Ingestion complete: %d files fetched, %.1f KB, %.1f seconds.",
        len(fetched_files),
        total_bytes_fetched / 1024,
        duration,
    )
    logger.info("═" * 60)

    return FetchResult(
        owner=owner,
        repo_name=repo_name,
        branch=effective_branch,
        repo_metadata=metadata,
        files=fetched_files,
        skipped_files=skipped_files,
        language_analysis=language_analysis,
        total_files_in_repo=total_tree_blobs,
        total_files_fetched=len(fetched_files),
        total_files_skipped=len(skipped_files),
        total_bytes_fetched=total_bytes_fetched,
        fetch_duration_seconds=round(duration, 2),
        fetch_timestamp=fetch_timestamp,
        errors=errors,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_validated_repo(
    client: GitHubClient,
    owner: str,
    repo_name: str,
    warnings: list[str],
) -> Repository:
    """
    Fetch and validate the repository object, raising clear errors on failure.

    Args:
        client:    Authenticated GitHub client.
        owner:     Repository owner.
        repo_name: Repository name.
        warnings:  Mutable list to append non-fatal warnings to.

    Returns:
        PyGithub :class:`~github.Repository.Repository` object.

    Raises:
        RepoNotFoundError: Repository does not exist.
        RepoPrivateError:  Repository is private and inaccessible.
        GitHubClientError: Other API failures.
    """
    try:
        repo = client.get_repo(owner, repo_name)
    except RepoNotFoundError:
        raise RepoNotFoundError(
            f"Repository {owner!r}/{repo_name!r} was not found on GitHub.\n"
            "Verify the owner and repository name are correct, and that the "
            "repository has not been deleted or renamed."
        )
    except RepoPrivateError:
        raise RepoPrivateError(
            f"Repository {owner!r}/{repo_name!r} is private.\n"
            "Add a GitHub personal access token with 'repo' scope to your .env "
            "file as GITHUB_TOKEN to access private repositories."
        )
    return repo


def _fetch_file_safe(
    client: GitHubClient,
    repo: Repository,
    path: str,
    branch: str,
    sha: str,
    errors: list[str],
) -> Optional[str]:
    """
    Fetch a single file's content, catching and logging all errors.

    Args:
        client:  GitHub client.
        repo:    Repository object.
        path:    File path within the repo.
        branch:  Branch to read from.
        sha:     Expected SHA (logged for audit trail).
        errors:  Mutable error list to append non-fatal error messages to.

    Returns:
        Decoded text content, or ``None`` on any failure.
    """
    logger.debug("Fetching %r (sha=%s).", path, sha[:8])
    try:
        return client.get_file_content(repo, path, branch)
    except GitHubClientError as exc:
        msg = f"Failed to fetch {path!r}: {exc}"
        logger.error(msg)
        errors.append(msg)
        return None
    except Exception as exc:  # noqa: BLE001 — unexpected errors must not abort the run
        msg = f"Unexpected error fetching {path!r}: {type(exc).__name__}: {exc}"
        logger.error(msg)
        errors.append(msg)
        return None
