"""
agent/nodes/fetch_node.py — Fetch Node Data

Retrieves all available data about the current node from Phase 2 and Phase 3.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def fetch_node(state: dict) -> dict:
    """
    Fetch all data about the current node.
    
    Combines data from:
    - Phase 2 call graph
    - Phase 3 ChromaDB chunks
    
    Args:
        state: AgentState dict
    
    Returns:
        Dict with updated nodes, edges, visited
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from agent.tools.chunk_lookup import chunk_lookup
    from agent.tools.graph_lookup import graph_lookup, get_node_from_call_graph
    from agent.layer_detector import detect_layer, is_cross_layer_node
    from agent import node_to_dict, edge_to_dict, TraversalNode, TraversalEdge
    
    qualified_name = state["current_node_name"]
    repo_owner = state["repo_owner"]
    repo_name = state["repo_name"]
    call_graph_data = state["call_graph_data"]
    depth_map = state["depth_map"]
    entry_points = state["entry_points"]
    
    logger.debug(f"Fetching node: {qualified_name}")
    
    # Look up in call graph
    graph_node = get_node_from_call_graph(qualified_name, call_graph_data)
    
    if not graph_node:
        # External or unresolved node
        logger.warning(f"Node not found in call graph: {qualified_name}")
        graph_node = {
            "qualified_name": qualified_name,
            "name": qualified_name.split(".")[-1],
            "file_path": "",
            "language": "unknown",
            "complexity_score": 0
        }
    
    # Look up chunk in ChromaDB
    chunk_data = chunk_lookup(qualified_name, repo_owner, repo_name)
    
    # Extract data
    file_path = chunk_data["file_path"] if chunk_data else graph_node.get("file_path", "")
    language = chunk_data["language"] if chunk_data else graph_node.get("language", "unknown")
    complexity_score = chunk_data["complexity_score"] if chunk_data else graph_node.get("complexity_score", 0)
    
    # Detect architectural layer
    architectural_layer = detect_layer(qualified_name, file_path)
    
    # Get call relationships
    relationships = graph_lookup(qualified_name, call_graph_data, "both")
    calls = relationships["calls"]
    called_by = relationships["called_by"]
    
    # Build TraversalNode
    node = TraversalNode(
        qualified_name=qualified_name,
        name=qualified_name.split(".")[-1],
        file_path=file_path,
        language=language,
        chunk_id=chunk_data["chunk_id"] if chunk_data else None,
        depth_from_entry=depth_map.get(qualified_name, 0),
        is_entry_point=qualified_name in entry_points,
        is_hub=False,  # Set in finalize
        is_orphan=False,  # Set in finalize
        complexity_score=complexity_score,
        calls_count=len(calls),
        called_by_count=len(called_by),
        architectural_layer=architectural_layer,
        role_description="",  # Filled by analyze_node if selected
        design_pattern=None,
        content_preview=chunk_data["content"][:150] if chunk_data else "",
        was_analyzed_by_llm=False,
        node_type=determine_node_type(qualified_name)
    )
    
    # Build edges for this node
    new_edges = []
    for callee in calls:
        # Detect callee layer
        callee_graph_node = get_node_from_call_graph(callee, call_graph_data)
        callee_file_path = callee_graph_node.get("file_path", "") if callee_graph_node else ""
        callee_layer = detect_layer(callee, callee_file_path)
        
        edge = TraversalEdge(
            from_node=qualified_name,
            to_node=callee,
            edge_type="calls",
            weight=1,
            is_cross_file=(file_path != callee_file_path) if callee_file_path else False,
            is_cross_layer=is_cross_layer_node(architectural_layer, callee_layer)
        )
        new_edges.append(edge)
    
    # Add node to state
    nodes = state["nodes"].copy()
    nodes[qualified_name] = node_to_dict(node)
    
    # Add edges to state
    edges = state["edges"] + [edge_to_dict(e) for e in new_edges]
    
    # Add to visited
    visited = state["visited"] + [qualified_name]
    
    logger.debug(f"Fetched node: {qualified_name} (layer={architectural_layer}, calls={len(calls)}, called_by={len(called_by)})")
    
    return {
        "nodes": nodes,
        "edges": edges,
        "visited": visited
    }


def determine_node_type(qualified_name: str) -> str:
    """
    Determine node type from qualified name.
    
    Args:
        qualified_name: e.g., "UserService.get_user"
    
    Returns:
        "function", "method", or "class_entry"
    """
    parts = qualified_name.split(".")
    
    if len(parts) == 1:
        return "function"
    elif len(parts) == 2:
        # Could be Class.method or module.function
        # Heuristic: if first part is CamelCase, it's a method
        if parts[0][0].isupper():
            return "method"
        else:
            return "function"
    else:
        return "method"
