"""
utils/file_hasher.py — File Path and Content Hashing Utilities

Short-hash helpers used for generating cache keys and unique identifiers
for parsed file output filenames.
"""

import hashlib


def hash_file_path(file_path: str) -> str:
    """
    Return a short deterministic hash of a file path.

    Used as the filename for per-file parse results so that any path
    (including those with slashes, special chars, and long components)
    maps to a safe, flat filename.

    Args:
        file_path: Relative file path within the repository.

    Returns:
        12-character hex digest string (MD5-based).

    Example::

        hash_file_path("src/models/user.py")  # → "3f2a1b8c9d4e"
    """
    return hashlib.md5(file_path.encode("utf-8")).hexdigest()[:12]


def hash_content(content: str) -> str:
    """
    Return a short deterministic hash of file content.

    Used for cache invalidation: if the content hash changes between runs,
    the file must be re-parsed regardless of the force flag.

    Args:
        content: Decoded text content of a source file.

    Returns:
        16-character hex digest string (SHA-256-based).

    Example::

        hash_content("def foo(): pass")  # → "4a7b2c8d1e3f9a0b"
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
