"""
agent/nodes/initialize.py — Initialize Agent Node

Validates inputs, loads graph data, seeds BFS queue.
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def initialize(state: dict) -> dict:
    """
    Initialize the traversal agent.
    
    Loads Phase 2 data, resolves entry points, seeds BFS queue.
    
    Args:
        state: AgentState dict
    
    Returns:
        Dict with initialized state keys
    """
    repo_owner = state["repo_owner"]
    repo_name = state["repo_name"]
    
    logger.info(f"Initializing traversal for {repo_owner}/{repo_name}")
    
    # Build repo folder path
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from config import DATA_DIR
    
    repo_folder = Path(DATA_DIR) / f"{repo_owner}__{repo_name}"
    parsed_folder = repo_folder / "parsed"
    
    # Load call_graph.json
    call_graph_path = parsed_folder / "call_graph.json"
    if not call_graph_path.exists():
        error_msg = f"call_graph.json not found at {call_graph_path}. Run Phase 2 first."
        logger.error(error_msg)
        return {
            "status": "error",
            "errors": [error_msg]
        }
    
    with open(call_graph_path, "r") as f:
        call_graph_data = json.load(f)
    
    logger.info(f"Loaded call graph with {len(call_graph_data.get('nodes', {}))} nodes")
    
    # Load dependency_map.json
    dependency_map_path = parsed_folder / "dependency_map.json"
    if not dependency_map_path.exists():
        logger.warning(f"dependency_map.json not found, using empty map")
        dependency_map_data = {}
    else:
        with open(dependency_map_path, "r") as f:
            dependency_map_data = json.load(f)
    
    # Load entry_points.json
    entry_points_path = parsed_folder / "entry_points.json"
    entry_points = []
    
    if entry_points_path.exists():
        with open(entry_points_path, "r") as f:
            entry_points_raw = json.load(f)
        
        # Extract entry function qualified names
        for entry_point in entry_points_raw:
            entry_functions = entry_point.get("entry_functions", [])
            entry_points.extend(entry_functions)
    
    # Fallback: use hub nodes if no entry points found
    if not entry_points:
        logger.warning("No entry points detected, using hub nodes as starting points")
        
        # Get top 3 most-called functions
        reverse_adjacency = call_graph_data.get("reverse_adjacency", {})
        nodes_by_called_count = []
        
        for qualified_name in call_graph_data.get("nodes", {}).keys():
            called_by_count = len(reverse_adjacency.get(qualified_name, []))
            nodes_by_called_count.append((qualified_name, called_by_count))
        
        nodes_by_called_count.sort(key=lambda x: x[1], reverse=True)
        entry_points = [qn for qn, _ in nodes_by_called_count[:3]]
        
        logger.info(f"Using hub nodes as entry points: {entry_points}")
    
    # Seed BFS queue
    queue = list(entry_points)
    depth_map = {ep: 0 for ep in entry_points}
    
    # Initialize tracking state
    visited = []
    nodes = {}
    edges = []
    node_analyses = {}
    llm_calls_made = 0
    status = "traversing"
    step_count = 0
    start_time = time.time()
    
    # Log traversal start
    traversal_log = [{
        "step": 0,
        "action": "initialize",
        "entry_points": entry_points,
        "queue_size": len(queue),
        "timestamp": datetime.now().isoformat()
    }]
    
    logger.info(f"Initialized with {len(entry_points)} entry points, queue size: {len(queue)}")
    
    return {
        "call_graph_data": call_graph_data,
        "dependency_map_data": dependency_map_data,
        "entry_points": entry_points,
        "queue": queue,
        "depth_map": depth_map,
        "visited": visited,
        "nodes": nodes,
        "edges": edges,
        "node_analyses": node_analyses,
        "llm_calls_made": llm_calls_made,
        "status": status,
        "step_count": step_count,
        "start_time": start_time,
        "traversal_log": traversal_log,
        "errors": []
    }
