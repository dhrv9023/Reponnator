"""
agent/state.py — LangGraph Agent State Definition

Defines the AgentState TypedDict that LangGraph uses to track traversal state.
All state keys must be JSON-serializable (no sets, no custom dataclasses, no Path objects).
"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage


def add_messages(existing: list, new: list) -> list:
    """Merge messages for LangGraph state."""
    return existing + new


class AgentState(TypedDict):
    """
    State for the LangGraph call graph traversal agent.
    
    All values must be JSON-serializable:
    - Use lists instead of sets
    - Use dicts instead of dataclasses
    - Use strings instead of Path objects
    """
    
    # ── Repo identity ──────────────────────────────────────
    repo_owner: str
    repo_name: str
    
    # ── Traversal queue (BFS) ─────────────────────────────
    queue: list[str]          # qualified names to visit next (FIFO for BFS)
    
    # ── Visited tracking ──────────────────────────────────
    visited: list[str]        # qualified names already processed
    
    # ── Built graph ───────────────────────────────────────
    nodes: dict               # qualified_name → TraversalNode as dict
    edges: list               # list of TraversalEdge as dicts
    node_analyses: dict       # qualified_name → LLM analysis text
    
    # ── Traversal control ─────────────────────────────────
    current_node_name: str    # qualified name being processed NOW
    depth_map: dict           # qualified_name → depth from entry
    max_depth: int            # configurable, default 6
    entry_points: list[str]   # starting qualified names
    
    # ── LLM budget tracking ───────────────────────────────
    llm_calls_made: int
    llm_budget: int           # max LLM calls allowed, default 30
    
    # ── Graph data from Phase 2 ───────────────────────────
    call_graph_data: dict     # full call_graph.json loaded into memory
    dependency_map_data: dict # full dependency_map.json in memory
    
    # ── Status + errors ───────────────────────────────────
    status: str               # "initializing", "traversing", "complete", "error"
    errors: list[str]
    traversal_log: list[dict] # step by step log for traversal_log.jsonl
    
    # ── LangGraph messages (required for tool calling) ────
    messages: Annotated[list[BaseMessage], add_messages]
    
    # ── Timing ────────────────────────────────────────────
    start_time: float
    step_count: int
