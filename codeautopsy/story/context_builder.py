"""
story/context_builder.py — Story Context Builder

Compresses Phase 2 structural data into a token-efficient context for story generation.
"""

import json
import logging
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


class StoryContextBuilder:
    """
    Builds compressed story context from Phase 2 output.
    
    Token budget: Must stay under 3,000 tokens.
    """
    
    MAX_FUNCTIONS_PER_MODULE = 8
    MAX_CLASSES_PER_MODULE = 5
    MAX_TOP_MODULES = 10
    MAX_ENTRY_POINTS = 3
    MAX_COMPLEXITY_HOTSPOTS = 5
    
    def __init__(self, repo_folder: Path):
        """
        Initialize context builder.
        
        Args:
            repo_folder: Path to repo folder (data/repos/{owner}__{repo})
        """
        self.repo_folder = repo_folder
        self.parsed_folder = repo_folder / "parsed"
        
        # Load Phase 2 data
        self.parse_manifest = self._load_json("parse_manifest.json")
        self.call_graph = self._load_json("call_graph.json")
        self.dependency_map = self._load_json("dependency_map.json")
        self.patterns = self._load_json("patterns.json")
        self.entry_points = self._load_json("entry_points.json")
    
    def _load_json(self, filename: str) -> dict:
        """Load JSON file from parsed folder."""
        path = self.parsed_folder / filename
        if not path.exists():
            logger.warning(f"File not found: {path}")
            return {}
        
        with open(path, "r") as f:
            return json.load(f)
    
    def build(self):
        """
        Build story context.
        
        Returns:
            StoryContext dataclass
        """
        from story import StoryContext, ModuleBrief
        
        logger.info("Building story context...")
        
        # Basic repo info
        repo_name = f"{self.parse_manifest.get('repo_owner', '')}/{self.parse_manifest.get('repo_name', '')}"
        
        # Load Phase 1 manifest.json for richer description and language distribution
        manifest_path = self.repo_folder / "manifest.json"
        repo_description = ""
        languages_breakdown = ""
        primary_language = self.parse_manifest.get("primary_language", "Unknown")
        
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                repo_description = manifest_data.get("repo", {}).get("description", "") or ""
                lang_analysis = manifest_data.get("language_analysis", {})
                if lang_analysis:
                    primary_language = lang_analysis.get("primary_language", primary_language)
                    langs = lang_analysis.get("languages", {})
                    languages_breakdown = ", ".join(f"{l} ({data.get('percentage', 0)}%)" for l, data in langs.items())
            except Exception as e:
                logger.warning(f"Failed to load manifest.json in StoryContextBuilder: {e}")

        total_files = self.parse_manifest.get("total_files_parsed", 0)
        total_functions = self.parse_manifest.get("total_functions_extracted", 0)
        total_classes = self.parse_manifest.get("total_classes_extracted", 0)
        
        # Detected pattern
        if isinstance(self.patterns, dict):
            detected_patterns = self.patterns.get("detected_patterns", [])
        elif isinstance(self.patterns, list):
            detected_patterns = self.patterns
        else:
            detected_patterns = []
        detected_pattern = detected_patterns[0] if detected_patterns else "Unknown"
        
        # Entry points
        entry_point_names = []
        for ep in self.entry_points[:self.MAX_ENTRY_POINTS]:
            entry_funcs = ep.get("entry_functions", [])
            for func in entry_funcs[:2]:  # Max 2 per entry point
                # Get short name
                short_name = self._get_short_name(func)
                entry_point_names.append(short_name)
        
        # Core utilities (files called by 3+ others)
        core_utilities = self._find_core_utilities()
        
        # Top modules by call count
        top_modules = self._build_top_modules()
        
        # Circular dependencies
        has_circular_deps = self._detect_circular_deps()
        
        # Complexity hotspots
        complexity_hotspots = self._find_complexity_hotspots()
        
        # Architectural signals
        architectural_signals = self._detect_architectural_signals()
        
        context = StoryContext(
            repo_name=repo_name,
            primary_language=primary_language,
            total_files=total_files,
            total_functions=total_functions,
            total_classes=total_classes,
            detected_pattern=detected_pattern,
            entry_points=entry_point_names,
            core_utilities=core_utilities,
            top_modules=top_modules,
            has_circular_deps=has_circular_deps,
            complexity_hotspots=complexity_hotspots,
            architectural_signals=architectural_signals,
            repo_description=repo_description,
            languages_breakdown=languages_breakdown
        )
        
        logger.info(f"Built story context: {total_files} files, {total_functions} functions")
        
        return context
    
    def _get_short_name(self, qualified_name: str) -> str:
        """Get short name from qualified name."""
        parts = qualified_name.split(".")
        if len(parts) > 2:
            return f"{parts[-2]}.{parts[-1]}"
        return qualified_name
    
    def _find_core_utilities(self) -> list[str]:
        """Find files called by 3+ other files."""
        # Build file-level call graph from edges
        file_called_by = defaultdict(set)
        
        edges = self.call_graph.get("edges", [])
        
        for edge in edges:
            if not edge.get("is_resolved", False):
                continue
            
            caller_file = edge.get("caller_file", "")
            callee_resolved = edge.get("callee_resolved", "")
            
            if not caller_file or not callee_resolved:
                continue
            
            # Find the file that contains the callee function
            # We need to search through parsed files
            parsed_files = self.parse_manifest.get("parsed_files", [])
            callee_file = None
            
            for file_data in parsed_files:
                functions = file_data.get("functions", [])
                for func in functions:
                    if func.get("qualified_name", "") == callee_resolved:
                        callee_file = file_data.get("file_path", "")
                        break
                if callee_file:
                    break
            
            if callee_file and caller_file != callee_file:
                file_called_by[callee_file].add(caller_file)
        
        # Find files called by 3+ others
        core_utils = []
        for file_path, callers in file_called_by.items():
            if len(callers) >= 3:
                short_name = Path(file_path).name
                core_utils.append(short_name)
        
        # Sort by call count descending
        core_utils.sort(key=lambda f: len([fp for fp, callers in file_called_by.items() if Path(fp).name == f]), reverse=True)
        
        return core_utils[:10]  # Top 10
    
    def _build_top_modules(self) -> list:
        """Build top modules by call volume."""
        from story import ModuleBrief
        
        # Get parsed files
        parsed_files = self.parse_manifest.get("parsed_files", [])
        
        # Build function -> file mapping
        func_to_file = {}
        for file_data in parsed_files:
            file_path = file_data.get("file_path", "")
            for func in file_data.get("functions", []):
                func_qn = func.get("qualified_name", "")
                if func_qn:
                    func_to_file[func_qn] = file_path
        
        # Count calls per file using adjacency
        adjacency = self.call_graph.get("adjacency", {})
        reverse_adjacency = self.call_graph.get("reverse_adjacency", {})
        
        file_calls = defaultdict(int)
        file_called_by = defaultdict(int)
        
        for func_qn, callees in adjacency.items():
            file_path = func_to_file.get(func_qn)
            if file_path:
                file_calls[file_path] += len(callees)
        
        for func_qn, callers in reverse_adjacency.items():
            file_path = func_to_file.get(func_qn)
            if file_path:
                file_called_by[file_path] += len(callers)
        
        # Score each file
        file_scores = []
        
        for file_data in parsed_files:
            file_path = file_data.get("file_path", "")
            if not file_path:
                continue
            
            functions = file_data.get("functions", [])
            classes = file_data.get("classes", [])
            
            calls_count = file_calls.get(file_path, 0)
            called_by_count = file_called_by.get(file_path, 0)
            
            score = called_by_count * 2 + calls_count
            
            file_scores.append((score, file_path, functions, classes, calls_count, called_by_count))
        
        # Sort by score descending
        file_scores.sort(reverse=True)
        
        # Build ModuleBrief for top modules
        top_modules = []
        for score, file_path, functions, classes, calls_count, called_by_count in file_scores[:self.MAX_TOP_MODULES]:
            # Get short filename
            filename = Path(file_path).name
            
            # Get function names (max 8)
            function_names = [f.get("name", "") for f in functions[:self.MAX_FUNCTIONS_PER_MODULE]]
            
            # Get class names (max 5)
            class_names = [c.get("name", "") for c in classes[:self.MAX_CLASSES_PER_MODULE]]
            
            module = ModuleBrief(
                filename=filename,
                function_names=function_names,
                class_names=class_names,
                called_by_count=called_by_count,
                calls_count=calls_count
            )
            
            top_modules.append(module)
        
        return top_modules
    
    def _detect_circular_deps(self) -> bool:
        """Detect if there are circular dependencies."""
        # Build file-level dependency graph from edges
        file_imports = defaultdict(set)
        
        edges = self.dependency_map.get("edges", [])
        
        for edge in edges:
            from_file = edge.get("from_file", "")
            to_file = edge.get("to_file", "")
            
            if from_file and to_file:
                file_imports[from_file].add(to_file)
        
        # Simple cycle detection: if A imports B and B imports A
        for file_a, imports_a in file_imports.items():
            for file_b in imports_a:
                if file_a in file_imports.get(file_b, set()):
                    return True
        
        return False
    
    def _find_complexity_hotspots(self) -> list[str]:
        """Find top 5 highest complexity functions."""
        # Get all functions with complexity scores
        parsed_files = self.parse_manifest.get("parsed_files", [])
        
        complexity_funcs = []
        
        for file_data in parsed_files:
            functions = file_data.get("functions", [])
            
            for func in functions:
                complexity = func.get("complexity_score", 0)
                if complexity > 0:
                    name = func.get("name", "")
                    file_path = file_data.get("file_path", "")
                    short_file = Path(file_path).name
                    
                    complexity_funcs.append((complexity, f"{short_file}::{name}"))
        
        # Sort by complexity descending
        complexity_funcs.sort(reverse=True)
        
        # Return top 5
        return [name for _, name in complexity_funcs[:self.MAX_COMPLEXITY_HOTSPOTS]]
    
    def _detect_architectural_signals(self) -> list[str]:
        """Detect architectural signals from file names and patterns."""
        signals = []
        
        # Check for common architectural patterns
        parsed_files = self.parse_manifest.get("parsed_files", [])
        file_paths = [f.get("file_path", "").lower() for f in parsed_files]
        
        # Middleware
        if any("middleware" in fp for fp in file_paths):
            signals.append("uses_middleware")
        
        # Migrations
        if any("migration" in fp for fp in file_paths):
            signals.append("has_migrations")
        
        # Event loop / async
        if any("async" in fp or "event" in fp for fp in file_paths):
            signals.append("event_driven")
        
        # API routes
        if any("route" in fp or "endpoint" in fp for fp in file_paths):
            signals.append("has_api_routes")
        
        # Database
        if any("db" in fp or "database" in fp or "model" in fp for fp in file_paths):
            signals.append("uses_database")
        
        # Testing
        if any("test" in fp for fp in file_paths):
            signals.append("has_tests")
        
        # Config
        if any("config" in fp or "setting" in fp for fp in file_paths):
            signals.append("has_config")
        
        # CLI
        if any("cli" in fp or "command" in fp for fp in file_paths):
            signals.append("has_cli")
        
        return signals


# Test function
if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    print("Testing Story Context Builder...")
    print("=" * 60)
    
    # Test with itsdangerous repo
    repo_folder = Path(__file__).parent.parent / "data" / "repos" / "pallets__itsdangerous"
    
    if not repo_folder.exists():
        print("✗ Test repo not found. Run Phase 2 first on pallets/itsdangerous")
        sys.exit(1)
    
    try:
        builder = StoryContextBuilder(repo_folder)
        context = builder.build()
        
        print(f"✓ Built story context:")
        print(f"  Repo: {context.repo_name}")
        print(f"  Language: {context.primary_language}")
        print(f"  Files: {context.total_files}")
        print(f"  Functions: {context.total_functions}")
        print(f"  Pattern: {context.detected_pattern}")
        print(f"  Entry points: {context.entry_points}")
        print(f"  Core utilities: {context.core_utilities}")
        print(f"  Top modules: {len(context.top_modules)}")
        print(f"  Circular deps: {context.has_circular_deps}")
        print(f"  Complexity hotspots: {context.complexity_hotspots}")
        print(f"  Signals: {context.architectural_signals}")
        print()
        print("✓ Story context builder tests complete!")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
