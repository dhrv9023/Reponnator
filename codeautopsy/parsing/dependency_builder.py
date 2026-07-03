"""
parsing/dependency_builder.py — Cross-file Import Dependency Map

Takes the list of all ParsedFile objects from the parse run and builds
a complete DependencyMap: which files import which other files, with
adjacency dicts for fast traversal.

Handles Python package resolution (__init__.py), JS index resolution
(index.js), relative import resolution, and circular dependency detection.
"""

from __future__ import annotations

import os
from pathlib import PurePosixPath
from typing import Optional

from parsing import DependencyEdge, DependencyMap, ParsedFile, ParsedImport
from utils.logger import get_logger

logger = get_logger(__name__)


def build_dependency_map(
    parsed_files: list[ParsedFile],
    repo_owner: str = "",
    repo_name: str = "",
) -> DependencyMap:
    """
    Build a complete cross-file dependency map from all parsed files.

    For each import in each file, attempts to resolve which local file
    it refers to.  Unresolvable imports are still included as edges with
    ``to_file=None``.

    Args:
        parsed_files: All ParsedFile objects from the parse run.
        repo_owner:   Repository owner (for DependencyMap metadata).
        repo_name:    Repository name (for DependencyMap metadata).

    Returns:
        A fully populated :class:`~parsing.DependencyMap`.
    """
    # Build lookup structures
    all_paths    = [pf.file_path for pf in parsed_files]
    path_set     = set(all_paths)
    path_by_stem = _build_stem_index(all_paths)

    edges:            list[DependencyEdge] = []
    external_deps:    set[str]             = set()
    adjacency:        dict[str, list[str]] = {p: [] for p in all_paths}
    reverse_adj:      dict[str, list[str]] = {p: [] for p in all_paths}

    for pf in parsed_files:
        for imp in pf.imports:
            to_file = None
            dep_type = _classify_dep(imp)

            if dep_type == "local":
                to_file = _resolve_local_import(
                    imp.module, pf.file_path, all_paths, path_set, path_by_stem
                )
            elif dep_type == "third_party":
                external_deps.add(imp.module.split(".")[0].split("/")[0])

            edge = DependencyEdge(
                from_file=pf.file_path,
                to_file=to_file,
                to_module=imp.module,
                dependency_type=dep_type,
                imported_items=list(imp.imported_items),
                line_number=imp.line_number,
            )
            edges.append(edge)

            if to_file and to_file in adjacency:
                if to_file not in adjacency[pf.file_path]:
                    adjacency[pf.file_path].append(to_file)
                if pf.file_path not in reverse_adj[to_file]:
                    reverse_adj[to_file].append(pf.file_path)

    dep_map = DependencyMap(
        repo_owner=repo_owner,
        repo_name=repo_name,
        edges=edges,
        external_dependencies=sorted(external_deps),
        local_files=all_paths,
        adjacency=adjacency,
        reverse_adjacency=reverse_adj,
    )

    # Detect and warn about circular dependencies
    cycles = detect_circular_dependencies(dep_map)
    if cycles:
        for cycle in cycles:
            logger.warning("Circular dependency: %s", " → ".join(cycle))

    return dep_map


def detect_circular_dependencies(dep_map: DependencyMap) -> list[list[str]]:
    """
    Detect circular dependency chains using DFS with in-stack tracking.

    Args:
        dep_map: A fully populated DependencyMap.

    Returns:
        List of cycle chains, where each chain is a list of file paths
        ending with the same file it started from (closed loop).
    """
    visited:  set[str] = set()
    in_stack: set[str] = set()
    stack:    list[str] = []
    cycles:   list[list[str]] = []

    def dfs(node: str) -> None:
        visited.add(node)
        in_stack.add(node)
        stack.append(node)

        for neighbour in dep_map.adjacency.get(node, []):
            if neighbour not in visited:
                dfs(neighbour)
            elif neighbour in in_stack:
                # Found a cycle
                cycle_start = stack.index(neighbour)
                cycles.append(stack[cycle_start:] + [neighbour])

        stack.pop()
        in_stack.discard(node)

    for file_path in dep_map.local_files:
        if file_path not in visited:
            dfs(file_path)

    return cycles


def get_most_imported_files(
    dep_map: DependencyMap, top_n: int = 10
) -> list[tuple[str, int]]:
    """
    Return the files most depended upon by other files (highest in-degree).

    These are the "core" files in the repository.

    Args:
        dep_map: A fully populated DependencyMap.
        top_n:   How many files to return (default 10).

    Returns:
        List of ``(file_path, import_count)`` tuples, sorted descending.
    """
    in_degree = {
        path: len(importers)
        for path, importers in dep_map.reverse_adjacency.items()
    }
    return sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:top_n]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_dep(imp: ParsedImport) -> str:
    """Return 'local', 'stdlib', or 'third_party' for an import."""
    if imp.is_local:
        return "local"
    if imp.is_stdlib:
        return "stdlib"
    return "third_party"


def _build_stem_index(paths: list[str]) -> dict[str, list[str]]:
    """
    Build an index from path stem (without extension) to full path.

    Used for resolving absolute local imports that omit the extension.
    """
    index: dict[str, list[str]] = {}
    for path in paths:
        stem = PurePosixPath(path).with_suffix("").as_posix()
        index.setdefault(stem, []).append(path)
        # Also index by the last component only
        short = PurePosixPath(path).stem
        index.setdefault(short, []).append(path)
    return index


def _resolve_local_import(
    module: str,
    from_file: str,
    all_paths: list[str],
    path_set: set[str],
    path_by_stem: dict[str, list[str]],
) -> Optional[str]:
    """
    Attempt to resolve a local import to an actual file path.

    Tries in order:
    1. Relative resolution (for imports starting with . or /)
    2. Direct path match
    3. Stem match (extension-agnostic)
    4. Python __init__.py package resolution
    5. JS index.js directory resolution

    Args:
        module:       The import module string (e.g. ``"./utils"``).
        from_file:    The file containing this import.
        all_paths:    All file paths in the repo.
        path_set:     Set version for O(1) lookup.
        path_by_stem: Stem → paths index.

    Returns:
        Resolved file path string or ``None`` if unresolvable.
    """
    from_dir = str(PurePosixPath(from_file).parent)
    if from_dir == ".":
        from_dir = ""

    # Normalize module: strip surrounding quotes that may appear in test fixtures
    mod = module.strip("'\"").replace("\\", "/")

    # Relative imports: starts with . or /
    if mod.startswith(".") or mod.startswith("/"):
        # Count leading dots (. = same dir, .. = parent)
        stripped = mod.lstrip("/")
        dots = 0
        while stripped.startswith("."):
            dots += 1
            stripped = stripped[1:]
        # Remove leading slash that may follow the dots
        rel_part = stripped.lstrip("/")

        # Navigate up from the file's directory
        base_dir = from_dir  # e.g. "" for root-level files
        for _ in range(max(0, dots - 1)):
            base_dir = str(PurePosixPath(base_dir).parent) if base_dir and base_dir != "." else ""
            if base_dir == ".":
                base_dir = ""

        if rel_part:
            candidate_base = f"{base_dir}/{rel_part}".strip("/")
        else:
            candidate_base = base_dir.strip("/") or "."

        return _try_resolve(candidate_base, path_set, path_by_stem)

    # Absolute module — convert dots to slashes (Python package style)
    mod_as_path = mod.replace(".", "/")

    # Try direct stem match
    result = _try_resolve(mod_as_path, path_set, path_by_stem)
    if result:
        return result

    # Try just the last component (e.g. "utils" → search for utils.py anywhere)
    last = mod_as_path.split("/")[-1]
    candidates = path_by_stem.get(last, [])
    if len(candidates) == 1:
        return candidates[0]

    return None


def _try_resolve(
    base: str,
    path_set: set[str],
    path_by_stem: dict[str, list[str]],
) -> Optional[str]:
    """
    Try several file path variants for a given stem.

    Checks in order: exact path, .py, .js, .ts, .go, .rs, __init__.py,
    index.js, index.ts.
    """
    candidates = [
        base,
        f"{base}.py",
        f"{base}.js",
        f"{base}.ts",
        f"{base}.tsx",
        f"{base}.go",
        f"{base}.rs",
        f"{base}/__init__.py",
        f"{base}/index.js",
        f"{base}/index.ts",
    ]
    for c in candidates:
        if c in path_set:
            return c

    # Stem index fallback
    matches = path_by_stem.get(base.split("/")[-1], [])
    if len(matches) == 1:
        return matches[0]

    return None
