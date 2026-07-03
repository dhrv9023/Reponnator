"""
agent/traversal_orchestrator.py — Traversal Orchestrator (Public API)

Main entry point for Phase 5 call graph traversal.
Phase 6 and main.py call this only.
"""

import time
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TraversalOrchestrator:
    """
    Public API for Phase 5 call graph traversal.
    
    Usage:
        orchestrator = TraversalOrchestrator("pallets", "itsdangerous")
        graph = orchestrator.traverse(max_depth=6, llm_budget=30)
    """
    
    def __init__(self, repo_owner: str, repo_name: str):
        """
        Initialize traversal orchestrator.
        
        Args:
            repo_owner: GitHub repo owner
            repo_name: GitHub repo name
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        
        # Get repo folder
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import DATA_DIR
        
        self.repo_folder = Path(DATA_DIR) / f"{repo_owner}__{repo_name}"
        
        # Verify Phase 2 and Phase 3 complete
        self._verify_prerequisites()
        
        # Build graph
        from .graph_builder import build_traversal_graph
        self.graph = build_traversal_graph()
        
        logger.info(f"TraversalOrchestrator initialized for {repo_owner}/{repo_name}")
    
    def _verify_prerequisites(self):
        """Verify Phase 2 and Phase 3 outputs exist."""
        # Check Phase 2
        parse_manifest = self.repo_folder / "parsed" / "parse_manifest.json"
        if not parse_manifest.exists():
            raise FileNotFoundError(
                f"Phase 2 not complete. Run: python main.py parse https://github.com/{self.repo_owner}/{self.repo_name}"
            )
        
        # Check Phase 3
        chunk_manifest = self.repo_folder / "chunks" / "chunk_manifest.json"
        if not chunk_manifest.exists():
            raise FileNotFoundError(
                f"Phase 3 not complete. Run: python main.py embed https://github.com/{self.repo_owner}/{self.repo_name}"
            )
        
        logger.info("✓ Prerequisites verified (Phase 2 and 3 complete)")
    
    def traverse(
        self,
        max_depth: int = 6,
        llm_budget: int = 30,
        force_retraverse: bool = False
    ):
        """
        Run the call graph traversal.
        
        Args:
            max_depth: Maximum BFS depth from entry points
            llm_budget: Maximum LLM analysis calls
            force_retraverse: If True, re-traverse even if already done
        
        Returns:
            TraversalGraph dataclass
        """
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import TRAVERSAL_OUTPUT_DIR
        from .traversal_output import build_traversal_graph, save_traversal_output
        
        # Check if already traversed
        traversal_manifest = self.repo_folder / TRAVERSAL_OUTPUT_DIR / "traversal_manifest.json"
        if traversal_manifest.exists() and not force_retraverse:
            logger.info("Already traversed. Use --force to redo.")
            return self.get_traversal_graph()
        
        logger.info(f"🔍 Traversing {self.repo_owner}/{self.repo_name} call graph...")
        logger.info(f"   Max depth: {max_depth}, LLM budget: {llm_budget}")
        
        # Build initial state
        initial_state = {
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "queue": [],
            "visited": [],
            "nodes": {},
            "edges": [],
            "node_analyses": {},
            "current_node_name": "",
            "depth_map": {},
            "max_depth": max_depth,
            "entry_points": [],
            "llm_calls_made": 0,
            "llm_budget": llm_budget,
            "call_graph_data": {},
            "dependency_map_data": {},
            "status": "initializing",
            "errors": [],
            "traversal_log": [],
            "messages": [],
            "start_time": time.time(),
            "step_count": 0
        }
        
        # Run the graph with streaming
        config = {
            "configurable": {
                "thread_id": f"{self.repo_owner}__{self.repo_name}__{int(time.time())}"
            },
            "recursion_limit": 1000
        }
        
        print(f"\n🔍 Traversing {self.repo_owner}/{self.repo_name} call graph...")
        print("=" * 60)
        
        # Stream execution with progress
        final_state = None
        for step in self.graph.stream(initial_state, config=config):
            node_name = list(step.keys())[0]
            node_output = step[node_name]
            
            # Print progress based on node
            if "pick_next" in step:
                visited = len(node_output.get("visited", []))
                queue = len(node_output.get("queue", []))
                current = node_output.get("current_node_name", "")
                print(f"\r  [{visited} visited | {queue} queued] Processing: {current[:50]:<50}", end="", flush=True)
            
            if "analyze_node" in step:
                llm_calls = node_output.get("llm_calls_made", 0)
                current = step.get("pick_next", {}).get("current_node_name", "")
                if llm_calls:
                    print(f"\n  🤖 Analyzed: {current[:40]:<40} (LLM call #{llm_calls})")
            
            final_state = node_output
        
        print("\n" + "=" * 60)
        
        # Get final state from graph
        if final_state is None:
            # Fallback: get state from checkpointer
            final_state = self.graph.get_state(config).values
        
        # Build + save output
        traversal_graph = build_traversal_graph(final_state)
        save_traversal_output(traversal_graph, final_state, self.repo_folder)
        
        # Print completion summary
        self._print_summary(traversal_graph)
        
        return traversal_graph
    
    def _print_summary(self, graph):
        """Print traversal completion summary."""
        print("\n╔══════════════════════════════════════════════════════════╗")
        print("║  CodeAutopsy — Traversal Complete                        ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print(f"║  Repo            : {self.repo_owner}/{self.repo_name:<30} ║")
        print(f"║  Nodes traversed : {graph.total_nodes_reachable:<35} ║")
        print(f"║  Edges mapped    : {graph.total_edges:<35} ║")
        print(f"║  Max depth       : {graph.max_depth_reached:<35} ║")
        print(f"║  LLM analyses    : {graph.llm_calls_made:<35} ║")
        print(f"║  Hub nodes       : {', '.join(graph.hub_nodes[:3]):<35} ║")
        print(f"║  Layers detected : {', '.join(list(graph.architectural_layers.keys())[:4]):<35} ║")
        print(f"║  Orphan nodes    : {len(graph.orphan_nodes):<35} ║")
        print(f"║  Duration        : {graph.traversal_duration_seconds:.1f}s{' ' * 30} ║")
        print(f"║  Saved to        : data/repos/{self.repo_owner}__{self.repo_name}/traversal/{' ' * 5} ║")
        print("╚══════════════════════════════════════════════════════════╝\n")
    
    def get_node_analysis(self, qualified_name: str) -> str:
        """
        Get LLM analysis for a specific node.
        
        Args:
            qualified_name: Function qualified name
        
        Returns:
            Analysis text or empty string if not analyzed
        """
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import TRAVERSAL_OUTPUT_DIR
        
        node_analyses_path = self.repo_folder / TRAVERSAL_OUTPUT_DIR / "node_analyses.json"
        if not node_analyses_path.exists():
            return ""
        
        with open(node_analyses_path, "r") as f:
            analyses = json.load(f)
        
        return analyses.get(qualified_name, "")
    
    def get_traversal_graph(self):
        """
        Load and return existing traversal graph.
        
        Returns:
            TraversalGraph dataclass
        """
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import TRAVERSAL_OUTPUT_DIR
        from agent import TraversalGraph
        
        traversal_graph_path = self.repo_folder / TRAVERSAL_OUTPUT_DIR / "traversal_graph.json"
        if not traversal_graph_path.exists():
            raise FileNotFoundError(
                f"Traversal graph not found. Run: orchestrator.traverse()"
            )
        
        with open(traversal_graph_path, "r") as f:
            data = json.load(f)
        
        return TraversalGraph(
            repo_owner=data["repo_owner"],
            repo_name=data["repo_name"],
            traversal_timestamp=data["traversal_timestamp"],
            nodes=data["nodes"],
            edges=data["edges"],
            entry_points=data["entry_points"],
            hub_nodes=data["hub_nodes"],
            orphan_nodes=data["orphan_nodes"],
            architectural_layers=data["architectural_layers"],
            total_nodes_reachable=data["stats"]["total_nodes"],
            total_nodes_analyzed=sum(
                1 for node in data["nodes"].values()
                if node.get("was_analyzed_by_llm", False)
            ),
            total_edges=data["stats"]["total_edges"],
            max_depth_reached=data["stats"]["max_depth_reached"],
            traversal_duration_seconds=data["stats"]["traversal_duration_seconds"],
            llm_calls_made=data["stats"]["llm_calls_made"]
        )
    
    def get_subgraph(self, root_node: str, depth: int = 2):
        """
        Get subset of graph reachable from root_node within given depth.
        
        Used by frontend for focused views.
        
        Args:
            root_node: Starting qualified name
            depth: Maximum depth to traverse
        
        Returns:
            TraversalGraph with subset of nodes/edges
        """
        # Load full graph
        full_graph = self.get_traversal_graph()
        
        # BFS from root_node
        visited = set()
        queue = [(root_node, 0)]
        subgraph_nodes = {}
        subgraph_edges = []
        
        while queue:
            current, current_depth = queue.pop(0)
            
            if current in visited or current_depth > depth:
                continue
            
            visited.add(current)
            
            # Add node
            if current in full_graph.nodes:
                subgraph_nodes[current] = full_graph.nodes[current]
            
            # Add edges and queue neighbors
            for edge in full_graph.edges:
                if edge["from_node"] == current:
                    subgraph_edges.append(edge)
                    queue.append((edge["to_node"], current_depth + 1))
        
        # Build subgraph
        from agent import TraversalGraph
        
        return TraversalGraph(
            repo_owner=full_graph.repo_owner,
            repo_name=full_graph.repo_name,
            traversal_timestamp=full_graph.traversal_timestamp,
            nodes=subgraph_nodes,
            edges=subgraph_edges,
            entry_points=[root_node],
            hub_nodes=[],
            orphan_nodes=[],
            architectural_layers={},
            total_nodes_reachable=len(subgraph_nodes),
            total_nodes_analyzed=0,
            total_edges=len(subgraph_edges),
            max_depth_reached=depth,
            traversal_duration_seconds=0,
            llm_calls_made=0
        )


# Test function
if __name__ == "__main__":
    import sys
    
    print("Testing TraversalOrchestrator...")
    print("=" * 60)
    
    # Test with itsdangerous repo
    repo_owner = "pallets"
    repo_name = "itsdangerous"
    
    try:
        orchestrator = TraversalOrchestrator(repo_owner, repo_name)
        print(f"✓ Orchestrator initialized for {repo_owner}/{repo_name}")
        
        # Run traversal with small budget for testing
        graph = orchestrator.traverse(max_depth=3, llm_budget=5, force_retraverse=True)
        
        print(f"\n✓ Traversal complete!")
        print(f"  Nodes: {graph.total_nodes_reachable}")
        print(f"  Edges: {graph.total_edges}")
        print(f"  LLM calls: {graph.llm_calls_made}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
