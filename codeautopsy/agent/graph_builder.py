"""
agent/graph_builder.py — LangGraph StateGraph Builder

Constructs the LangGraph StateGraph for call graph traversal.
"""

import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .nodes import (
    initialize,
    pick_next,
    fetch_node,
    analyze_node,
    expand_neighbors,
    check_termination,
    finalize
)
from .nodes.check_termination import should_continue

logger = logging.getLogger(__name__)


def build_traversal_graph():
    """
    Constructs the LangGraph StateGraph for call graph traversal.
    
    Graph structure:
    
    initialize
        ↓
    pick_next ←─────────────────────────────────┐
        ↓ (has node)          ↓ (queue empty)    │
    fetch_node           finalize                │
        ↓                    ↓                   │
    analyze_node            END                  │
        ↓                                        │
    expand_neighbors                             │
        ↓                                        │
    check_termination ──(continue)───────────────┘
        ↓ (done)
    finalize
        ↓
    END
    
    Returns:
        Compiled LangGraph
    """
    logger.info("Building LangGraph StateGraph...")
    
    # Create StateGraph
    graph = StateGraph(AgentState)
    
    # Add all nodes
    graph.add_node("initialize", initialize)
    graph.add_node("pick_next", pick_next)
    graph.add_node("fetch_node", fetch_node)
    graph.add_node("analyze_node", analyze_node)
    graph.add_node("expand_neighbors", expand_neighbors)
    graph.add_node("check_termination", check_termination)
    graph.add_node("finalize", finalize)
    
    # Set entry point
    graph.set_entry_point("initialize")
    
    # Linear edges (always happen)
    graph.add_edge("initialize", "pick_next")
    graph.add_edge("fetch_node", "analyze_node")
    graph.add_edge("analyze_node", "expand_neighbors")
    graph.add_edge("expand_neighbors", "check_termination")
    
    # Conditional: pick_next → fetch_node or finalize
    def route_from_pick(state: dict) -> str:
        """Route from pick_next based on status."""
        if state.get("status") == "complete":
            return "finalize"
        if not state.get("queue"):
            return "finalize"
        # Check if current node already visited (race condition guard)
        current = state.get("current_node_name", "")
        visited = state.get("visited", [])
        if current in visited[:-1]:  # Allow last item (just added)
            return "pick_next"
        return "fetch_node"
    
    graph.add_conditional_edges(
        "pick_next",
        route_from_pick,
        {
            "fetch_node": "fetch_node",
            "pick_next": "pick_next",
            "finalize": "finalize"
        }
    )
    
    # Conditional: check_termination → pick_next or finalize
    graph.add_conditional_edges(
        "check_termination",
        should_continue,
        {
            "pick_next": "pick_next",
            "finalize": "finalize"
        }
    )
    
    # Terminal edge
    graph.add_edge("finalize", END)
    
    # Compile with memory checkpointing
    memory = MemorySaver()
    compiled_graph = graph.compile(checkpointer=memory)
    
    logger.info("✓ LangGraph StateGraph built successfully")
    
    return compiled_graph


# Test function
if __name__ == "__main__":
    print("Building LangGraph StateGraph...")
    print("=" * 60)
    
    try:
        graph = build_traversal_graph()
        print("✓ Graph built successfully!")
        print(f"  Nodes: initialize, pick_next, fetch_node, analyze_node, expand_neighbors, check_termination, finalize")
        print(f"  Entry point: initialize")
        print(f"  Terminal: END")
    except Exception as e:
        print(f"✗ Failed to build graph: {e}")
        import traceback
        traceback.print_exc()
