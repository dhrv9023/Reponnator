"""
ingestion/file_filter.py — File Filtering Logic

Decides which files in a GitHub repository tree should be fetched and
which should be skipped.  Filters are applied in a strict, documented order
via the master :func:`should_fetch_file` function.

Filter ordering (first failing check wins):
  1. Ignored directory in path
  2. Ignored filename glob pattern
  3. Not a supported code file extension
  4. Exceeds per-file size limit
  5. Binary content check (applied after content is fetched)
"""

import fnmatch
from pathlib import PurePosixPath
from typing import Optional

from config import (
    EXTENSION_TO_LANGUAGE,
    IGNORED_DIRECTORIES,
    IGNORED_FILE_PATTERNS,
    MAX_FILE_SIZE_BYTES,
    BINARY_DETECTION_SAMPLE_BYTES,
    BINARY_NULL_BYTE_THRESHOLD,
    BINARY_NONPRINTABLE_THRESHOLD,
)
from utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Individual filter predicates
# ---------------------------------------------------------------------------

def is_ignored_directory(path: str) -> bool:
    """
    Return True if any component of *path* is in ``IGNORED_DIRECTORIES``.

    The check is case-insensitive to handle mixed-case directory names.

    Args:
        path: Posix-style relative path within the repository (e.g. ``src/utils/helper.py``).

    Returns:
        ``True`` when the path should be skipped; ``False`` to keep it.

    Example:
        >>> is_ignored_directory("src/node_modules/lodash/index.js")
        True
        >>> is_ignored_directory("src/models/user.py")
        False
    """
    parts = PurePosixPath(path).parts
    for part in parts[:-1]:  # Exclude the filename itself; only check directory components
        if part.lower() in {d.lower() for d in IGNORED_DIRECTORIES}:
            logger.debug("Path %r contains ignored directory %r — skipping.", path, part)
            return True
    return False


def is_ignored_pattern(filename: str) -> bool:
    """
    Return True if *filename* matches any glob pattern in ``IGNORED_FILE_PATTERNS``.

    Uses :func:`fnmatch.fnmatch` for standard glob matching.

    Args:
        filename: Bare filename (without directory components).

    Returns:
        ``True`` when the file should be skipped.

    Example:
        >>> is_ignored_pattern("app.min.js")
        True
        >>> is_ignored_pattern("app.js")
        False
    """
    lower_name = filename.lower()
    for pattern in IGNORED_FILE_PATTERNS:
        if fnmatch.fnmatch(lower_name, pattern.lower()):
            logger.debug("Filename %r matches ignored pattern %r — skipping.", filename, pattern)
            return True
    return False


def is_supported_code_file(path: str) -> bool:
    """
    Return True if the file extension appears in ``SUPPORTED_EXTENSIONS``.

    The comparison is case-insensitive (.PY and .py both match).

    Args:
        path: Posix-style relative file path within the repository.

    Returns:
        ``True`` when the extension maps to a known programming language.
    """
    suffix = PurePosixPath(path).suffix.lower()
    if not suffix:
        return False
    return suffix in EXTENSION_TO_LANGUAGE


def is_within_size_limit(size_bytes: int) -> bool:
    """
    Return True if *size_bytes* is within the per-file size limit.

    Args:
        size_bytes: File size reported by the GitHub API tree response.

    Returns:
        ``True`` when the file is small enough to fetch.
    """
    return size_bytes <= MAX_FILE_SIZE_BYTES


def is_likely_binary(content: str) -> bool:
    """
    Heuristically determine whether *content* is binary data.

    Samples up to ``BINARY_DETECTION_SAMPLE_BYTES`` characters from the
    beginning of the content and checks two indicators:
    - Presence of null bytes (strong binary indicator).
    - Ratio of non-printable characters above threshold.

    Args:
        content: Decoded text string returned by the GitHub API.

    Returns:
        ``True`` when the content appears to be binary.
    """
    if not content:
        return False

    sample = content[:BINARY_DETECTION_SAMPLE_BYTES]
    total = len(sample)
    if total == 0:
        return False

    null_count = sample.count("\x00")
    if null_count / total > BINARY_NULL_BYTE_THRESHOLD:
        return True

    non_printable = sum(
        1 for ch in sample
        if not ch.isprintable() and ch not in ("\n", "\r", "\t")
    )
    return non_printable / total > BINARY_NONPRINTABLE_THRESHOLD


# ---------------------------------------------------------------------------
# Master filter
# ---------------------------------------------------------------------------

def should_fetch_file(path: str, size_bytes: int) -> tuple[bool, str]:
    """
    Decide whether a file should be fetched, applying all filters in order.

    This is the primary entry point for the file-filtering system.
    It combines all individual predicates into a single, ordered check.

    Args:
        path:       Posix-style relative path within the repository.
        size_bytes: File size in bytes as reported by the GitHub API tree.

    Returns:
        A tuple ``(should_fetch: bool, reason: str)``.
        When *should_fetch* is ``False``, *reason* explains exactly why.
        When *should_fetch* is ``True``, *reason* is ``"ok"``.

    Example:
        >>> should_fetch_file("src/node_modules/pkg/index.js", 1024)
        (False, "ignored directory: node_modules")
        >>> should_fetch_file("src/app.min.js", 512)
        (False, "ignored pattern: *.min.js")
        >>> should_fetch_file("README.md", 2048)
        (False, "unsupported extension: .md")
        >>> should_fetch_file("src/models/user.py", 3000)
        (True, "ok")
    """
    filename = PurePosixPath(path).name

    # 1. Ignored directory
    if is_ignored_directory(path):
        parts = PurePosixPath(path).parts
        bad_dirs = [
            p for p in parts[:-1]
            if p.lower() in {d.lower() for d in IGNORED_DIRECTORIES}
        ]
        reason = f"ignored directory: {bad_dirs[0]}" if bad_dirs else "ignored directory"
        logger.debug("SKIP %r — %s", path, reason)
        return False, reason

    # 2. Ignored filename pattern
    for pattern in IGNORED_FILE_PATTERNS:
        if fnmatch.fnmatch(filename.lower(), pattern.lower()):
            reason = f"ignored pattern: {pattern}"
            logger.debug("SKIP %r — %s", path, reason)
            return False, reason

    # 3. Unsupported extension
    if not is_supported_code_file(path):
        suffix = PurePosixPath(path).suffix or "(no extension)"
        reason = f"unsupported extension: {suffix}"
        logger.debug("SKIP %r — %s", path, reason)
        return False, reason

    # 4. Size limit (pre-fetch, based on tree metadata)
    if not is_within_size_limit(size_bytes):
        reason = (
            f"file too large: {size_bytes:,} bytes "
            f"(limit: {MAX_FILE_SIZE_BYTES:,} bytes)"
        )
        logger.debug("SKIP %r — %s", path, reason)
        return False, reason

    return True, "ok"


# ---------------------------------------------------------------------------
# Language lookup
# ---------------------------------------------------------------------------

def get_file_language(path: str) -> Optional[str]:
    """
    Return the programming language name for a given file path.

    Uses the ``EXTENSION_TO_LANGUAGE`` reverse-lookup table populated in
    ``config.py`` from ``SUPPORTED_EXTENSIONS``.

    Args:
        path: Posix-style relative file path within the repository.

    Returns:
        Language name string (e.g. ``"Python"``), or ``None`` if the
        extension is not recognised.

    Example:
        >>> get_file_language("src/app.py")
        'Python'
        >>> get_file_language("package.json")
        None
    """
    suffix = PurePosixPath(path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix)
