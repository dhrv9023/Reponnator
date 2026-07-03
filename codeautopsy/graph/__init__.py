"""
graph/knowledge_graph.py — In-Memory Knowledge Graph for CodeAutopsy

Loads the call graph produced by Phase 2 (call_graph.json) into a NetworkX
DiGraph so that graph traversal (BFS/DFS neighbor lookup, path finding, etc.)
runs in micro-seconds from RAM instead of doing repeated ChromaDB look-ups.

Usage:
    from graph.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph("pallets__itsdangerous")
    neighbors = kg.get_neighbors("Signer.sign", depth=2)
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False
    logger.warning(
        "networkx not installed — KnowledgeGraph will fall back to "
        "dict-based traversal. Run: pip install networkx"
    )


class KnowledgeGraph:
    """
    In-memory directed call graph for a single repository.

    Built once from Phase 2's call_graph.json; all traversal queries
    are pure in-memory (O(V+E)) and return results in < 1 ms for typical
    repos.

    Attributes:
        repo_key: "owner__repo" string
        node_count: number of functions/classes in the graph
        edge_count: number of call/import edges
    """

    def __init__(self, repo_key: str, data_dir: str = "data/repos"):
        """
        Load and build the knowledge graph.

        Args:
            repo_key: Repository key, e.g. "pallets__itsdangerous"
            data_dir: Base data directory containing repo folders
        """
        self.repo_key = repo_key
        self._data_dir = Path(data_dir)
        self._adj: dict[str, dict] = {}       # fallback if networkx absent
        self._nodes: dict[str, dict] = {}     # node metadata

        if _NX_AVAILABLE:
            self.G: Optional["nx.DiGraph"] = nx.DiGraph()
        else:
            self.G = None

        self._load()

    # ------------------------------------------------------------------
    # Internal loading
    # ------------------------------------------------------------------

    def _load(self):
        """Load call_graph.json and populate the graph."""
        call_graph_path = (
            self._data_dir / self.repo_key / "parsed" / "call_graph.json"
        )

        if not call_graph_path.exists():
            # Graceful degradation — graph stays empty
            logger.warning(
                f"call_graph.json not found at {call_graph_path}. "
                "Graph features disabled until Phase 2 is complete."
            )
            return

        with open(call_graph_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Add nodes
        functions = data.get("functions", [])
        for fn in functions:
            name = fn.get("qualified_name") or fn.get("name", "")
            if not name:
                continue
            self._nodes[name] = fn
            if self.G is not None:
                self.G.add_node(name, **fn)
            else:
                self._adj.setdefault(name, {"out": [], "in": []})

        # Add edges
        edges = data.get("edges", [])
        for edge in edges:
            caller = edge.get("caller", "")
            callee = edge.get("callee", "")
            if not caller or not callee:
                continue
            if self.G is not None:
                self.G.add_edge(caller, callee, **{
                    k: v for k, v in edge.items()
                    if k not in ("caller", "callee")
                })
            else:
                self._adj.setdefault(caller, {"out": [], "in": []})
                self._adj.setdefault(callee, {"out": [], "in": []})
                self._adj[caller]["out"].append(callee)
                self._adj[callee]["in"].append(caller)

        node_count = self.G.number_of_nodes() if self.G else len(self._nodes)
        edge_count = self.G.number_of_edges() if self.G else sum(
            len(v["out"]) for v in self._adj.values()
        )
        logger.info(
            f"KnowledgeGraph loaded for {self.repo_key}: "
            f"{node_count} nodes, {edge_count} edges"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        if self.G is not None:
            return self.G.number_of_nodes()
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        if self.G is not None:
            return self.G.number_of_edges()
        return sum(len(v["out"]) for v in self._adj.values())

    def has_node(self, name: str) -> bool:
        """Return True if a function/class exists in the graph."""
        if self.G is not None:
            return self.G.has_node(name)
        return name in self._nodes

    def get_node_data(self, name: str) -> dict:
        """Return metadata for a node (function/class)."""
        if self.G is not None and self.G.has_node(name):
            return dict(self.G.nodes[name])
        return dict(self._nodes.get(name, {}))

    def get_callees(self, name: str) -> list[str]:
        """Return functions that `name` calls (outgoing edges)."""
        if self.G is not None:
            return list(self.G.successors(name)) if self.G.has_node(name) else []
        return list(self._adj.get(name, {}).get("out", []))

    def get_callers(self, name: str) -> list[str]:
        """Return functions that call `name` (incoming edges)."""
        if self.G is not None:
            return list(self.G.predecessors(name)) if self.G.has_node(name) else []
        return list(self._adj.get(name, {}).get("in", []))

    def get_neighbors(self, name: str, depth: int = 2) -> list[str]:
        """
        Return all nodes reachable from `name` within `depth` hops
        (both directions — callers + callees).

        This is the primary replacement for the slow ChromaDB loop in
        retriever.retrieve_by_graph().

        Args:
            name: Qualified function/class name
            depth: BFS depth limit (default 2)

        Returns:
            List of qualified names (excluding `name` itself)
        """
        if self.G is not None:
            if not self.G.has_node(name):
                return []
            # Forward (callees)
            forward = set(nx.bfs_tree(self.G, name, depth_limit=depth).nodes())
            # Backward (callers) — reverse graph
            backward = set(
                nx.bfs_tree(self.G.reverse(copy=False), name, depth_limit=depth).nodes()
            )
            neighbors = (forward | backward) - {name}
            return list(neighbors)

        # Fallback: manual BFS on dict
        visited: set[str] = set()
        queue = [(name, 0)]
        while queue:
            node, d = queue.pop(0)
            if node in visited or d > depth:
                continue
            visited.add(node)
            if d < depth:
                for nb in self._adj.get(node, {}).get("out", []):
                    queue.append((nb, d + 1))
                for nb in self._adj.get(node, {}).get("in", []):
                    queue.append((nb, d + 1))
        visited.discard(name)
        return list(visited)

    def get_entry_points(self) -> list[str]:
        """Return all functions marked as entry points."""
        if self.G is not None:
            return [
                n for n, d in self.G.nodes(data=True)
                if d.get("is_entry_point")
            ]
        return [
            name for name, data in self._nodes.items()
            if data.get("is_entry_point")
        ]

    def get_shortest_path(self, src: str, dst: str) -> list[str]:
        """
        Return the shortest call path from `src` to `dst`.

        Returns [] if no path exists or networkx is unavailable.
        """
        if self.G is None:
            return []
        try:
            return nx.shortest_path(self.G, src, dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_all_nodes(self) -> list[str]:
        """Return all qualified names in the graph."""
        if self.G is not None:
            return list(self.G.nodes())
        return list(self._nodes.keys())

    def summary(self) -> dict:
        """Return a brief summary dict (useful for API endpoints)."""
        return {
            "repo_key": self.repo_key,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entry_points": self.get_entry_points(),
            "networkx_available": _NX_AVAILABLE,
        }
