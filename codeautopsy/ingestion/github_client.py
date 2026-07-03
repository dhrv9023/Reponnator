"""
ingestion/github_client.py — GitHub API Client Wrapper

All GitHub API interactions flow through this module.  It wraps PyGithub
with retry logic, custom exception types, rate-limit awareness, and
careful error handling for every edge case documented by the GitHub API.

Custom exceptions:
    RepoNotFoundError   — 404 response (repo absent or renamed)
    RepoPrivateError    — 403/404 for private repos without auth
    GitHubClientError   — All other API errors
    RateLimitError      — Rate limit exceeded and could not recover
"""

import base64
import time
from typing import Any, Optional

from github import (
    Github,
    GithubException,
    RateLimitExceededException,
    UnknownObjectException,
)
from github.Repository import Repository

from config import (
    MAX_FILE_SIZE_BYTES,
    MAX_RETRIES,
    RETRY_DELAY_SECONDS,
)
from utils.logger import get_logger
from utils.rate_limiter import RateLimiter

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------

class GitHubClientError(Exception):
    """Base class for all GitHub client errors."""


class RepoNotFoundError(GitHubClientError):
    """Raised when the requested repository does not exist on GitHub."""


class RepoPrivateError(GitHubClientError):
    """Raised when the repository is private and the token lacks access."""


class RateLimitError(GitHubClientError):
    """Raised when the rate limit could not be recovered automatically."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class GitHubClient:
    """
    Thin, fault-tolerant wrapper around :class:`github.Github`.

    Args:
        token: GitHub personal access token, or ``None`` for anonymous access.
               Anonymous access is limited to 60 requests per hour.
    """

    def __init__(self, token: Optional[str] = None) -> None:
        self._token = token
        self._gh = Github(login_or_token=token) if token else Github()
        self._rate_limiter: Optional[RateLimiter] = None

        if token:
            self._verify_token()
        else:
            logger.warning(
                "No GitHub token configured. Anonymous API access is limited to "
                "60 requests per hour. Add GITHUB_TOKEN to your .env file to "
                "raise this limit to 5,000 requests per hour."
            )

        # Initialise rate limiter after token check
        self._rate_limiter = RateLimiter(self._gh)
        logger.debug("Rate limit status on startup: %s", self._rate_limiter.get_rate_limit_status())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_repo(self, owner: str, repo_name: str) -> Repository:
        """
        Fetch a GitHub repository object by owner and name.

        Args:
            owner:     Repository owner (user or organization).
            repo_name: Repository name.

        Returns:
            A PyGithub :class:`~github.Repository.Repository` object.

        Raises:
            RepoNotFoundError:  The repository does not exist.
            RepoPrivateError:   The repository is private and inaccessible.
            GitHubClientError:  Any other API error.
        """
        full_name = f"{owner}/{repo_name}"
        logger.debug("Fetching repository object for %r.", full_name)

        def _do_get() -> Repository:
            self._wait_if_needed()
            return self._gh.get_repo(full_name)

        return self._with_retry(_do_get, context=f"get_repo({full_name})")

    def get_repo_metadata(self, repo: Repository) -> dict[str, Any]:
        """
        Extract rich metadata from a repository object into a plain dict.

        Args:
            repo: A PyGithub :class:`~github.Repository.Repository` instance.

        Returns:
            Dictionary with name, owner, description, stars, forks, topics,
            license, dates, and various boolean flags.
        """
        logger.debug("Extracting metadata for %r.", repo.full_name)
        try:
            license_name = repo.license.name if repo.license else None
        except (AttributeError, GithubException):
            license_name = None

        try:
            topics = repo.get_topics()
        except GithubException:
            topics = []

        return {
            "name":               repo.name,
            "owner":              repo.owner.login,
            "full_name":          repo.full_name,
            "description":        repo.description or "",
            "primary_language":   repo.language or "Unknown",
            "stars":              repo.stargazers_count,
            "forks":              repo.forks_count,
            "size_kb":            repo.size,
            "default_branch":     repo.default_branch,
            "topics":             list(topics),
            "created_at":         repo.created_at.isoformat() if repo.created_at else None,
            "updated_at":         repo.updated_at.isoformat() if repo.updated_at else None,
            "license":            license_name,
            "is_fork":            repo.fork,
            "is_archived":        repo.archived,
            "has_wiki":           repo.has_wiki,
            "open_issues_count":  repo.open_issues_count,
            "homepage":           repo.homepage or "",
            "visibility":         repo.visibility if hasattr(repo, "visibility") else "public",
        }

    def get_file_tree(
        self,
        repo: Repository,
        branch: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Recursively fetch the complete file tree for a repository branch.

        Args:
            repo:   PyGithub repository object.
            branch: Branch name to fetch; defaults to the repo's default branch.

        Returns:
            List of dicts, each with keys:
            ``path``, ``type`` (``'blob'``/``'tree'``/``'commit'``),
            ``size`` (bytes, 0 for trees), ``sha``, ``url``.

        Raises:
            GitHubClientError: If the tree cannot be retrieved.
        """
        ref = branch or repo.default_branch
        logger.debug("Fetching recursive file tree for %r @ %r.", repo.full_name, ref)
        self._wait_if_needed()

        try:
            tree = repo.get_git_tree(ref, recursive=True)
        except UnknownObjectException as exc:
            raise GitHubClientError(
                f"Branch or ref {ref!r} not found in {repo.full_name!r}: {exc}"
            ) from exc
        except GithubException as exc:
            raise GitHubClientError(
                f"Failed to fetch file tree for {repo.full_name!r}: {exc}"
            ) from exc

        if tree.truncated:
            logger.warning(
                "File tree for %r is truncated by the GitHub API — "
                "the repository likely has more than 100,000 files. "
                "Only files returned by the API will be processed.",
                repo.full_name,
            )

        entries: list[dict[str, Any]] = []
        for element in tree.tree:
            entries.append({
                "path": element.path,
                "type": element.type,   # 'blob', 'tree', or 'commit' (submodule)
                "size": element.size or 0,
                "sha":  element.sha,
                "url":  element.url,
            })

        logger.debug("File tree fetched: %d entries total.", len(entries))
        return entries

    def get_file_content(
        self,
        repo: Repository,
        file_path: str,
        branch: str,
    ) -> Optional[str]:
        """
        Fetch the decoded text content of a single file.

        Args:
            repo:      PyGithub repository object.
            file_path: Path to the file within the repository.
            branch:    Branch name from which to read the file.

        Returns:
            Decoded text content of the file, or ``None`` if the file
            cannot be fetched, decoded, or exceeds the size limit.
        """
        self._wait_if_needed()

        def _do_fetch() -> Optional[str]:
            try:
                file_obj = repo.get_contents(file_path, ref=branch)
            except UnknownObjectException:
                logger.warning("File not found via contents API: %r", file_path)
                return None
            except GithubException as exc:
                raise GitHubClientError(
                    f"API error fetching {file_path!r}: {exc}"
                ) from exc

            # Handle lists (directories misidentified as files — shouldn't happen
            # after tree filtering but guard defensively)
            if isinstance(file_obj, list):
                logger.warning("Path %r resolved to a directory, not a file — skipping.", file_path)
                return None

            size_bytes: int = file_obj.size or 0
            if size_bytes > MAX_FILE_SIZE_BYTES:
                logger.warning(
                    "Skipping %r: size %d bytes exceeds MAX_FILE_SIZE_BYTES (%d).",
                    file_path,
                    size_bytes,
                    MAX_FILE_SIZE_BYTES,
                )
                return None

            if size_bytes == 0:
                logger.debug("Skipping empty file: %r", file_path)
                return None

            return _decode_content(file_obj, file_path)

        try:
            return self._with_retry(_do_fetch, context=f"get_file_content({file_path})")
        except GitHubClientError as exc:
            logger.error("Could not fetch file %r: %s", file_path, exc)
            return None

    def check_repo_exists(self, owner: str, repo_name: str) -> bool:
        """
        Quickly test whether a repository is publicly accessible.

        Args:
            owner:     Repository owner.
            repo_name: Repository name.

        Returns:
            ``True`` if the repository exists and is accessible.
        """
        try:
            self.get_repo(owner, repo_name)
            return True
        except (RepoNotFoundError, RepoPrivateError):
            return False
        except GitHubClientError:
            return False

    def get_rate_limit_status(self) -> dict[str, Any]:
        """
        Return the current API rate limit state.

        Returns:
            Dict with ``remaining``, ``limit``, ``used``,
            ``reset_time``, and ``seconds_until_reset``.
        """
        if self._rate_limiter is None:
            return {}
        return self._rate_limiter.get_rate_limit_status()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _verify_token(self) -> None:
        """
        Validate the supplied token by making a lightweight authenticated call.

        Raises:
            GitHubClientError: If the token is invalid or revoked.
        """
        try:
            user = self._gh.get_user()
            logger.info("Authenticated as GitHub user: %r", user.login)
        except GithubException as exc:
            if exc.status == 401:
                raise GitHubClientError(
                    "The GitHub token in your .env file is invalid or has been revoked. "
                    "Please generate a new token at https://github.com/settings/tokens "
                    "and update GITHUB_TOKEN in your .env file."
                ) from exc
            raise GitHubClientError(
                f"Could not verify GitHub token: {exc}"
            ) from exc

    def _wait_if_needed(self) -> None:
        """Delegate to the rate limiter before making an API call."""
        if self._rate_limiter is not None:
            self._rate_limiter.check_and_wait()

    def _with_retry(self, func, *, context: str) -> Any:
        """
        Execute *func* with exponential-backoff retry logic.

        Args:
            func:    Callable that performs the GitHub API operation.
            context: Human-readable description for log messages.

        Returns:
            The return value of *func* on success.

        Raises:
            RepoNotFoundError:  On 404 from the API.
            RepoPrivateError:   On 403 from a private repo.
            RateLimitError:     If rate limit persists after waiting.
            GitHubClientError:  On non-recoverable API errors.
        """
        last_exception: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func()

            except RateLimitExceededException as exc:
                logger.warning("Rate limit exceeded during %s (attempt %d).", context, attempt)
                if self._rate_limiter:
                    self._rate_limiter.update_from_exception(exc)
                else:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)
                last_exception = exc

            except UnknownObjectException as exc:
                # 404 — determine if repo exists but is private or truly absent
                status = exc.status if hasattr(exc, "status") else 404
                if status == 404:
                    # Re-raise immediately; retrying won't help
                    raise RepoNotFoundError(
                        f"Repository not found: {context}. "
                        "Verify the owner and repo name are correct."
                    ) from exc
                raise GitHubClientError(f"Unknown object: {exc}") from exc

            except GithubException as exc:
                status = exc.status if hasattr(exc, "status") else 0
                if status == 401:
                    raise GitHubClientError(
                        "GitHub API authentication failed. Your token may be invalid."
                    ) from exc
                if status == 403:
                    data = exc.data or {}
                    msg  = str(data.get("message", "")).lower()
                    if "private" in msg or "access" in msg:
                        raise RepoPrivateError(
                            f"Repository is private or you lack access: {context}. "
                            "Add a GitHub token with 'repo' scope to your .env file."
                        ) from exc
                    # Other 403 (e.g. secondary rate limit)
                    logger.warning(
                        "GitHub 403 during %s (attempt %d/%d): %s",
                        context, attempt, MAX_RETRIES, exc,
                    )
                elif status >= 500:
                    logger.warning(
                        "GitHub server error %d during %s (attempt %d/%d). Retrying…",
                        status, context, attempt, MAX_RETRIES,
                    )
                else:
                    raise GitHubClientError(
                        f"GitHub API error during {context}: {exc}"
                    ) from exc

                last_exception = exc
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                    logger.debug("Waiting %.1fs before retry…", delay)
                    time.sleep(delay)

        raise GitHubClientError(
            f"All {MAX_RETRIES} attempts failed for {context}: {last_exception}"
        ) from last_exception


# ---------------------------------------------------------------------------
# Content decoding helper (module-level, used by get_file_content)
# ---------------------------------------------------------------------------

def _decode_content(file_obj: Any, file_path: str) -> Optional[str]:
    """
    Decode a PyGithub ContentFile into a UTF-8 string.

    Tries UTF-8 first, then falls back to latin-1.  Returns ``None``
    if neither encoding succeeds or if the content field is missing.

    Args:
        file_obj:  PyGithub ContentFile object.
        file_path: Path string (used only in log messages).

    Returns:
        Decoded text string, or ``None``.
    """
    raw_bytes: Optional[bytes] = None

    # PyGithub exposes decoded_content as bytes for blobs
    try:
        if file_obj.encoding == "base64" and file_obj.content:
            raw_bytes = base64.b64decode(file_obj.content)
        elif hasattr(file_obj, "decoded_content") and file_obj.decoded_content:
            raw_bytes = file_obj.decoded_content
    except Exception as exc:
        logger.warning("Failed to extract raw bytes from %r: %s", file_path, exc)
        return None

    if raw_bytes is None:
        logger.debug("No content bytes for %r — skipping.", file_path)
        return None

    # Try UTF-8 (with BOM strip)
    try:
        text = raw_bytes.decode("utf-8-sig")
        # Normalise Windows line endings
        return text.replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        pass

    # Fallback: latin-1 (never fails, but may produce garbled text for binary)
    try:
        text = raw_bytes.decode("latin-1")
        logger.debug("File %r decoded with latin-1 fallback.", file_path)
        return text.replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        logger.warning(
            "Skipping %r: content cannot be decoded as UTF-8 or latin-1.", file_path
        )
        return None


def create_client_from_env() -> "GitHubClient":
    """
    Convenience factory that reads ``GITHUB_TOKEN`` from the environment / .env.

    Returns:
        A configured :class:`GitHubClient` instance.
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN") or None
    return GitHubClient(token=token)
