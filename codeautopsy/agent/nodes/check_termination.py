"""
agent/nodes/check_termination.py — Check Termination

Determines if traversal should continue or stop.
"""

import logging

logger = logging.getLogger(__name__)


def check_termination(state: dict) -> dict:
    """
    Check if traversal should terminate.
    
    This node has no logic — it just passes state through.
    The routing decision is made in the EDGE function (should_continue).
    
    Args:
        state: AgentState dict
    
    Returns:
        Empty dict (no state change)
    """
    # No-op node — routing happens in graph_builder.py
    return {}


def should_continue(state: dict) -> str:
    """
    Routing function for check_termination node.
    
    Determines whether to continue traversal or finalize.
    
    Args:
        state: AgentState dict
    
    Returns:
        "finalize" or "pick_next"
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from config import MAX_TRAVERSAL_NODES
    
    # Check status
    if state["status"] == "complete":
        return "finalize"
    
    # Check queue
    if not state["queue"]:
        return "finalize"
    
    # Check node limit
    if len(state["visited"]) >= MAX_TRAVERSAL_NODES:
        return "finalize"
    
    # Safety: prevent infinite loop
    if state["step_count"] > MAX_TRAVERSAL_NODES * 3:
        logger.warning("Step count exceeded safety limit, finalizing")
        return "finalize"
    
    # Continue traversal
    return "pick_next"
