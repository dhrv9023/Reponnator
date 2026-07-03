"""
parsing/languages/python_parser.py — Python-specific Tree-sitter Parser

Handles .py, .pyi, .pyw files. Extracts functions (including nested,
async, lambda), classes (including dataclasses, abstract, inner),
imports (absolute, relative, star, conditional), call relationships,
global variables, and entry point detection.
"""

from __future__ import annotations

import re
from typing import Optional

from tree_sitter import Node

from config import MAX_FUNCTION_BODY_CHARS
from parsing import (
    ParsedClass,
    ParsedFunction,
    ParsedImport,
    ParsedParameter,
)
from parsing.base_parser import BaseParser
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Tree-sitter query strings (validated against tree-sitter-languages 1.10.2)
# ---------------------------------------------------------------------------

_FUNC_QUERY = """
(function_definition
  name: (identifier) @func.name) @func.def
"""

_CLASS_QUERY = """
(class_definition
  name: (identifier) @class.name) @class.def
"""

_IMPORT_QUERY = """
[
  (import_statement) @import.simple
  (import_from_statement) @import.from
]
"""

_CALL_QUERY = """
[
  (call function: (identifier) @call.direct)
  (call function: (attribute attribute: (identifier) @call.method))
]
"""

_GLOBAL_QUERY = """
(module
  (expression_statement
    (assignment left: (identifier) @global.name)) @global.stmt)
"""

_DECORATOR_QUERY = """
(decorator) @decorator
"""


class PythonParser(BaseParser):
    """
    Python language parser using tree-sitter.

    Handles all standard Python patterns including nested functions,
    class methods, decorators, async functions, type annotations,
    instance variables from __init__, and conditional imports.
    """

    language_name  = "python"
    language_label = "Python"

    # -----------------------------------------------------------------------
    # Abstract method implementations
    # -----------------------------------------------------------------------

    def extract_functions(
        self, tree, source_bytes: bytes, file_path: str
    ) -> list[ParsedFunction]:
        """Extract all function definitions including nested and methods."""
        captures = self._safe_query(_FUNC_QUERY, tree.root_node)
        func_nodes: dict[int, Node] = {}
        func_names: dict[int, str] = {}

        for node, cap in captures:
            if cap == "func.name":
                func_names[node.parent.id] = self.get_node_text(node, source_bytes)
            elif cap == "func.def":
                func_nodes[node.id] = node

        functions: list[ParsedFunction] = []
        for node_id, func_node in func_nodes.items():
            name = func_names.get(node_id, "unknown")
            try:
                fn = self._build_function(func_node, name, source_bytes, file_path)
                functions.append(fn)
            except Exception as exc:
                logger.debug("Error building function %r in %r: %s", name, file_path, exc)

        # Also extract lambdas
        functions.extend(self._extract_lambdas(tree, source_bytes, file_path))
        return functions

    def extract_classes(
        self, tree, source_bytes: bytes, file_path: str
    ) -> list[ParsedClass]:
        """Extract all class definitions."""
        captures = self._safe_query(_CLASS_QUERY, tree.root_node)
        class_nodes: dict[int, Node] = {}
        class_names: dict[int, str] = {}

        for node, cap in captures:
            if cap == "class.name":
                class_names[node.parent.id] = self.get_node_text(node, source_bytes)
            elif cap == "class.def":
                class_nodes[node.id] = node

        classes: list[ParsedClass] = []
        for node_id, cls_node in class_nodes.items():
            name = class_names.get(node_id, "unknown")
            try:
                cls = self._build_class(cls_node, name, source_bytes, file_path)
                classes.append(cls)
            except Exception as exc:
                logger.debug("Error building class %r in %r: %s", name, file_path, exc)

        return classes

    def extract_imports(
        self, tree, source_bytes: bytes, file_path: str
    ) -> list[ParsedImport]:
        """Extract all import statements (simple, from, relative, conditional)."""
        captures = self._safe_query(_IMPORT_QUERY, tree.root_node)
        imports: list[ParsedImport] = []

        for node, cap in captures:
            try:
                parsed = self._parse_import_node(node, cap, source_bytes, file_path)
                if parsed:
                    imports.extend(parsed)
            except Exception as exc:
                logger.debug("Error parsing import in %r: %s", file_path, exc)

        return imports

    def extract_global_variables(
        self, tree, source_bytes: bytes, file_path: str
    ) -> list[str]:
        """Extract module-level variable and constant names."""
        captures = self._safe_query(_GLOBAL_QUERY, tree.root_node)
        names: list[str] = []
        seen: set[str] = set()

        for node, cap in captures:
            if cap == "global.name":
                name = self.get_node_text(node, source_bytes)
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)

        return names

    def detect_entry_point(
        self, tree, source_bytes: bytes, file_path: str
    ) -> bool:
        """Return True if the file contains a main block or is a known entry file."""
        src = source_bytes.decode("utf-8", errors="replace")
        has_main_block = "__name__" in src and "__main__" in src
        fname = file_path.split("/")[-1].lower()
        is_entry_file = fname in (
            "main.py", "app.py", "server.py", "run.py", "cli.py",
            "manage.py", "wsgi.py", "asgi.py", "__main__.py",
        )
        return has_main_block or is_entry_file

    # -----------------------------------------------------------------------
    # Python-specific helpers
    # -----------------------------------------------------------------------

    def _build_function(
        self,
        func_node: Node,
        name: str,
        source_bytes: bytes,
        file_path: str,
    ) -> ParsedFunction:
        """Build a ParsedFunction from a function_definition AST node."""
        start_line = func_node.start_point[0] + 1
        end_line   = func_node.end_point[0] + 1

        # Parent class (if inside class body)
        parent_class = self._find_parent_class(func_node, source_bytes)
        qualified    = f"{parent_class}.{name}" if parent_class else name
        is_method    = parent_class is not None
        is_constructor = name == "__init__" and is_method

        # Async
        is_async = any(c.type == "async" for c in func_node.children)

        # Private: single _ prefix (not dunder)
        is_private = name.startswith("_") and not (
            name.startswith("__") and name.endswith("__") and len(name) > 4
        )

        # Decorators
        decorators = self._get_decorators(func_node, source_bytes)
        is_static  = "staticmethod" in decorators or "classmethod" in decorators

        # Parameters
        params = self._extract_params(func_node, source_bytes)

        # Return type
        return_type = self._get_return_type(func_node, source_bytes)

        # Docstring
        docstring = self.get_docstring(func_node, source_bytes)

        # Body
        full_body    = self.get_node_text(func_node, source_bytes)
        body_preview = full_body[:200]
        if len(full_body) > MAX_FUNCTION_BODY_CHARS:
            full_body = "[TRUNCATED — see source file]"

        # Calls
        calls = self._extract_calls_in_node(func_node, source_bytes)

        # Complexity
        complexity = self.calculate_complexity(func_node, source_bytes)

        return ParsedFunction(
            name=name,
            qualified_name=qualified,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            parameters=params,
            return_type=return_type,
            docstring=docstring,
            body_preview=body_preview,
            full_body=full_body,
            parent_class=parent_class,
            is_method=is_method,
            is_constructor=is_constructor,
            is_private=is_private,
            is_static=is_static,
            is_async=is_async,
            decorators=decorators,
            calls=calls,
            complexity_score=complexity,
        )

    def _build_class(
        self,
        cls_node: Node,
        name: str,
        source_bytes: bytes,
        file_path: str,
    ) -> ParsedClass:
        """Build a ParsedClass from a class_definition AST node."""
        start_line = cls_node.start_point[0] + 1
        end_line   = cls_node.end_point[0] + 1

        # Base classes
        base_classes = self._get_base_classes(cls_node, source_bytes)

        # Docstring
        docstring = self.get_docstring(cls_node, source_bytes)

        # Decorators
        decorators = self._get_decorators(cls_node, source_bytes)

        # is_abstract: has @abstractmethod anywhere in body, or ABC in bases
        src_text = self.get_node_text(cls_node, source_bytes)
        is_abstract = (
            "@abstractmethod" in src_text
            or "ABC" in base_classes
            or "ABCMeta" in decorators
        )

        # Collect methods from body
        methods, class_vars, instance_vars = self._collect_class_members(
            cls_node, name, source_bytes
        )

        return ParsedClass(
            name=name,
            qualified_name=name,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
            base_classes=base_classes,
            implemented_interfaces=[],
            methods=methods,
            class_variables=class_vars,
            instance_variables=instance_vars,
            is_abstract=is_abstract,
            is_interface=False,
            decorators=decorators,
        )

    def _parse_import_node(
        self,
        node: Node,
        cap: str,
        source_bytes: bytes,
        file_path: str,
    ) -> list[ParsedImport]:
        """Parse an import_statement or import_from_statement node."""
        line = node.start_point[0] + 1
        is_conditional = self._is_in_conditional_block(node)
        results: list[ParsedImport] = []

        if cap == "import.simple":
            # import os, import pathlib.Path
            for child in node.named_children:
                if child.type in ("dotted_name", "aliased_import"):
                    if child.type == "aliased_import":
                        module_node = child.child_by_field_name("name")
                        alias_node  = child.child_by_field_name("alias")
                        module = self.get_node_text(module_node, source_bytes) if module_node else ""
                        alias  = self.get_node_text(alias_node,  source_bytes) if alias_node  else ""
                        aliases = {alias: module} if alias else {}
                    else:
                        module  = self.get_node_text(child, source_bytes)
                        aliases = {}

                    is_stdlib, is_third, is_local = self.resolve_import_type(module, "Python")
                    results.append(ParsedImport(
                        file_path=file_path,
                        line_number=line,
                        import_type="absolute",
                        module=module,
                        imported_items=[],
                        aliases=aliases,
                        is_stdlib=is_stdlib,
                        is_third_party=is_third,
                        is_local=is_local,
                        is_conditional=is_conditional,
                    ))

        elif cap == "import.from":
            # from os import path, from .utils import helper
            module_node = node.child_by_field_name("module_name")
            if module_node is None:
                # relative import: from . import something
                module = "."
            else:
                module = self.get_node_text(module_node, source_bytes)

            # relative import detection
            is_relative = module.startswith(".") or any(
                c.type == "relative_import" for c in node.children
            )
            # Check for relative_import node
            for c in node.children:
                if c.type == "relative_import":
                    module = self.get_node_text(c, source_bytes)
                    is_relative = True
                    break

            # Collect imported names
            imported_items: list[str] = []
            aliases: dict[str, str] = {}
            for child in node.named_children:
                if child.type == "dotted_name" and child != module_node:
                    imported_items.append(self.get_node_text(child, source_bytes))
                elif child.type == "aliased_import":
                    name_n  = child.child_by_field_name("name")
                    alias_n = child.child_by_field_name("alias")
                    item    = self.get_node_text(name_n,  source_bytes) if name_n  else ""
                    alias   = self.get_node_text(alias_n, source_bytes) if alias_n else ""
                    if item:
                        imported_items.append(item)
                    if alias and item:
                        aliases[alias] = item
                elif child.type == "wildcard_import":
                    imported_items = ["*"]

            import_type = "relative" if is_relative else "absolute"
            is_stdlib, is_third, is_local = self.resolve_import_type(module, "Python")
            if is_relative:
                is_local   = True
                is_stdlib  = False
                is_third   = False

            results.append(ParsedImport(
                file_path=file_path,
                line_number=line,
                import_type=import_type,
                module=module,
                imported_items=imported_items,
                aliases=aliases,
                is_stdlib=is_stdlib,
                is_third_party=is_third,
                is_local=is_local,
                is_conditional=is_conditional,
            ))

        return results

    def _extract_params(self, func_node: Node, source_bytes: bytes) -> list[ParsedParameter]:
        """Extract function parameters with types and defaults."""
        params: list[ParsedParameter] = []
        params_node = func_node.child_by_field_name("parameters")
        if params_node is None:
            return params

        for child in params_node.named_children:
            try:
                params.extend(self._parse_param(child, source_bytes))
            except Exception:
                pass
        return params

    def _parse_param(self, node: Node, source_bytes: bytes) -> list[ParsedParameter]:
        """Parse a single parameter node into ParsedParameter(s)."""
        t = node.type
        name_text = self.get_node_text(node, source_bytes)

        if t == "identifier":
            return [ParsedParameter(name=name_text)]

        if t == "typed_parameter":
            name_n = node.child_by_field_name("name") or node.named_children[0]
            type_n = node.child_by_field_name("type")
            name   = self.get_node_text(name_n, source_bytes) if name_n else name_text
            ann    = self.get_node_text(type_n,  source_bytes) if type_n  else None
            return [ParsedParameter(name=name, type_annotation=ann)]

        if t == "default_parameter":
            name_n    = node.child_by_field_name("name")
            default_n = node.child_by_field_name("value")
            name      = self.get_node_text(name_n,    source_bytes) if name_n    else name_text
            default   = self.get_node_text(default_n, source_bytes) if default_n else None
            return [ParsedParameter(name=name, default_value=default)]

        if t == "typed_default_parameter":
            name_n    = node.child_by_field_name("name")
            type_n    = node.child_by_field_name("type")
            default_n = node.child_by_field_name("value")
            name      = self.get_node_text(name_n,    source_bytes) if name_n    else name_text
            ann       = self.get_node_text(type_n,    source_bytes) if type_n    else None
            default   = self.get_node_text(default_n, source_bytes) if default_n else None
            return [ParsedParameter(name=name, type_annotation=ann, default_value=default)]

        if t in ("list_splat_pattern", "dictionary_splat_pattern"):
            inner = node.named_children[0] if node.named_children else node
            name  = self.get_node_text(inner, source_bytes)
            return [ParsedParameter(name=name, is_variadic=True)]

        return []

    def _get_return_type(self, func_node: Node, source_bytes: bytes) -> Optional[str]:
        """Extract the return type annotation if present."""
        rt = func_node.child_by_field_name("return_type")
        return self.get_node_text(rt, source_bytes).lstrip("->").strip() if rt else None

    def _get_decorators(self, node: Node, source_bytes: bytes) -> list[str]:
        """Collect decorator names applied to a function or class node."""
        decorators: list[str] = []
        # Walk previous siblings
        parent = node.parent
        if parent is None:
            return decorators
        found = False
        for child in parent.children:
            if child.id == node.id:
                found = True
                break
            if child.type == "decorator":
                # Get everything after the '@'
                text = self.get_node_text(child, source_bytes).lstrip("@").strip()
                # Take only the first line (decorator args omitted)
                text = text.splitlines()[0].split("(")[0].strip()
                decorators.append(text)
        return decorators if found else []

    def _get_base_classes(self, cls_node: Node, source_bytes: bytes) -> list[str]:
        """Extract parent class names from a class definition."""
        bases: list[str] = []
        args = cls_node.child_by_field_name("superclasses")
        if args is None:
            return bases
        for child in args.named_children:
            if child.type not in ("comment",):
                text = self.get_node_text(child, source_bytes).strip()
                if text:
                    bases.append(text)
        return bases

    def _find_parent_class(self, func_node: Node, source_bytes: bytes) -> Optional[str]:
        """Walk up the AST to find if this function is inside a class body."""
        node = func_node.parent
        while node is not None:
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    return self.get_node_text(name_node, source_bytes)
            if node.type == "module":
                break
            node = node.parent
        return None

    def _collect_class_members(
        self, cls_node: Node, class_name: str, source_bytes: bytes
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Return (method_qnames, class_vars, instance_vars) for a class node.
        """
        methods: list[str] = []
        class_vars: list[str] = []
        instance_vars: list[str] = []

        body = cls_node.child_by_field_name("body")
        if body is None:
            return methods, class_vars, instance_vars

        for child in body.named_children:
            if child.type == "function_definition":
                name_n = child.child_by_field_name("name")
                if name_n:
                    mname = self.get_node_text(name_n, source_bytes)
                    methods.append(f"{class_name}.{mname}")
                    # Instance vars from __init__
                    if mname == "__init__":
                        instance_vars.extend(
                            self._collect_self_assignments(child, source_bytes)
                        )
            elif child.type in ("expression_statement", "assignment"):
                # Class-level variable
                target = child.child_by_field_name("left") or (
                    child.named_children[0] if child.named_children else None
                )
                if target and target.type == "identifier":
                    class_vars.append(self.get_node_text(target, source_bytes))

        return methods, class_vars, instance_vars

    def _collect_self_assignments(self, init_node: Node, source_bytes: bytes) -> list[str]:
        """Find self.x = … assignments inside __init__."""
        names: list[str] = []
        body = init_node.child_by_field_name("body")
        if body is None:
            return names

        for stmt in body.children:
            if stmt.type in ("expression_statement",):
                for child in stmt.named_children:
                    if child.type == "assignment":
                        left = child.child_by_field_name("left")
                        if left and left.type == "attribute":
                            obj = left.child_by_field_name("object")
                            attr = left.child_by_field_name("attribute")
                            if obj and self.get_node_text(obj, source_bytes) == "self":
                                if attr:
                                    names.append(self.get_node_text(attr, source_bytes))
        return names

    def _extract_calls_in_node(self, func_node: Node, source_bytes: bytes) -> list[str]:
        """Extract all function/method call names within a function body."""
        captures = self._safe_query(_CALL_QUERY, func_node)
        calls: list[str] = []
        seen: set[str] = set()
        for node, cap in captures:
            name = self.get_node_text(node, source_bytes)
            if name and name not in seen:
                seen.add(name)
                calls.append(name)
        return calls

    def _extract_lambdas(
        self, tree, source_bytes: bytes, file_path: str
    ) -> list[ParsedFunction]:
        """Extract lambda functions with auto-generated names."""
        q_str = "(lambda) @lambda"
        captures = self._safe_query(q_str, tree.root_node)
        lambdas: list[ParsedFunction] = []
        for node, _ in captures:
            line = node.start_point[0] + 1
            name = f"lambda_line_{line}"
            body = self.get_node_text(node, source_bytes)
            lambdas.append(ParsedFunction(
                name=name,
                qualified_name=name,
                file_path=file_path,
                start_line=line,
                end_line=node.end_point[0] + 1,
                body_preview=body[:200],
                full_body=body,
                is_private=False,
            ))
        return lambdas

    def _is_in_conditional_block(self, node: Node) -> bool:
        """Return True if an import node is inside an if or try block."""
        parent = node.parent
        while parent is not None:
            if parent.type in ("if_statement", "try_statement"):
                return True
            if parent.type == "module":
                break
            parent = parent.parent
        return False
