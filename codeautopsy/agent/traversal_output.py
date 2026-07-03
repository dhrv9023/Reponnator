"""
agent/traversal_output.py — Traversal Output Builder

Builds final output files from completed AgentState.
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def build_traversal_graph(state: dict):
    """
    Convert AgentState to TraversalGraph dataclass.
    
    Args:
        state: Final AgentState dict
    
    Returns:
        TraversalGraph dataclass
    """
    from agent import TraversalGraph
    
    # Build architectural layers dict
    layers = {}
    for qualified_name, node in state["nodes"].items():
        layer = node["architectural_layer"]
        if layer not in layers:
            layers[layer] = []
        layers[layer].append(qualified_name)
    
    # Get hub nodes
    hub_nodes = [
        qn for qn, node in state["nodes"].items()
        if node.get("is_hub", False)
    ]
    
    # Get orphan nodes
    orphan_nodes = [
        qn for qn, node in state["nodes"].items()
        if node.get("is_orphan", False)
    ]
    
    # Calculate max depth
    max_depth = max(
        node["depth_from_entry"]
        for node in state["nodes"].values()
    ) if state["nodes"] else 0
    
    # Count analyzed nodes
    total_analyzed = sum(
        1 for node in state["nodes"].values()
        if node.get("was_analyzed_by_llm", False)
    )
    
    # Calculate duration
    duration = time.time() - state["start_time"]
    
    return TraversalGraph(
        repo_owner=state["repo_owner"],
        repo_name=state["repo_name"],
        traversal_timestamp=datetime.now().isoformat(),
        nodes=state["nodes"],
        edges=state["edges"],
        entry_points=state["entry_points"],
        hub_nodes=hub_nodes,
        orphan_nodes=orphan_nodes,
        architectural_layers=layers,
        total_nodes_reachable=len(state["nodes"]),
        total_nodes_analyzed=total_analyzed,
        total_edges=len(state["edges"]),
        max_depth_reached=max_depth,
        traversal_duration_seconds=duration,
        llm_calls_made=state["llm_calls_made"]
    )


def save_traversal_output(
    graph,
    state: dict,
    repo_folder: Path
):
    """
    Save all traversal output files.
    
    Args:
        graph: TraversalGraph dataclass
        state: Final AgentState dict
        repo_folder: Path to repo folder
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import TRAVERSAL_OUTPUT_DIR, CODEAUTOPSY_VERSION
    from agent import TraversalManifest
    
    output_dir = repo_folder / TRAVERSAL_OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)
    
    logger.info(f"Saving traversal output to {output_dir}")
    
    # 1. Save main graph (Phase 6 input)
    traversal_graph_path = output_dir / "traversal_graph.json"
    with open(traversal_graph_path, "w") as f:
        json.dump({
            "repo_owner": graph.repo_owner,
            "repo_name": graph.repo_name,
            "traversal_timestamp": graph.traversal_timestamp,
            "nodes": graph.nodes,
            "edges": graph.edges,
            "entry_points": graph.entry_points,
            "hub_nodes": graph.hub_nodes,
            "orphan_nodes": graph.orphan_nodes,
            "architectural_layers": graph.architectural_layers,
            "stats": {
                "total_nodes": graph.total_nodes_reachable,
                "total_edges": graph.total_edges,
                "max_depth_reached": graph.max_depth_reached,
                "llm_calls_made": graph.llm_calls_made,
                "traversal_duration_seconds": graph.traversal_duration_seconds
            }
        }, f, indent=2)
    
    logger.info(f"✓ Saved traversal_graph.json ({len(graph.nodes)} nodes, {len(graph.edges)} edges)")
    
    # 2. Save per-node LLM analyses
    node_analyses_path = output_dir / "node_analyses.json"
    with open(node_analyses_path, "w") as f:
        json.dump(state["node_analyses"], f, indent=2)
    
    logger.info(f"✓ Saved node_analyses.json ({len(state['node_analyses'])} analyses)")
    
    # 3. Save traversal log (debugging + transparency)
    traversal_log_path = output_dir / "traversal_log.jsonl"
    with open(traversal_log_path, "w") as f:
        for log_entry in state["traversal_log"]:
            f.write(json.dumps(log_entry) + "\n")
    
    logger.info(f"✓ Saved traversal_log.jsonl ({len(state['traversal_log'])} entries)")
    
    # 4. Save manifest
    manifest = TraversalManifest(
        codeautopsy_version=CODEAUTOPSY_VERSION,
        traversal_timestamp=graph.traversal_timestamp,
        repo_owner=graph.repo_owner,
        repo_name=graph.repo_name,
        entry_points_used=graph.entry_points,
        total_nodes=graph.total_nodes_reachable,
        total_edges=graph.total_edges,
        llm_calls_made=graph.llm_calls_made,
        traversal_duration_seconds=graph.traversal_duration_seconds,
        max_depth=graph.max_depth_reached,
        hub_nodes=graph.hub_nodes,
        architectural_layers_detected=list(graph.architectural_layers.keys()),
        errors=state.get("errors", [])
    )
    
    manifest_path = output_dir / "traversal_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({
            "codeautopsy_version": manifest.codeautopsy_version,
            "traversal_timestamp": manifest.traversal_timestamp,
            "repo_owner": manifest.repo_owner,
            "repo_name": manifest.repo_name,
            "entry_points_used": manifest.entry_points_used,
            "total_nodes": manifest.total_nodes,
            "total_edges": manifest.total_edges,
            "llm_calls_made": manifest.llm_calls_made,
            "traversal_duration_seconds": manifest.traversal_duration_seconds,
            "max_depth": manifest.max_depth,
            "hub_nodes": manifest.hub_nodes,
            "architectural_layers_detected": manifest.architectural_layers_detected,
            "errors": manifest.errors
        }, f, indent=2)
    
    logger.info(f"✓ Saved traversal_manifest.json")
    
    # 5. Build Mermaid preview
    mermaid_preview = build_mermaid_preview(graph)
    mermaid_path = output_dir / "mermaid_preview.md"
    with open(mermaid_path, "w") as f:
        f.write(mermaid_preview)
    
    logger.info(f"✓ Saved mermaid_preview.md")


def build_mermaid_preview(graph) -> str:
    """
    Build a SIMPLIFIED Mermaid diagram string for quick preview.
    
    Full Mermaid generation happens in Phase 6.
    This preview: top 20 nodes by called_by_count only, grouped by layer.
    
    Args:
        graph: TraversalGraph dataclass
    
    Returns:
        Mermaid diagram string
    """
    # Get top 20 nodes by called_by_count
    nodes_by_importance = sorted(
        graph.nodes.items(),
        key=lambda x: x[1]["called_by_count"],
        reverse=True
    )[:20]
    
    # Group by layer
    layers = {}
    for qualified_name, node in nodes_by_importance:
        layer = node["architectural_layer"]
        if layer not in layers:
            layers[layer] = []
        layers[layer].append((qualified_name, node))
    
    # Build Mermaid
    mermaid = "```mermaid\ngraph TD\n"
    
    # Add subgraphs for each layer
    node_ids = {}
    node_counter = 1
    
    for layer, nodes in layers.items():
        mermaid += f'  subgraph {layer}["{layer.upper()} Layer"]\n'
        for qualified_name, node in nodes:
            node_id = f"node{node_counter}"
            node_ids[qualified_name] = node_id
            node_counter += 1
            
            # Truncate long names
            display_name = qualified_name.split(".")[-1]
            if len(display_name) > 20:
                display_name = display_name[:17] + "..."
            
            mermaid += f'    {node_id}["{display_name}"]\n'
        mermaid += "  end\n"
    
    # Add edges (only between nodes in preview)
    for edge in graph.edges:
        from_node = edge["from_node"]
        to_node = edge["to_node"]
        
        if from_node in node_ids and to_node in node_ids:
            from_id = node_ids[from_node]
            to_id = node_ids[to_node]
            mermaid += f"  {from_id} --> {to_id}\n"
    
    mermaid += "```\n"
    
    return mermaid
