"""
agent/__init__.py — Phase 5 Dataclasses

Defines all data structures used in the LangGraph agent for call graph traversal.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TraversalNode:
    """
    Represents a single node in the traversal graph (a function, method, or class).
    """
    qualified_name: str                # e.g., "UserService.get_user"
    name: str                          # e.g., "get_user"
    file_path: str                     # e.g., "src/services/user_service.py"
    language: str                      # e.g., "Python"
    chunk_id: Optional[str]            # UUID from ChromaDB, None if not embedded
    depth_from_entry: int              # BFS depth from entry point
    is_entry_point: bool               # True if this is an entry point
    is_hub: bool                       # True if called by many others
    is_orphan: bool                    # True if never called by anyone
    complexity_score: int              # Cyclomatic complexity
    calls_count: int                   # How many functions this calls
    called_by_count: int               # How many functions call this
    architectural_layer: str           # "entry", "service", "repository", etc.
    role_description: str              # AI-generated description (or empty)
    design_pattern: Optional[str]      # AI-detected pattern (or None)
    content_preview: str               # First 150 chars of function body
    was_analyzed_by_llm: bool          # True if LLM analyzed this node
    node_type: str                     # "function", "method", "class_entry"


@dataclass
class TraversalEdge:
    """
    Represents a directed edge in the traversal graph (a function call).
    """
    from_node: str                     # qualified name of caller
    to_node: str                       # qualified name of callee
    edge_type: str                     # "calls", "imports", "inherits"
    weight: int                        # call frequency (1 if unknown)
    is_cross_file: bool                # True if caller and callee in different files
    is_cross_layer: bool               # True if crosses architectural layer boundary


@dataclass
class TraversalGraph:
    """
    Complete traversal graph output (Phase 6 input).
    """
    repo_owner: str
    repo_name: str
    traversal_timestamp: str
    nodes: dict[str, dict]             # qualified_name → TraversalNode as dict
    edges: list[dict]                  # list of TraversalEdge as dicts
    entry_points: list[str]            # qualified names
    hub_nodes: list[str]               # top 10 most-called
    orphan_nodes: list[str]            # never called
    architectural_layers: dict[str, list[str]]  # layer → [qualified_names]
    total_nodes_reachable: int
    total_nodes_analyzed: int          # had LLM analysis
    total_edges: int
    max_depth_reached: int
    traversal_duration_seconds: float
    llm_calls_made: int


@dataclass
class TraversalManifest:
    """
    Summary manifest for traversal run.
    """
    codeautopsy_version: str
    traversal_timestamp: str
    repo_owner: str
    repo_name: str
    entry_points_used: list[str]
    total_nodes: int
    total_edges: int
    llm_calls_made: int
    traversal_duration_seconds: float
    max_depth: int
    hub_nodes: list[str]
    architectural_layers_detected: list[str]
    errors: list[str]


# Helper functions for dataclass serialization

def node_to_dict(node: TraversalNode) -> dict:
    """Convert TraversalNode to dict for JSON serialization."""
    return {
        "qualified_name": node.qualified_name,
        "name": node.name,
        "file_path": node.file_path,
        "language": node.language,
        "chunk_id": node.chunk_id,
        "depth_from_entry": node.depth_from_entry,
        "is_entry_point": node.is_entry_point,
        "is_hub": node.is_hub,
        "is_orphan": node.is_orphan,
        "complexity_score": node.complexity_score,
        "calls_count": node.calls_count,
        "called_by_count": node.called_by_count,
        "architectural_layer": node.architectural_layer,
        "role_description": node.role_description,
        "design_pattern": node.design_pattern,
        "content_preview": node.content_preview,
        "was_analyzed_by_llm": node.was_analyzed_by_llm,
        "node_type": node.node_type
    }


def dict_to_node(d: dict) -> TraversalNode:
    """Convert dict to TraversalNode."""
    return TraversalNode(**d)


def edge_to_dict(edge: TraversalEdge) -> dict:
    """Convert TraversalEdge to dict for JSON serialization."""
    return {
        "from_node": edge.from_node,
        "to_node": edge.to_node,
        "edge_type": edge.edge_type,
        "weight": edge.weight,
        "is_cross_file": edge.is_cross_file,
        "is_cross_layer": edge.is_cross_layer
    }


def dict_to_edge(d: dict) -> TraversalEdge:
    """Convert dict to TraversalEdge."""
    return TraversalEdge(**d)
