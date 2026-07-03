"""
agent/tools/graph_lookup.py — Call Graph Lookup Tool

Queries Phase 2 call graph data for function relationships.
"""

from typing import Literal


def graph_lookup(
    qualified_name: str,
    call_graph_data: dict,
    lookup_type: Literal["calls", "called_by", "both"] = "both"
) -> dict:
    """
    Looks up call relationships for a function from the Phase 2 call graph.
    
    Args:
        qualified_name: e.g., "UserService.get_user"
        call_graph_data: Full call_graph.json loaded into memory
        lookup_type: "calls", "called_by", or "both"
    
    Returns:
        Dict with:
        {
            "calls": ["func1", "func2", ...],
            "called_by": ["func3", "func4", ...]
        }
    """
    result = {"calls": [], "called_by": []}
    
    # Get adjacency maps from call graph
    adjacency = call_graph_data.get("adjacency", {})
    reverse_adjacency = call_graph_data.get("reverse_adjacency", {})
    
    # Look up calls (what this function calls)
    if lookup_type in ["calls", "both"]:
        calls = adjacency.get(qualified_name, [])
        # Filter out external (unresolved) calls
        result["calls"] = [c for c in calls if not c.startswith("?.")]
    
    # Look up called_by (what calls this function)
    if lookup_type in ["called_by", "both"]:
        called_by = reverse_adjacency.get(qualified_name, [])
        # Filter out external calls
        result["called_by"] = [c for c in called_by if not c.startswith("?.")]
    
    return result


def get_node_from_call_graph(qualified_name: str, call_graph_data: dict) -> dict:
    """
    Get node data from call graph.
    
    Args:
        qualified_name: Function qualified name
        call_graph_data: Full call_graph.json
    
    Returns:
        Node dict or empty dict if not found
    """
    nodes = call_graph_data.get("nodes", {})
    return nodes.get(qualified_name, {})


def get_all_functions(call_graph_data: dict) -> list[str]:
    """
    Get all function qualified names from call graph.
    
    Args:
        call_graph_data: Full call_graph.json
    
    Returns:
        List of qualified names
    """
    nodes = call_graph_data.get("nodes", {})
    return list(nodes.keys())


def get_hub_nodes(call_graph_data: dict, threshold: int = 5) -> list[tuple[str, int]]:
    """
    Get hub nodes (functions called by many others).
    
    Args:
        call_graph_data: Full call_graph.json
        threshold: Minimum called_by_count to be considered a hub
    
    Returns:
        List of (qualified_name, called_by_count) tuples, sorted by count descending
    """
    nodes = call_graph_data.get("nodes", {})
    reverse_adjacency = call_graph_data.get("reverse_adjacency", {})
    
    hubs = []
    for qualified_name in nodes.keys():
        called_by_count = len(reverse_adjacency.get(qualified_name, []))
        if called_by_count >= threshold:
            hubs.append((qualified_name, called_by_count))
    
    # Sort by count descending
    hubs.sort(key=lambda x: x[1], reverse=True)
    return hubs


# Test function
if __name__ == "__main__":
    import json
    from pathlib import Path
    
    print("Testing graph_lookup...")
    print("=" * 60)
    
    # Load test call graph
    test_call_graph_path = Path(__file__).parent.parent.parent / "data" / "repos" / "pallets__itsdangerous" / "parsed" / "call_graph.json"
    
    if not test_call_graph_path.exists():
        print("✗ Test call graph not found. Run Phase 2 first on pallets/itsdangerous")
        exit(1)
    
    with open(test_call_graph_path, "r") as f:
        call_graph_data = json.load(f)
    
    print(f"Loaded call graph with {len(call_graph_data.get('nodes', {}))} nodes")
    print()
    
    # Test graph_lookup
    test_functions = [
        "Signer.sign",
        "TimestampSigner.unsign",
        "URLSafeSerializer"
    ]
    
    for qualified_name in test_functions:
        print(f"Looking up: {qualified_name}")
        result = graph_lookup(qualified_name, call_graph_data, "both")
        print(f"  Calls: {result['calls'][:3]}{'...' if len(result['calls']) > 3 else ''}")
        print(f"  Called by: {result['called_by'][:3]}{'...' if len(result['called_by']) > 3 else ''}")
        print()
    
    # Test hub nodes
    print("Hub nodes (called by >= 5 others):")
    hubs = get_hub_nodes(call_graph_data, threshold=3)
    for qualified_name, count in hubs[:5]:
        print(f"  {qualified_name}: called by {count} functions")
    
    print("\n✓ graph_lookup tests complete!")
