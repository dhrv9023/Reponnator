"""
agent/nodes/expand_neighbors.py — Expand Neighbors

Adds unvisited neighbors to BFS queue.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def expand_neighbors(state: dict) -> dict:
    """
    Add unvisited neighbors to the BFS queue.
    
    Args:
        state: AgentState dict
    
    Returns:
        Dict with updated queue, depth_map
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from config import MAX_TRAVERSAL_DEPTH
    from agent.tools.graph_lookup import graph_lookup
    
    qualified_name = state["current_node_name"]
    call_graph_data = state["call_graph_data"]
    depth_map = state["depth_map"]
    visited = state["visited"]
    queue = state["queue"]
    
    # Get current depth
    current_depth = depth_map.get(qualified_name, 0)
    
    # Check if we've reached max depth
    if current_depth >= MAX_TRAVERSAL_DEPTH:
        logger.debug(f"Max depth reached at {qualified_name}, not expanding")
        return {}
    
    # Get neighbors (functions this calls)
    relationships = graph_lookup(qualified_name, call_graph_data, "calls")
    calls = relationships["calls"]
    
    # Determine neighbors to add
    neighbors_to_add = []
    new_depth_map = depth_map.copy()
    
    for callee in calls:
        if callee not in visited and callee not in queue:
            neighbors_to_add.append(callee)
            new_depth_map[callee] = current_depth + 1
    
    # Priority ordering for queue insertion
    # - High complexity callees: insert at FRONT
    # - Normal callees: append to END
    
    high_priority = []
    normal_priority = []
    
    for callee in neighbors_to_add:
        # Check complexity from call graph
        callee_node = call_graph_data.get("nodes", {}).get(callee, {})
        complexity = callee_node.get("complexity_score", 0)
        
        if complexity > 5:
            high_priority.append(callee)
        else:
            normal_priority.append(callee)
    
    # Build new queue: high priority at front, normal at end
    new_queue = high_priority + queue + normal_priority
    
    # Also check called_by for reverse traversal (only from entry points)
    if state["nodes"].get(qualified_name, {}).get("is_entry_point") and current_depth == 0:
        relationships_reverse = graph_lookup(qualified_name, call_graph_data, "called_by")
        called_by = relationships_reverse["called_by"]
        
        for caller in called_by:
            if caller not in visited and caller not in new_queue:
                new_queue.append(caller)
                new_depth_map[caller] = 1
                neighbors_to_add.append(caller)
    
    # Log
    if neighbors_to_add:
        logger.debug(f"Expanded {qualified_name}: added {len(neighbors_to_add)} neighbors")
    
    traversal_log_entry = {
        "step": state["step_count"],
        "action": "expand",
        "node": qualified_name,
        "neighbors_added": neighbors_to_add,
        "queue_new_size": len(new_queue),
        "timestamp": datetime.now().isoformat()
    }
    
    return {
        "queue": new_queue,
        "depth_map": new_depth_map,
        "traversal_log": state["traversal_log"] + [traversal_log_entry]
    }
