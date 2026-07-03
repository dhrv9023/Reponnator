"""
api/models/requests.py — Pydantic request models

All API request bodies validated with Pydantic v2.
"""

from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


class IngestRequest(BaseModel):
    """Request to ingest a GitHub repository (Phase 1)."""
    github_url: str = Field(..., description="GitHub repository URL")
    branch: Optional[str] = Field(
        default=None,
        description="Branch to fetch. Omit or set to null to use the repo's default branch (auto-detected from GitHub)."
    )
    force: bool = Field(default=False, description="Force re-fetch if already cached")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "github_url": "https://github.com/pallets/flask",
                    "branch": None,
                    "force": False
                }
            ]
        }
    }


class ParseRequest(BaseModel):
    """Request to parse a repository (Phase 2)."""
    repo_key: str = Field(..., description="Repository key (owner__repo)")
    force: bool = Field(default=False, description="Force re-parse if already cached")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "repo_key": "pallets__flask",
                    "force": False
                }
            ]
        }
    }


class ChunkRequest(BaseModel):
    """Request to chunk and embed a repository (Phase 3)."""
    repo_key: str = Field(..., description="Repository key (owner__repo)")
    force: bool = Field(default=False, description="Force re-chunk if already cached")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "repo_key": "pallets__flask",
                    "force": False
                }
            ]
        }
    }


class QARequest(BaseModel):
    """Request to ask a question about a repository (Phase 4)."""
    repo_key: str = Field(..., description="Repository key (owner__repo)")
    question: str = Field(..., description="Natural language question", min_length=1)
    session_id: str | None = Field(default=None, description="Optional session ID for conversation memory")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "repo_key": "pallets__flask",
                    "question": "What does the app.py entry point do?",
                    "session_id": None
                }
            ]
        }
    }


class DiagramRequest(BaseModel):
    """Request to generate a Mermaid diagram (Phase 6)."""
    repo_key: str = Field(..., description="Repository key (owner__repo)")
    force: bool = Field(default=False, description="Force re-generate if already cached")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "repo_key": "pallets__flask",
                    "force": False
                }
            ]
        }
    }


class StoryRequest(BaseModel):
    """Request to generate an architectural story (Phase 7)."""
    repo_key: str = Field(..., description="Repository key (owner__repo)")
    force: bool = Field(default=False, description="Force re-generate if already cached")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "repo_key": "pallets__flask",
                    "force": False
                }
            ]
        }
    }
