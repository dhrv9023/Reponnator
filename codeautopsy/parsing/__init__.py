"""
parsing/__init__.py — Shared Dataclasses and JSON Serialization

All Phase 2 data structures are defined here so every module imports
from a single location.  The ``to_json`` / ``from_json`` utilities
handle serialization of these types to and from disk.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ===========================================================================
# Core data structures
# ===========================================================================

@dataclasses.dataclass
class ParsedParameter:
    """One parameter of a function / method."""

    name: str
    type_annotation: Optional[str] = None   # None if untyped
    default_value:   Optional[str] = None   # None if no default
    is_variadic:     bool          = False  # *args / **kwargs / ...rest


@dataclasses.dataclass
class ParsedFunction:
    """A fully-extracted function or method from a source file."""

    name:           str
    qualified_name: str             # e.g. "UserService.get_user"
    file_path:      str
    start_line:     int
    end_line:       int
    parameters:     list[ParsedParameter] = dataclasses.field(default_factory=list)
    return_type:    Optional[str]  = None
    docstring:      Optional[str]  = None
    body_preview:   str            = ""     # first 200 chars of body
    full_body:      str            = ""     # complete source (may be "[TRUNCATED]")
    parent_class:   Optional[str]  = None   # None if module-level function
    is_method:      bool           = False
    is_constructor: bool           = False  # __init__, constructor, New()
    is_private:     bool           = False  # _ prefix, private keyword
    is_static:      bool           = False
    is_async:       bool           = False
    decorators:     list[str]      = dataclasses.field(default_factory=list)
    calls:          list[str]      = dataclasses.field(default_factory=list)
    complexity_score: int          = 0


@dataclasses.dataclass
class ParsedClass:
    """A fully-extracted class, struct, interface, or enum."""

    name:                   str
    qualified_name:         str
    file_path:              str
    start_line:             int
    end_line:               int
    docstring:              Optional[str]  = None
    base_classes:           list[str]      = dataclasses.field(default_factory=list)
    implemented_interfaces: list[str]      = dataclasses.field(default_factory=list)
    methods:                list[str]      = dataclasses.field(default_factory=list)  # qualified names
    class_variables:        list[str]      = dataclasses.field(default_factory=list)
    instance_variables:     list[str]      = dataclasses.field(default_factory=list)
    is_abstract:            bool           = False
    is_interface:           bool           = False
    decorators:             list[str]      = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ParsedImport:
    """One import statement from a source file."""

    file_path:      str
    line_number:    int
    import_type:    str            # "absolute", "relative", "dynamic", "star"
    module:         str            # "os.path", "pandas", "../utils"
    imported_items: list[str]      = dataclasses.field(default_factory=list)
    aliases:        dict[str, str] = dataclasses.field(default_factory=dict)
    is_stdlib:      bool           = False
    is_third_party: bool           = False
    is_local:       bool           = False
    is_conditional: bool           = False  # inside if/try block


@dataclasses.dataclass
class ParsedFile:
    """Complete parse result for one source file."""

    file_path:        str
    language:         str
    sha:              str
    size_bytes:       int
    total_lines:      int
    functions:        list[ParsedFunction] = dataclasses.field(default_factory=list)
    classes:          list[ParsedClass]    = dataclasses.field(default_factory=list)
    imports:          list[ParsedImport]   = dataclasses.field(default_factory=list)
    global_variables: list[str]            = dataclasses.field(default_factory=list)
    module_docstring: Optional[str]        = None
    is_entry_point:   bool                 = False
    has_main_block:   bool                 = False
    has_exports:      bool                 = False
    parse_errors:     list[str]            = dataclasses.field(default_factory=list)
    parse_success:    bool                 = True


@dataclasses.dataclass
class DependencyEdge:
    """One directed dependency from one file to another (or an external package)."""

    from_file:       str
    to_file:         Optional[str]   # None if external dependency
    to_module:       str             # original import string
    dependency_type: str             # "local", "stdlib", "third_party"
    imported_items:  list[str]       = dataclasses.field(default_factory=list)
    line_number:     int             = 0


@dataclasses.dataclass
class CallEdge:
    """One directed call from one function to another."""

    caller_file:      str
    caller_function:  str
    caller_qualified: str
    callee_name:      str             # raw name as it appears in code
    callee_resolved:  Optional[str]   # resolved qualified name if possible
    call_line:        int
    is_resolved:      bool            = False


@dataclasses.dataclass
class DependencyMap:
    """Complete cross-file import dependency graph for a repository."""

    repo_owner:           str
    repo_name:            str
    edges:                list[DependencyEdge]       = dataclasses.field(default_factory=list)
    external_dependencies: list[str]                 = dataclasses.field(default_factory=list)
    local_files:          list[str]                  = dataclasses.field(default_factory=list)
    adjacency:            dict[str, list[str]]       = dataclasses.field(default_factory=dict)
    reverse_adjacency:    dict[str, list[str]]       = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class CallGraph:
    """Complete function-level call graph for a repository."""

    repo_owner:        str
    repo_name:         str
    edges:             list[CallEdge]           = dataclasses.field(default_factory=list)
    nodes:             list[str]                = dataclasses.field(default_factory=list)
    adjacency:         dict[str, list[str]]     = dataclasses.field(default_factory=dict)
    reverse_adjacency: dict[str, list[str]]     = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ParseManifest:
    """Summary of a complete Phase 2 parse run."""

    codeautopsy_version:     str
    parse_timestamp:         str
    repo_owner:              str
    repo_name:               str
    total_files_parsed:      int
    total_files_failed:      int
    total_functions_extracted: int
    total_classes_extracted: int
    total_imports_extracted: int
    total_call_edges:        int
    total_dependency_edges:  int
    parse_duration_seconds:  float
    detected_patterns:       list[str]  = dataclasses.field(default_factory=list)
    entry_points:            list[str]  = dataclasses.field(default_factory=list)
    errors:                  list[str]  = dataclasses.field(default_factory=list)


# ===========================================================================
# JSON serialization helpers
# ===========================================================================

class _DataclassEncoder(json.JSONEncoder):
    """Custom encoder that handles dataclasses, datetime, Path, and sets."""

    def default(self, obj: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, (set, frozenset)):
            return sorted(obj)
        return super().default(obj)


def to_json(obj: Any, indent: int = 2) -> str:
    """
    Serialize any dataclass (or plain dict/list) to a JSON string.

    Handles nested dataclasses, datetime objects, Path objects, and sets.

    Args:
        obj:    The object to serialize. May be a dataclass, dict, or list.
        indent: JSON indentation level (default 2 for human-readability).

    Returns:
        Pretty-printed JSON string.
    """
    return json.dumps(obj, cls=_DataclassEncoder, indent=indent, ensure_ascii=False)


def save_json(obj: Any, path: Path) -> None:
    """
    Serialize *obj* and write it to *path*, creating parent dirs as needed.

    Args:
        obj:  Object to serialize.
        path: Destination file path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(obj), encoding="utf-8")


def load_json(path: Path) -> Any:
    """
    Load and return the parsed JSON content at *path*.

    Args:
        path: Source file path.

    Returns:
        Parsed Python object (dict, list, etc.).

    Raises:
        FileNotFoundError: If path does not exist.
        json.JSONDecodeError: If content is malformed.
    """
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    # Dataclasses
    "ParsedParameter",
    "ParsedFunction",
    "ParsedClass",
    "ParsedImport",
    "ParsedFile",
    "DependencyEdge",
    "CallEdge",
    "DependencyMap",
    "CallGraph",
    "ParseManifest",
    # Serialization
    "to_json",
    "save_json",
    "load_json",
]
