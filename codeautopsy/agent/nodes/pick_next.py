"""
agent/nodes/pick_next.py — Pick Next Node

Dequeues next node to process from BFS queue.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def pick_next(state: dict) -> dict:
    """
    Pick the next node to process from the BFS queue.
    
    Args:
        state: AgentState dict
    
    Returns:
        Dict with updated queue, current_node_name, step_count
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from config import MAX_TRAVERSAL_NODES
    
    queue = state["queue"]
    visited = state["visited"]
    step_count = state["step_count"]
    
    # Check termination conditions
    if not queue:
        logger.info("Queue empty, traversal complete")
        return {"status": "complete"}
    
    if len(visited) >= MAX_TRAVERSAL_NODES:
        logger.warning(f"Max nodes reached ({MAX_TRAVERSAL_NODES}), stopping traversal")
        return {"status": "complete"}
    
    # All items in queue already visited
    if all(item in visited for item in queue):
        logger.info("All queued nodes already visited, traversal complete")
        return {"status": "complete", "queue": []}
    
    # Pop first item from queue (BFS = FIFO)
    current = queue[0]
    new_queue = queue[1:]
    
    # Skip if already visited
    while current in visited and len(new_queue) > 0:
        current = new_queue[0]
        new_queue = new_queue[1:]
    
    if current in visited:
        logger.info("All remaining nodes visited, traversal complete")
        return {"status": "complete", "queue": []}
    
    # Log step
    traversal_log_entry = {
        "step": step_count + 1,
        "action": "pick_next",
        "node": current,
        "depth": state["depth_map"].get(current, "?"),
        "queue_remaining": len(new_queue),
        "visited_count": len(visited),
        "timestamp": datetime.now().isoformat()
    }
    
    logger.debug(f"Picked node: {current} (depth={state['depth_map'].get(current, '?')})")
    
    return {
        "current_node_name": current,
        "queue": new_queue,
        "step_count": step_count + 1,
        "traversal_log": state["traversal_log"] + [traversal_log_entry]
    }
