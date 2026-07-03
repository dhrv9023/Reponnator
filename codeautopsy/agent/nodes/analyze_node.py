"""
agent/nodes/analyze_node.py — Analyze Node with LLM

Selectively calls LLM to analyze important nodes.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def analyze_node(state: dict) -> dict:
    """
    Analyze the current node with LLM (if eligible).
    
    Only analyzes nodes that meet eligibility criteria to stay within LLM budget.
    
    Args:
        state: AgentState dict
    
    Returns:
        Dict with updated nodes, node_analyses, llm_calls_made
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from config import (
        ANALYZE_ENTRY_POINTS,
        ANALYZE_HUBS,
        ANALYZE_DEPTH_THRESHOLD,
        ANALYZE_CROSS_LAYER,
        MIN_COMPLEXITY_FOR_ANALYSIS
    )
    from rag.llm_client import LLMClient
    from agent.tools.chunk_lookup import chunk_lookup
    
    qualified_name = state["current_node_name"]
    nodes = state["nodes"]
    node = nodes.get(qualified_name)
    
    if not node:
        logger.warning(f"Node not found in state: {qualified_name}")
        return {}
    
    # Check eligibility
    depth = node["depth_from_entry"]
    complexity = node["complexity_score"]
    is_entry = node["is_entry_point"]
    is_cross_layer = any(
        edge["is_cross_layer"]
        for edge in state["edges"]
        if edge["from_node"] == qualified_name
    )
    
    eligible = (
        (ANALYZE_ENTRY_POINTS and is_entry) or
        (ANALYZE_DEPTH_THRESHOLD and depth <= ANALYZE_DEPTH_THRESHOLD) or
        (ANALYZE_CROSS_LAYER and is_cross_layer) or
        (complexity >= MIN_COMPLEXITY_FOR_ANALYSIS)
    ) and state["llm_calls_made"] < state["llm_budget"]
    
    if not eligible:
        logger.debug(f"Node not eligible for LLM analysis: {qualified_name}")
        return {}
    
    # Get chunk content
    chunk_data = chunk_lookup(
        qualified_name,
        state["repo_owner"],
        state["repo_name"]
    )
    
    if not chunk_data:
        logger.warning(f"No chunk data for analysis: {qualified_name}")
        return {}
    
    content = chunk_data["content"]
    if len(content) > 1500:
        content = content[:1500] + "..."
    
    # Build LLM prompt
    system_prompt = "You are analyzing a single function from a GitHub repository."
    
    user_prompt = f"""Repository: {state['repo_owner']}/{state['repo_name']}
Function: {qualified_name}
File: {node['file_path']}
Language: {node['language']}
Architectural Layer: {node['architectural_layer']}
Called by {node['called_by_count']} other functions.
Calls {node['calls_count']} other functions.
Complexity score: {complexity}

Function content:
{content}

Analyze this function in 3-4 sentences. Cover:
- What this function does (its purpose)
- What architectural role it plays
- Any notable design pattern you can identify
- Why it is placed at this layer

Be specific and reference actual code details. Do not be generic.
Format: Plain prose, no bullet points, no headers. Max 4 sentences."""
    
    # Call LLM
    try:
        llm_client = LLMClient()
        analysis = llm_client.generate(
            system_prompt,
            user_prompt,
            max_tokens=200,
            temperature=0.1
        )
        
        logger.info(f"✓ Analyzed: {qualified_name}")
        
        # Extract role description and design pattern
        role_description = analysis.strip()
        design_pattern = extract_design_pattern(analysis)
        
        # Update node
        updated_nodes = nodes.copy()
        updated_nodes[qualified_name]["role_description"] = role_description
        updated_nodes[qualified_name]["design_pattern"] = design_pattern
        updated_nodes[qualified_name]["was_analyzed_by_llm"] = True
        
        # Update node_analyses
        node_analyses = state["node_analyses"].copy()
        node_analyses[qualified_name] = analysis
        
        return {
            "nodes": updated_nodes,
            "node_analyses": node_analyses,
            "llm_calls_made": state["llm_calls_made"] + 1
        }
    
    except Exception as e:
        logger.error(f"LLM analysis failed for {qualified_name}: {e}")
        return {}


def extract_design_pattern(analysis: str) -> str:
    """
    Extract design pattern from LLM analysis.
    
    Args:
        analysis: LLM-generated analysis text
    
    Returns:
        Pattern name or None
    """
    patterns = [
        "Singleton", "Factory", "Repository", "Strategy",
        "Observer", "Decorator", "Facade", "Proxy",
        "Command", "Builder", "Adapter", "Bridge"
    ]
    
    analysis_lower = analysis.lower()
    
    for pattern in patterns:
        if pattern.lower() in analysis_lower:
            return pattern
    
    return None
