"""
diagram/mermaid_generator.py — Mermaid.js Diagram Generator

Converts Phase 2 JSON output to interactive Mermaid.js flowchart diagrams.
"""

import json
import re
import logging
from pathlib import Path
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class MermaidGenerator:
    """
    Generates Mermaid.js diagrams from Phase 2 parsed data.
    """
    
    MAX_NODES = 80  # Maximum nodes in diagram
    
    def __init__(self, repo_folder: Path):
        """
        Initialize generator.
        
        Args:
            repo_folder: Path to repo folder (data/repos/{owner}__{repo})
        """
        self.repo_folder = repo_folder
        self.parsed_folder = repo_folder / "parsed"
        self.output_folder = repo_folder / "diagram"
        
        # Load Phase 2 data
        self.call_graph = self._load_json("call_graph.json")
        self.dependency_map = self._load_json("dependency_map.json")
        self.parse_manifest = self._load_json("parse_manifest.json")
        self.patterns = self._load_json("patterns.json")
        
        # Node tracking
        self.nodes = {}  # file_path → node_data
        self.edges = []  # list of (from, to, edge_type)
        self.node_id_map = {}  # file_path → sanitized_id

        # Load parsed files to populate nodes and QN-to-file map
        self.qn_to_file = {}
        self.parsed_files = []
        files_dir = self.parsed_folder / "files"
        if files_dir.exists():
            for json_path in sorted(files_dir.glob("*.json")):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        file_data = json.load(f)
                        self.parsed_files.append(file_data)
                        file_path = file_data.get("file_path", "")
                        if file_path:
                            # Map functions
                            for f_item in file_data.get("functions", []):
                                qn = f_item.get("qualified_name")
                                if qn:
                                    self.qn_to_file[qn] = file_path
                            # Map classes
                            for c_item in file_data.get("classes", []):
                                qn = c_item.get("qualified_name")
                                if qn:
                                    self.qn_to_file[qn] = file_path
                except Exception as exc:
                    logger.error(f"Failed to load parsed file {json_path}: {exc}")
    
    def _load_json(self, filename: str) -> dict:
        """Load JSON file from parsed folder."""
        path = self.parsed_folder / filename
        if not path.exists():
            logger.warning(f"File not found: {path}")
            return {}
        
        with open(path, "r") as f:
            return json.load(f)
    
    def generate(self) -> tuple[str, dict]:
        """
        Generate Mermaid diagram and metadata.
        
        Returns:
            (mermaid_code, metadata_dict)
        """
        logger.info("Generating Mermaid diagram...")
        
        # Build nodes from parsed files
        self._build_nodes()
        
        # Build edges from dependencies and call graph
        self._build_edges()
        
        # Limit to MAX_NODES
        self._limit_nodes()
        
        # Generate Mermaid code
        mermaid_code = self._generate_mermaid_code()
        
        # Generate metadata
        metadata = self._generate_metadata()
        
        logger.info(f"Generated diagram with {len(self.nodes)} nodes, {len(self.edges)} edges")
        
        return mermaid_code, metadata
    
    def _build_nodes(self):
        """Build nodes from parsed files."""
        for file_data in self.parsed_files:
            file_path = file_data.get("file_path", "")
            if not file_path:
                continue
            
            # Get functions and classes
            functions = file_data.get("functions", [])
            classes = file_data.get("classes", [])
            
            # Determine node type
            node_type = self._determine_node_type(file_path, functions, classes)
            
            # Create node
            self.nodes[file_path] = {
                "file_path": file_path,
                "label": self._get_short_label(file_path),
                "type": node_type,
                "functions": [f.get("name", "") for f in functions],
                "classes": [c.get("name", "") for c in classes],
                "call_count": 0,  # Will be updated later
                "called_by_count": 0
            }
    
    def _determine_node_type(self, file_path: str, functions: list, classes: list) -> str:
        """
        Determine node type based on file characteristics.
        
        Returns:
            "entry_point", "core_utility", or "module"
        """
        # Check if entry point
        entry_points = self.parse_manifest.get("entry_points", [])
        for ep in entry_points:
            # Handle both string and dict formats
            if isinstance(ep, str):
                if file_path == ep or file_path.endswith(ep):
                    return "entry_point"
            elif isinstance(ep, dict):
                ep_file = ep.get("file_path", "")
                if file_path == ep_file or file_path.endswith(ep_file):
                    return "entry_point"
        
        # Check if core utility (will be updated based on call count)
        return "module"
    
    def _get_short_label(self, file_path: str) -> str:
        """
        Get short label for node (filename only).
        
        Args:
            file_path: Full file path
        
        Returns:
            Short label (e.g., "user_service.py")
        """
        return Path(file_path).name
    
    def _build_edges(self):
        """Build edges from dependencies and call graph."""
        # Import dependencies (solid edges) - handle new structure
        # dependency_map has "adjacency" and "edges" keys
        dep_adjacency = self.dependency_map.get("adjacency", {})
        
        for file_path, deps in dep_adjacency.items():
            if file_path not in self.nodes:
                continue
            
            # deps is a list of imported files
            if isinstance(deps, list):
                for dep_file in deps:
                    if dep_file and dep_file in self.nodes:
                        self.edges.append((file_path, dep_file, "import"))
            elif isinstance(deps, dict):
                # Legacy format
                for dep_type, dep_list in deps.items():
                    if dep_type == "local_imports":
                        for dep in dep_list:
                            if isinstance(dep, str):
                                dep_file = dep
                            else:
                                dep_file = dep.get("resolved_path", "")
                            if dep_file and dep_file in self.nodes:
                                self.edges.append((file_path, dep_file, "import"))
        
        # Call graph (dashed edges between files)
        adjacency = self.call_graph.get("adjacency", {})
        
        # Build file-level call graph
        file_calls = defaultdict(set)
        
        for caller_qn, callees in adjacency.items():
            # Get caller file
            caller_file = self._get_file_from_qualified_name(caller_qn)
            if not caller_file or caller_file not in self.nodes:
                continue
            
            for callee_qn in callees:
                # Get callee file
                callee_file = self._get_file_from_qualified_name(callee_qn)
                if not callee_file or callee_file not in self.nodes:
                    continue
                
                # Skip self-calls
                if caller_file == callee_file:
                    continue
                
                file_calls[caller_file].add(callee_file)
        
        # Add call edges
        for caller_file, callee_files in file_calls.items():
            for callee_file in callee_files:
                self.edges.append((caller_file, callee_file, "call"))
        
        # FALLBACK: If no edges found, create edges based on file analysis
        if len(self.edges) == 0:
            logger.warning("No edges found from dependency/call graph. Creating edges from parsed files...")
            self._create_fallback_edges()
        
        # Update call counts
        for from_file, to_file, edge_type in self.edges:
            if from_file in self.nodes:
                self.nodes[from_file]["call_count"] += 1
            if to_file in self.nodes:
                self.nodes[to_file]["called_by_count"] += 1
        
        # Update core utility nodes (called by 3+ others)
        for file_path, node in self.nodes.items():
            if node["called_by_count"] >= 3 and node["type"] == "module":
                node["type"] = "core_utility"
    
    def _create_fallback_edges(self):
        """
        Create edges based on file imports when dependency/call graph is empty.
        Analyzes import statements in parsed files.
        """
        for file_data in self.parsed_files:
            file_path = file_data.get("file_path", "")
            if not file_path or file_path not in self.nodes:
                continue
            
            imports = file_data.get("imports", [])
            
            # Process imports to find local file references
            for imp in imports:
                module_name = imp.get("module", "")
                import_type = imp.get("type", "")
                
                # Skip standard library and third-party
                if import_type in ["stdlib", "third_party"]:
                    continue
                
                # Try to find matching file by module name
                # e.g., "model" → "model.py", "data.prepare" → "data/prepare.py"
                possible_paths = self._resolve_module_to_file(module_name, file_path)
                
                for target_file in possible_paths:
                    if target_file in self.nodes and target_file != file_path:
                        self.edges.append((file_path, target_file, "import"))
                        break
    
    def _resolve_module_to_file(self, module_name: str, source_file: str) -> list[str]:
        """
        Resolve a module name to possible file paths.
        
        Args:
            module_name: e.g., "model", "data.prepare", ".utils"
            source_file: The file doing the importing
        
        Returns:
            List of possible file paths
        """
        possibilities = []
        
        # Direct match: model → model.py
        for file_path in self.nodes.keys():
            file_stem = Path(file_path).stem
            
            # Exact match
            if file_stem == module_name:
                possibilities.append(file_path)
            
            # Module path match: data.prepare → data/prepare.py
            if module_name.replace('.', '/') in file_path:
                possibilities.append(file_path)
            
            # Relative import: .model → same dir
            if module_name.startswith('.'):
                source_dir = str(Path(source_file).parent)
                target_name = module_name.lstrip('.')
                if source_dir in file_path and target_name in file_path:
                    possibilities.append(file_path)
        
        return possibilities
    
    def _get_file_from_qualified_name(self, qualified_name: str) -> Optional[str]:
        """
        Get file path from qualified name using call graph nodes.
        
        Args:
            qualified_name: e.g., "UserService.get_user"
        
        Returns:
            File path or None
        """
        return self.qn_to_file.get(qualified_name)
    
    def _limit_nodes(self):
        """Limit diagram to MAX_NODES by removing least important nodes."""
        if len(self.nodes) <= self.MAX_NODES:
            return
        
        logger.warning(f"Too many nodes ({len(self.nodes)}), limiting to {self.MAX_NODES}")
        
        # Score nodes by importance
        scored_nodes = []
        for file_path, node in self.nodes.items():
            score = 0
            
            # Entry points are most important
            if node["type"] == "entry_point":
                score += 1000
            
            # Core utilities are important
            if node["type"] == "core_utility":
                score += 500
            
            # Nodes with many connections are important
            score += node["called_by_count"] * 10
            score += node["call_count"] * 5
            
            # Nodes with many functions/classes are important
            score += len(node["functions"]) * 2
            score += len(node["classes"]) * 3
            
            scored_nodes.append((score, file_path))
        
        # Sort by score descending
        scored_nodes.sort(reverse=True)
        
        # Keep top MAX_NODES
        keep_files = set(fp for _, fp in scored_nodes[:self.MAX_NODES])
        
        # Remove nodes
        self.nodes = {fp: node for fp, node in self.nodes.items() if fp in keep_files}
        
        # Remove edges that reference removed nodes
        self.edges = [
            (from_file, to_file, edge_type)
            for from_file, to_file, edge_type in self.edges
            if from_file in keep_files and to_file in keep_files
        ]
    
    def _sanitize_id(self, file_path: str) -> str:
        """
        Sanitize file path to valid Mermaid node ID.
        
        Args:
            file_path: File path
        
        Returns:
            Sanitized ID (alphanumeric + underscore only)
        """
        # Remove extension
        name = Path(file_path).stem
        
        # Replace special chars with underscore
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        
        # Ensure starts with letter
        if sanitized and not sanitized[0].isalpha():
            sanitized = 'n_' + sanitized
        
        # Ensure unique
        base = sanitized
        counter = 1
        while sanitized in self.node_id_map.values():
            sanitized = f"{base}_{counter}"
            counter += 1
        
        return sanitized
    
    def _generate_mermaid_code(self) -> str:
        """Generate Mermaid.js flowchart code."""
        lines = ["flowchart TD"]
        lines.append("")
        
        # Build node ID map
        for file_path in self.nodes.keys():
            self.node_id_map[file_path] = self._sanitize_id(file_path)
        
        # Add nodes
        lines.append("  %% Nodes")
        for file_path, node in self.nodes.items():
            node_id = self.node_id_map[file_path]
            label = node["label"]
            
            # Choose node shape based on type
            if node["type"] == "entry_point":
                # Rectangle with rounded corners
                lines.append(f'  {node_id}(["{label}"])')
            elif node["type"] == "core_utility":
                # Hexagon
                lines.append(f'  {node_id}{{{{{label}}}}}')
            else:
                # Standard box
                lines.append(f'  {node_id}["{label}"]')
            
            # Add click event
            lines.append(f'  click {node_id} call nodeClick("{node_id}")')
        
        lines.append("")
        
        # Add edges
        lines.append("  %% Edges")
        
        # Deduplicate edges
        unique_edges = set()
        for from_file, to_file, edge_type in self.edges:
            from_id = self.node_id_map.get(from_file)
            to_id = self.node_id_map.get(to_file)
            
            if from_id and to_id:
                unique_edges.add((from_id, to_id, edge_type))
        
        # Sort edges for consistent output
        for from_id, to_id, edge_type in sorted(unique_edges):
            if edge_type == "import":
                # Solid edge for imports
                lines.append(f'  {from_id} --> {to_id}')
            else:
                # Dashed edge for calls
                lines.append(f'  {from_id} -.-> {to_id}')
        
        lines.append("")
        
        # Add styling
        lines.append("  %% Styling")
        lines.append("  classDef entryPoint fill:#10b981,stroke:#059669,stroke-width:2px,color:#fff")
        lines.append("  classDef coreUtil fill:#3b82f6,stroke:#2563eb,stroke-width:2px,color:#fff")
        lines.append("  classDef module fill:#6b7280,stroke:#4b5563,stroke-width:1px,color:#fff")
        
        # Apply classes
        for file_path, node in self.nodes.items():
            node_id = self.node_id_map[file_path]
            if node["type"] == "entry_point":
                lines.append(f'  class {node_id} entryPoint')
            elif node["type"] == "core_utility":
                lines.append(f'  class {node_id} coreUtil')
            else:
                lines.append(f'  class {node_id} module')
        
        return "\n".join(lines)
    
    def _generate_metadata(self) -> dict:
        """Generate metadata JSON for frontend."""
        nodes_metadata = []
        
        for file_path, node in self.nodes.items():
            node_id = self.node_id_map[file_path]
            
            nodes_metadata.append({
                "id": node_id,
                "label": node["label"],
                "file_path": file_path,
                "type": node["type"],
                "functions": node["functions"],
                "classes": node["classes"],
                "call_count": node["call_count"],
                "called_by_count": node["called_by_count"]
            })
        
        return {
            "repo_owner": self.parse_manifest.get("repo_owner", ""),
            "repo_name": self.parse_manifest.get("repo_name", ""),
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "nodes": nodes_metadata,
            "patterns": self.patterns if isinstance(self.patterns, list) else self.patterns.get("detected_patterns", [])
        }
    
    def save(self, mermaid_code: str, metadata: dict):
        """Save Mermaid code and metadata to files."""
        self.output_folder.mkdir(exist_ok=True)
        
        # Save Mermaid code
        mermaid_path = self.output_folder / "mermaid_diagram.mmd"
        with open(mermaid_path, "w") as f:
            f.write(mermaid_code)
        
        logger.info(f"Saved Mermaid diagram to {mermaid_path}")
        
        # Save metadata
        metadata_path = self.output_folder / "diagram_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Saved metadata to {metadata_path}")


def generate_mermaid_diagram(repo_folder: Path) -> tuple[str, dict]:
    """
    Generate Mermaid diagram from Phase 2 output.
    
    Args:
        repo_folder: Path to repo folder
    
    Returns:
        (mermaid_code, metadata_dict)
    """
    generator = MermaidGenerator(repo_folder)
    mermaid_code, metadata = generator.generate()
    generator.save(mermaid_code, metadata)
    return mermaid_code, metadata


# Test function
if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    print("Testing Mermaid Generator...")
    print("=" * 60)
    
    # Test with itsdangerous repo
    repo_folder = Path(__file__).parent.parent / "data" / "repos" / "pallets__itsdangerous"
    
    if not repo_folder.exists():
        print("✗ Test repo not found. Run Phase 2 first on pallets/itsdangerous")
        sys.exit(1)
    
    try:
        mermaid_code, metadata = generate_mermaid_diagram(repo_folder)
        
        print(f"✓ Generated diagram:")
        print(f"  Nodes: {metadata['total_nodes']}")
        print(f"  Edges: {metadata['total_edges']}")
        print(f"  Entry points: {sum(1 for n in metadata['nodes'] if n['type'] == 'entry_point')}")
        print(f"  Core utilities: {sum(1 for n in metadata['nodes'] if n['type'] == 'core_utility')}")
        print()
        print("Mermaid code preview (first 20 lines):")
        print("-" * 60)
        for line in mermaid_code.split("\n")[:20]:
            print(line)
        print("...")
        print()
        print("✓ Mermaid generator tests complete!")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
