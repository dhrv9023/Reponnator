"""
ingestion/storage.py — Disk Persistence and Manifest Management

Saves a complete :class:`~ingestion.file_fetcher.FetchResult` to the local
filesystem in a deterministic layout and writes a structured ``manifest.json``
file summarising the entire fetch operation.

Directory layout::

    data/repos/
    └── {owner}__{repo_name}/
        ├── manifest.json          ← structured fetch summary
        ├── fetch.log              ← written by utils.logger during the run
        └── files/
            └── <original repo paths mirrored here>

When a previous fetch exists, the old folder is renamed rather than deleted
so no historical data is silently lost.
"""

import dataclasses
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import CODEAUTOPSY_VERSION, DATA_DIR
from ingestion.file_fetcher import FetchResult, FetchedFile, SkippedFile
from utils.logger import get_logger

logger = get_logger(__name__)

_MANIFEST_FILENAME = "manifest.json"
_FILES_SUBDIR      = "files"

# Maximum path component length (conservatively safe for all platforms)
_MAX_PATH_COMPONENT_LEN: int = 200


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_fetch_result(result: FetchResult, data_dir: Optional[Path] = None) -> Path:
    """
    Persist a :class:`FetchResult` to disk and write ``manifest.json``.

    Args:
        result:   Populated :class:`FetchResult` from the ingestion pipeline.
        data_dir: Override for the base data directory; defaults to ``DATA_DIR``
                  from ``config.py``.

    Returns:
        Path to the root of the saved repo folder (e.g. ``data/repos/pallets__flask/``).

    Raises:
        OSError: If a critical disk write failure occurs.
    """
    base = data_dir or DATA_DIR
    repo_folder_name = _folder_name(result.owner, result.repo_name)
    repo_folder = base / repo_folder_name

    # Rotate old folder if it exists
    _rotate_existing(repo_folder)

    # Create fresh directory structure
    files_dir = repo_folder / _FILES_SUBDIR
    files_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Created repo folder: %s", repo_folder)

    # Configure logging to also write to fetch.log inside this folder
    from utils.logger import configure_for_repo
    configure_for_repo(repo_folder)

    # Save each fetched file
    _save_code_files(result.files, files_dir)

    # Write manifest
    _write_manifest(result, repo_folder)

    return repo_folder


def load_manifest(repo_folder: Path) -> dict[str, Any]:
    """
    Load and return the ``manifest.json`` for a previously fetched repository.

    Args:
        repo_folder: Root folder of the saved repo.

    Returns:
        Parsed manifest dictionary.

    Raises:
        FileNotFoundError: If ``manifest.json`` does not exist.
        json.JSONDecodeError: If the manifest is corrupted.
    """
    manifest_path = repo_folder / _MANIFEST_FILENAME
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No manifest found at {manifest_path}. "
            "The repository may not have been fetched yet, or the fetch was incomplete."
        )
    with manifest_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def list_fetched_repos(data_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    """
    Enumerate all previously fetched repositories found in *data_dir*.

    Reads each ``manifest.json`` to surface key stats without loading file
    contents, enabling quick cache lookup before starting a new fetch.

    Args:
        data_dir: Override for base data directory; defaults to ``DATA_DIR``.

    Returns:
        List of dicts, each with ``owner``, ``repo_name``, ``full_name``,
        ``fetch_timestamp``, ``total_files_fetched``, ``primary_language``,
        and ``repo_folder`` (absolute path string).
        Directories without a valid manifest are silently skipped.
    """
    base = data_dir or DATA_DIR
    repos: list[dict[str, Any]] = []

    if not base.exists():
        return repos

    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        # Skip rotated / timestamped backup folders
        if re.search(r"__\d{4}-\d{2}-\d{2}T", entry.name):
            continue
        manifest_path = entry / _MANIFEST_FILENAME
        if not manifest_path.exists():
            continue
        try:
            with manifest_path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            repo_info = data.get("repo", {})
            stats     = data.get("ingestion_stats", {})
            lang      = data.get("language_analysis", {})
            repos.append({
                "owner":               repo_info.get("owner", ""),
                "repo_name":           repo_info.get("name", ""),
                "full_name":           repo_info.get("full_name", ""),
                "fetch_timestamp":     data.get("fetch_timestamp", ""),
                "total_files_fetched": stats.get("total_files_fetched", 0),
                "primary_language":    lang.get("primary_language", "Unknown"),
                "repo_folder":         str(entry),
                "is_complete":         _is_manifest_complete(data),
            })
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.warning("Could not read manifest in %r: %s", str(entry), exc)

    return repos


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _folder_name(owner: str, repo_name: str) -> str:
    """Return the canonical folder name for a given owner/repo pair."""
    return f"{owner}__{repo_name}"


def _rotate_existing(repo_folder: Path) -> None:
    """
    If *repo_folder* already exists, rename it with a timestamp suffix.

    This preserves historical fetch data without silent deletion.

    Args:
        repo_folder: Target folder that may already exist.
    """
    if not repo_folder.exists():
        return

    manifest_path = repo_folder / _MANIFEST_FILENAME
    timestamp_suffix = "unknown"
    if manifest_path.exists():
        try:
            with manifest_path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            ts = data.get("fetch_timestamp", "")
            # Make timestamp safe for filenames: remove colons
            timestamp_suffix = ts.replace(":", "-").replace("Z", "")
        except (json.JSONDecodeError, OSError):
            timestamp_suffix = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")

    backup_name = f"{repo_folder.name}__{timestamp_suffix}"
    backup_path = repo_folder.parent / backup_name
    logger.info(
        "Existing fetch found at %s — rotating to %s.",
        repo_folder.name,
        backup_name,
    )
    repo_folder.rename(backup_path)


def _save_code_files(files: list[FetchedFile], files_dir: Path) -> None:
    """
    Write all fetched file contents to the mirrored directory structure.

    Args:
        files:     List of :class:`FetchedFile` objects.
        files_dir: Root directory where the mirrored repo tree will be created.
    """
    saved = 0
    for fetched_file in files:
        dest_path = _safe_destination(files_dir, fetched_file.path)
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(fetched_file.content, encoding="utf-8")
            logger.debug("Saved %r → %s", fetched_file.path, dest_path.relative_to(files_dir))
            saved += 1
        except OSError as exc:
            if exc.errno == 28:  # ENOSPC — disk full
                logger.critical(
                    "DISK FULL while saving %r. Stopping file writes. "
                    "Free up disk space and re-run with --force.",
                    fetched_file.path,
                )
                raise
            logger.error("Failed to save %r: %s", fetched_file.path, exc)

    logger.info("Saved %d/%d code files to disk.", saved, len(files))


def _safe_destination(files_dir: Path, repo_path: str) -> Path:
    """
    Compute a safe filesystem destination path for a repository file.

    Handles:
    - Path components that are too long for the OS.
    - Path components with characters invalid on common filesystems.
    - Case collisions (extremely rare; detected via hash suffix).

    Args:
        files_dir: Root of the mirrored file tree.
        repo_path: Relative path as it appears in the repository.

    Returns:
        Safe absolute :class:`pathlib.Path` to write the file to.
    """
    # Sanitise each component
    parts = Path(repo_path).parts
    safe_parts: list[str] = []
    for part in parts:
        sanitised = _sanitise_path_component(part)
        safe_parts.append(sanitised)

    dest = files_dir.joinpath(*safe_parts)

    # Detect case collision: if a differently-cased path already exists
    if dest.exists():
        # Append a short hash to disambiguate
        path_hash = hashlib.md5(repo_path.encode()).hexdigest()[:6]
        name = dest.stem + f"_{path_hash}" + dest.suffix
        dest = dest.parent / name
        logger.warning(
            "Case collision detected for %r — saving as %r.", repo_path, dest.name
        )

    return dest


def _sanitise_path_component(component: str) -> str:
    """
    Ensure a single path component is safe to use as a filesystem name.

    Args:
        component: A single segment of a file path.

    Returns:
        Sanitised string safe for use as a directory or file name.
    """
    # Replace characters invalid on Windows (also covers most Unix edge cases)
    sanitised = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", component)

    # Truncate overly long names (keep a hash suffix for uniqueness)
    if len(sanitised) > _MAX_PATH_COMPONENT_LEN:
        digest = hashlib.md5(sanitised.encode()).hexdigest()[:8]
        sanitised = sanitised[:_MAX_PATH_COMPONENT_LEN - 9] + "_" + digest

    return sanitised


def _write_manifest(result: FetchResult, repo_folder: Path) -> None:
    """
    Serialise the :class:`FetchResult` into ``manifest.json``.

    Args:
        result:      Completed fetch result.
        repo_folder: Root of the saved repo directory.
    """
    manifest = _build_manifest(result)
    manifest_path = repo_folder / _MANIFEST_FILENAME
    try:
        with manifest_path.open("w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, default=_json_serialiser)
        logger.info("Manifest written: %s", manifest_path)
    except OSError as exc:
        logger.error(
            "Failed to write manifest.json (files already saved): %s", exc
        )


def _build_manifest(result: FetchResult) -> dict[str, Any]:
    """
    Convert a :class:`FetchResult` into the canonical manifest dictionary.

    Args:
        result: Completed fetch result dataclass.

    Returns:
        Plain dictionary suitable for JSON serialisation.
    """
    meta = result.repo_metadata
    return {
        "codeautopsy_version": CODEAUTOPSY_VERSION,
        "fetch_timestamp":     result.fetch_timestamp,
        "repo": {
            "owner":          result.owner,
            "name":           result.repo_name,
            "full_name":      f"{result.owner}/{result.repo_name}",
            "url":            f"https://github.com/{result.owner}/{result.repo_name}",
            "branch":         result.branch,
            "description":    meta.get("description", ""),
            "stars":          meta.get("stars", 0),
            "forks":          meta.get("forks", 0),
            "primary_language": meta.get("primary_language", "Unknown"),
            "topics":         meta.get("topics", []),
            "license":        meta.get("license"),
            "created_at":     meta.get("created_at"),
            "updated_at":     meta.get("updated_at"),
            "is_fork":        meta.get("is_fork", False),
            "is_archived":    meta.get("is_archived", False),
            "size_kb":        meta.get("size_kb", 0),
        },
        "ingestion_stats": {
            "total_files_in_repo":   result.total_files_in_repo,
            "total_files_fetched":   result.total_files_fetched,
            "total_files_skipped":   result.total_files_skipped,
            "total_bytes_fetched":   result.total_bytes_fetched,
            "fetch_duration_seconds": result.fetch_duration_seconds,
        },
        "language_analysis": result.language_analysis,
        "files": [
            {
                "path":       f.path,
                "language":   f.language,
                "size_bytes": f.size_bytes,
                "sha":        f.sha,
            }
            for f in result.files
        ],
        "skipped_files": [
            {
                "path":       s.path,
                "reason":     s.reason,
                "size_bytes": s.size_bytes,
            }
            for s in result.skipped_files
        ],
        "errors":   result.errors,
        "warnings": result.warnings,
    }


def _is_manifest_complete(data: dict[str, Any]) -> bool:
    """
    Check whether a loaded manifest indicates a complete fetch run.

    A manifest is considered incomplete if it is missing required top-level
    keys, indicating the previous run may have crashed mid-way.

    Args:
        data: Loaded manifest dictionary.

    Returns:
        ``True`` if the manifest appears complete.
    """
    required_keys = {"codeautopsy_version", "fetch_timestamp", "repo",
                     "ingestion_stats", "language_analysis", "files"}
    return required_keys.issubset(data.keys())


def _json_serialiser(obj: Any) -> Any:
    """
    Custom JSON serialiser for types not handled by the default encoder.

    Args:
        obj: Object that the default encoder cannot handle.

    Returns:
        JSON-serialisable representation.

    Raises:
        TypeError: For types we genuinely cannot serialise.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__!r} is not JSON serialisable")
