"""
api/models/responses.py — Pydantic response models

All API responses validated with Pydantic v2.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class JobResponse(BaseModel):
    """Response when a background job is created."""
    job_id: str = Field(..., description="Unique job identifier (UUID)")
    status: str = Field(..., description="Job status: queued, running, complete, failed")
    repo_key: str = Field(..., description="Repository key (owner__repo)")


class JobStatusResponse(BaseModel):
    """Detailed job status response."""
    job_id: str
    phase: str = Field(..., description="Phase name: ingest, parse, chunk, qa, diagram, story")
    repo_key: str
    status: str = Field(..., description="Job status: queued, running, complete, failed")
    progress_percent: int = Field(default=0, ge=0, le=100)
    current_step: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class RepoSummary(BaseModel):
    """Summary of a repository."""
    repo_key: str
    owner: str
    name: str
    total_files: int
    primary_language: str
    ingested_at: datetime
    phases_complete: List[str] = Field(default_factory=list)


class RepoListResponse(BaseModel):
    """List of repositories."""
    repos: List[RepoSummary]


class RepoDetailResponse(BaseModel):
    """Detailed repository metadata."""
    repo_key: str
    owner: str
    name: str
    branch: str
    total_files: int
    total_bytes: int
    primary_language: str
    languages: Dict[str, Any]
    ingested_at: datetime
    phases_complete: List[str]


class ParseResponse(BaseModel):
    """Phase 2 parse output summary."""
    repo_key: str
    total_functions: int
    total_classes: int
    call_edges: int
    detected_patterns: List[str]
    entry_points: List[str]
    parse_duration_seconds: float
    files_parsed: int
    files_failed: int


class ChunkResponse(BaseModel):
    """Phase 3 chunk output summary."""
    repo_key: str
    total_chunks: int
    embedding_model: str
    embedding_dimensions: int
    total_tokens: int
    average_tokens_per_chunk: int
    chroma_collection_name: str
    embed_duration_seconds: float


class Citation(BaseModel):
    """Source code citation."""
    filename: str
    line_start: int | None = None
    line_end: int | None = None
    snippet: str | None = None


class QAResponse(BaseModel):
    """Phase 4 Q&A response."""
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    session_id: str
    tokens_used: int
    confidence: str = Field(..., description="high, medium, low")


class NodeMetadata(BaseModel):
    """Diagram node metadata."""
    id: str
    label: str
    type: str = Field(..., description="entry_point, core_utility, module")
    functions: List[str] = Field(default_factory=list)
    classes: List[str] = Field(default_factory=list)
    call_count: int


class DiagramResponse(BaseModel):
    """Phase 6 diagram output."""
    mermaid_syntax: str
    node_count: int
    edge_count: int
    metadata: List[NodeMetadata]


class KeyModule(BaseModel):
    """Key module in architectural story."""
    module_id: str
    role_title: str
    explanation: str


class StoryResponse(BaseModel):
    """Phase 7 architectural story output."""
    project_summary: str = ""
    tech_stack: List[str] = Field(default_factory=list, description="Detected libraries/frameworks from source code")
    primary_commitment: str
    origin_story: str
    how_it_flows: str
    key_modules: List[KeyModule]
    design_tensions: str
    founding_metaphor: str
    verdict: str
    # Metadata
    model_used: str
    generation_duration_seconds: float
    tokens_used: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="ok")
    version: str
    groq_configured: bool
    github_token_configured: bool
