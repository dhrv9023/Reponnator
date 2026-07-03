"""
ingestion/__init__.py

Public interface for the ingestion package.

Exports the primary orchestration entry point and result types so that
downstream phases (parsing, embedding, RAG) can import cleanly from the
top-level package.
"""

from ingestion.file_fetcher import FetchResult, FetchedFile, SkippedFile, fetch_repository
from ingestion.url_parser import ParsedURL, parse_github_url
from ingestion.github_client import (
    GitHubClient,
    GitHubClientError,
    RepoNotFoundError,
    RepoPrivateError,
    RateLimitError,
    create_client_from_env,
)

__all__ = [
    "FetchResult",
    "FetchedFile",
    "SkippedFile",
    "fetch_repository",
    "ParsedURL",
    "parse_github_url",
    "GitHubClient",
    "GitHubClientError",
    "RepoNotFoundError",
    "RepoPrivateError",
    "RateLimitError",
    "create_client_from_env",
]
