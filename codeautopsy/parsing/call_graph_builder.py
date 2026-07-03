"""
parsing/call_graph_builder.py — Function-Level Call Graph

Takes all ParsedFile objects and builds a complete function call graph:
which functions call which other functions across the entire repository.

Resolves callee names using a multi-step lookup:
  1. Same-file functions first
  2. Imported names from this file's imports
  3. Global name index across all files
  4. Mark unresolved with is_resolved=False
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from parsing import CallEdge, CallGraph, DependencyMap, ParsedFile
from utils.logger import get_logger

logger = get_logger(__name__)

# Built-in names to skip (never add to graph edges)
_PYTHON_BUILTINS = frozenset({
    "print", "len", "range", "str", "int", "float", "bool", "list",
    "dict", "set", "tuple", "type", "isinstance", "issubclass", "hasattr",
    "getattr", "setattr", "delattr", "sorted", "reversed", "enumerate",
    "zip", "map", "filter", "any", "all", "sum", "min", "max", "abs",
    "round", "open", "input", "super", "property", "staticmethod",
    "classmethod", "repr", "hash", "id", "callable", "iter", "next",
    "vars", "dir", "help", "exec", "eval", "compile", "chr", "ord",
    "hex", "oct", "bin", "format", "object", "Exception", "ValueError",
    "TypeError", "KeyError", "IndexError", "RuntimeError", "NotImplementedError",
    "StopIteration", "GeneratorExit", "SystemExit", "KeyboardInterrupt",
})
_JS_BUILTINS = frozenset({
    "console", "setTimeout", "setInterval", "clearTimeout", "clearInterval",
    "fetch", "Promise", "JSON", "Math", "Date", "Array", "Object", "String",
    "Number", "Boolean", "Error", "Symbol", "Map", "Set", "WeakMap",
    "WeakSet", "Proxy", "Reflect", "parseInt", "parseFloat", "isNaN",
    "isFinite", "encodeURIComponent", "decodeURIComponent",
})
_ALL_BUILTINS = _PYTHON_BUILTINS | _JS_BUILTINS


def build_call_graph(
    parsed_files: list[ParsedFile],
    dependency_map: DependencyMap,
    repo_owner: str = "",
    repo_name: str = "",
) -> CallGraph:
    """
    Build the complete function-level call graph for a repository.

    Args:
        parsed_files:   All ParsedFile objects.
        dependency_map: Already-built DependencyMap for import resolution.
        repo_owner:     Repository owner for metadata.
        repo_name:      Repository name for metadata.

    Returns:
        A fully populated :class:`~parsing.CallGraph`.
    """
    # Build name → qualified_name → file_path lookup
    name_index: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for pf in parsed_files:
        for fn in pf.functions:
            name_index[fn.name].append((fn.qualified_name, pf.file_path))
            name_index[fn.qualified_name].append((fn.qualified_name, pf.file_path))

    edges: list[CallEdge]             = []
    adjacency: dict[str, list[str]]   = defaultdict(list)
    reverse_adj: dict[str, list[str]] = defaultdict(list)
    all_nodes: set[str]               = set()

    for pf in parsed_files:
        # Build per-file import aliases: local name → qualified_name
        local_imports = _build_local_import_map(pf, dependency_map, name_index)

        for fn in pf.functions:
            all_nodes.add(fn.qualified_name)

            for callee_name in fn.calls:
                if callee_name in _ALL_BUILTINS:
                    continue

                resolved, is_res = _resolve_callee(
                    callee_name,
                    fn.qualified_name,
                    pf.file_path,
                    pf,
                    local_imports,
                    name_index,
                )

                edge = CallEdge(
                    caller_file=pf.file_path,
                    caller_function=fn.name,
                    caller_qualified=fn.qualified_name,
                    callee_name=callee_name,
                    callee_resolved=resolved,
                    call_line=fn.start_line,  # approximation
                    is_resolved=is_res,
                )
                edges.append(edge)

                if resolved and is_res:
                    all_nodes.add(resolved)
                    if resolved not in adjacency[fn.qualified_name]:
                        adjacency[fn.qualified_name].append(resolved)
                    if fn.qualified_name not in reverse_adj[resolved]:
                        reverse_adj[resolved].append(fn.qualified_name)

    return CallGraph(
        repo_owner=repo_owner,
        repo_name=repo_name,
        edges=edges,
        nodes=sorted(all_nodes),
        adjacency=dict(adjacency),
        reverse_adjacency=dict(reverse_adj),
    )


def find_orphan_functions(call_graph: CallGraph) -> list[str]:
    """
    Return functions never called by any other function.

    These are potential entry points or dead code.

    Args:
        call_graph: A fully built CallGraph.

    Returns:
        List of qualified function names with zero in-edges.
    """
    called = set(call_graph.reverse_adjacency.keys())
    return [n for n in call_graph.nodes if n not in called]


def find_hub_functions(call_graph: CallGraph, top_n: int = 10) -> list[str]:
    """
    Return the functions called by the most other functions.

    These are the "core utilities" of the codebase.

    Args:
        call_graph: A fully built CallGraph.
        top_n:      How many hubs to return.

    Returns:
        List of qualified function names sorted by call count descending.
    """
    in_degree = {
        fn: len(callers)
        for fn, callers in call_graph.reverse_adjacency.items()
    }
    return [fn for fn, _ in sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:top_n]]


def get_call_depth(call_graph: CallGraph, start_function: str) -> dict[str, int]:
    """
    BFS from start_function to compute call depth of each reachable function.

    Args:
        call_graph:     A fully built CallGraph.
        start_function: Qualified name of the starting function.

    Returns:
        Dict mapping qualified name → depth from start (0-indexed).
    """
    if start_function not in call_graph.adjacency:
        return {start_function: 0} if start_function in call_graph.nodes else {}

    visited: dict[str, int] = {start_function: 0}
    queue = [start_function]

    while queue:
        current = queue.pop(0)
        depth   = visited[current]
        for callee in call_graph.adjacency.get(current, []):
            if callee not in visited:
                visited[callee] = depth + 1
                queue.append(callee)

    return visited


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_local_import_map(
    pf: ParsedFile,
    dep_map: DependencyMap,
    name_index: dict[str, list[tuple[str, str]]],
) -> dict[str, str]:
    """
    Build a mapping from locally-imported names to their qualified names.

    For example, if a file does ``from services.user import UserService``,
    then ``{"UserService": "UserService"}`` is added so callee resolution
    can find it.
    """
    local_map: dict[str, str] = {}
    for imp in pf.imports:
        if not imp.is_local:
            continue
        for item in imp.imported_items:
            if item == "*":
                continue
            # Check if this item matches a known function
            matches = name_index.get(item, [])
            if len(matches) == 1:
                local_map[item] = matches[0][0]
    return local_map


def _resolve_callee(
    callee_name: str,
    caller_qualified: str,
    file_path: str,
    pf: ParsedFile,
    local_imports: dict[str, str],
    name_index: dict[str, list[tuple[str, str]]],
) -> tuple[Optional[str], bool]:
    """
    Attempt to resolve a callee name to its qualified name.

    Returns:
        ``(resolved_qualified_name, is_resolved)``
    """
    # 1. Check local imports first
    if callee_name in local_imports:
        return (local_imports[callee_name], True)

    # 2. Same-file functions
    same_file = [
        (qn, fp) for qn, fp in name_index.get(callee_name, [])
        if fp == file_path
    ]
    if same_file:
        return (same_file[0][0], True)

    # 3. Global name index — unambiguous match
    global_matches = name_index.get(callee_name, [])
    if len(global_matches) == 1:
        return (global_matches[0][0], True)

    # 4. Method call — "obj.method" — try to resolve "method" part
    if "." in callee_name:
        method = callee_name.split(".")[-1]
        method_matches = name_index.get(method, [])
        if len(method_matches) == 1:
            return (method_matches[0][0], True)

    # Unresolvable
    return (None, False)
