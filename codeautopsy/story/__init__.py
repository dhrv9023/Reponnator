"""
story/__init__.py — Phase 7 Architectural Story Engine (Repponator)

Generates editorial-quality architectural narratives from Phase 2 structural analysis.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModuleBrief:
    """Brief summary of a module for story context."""
    filename: str
    function_names: list[str]  # max 8
    class_names: list[str]     # max 5
    called_by_count: int
    calls_count: int


@dataclass
class StoryContext:
    """Compressed context for story generation."""
    repo_name: str
    primary_language: str
    total_files: int
    total_functions: int
    total_classes: int
    detected_pattern: str           # "REST API", "MVC", "Event-driven", etc.
    entry_points: list[str]         # top 3 by confidence
    core_utilities: list[str]       # files called by 3+ others
    top_modules: list[ModuleBrief]  # top 10 by call_count
    has_circular_deps: bool
    complexity_hotspots: list[str]  # top 5 highest cyclomatic complexity
    architectural_signals: list[str] # ["uses_middleware", "has_migrations", etc.]
    repo_description: str = ""
    languages_breakdown: str = ""
    # Actual source code excerpts — each entry: {path, language, content}
    file_contents: list[dict] = field(default_factory=list)


@dataclass
class KeyModule:
    """A key module in the architectural story."""
    module_id: str        # filename used as diagram node id
    role_title: str       # e.g., "The Gateway", "The Orchestrator"
    explanation: str      # 2 sentences


@dataclass
class ArchitecturalStory:
    """Complete architectural narrative."""
    project_summary: str = ""    # Plain-English: what this project is and does
    tech_stack: list[str] = field(default_factory=list)  # ["FastAPI", "librosa", "PyTorch", ...]
    primary_commitment: str = ""  # One sentence
    origin_story: str = ""        # 2-3 sentences
    how_it_flows: str = ""        # 3-4 sentences
    key_modules: list[KeyModule] = field(default_factory=list)  # Module narratives
    design_tensions: str = ""     # 2-3 sentences
    founding_metaphor: str = ""   # One vivid metaphor
    verdict: str = ""             # 2 sentences


@dataclass
class StoryMetadata:
    """Metadata about story generation."""
    repo_owner: str
    repo_name: str
    model_used: str
    temperature: float
    max_tokens: int
    prompt_tokens: int
    completion_tokens: int
    generation_timestamp: str
    generation_duration_seconds: float


__all__ = [
    "ModuleBrief",
    "StoryContext",
    "KeyModule",
    "ArchitecturalStory",
    "StoryMetadata"
]
