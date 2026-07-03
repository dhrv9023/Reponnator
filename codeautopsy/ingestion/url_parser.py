"""
ingestion/url_parser.py — GitHub URL Validation and Normalization

Single responsibility: accept any raw user-supplied string that might
represent a GitHub repository and return a clean, structured ParsedURL
object with owner, repo name, optional branch, and canonical URL.

Handles every realistic input format:
- https://github.com/owner/repo
- https://github.com/owner/repo/
- https://github.com/owner/repo.git
- https://github.com/owner/repo/tree/main
- https://github.com/owner/repo/tree/main/subfolder
- https://github.com/owner/repo/blob/main/file.py
- http://github.com/owner/repo
- github.com/owner/repo  (no protocol)
- git@github.com:owner/repo.git  (SSH)
- owner/repo  (shorthand)
"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse

from utils.logger import get_logger

logger = get_logger(__name__)

# Maximum lengths defined by GitHub
_MAX_OWNER_LEN: int = 39
_MAX_REPO_LEN: int = 100

# Valid GitHub name pattern: alphanumeric and hyphens (owner), plus dots/underscores (repo)
_OWNER_RE: re.Pattern = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,37}[a-zA-Z0-9])?$|^[a-zA-Z0-9]$")
_REPO_RE: re.Pattern  = re.compile(r"^[a-zA-Z0-9_.\-]+$")

# SSH URL format: git@github.com:owner/repo.git
_SSH_RE: re.Pattern  = re.compile(
    r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    re.IGNORECASE,
)

# Shorthand owner/repo (no slashes other than the single separator)
_SHORTHAND_RE: re.Pattern = re.compile(
    r"^(?P<owner>[a-zA-Z0-9][a-zA-Z0-9\-]{0,38})/(?P<repo>[a-zA-Z0-9_.\-]+)$"
)


@dataclass(frozen=True)
class ParsedURL:
    """Structured result from :func:`parse_github_url`."""

    owner: str
    """Repository owner (user or org), lower-cased."""

    repo_name: str
    """Repository name (without .git suffix), lower-cased."""

    branch: Optional[str]
    """Branch extracted from the URL path (e.g. ``/tree/develop``), or ``None``."""

    original_url: str
    """The raw string that was supplied by the caller."""

    normalized_url: str
    """Canonical ``https://github.com/owner/repo`` form."""


def parse_github_url(raw_input: str) -> ParsedURL:
    """
    Parse and validate a GitHub repository URL in any supported format.

    Args:
        raw_input: Any string the user might type as a GitHub repo reference.

    Returns:
        A :class:`ParsedURL` dataclass with clean, validated fields.

    Raises:
        ValueError: With a descriptive message when the input cannot be
                    resolved to a valid GitHub repository URL.
    """
    if not raw_input or not raw_input.strip():
        raise ValueError(
            "No URL provided. Please supply a GitHub repository URL.\n"
            "Example: https://github.com/pallets/flask"
        )

    raw = raw_input.strip()
    logger.debug("Parsing raw URL input: %r", raw)

    # 1. Try SSH format first
    owner, repo_name, branch = _try_ssh(raw)
    if owner is None:
        # 2. Try shorthand owner/repo
        owner, repo_name, branch = _try_shorthand(raw)
    if owner is None:
        # 3. Try full HTTP(S)/no-protocol URL
        owner, repo_name, branch = _try_http_url(raw)

    if owner is None or repo_name is None:
        raise ValueError(
            f"Could not parse {raw!r} as a GitHub repository URL.\n"
            "Accepted formats:\n"
            "  https://github.com/owner/repo\n"
            "  git@github.com:owner/repo.git\n"
            "  owner/repo\n"
        )

    # Strip trailing .git from repo name if somehow still present
    repo_name = repo_name.removesuffix(".git")

    # Validate extracted components
    _validate_owner(owner, raw)
    _validate_repo_name(repo_name, raw)

    owner     = owner.lower()
    repo_name = repo_name.lower()
    normalized = f"https://github.com/{owner}/{repo_name}"

    logger.debug(
        "Parsed URL → owner=%r repo=%r branch=%r normalized=%r",
        owner,
        repo_name,
        branch,
        normalized,
    )

    return ParsedURL(
        owner=owner,
        repo_name=repo_name,
        branch=branch,
        original_url=raw_input,
        normalized_url=normalized,
    )


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

def _try_ssh(raw: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Attempt to parse an SSH-format URL (git@github.com:owner/repo.git)."""
    match = _SSH_RE.match(raw)
    if not match:
        return None, None, None
    return match.group("owner"), match.group("repo"), None


def _try_shorthand(raw: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Attempt to parse the bare ``owner/repo`` shorthand format."""
    # Must not start with / and must contain exactly one /
    if raw.startswith("/") or raw.startswith("http") or raw.startswith("git"):
        return None, None, None
    match = _SHORTHAND_RE.match(raw)
    if not match:
        return None, None, None
    return match.group("owner"), match.group("repo"), None


def _try_http_url(raw: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Attempt to parse an HTTP/HTTPS URL (with or without the protocol prefix).

    Returns:
        Tuple of (owner, repo_name, branch) or (None, None, None).

    Raises:
        ValueError: For URLs that are clearly non-GitHub or unsupported hosts.
    """
    # Ensure the raw string is parseable by urllib; add scheme if missing
    if not raw.startswith(("http://", "https://")):
        raw_with_scheme = "https://" + raw
    else:
        raw_with_scheme = raw

    try:
        parsed = urlparse(raw_with_scheme)
    except ValueError as exc:
        raise ValueError(f"Malformed URL {raw!r}: {exc}") from exc

    host = (parsed.hostname or "").lower().rstrip(".")

    # Block non-GitHub hosts with a helpful message
    if host and host not in ("github.com", "www.github.com"):
        if any(h in host for h in ("gitlab", "bitbucket", "codeberg", "gitea")):
            raise ValueError(
                f"The URL {raw!r} points to {host!r}, which is not GitHub.\n"
                "CodeAutopsy currently supports GitHub repositories only."
            )
        if host:
            raise ValueError(
                f"Unrecognised host {host!r} in URL {raw!r}.\n"
                "Only github.com URLs are supported."
            )

    # Strip query string and fragment; split path into components
    path = parsed.path.strip("/")
    path = path.removesuffix(".git")

    # Remove query params from the last path segment
    if "?" in path:
        path = path[:path.index("?")]

    parts = [p for p in path.split("/") if p]

    if len(parts) < 2:
        if len(parts) == 1:
            raise ValueError(
                f"The URL {raw!r} appears to be a GitHub *user/org* page, "
                "not a repository URL.\nPlease provide a full repo URL, e.g.: "
                f"https://github.com/{parts[0]}/your-repo"
            )
        raise ValueError(
            f"Cannot extract a repository from {raw!r}.\n"
            "The URL must include both an owner and a repository name."
        )

    owner    = parts[0]
    repo     = parts[1]
    branch: Optional[str] = None

    # Extract branch from /tree/<branch>/... or /blob/<branch>/...
    if len(parts) >= 4 and parts[2] in ("tree", "blob"):
        branch = parts[3]

    return owner, repo, branch


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _validate_owner(owner: str, raw: str) -> None:
    """
    Raise ValueError if *owner* violates GitHub's naming rules.

    Args:
        owner: Candidate owner string to validate.
        raw:   Original raw URL (included in error messages).

    Raises:
        ValueError: When owner is invalid.
    """
    if not owner:
        raise ValueError(f"Could not extract an owner name from {raw!r}.")
    if len(owner) > _MAX_OWNER_LEN:
        raise ValueError(
            f"Owner name {owner!r} is {len(owner)} characters long; "
            f"GitHub limits owner names to {_MAX_OWNER_LEN} characters."
        )
    if not _OWNER_RE.match(owner):
        raise ValueError(
            f"Owner name {owner!r} contains invalid characters.\n"
            "GitHub owner names may only contain alphanumeric characters and hyphens, "
            "and cannot start or end with a hyphen."
        )


def _validate_repo_name(repo_name: str, raw: str) -> None:
    """
    Raise ValueError if *repo_name* violates GitHub's naming rules.

    Args:
        repo_name: Candidate repository name to validate.
        raw:       Original raw URL (included in error messages).

    Raises:
        ValueError: When repo_name is invalid.
    """
    if not repo_name:
        raise ValueError(f"Could not extract a repository name from {raw!r}.")
    if len(repo_name) > _MAX_REPO_LEN:
        raise ValueError(
            f"Repository name {repo_name!r} is {len(repo_name)} characters long; "
            f"GitHub limits repository names to {_MAX_REPO_LEN} characters."
        )
    if not _REPO_RE.match(repo_name):
        raise ValueError(
            f"Repository name {repo_name!r} contains invalid characters.\n"
            "GitHub repository names may only contain alphanumeric characters, "
            "hyphens, underscores, and periods."
        )
