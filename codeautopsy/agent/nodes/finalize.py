"""
agent/nodes/finalize.py — Finalize Traversal

Computes final graph properties and marks status complete.
"""

import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def finalize(state: dict) -> dict:
    """
    Finalize the traversal.
    
    - Detect hub nodes
    - Detect orphan nodes
    - Build architectural layers dict
    - Calculate final stats
    
    Args:
        state: AgentState dict
    
    Returns:
        Dict with finalized state
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from config import HUB_NODE_THRESHOLD
    
    nodes = state["nodes"]
    edges = state["edges"]
    
    logger.info("Finalizing traversal...")
    
    # 1. Detect hub nodes
    hub_nodes = []
    for qualified_name, node in nodes.items():
        if node["called_by_count"] >= HUB_NODE_THRESHOLD:
            node["is_hub"] = True
            hub_nodes.append((qualified_name, node["called_by_count"]))
    
    # Sort by called_by_count descending, take top 10
    hub_nodes.sort(key=lambda x: x[1], reverse=True)
    hub_nodes = [qn for qn, _ in hub_nodes[:10]]
    
    logger.info(f"Detected {len(hub_nodes)} hub nodes")
    
    # 2. Detect orphan nodes
    orphan_nodes = []
    for qualified_name, node in nodes.items():
        if node["called_by_count"] == 0 and not node["is_entry_point"]:
            node["is_orphan"] = True
            orphan_nodes.append(qualified_name)
    
    logger.info(f"Detected {len(orphan_nodes)} orphan nodes")
    
    # 3. Build architectural layers dict
    layers = {}
    for qualified_name, node in nodes.items():
        layer = node["architectural_layer"]
        if layer not in layers:
            layers[layer] = []
        layers[layer].append(qualified_name)
    
    logger.info(f"Architectural layers: {list(layers.keys())}")
    
    # 4. Analyze top hub nodes that weren't analyzed yet
    # (If LLM budget allows)
    if state["llm_calls_made"] < state["llm_budget"]:
        from agent.nodes.analyze_node import analyze_node as analyze_node_func
        from agent.tools.chunk_lookup import chunk_lookup
        from rag.llm_client import LLMClient
        
        for hub_qn in hub_nodes[:5]:
            if not nodes[hub_qn]["was_analyzed_by_llm"]:
                if state["llm_calls_made"] >= state["llm_budget"]:
                    break
                
                logger.info(f"Analyzing hub node: {hub_qn}")
                
                # Inline analysis for hub nodes
                try:
                    chunk_data = chunk_lookup(
                        hub_qn,
                        state["repo_owner"],
                        state["repo_name"]
                    )
                    
                    if chunk_data:
                        content = chunk_data["content"][:1500]
                        
                        llm_client = LLMClient()
                        analysis = llm_client.generate(
                            "You are analyzing a hub function (called by many others) from a GitHub repository.",
                            f"""Repository: {state['repo_owner']}/{state['repo_name']}
Function: {hub_qn}
File: {nodes[hub_qn]['file_path']}
This is a HUB node (called by {nodes[hub_qn]['called_by_count']} functions).

Function content:
{content}

Analyze this hub function in 3-4 sentences. Focus on why it's so widely used.""",
                            max_tokens=200,
                            temperature=0.1
                        )
                        
                        nodes[hub_qn]["role_description"] = analysis.strip()
                        nodes[hub_qn]["was_analyzed_by_llm"] = True
                        state["llm_calls_made"] += 1
                        
                        logger.info(f"✓ Analyzed hub: {hub_qn}")
                
                except Exception as e:
                    logger.error(f"Failed to analyze hub {hub_qn}: {e}")
    
    # 5. Calculate final stats
    total_duration = time.time() - state["start_time"]
    
    # Log completion
    traversal_log_entry = {
        "step": state["step_count"],
        "action": "finalize",
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "hub_nodes": hub_nodes,
        "orphan_nodes_count": len(orphan_nodes),
        "duration": total_duration,
        "timestamp": datetime.now().isoformat()
    }
    
    logger.info(f"Traversal complete: {len(nodes)} nodes, {len(edges)} edges, {total_duration:.1f}s")
    
    return {
        "nodes": nodes,
        "status": "complete",
        "traversal_log": state["traversal_log"] + [traversal_log_entry]
    }
