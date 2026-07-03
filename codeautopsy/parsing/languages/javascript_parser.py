"""
parsing/languages/javascript_parser.py — JavaScript/JSX Parser

Handles .js, .mjs, .cjs, .jsx files.
Extracts function declarations, arrow functions, function expressions,
class methods, CommonJS require() and ES6 import statements, exports,
and call relationships.
"""

from __future__ import annotations

from typing import Optional

from tree_sitter import Node

from config import MAX_FUNCTION_BODY_CHARS
from parsing import ParsedClass, ParsedFunction, ParsedImport, ParsedParameter
from parsing.base_parser import BaseParser
from utils.logger import get_logger

logger = get_logger(__name__)

_FUNC_DECL_QUERY = "(function_declaration name: (identifier) @name) @func"
_METHOD_DEF_QUERY = "(method_definition name: (property_identifier) @name) @method"
_ARROW_QUERY      = "(variable_declarator name: (identifier) @name value: [(arrow_function)(function)] @body) @arrow_decl"
_CLASS_QUERY      = "(class_declaration name: (identifier) @name) @class"
_CALL_QUERY       = """
[
  (call_expression function: (identifier) @call.direct)
  (call_expression function: (member_expression property: (property_identifier) @call.method))
]
"""
_REQUIRE_QUERY    = "(call_expression function: (identifier) @fn arguments: (arguments (string) @module)) @require"
_IMPORT_QUERY     = "(import_statement) @import"
_EXPORT_QUERY     = "(export_statement) @export"


class JavaScriptParser(BaseParser):
    """JavaScript/JSX language parser."""

    language_name  = "javascript"
    language_label = "JavaScript"

    def extract_functions(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedFunction]:
        fns: list[ParsedFunction] = []

        # 1. function declarations
        for node, cap in self._safe_query(_FUNC_DECL_QUERY, tree.root_node):
            if cap == "func":
                name_n = node.child_by_field_name("name")
                if name_n:
                    fns.append(self._build_js_function(node, self.get_node_text(name_n, source_bytes), source_bytes, file_path))

        # 2. arrow functions and function expressions assigned to variables
        seen_arrows: set[int] = set()
        for node, cap in self._safe_query(_ARROW_QUERY, tree.root_node):
            if cap == "arrow_decl" and node.id not in seen_arrows:
                seen_arrows.add(node.id)
                name_n = node.child_by_field_name("name")
                val_n  = node.child_by_field_name("value")
                if name_n and val_n:
                    fns.append(self._build_js_function(val_n, self.get_node_text(name_n, source_bytes), source_bytes, file_path))

        # 3. class methods
        for node, cap in self._safe_query(_METHOD_DEF_QUERY, tree.root_node):
            if cap == "name":
                method_node = node.parent  # method_definition
                if method_node:
                    parent_class = self._find_parent_class_js(method_node, source_bytes)
                    mname = self.get_node_text(node, source_bytes)
                    fns.append(self._build_js_function(
                        method_node, mname, source_bytes, file_path,
                        parent_class=parent_class,
                    ))

        return fns

    def extract_classes(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedClass]:
        classes: list[ParsedClass] = []
        for node, cap in self._safe_query(_CLASS_QUERY, tree.root_node):
            if cap == "class":
                name_n = node.child_by_field_name("name")
                if not name_n:
                    continue
                name = self.get_node_text(name_n, source_bytes)
                # Heritage: walk children for 'extends' clause
                bases: list[str] = []
                for child in node.children:
                    if child.type == "class_heritage":
                        for sub in child.named_children:
                            t = self.get_node_text(sub, source_bytes).strip()
                            if t:
                                bases.append(t)

                # Collect method names
                methods: list[str] = []
                body = node.child_by_field_name("body")
                if body:
                    for child in body.named_children:
                        if child.type == "method_definition":
                            mn = child.child_by_field_name("name")
                            if mn:
                                methods.append(f"{name}.{self.get_node_text(mn, source_bytes)}")

                classes.append(ParsedClass(
                    name=name, qualified_name=name, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    docstring=self.get_docstring(node, source_bytes),
                    base_classes=bases, methods=methods,
                ))
        return classes

    def extract_imports(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedImport]:
        imports: list[ParsedImport] = []

        # ES6 imports
        for node, cap in self._safe_query(_IMPORT_QUERY, tree.root_node):
            if cap == "import":
                imports.extend(self._parse_es6_import(node, source_bytes, file_path))

        # CommonJS require()
        for node, cap in self._safe_query(_REQUIRE_QUERY, tree.root_node):
            if cap == "require":
                fn_n = None
                mod_n = None
                for child, ccap in self._safe_query(_REQUIRE_QUERY, node):
                    if ccap == "fn": fn_n = child
                    if ccap == "module": mod_n = child
                if mod_n:
                    fn_text = self.get_node_text(fn_n, source_bytes) if fn_n else ""
                    if fn_text == "require":
                        module = self.get_node_text(mod_n, source_bytes).strip("\"'")
                        is_stdlib, is_third, is_local = self.resolve_import_type(module, "JavaScript")
                        imports.append(ParsedImport(
                            file_path=file_path, line_number=node.start_point[0] + 1,
                            import_type="absolute", module=module,
                            is_stdlib=is_stdlib, is_third_party=is_third, is_local=is_local,
                        ))
        return imports

    def extract_global_variables(self, tree, source_bytes: bytes, file_path: str) -> list[str]:
        names: list[str] = []
        q = "(lexical_declaration (variable_declarator name: (identifier) @name)) @decl"
        for node, cap in self._safe_query(q, tree.root_node):
            if cap == "name" and node.parent and node.parent.parent and node.parent.parent.parent:
                if node.parent.parent.parent.type in ("program", "module"):
                    names.append(self.get_node_text(node, source_bytes))
        return names

    def detect_entry_point(self, tree, source_bytes: bytes, file_path: str) -> bool:
        fname = file_path.split("/")[-1].lower()
        src = source_bytes.decode("utf-8", errors="replace")
        return (
            fname in ("index.js", "server.js", "app.js", "main.js")
            or "process.argv" in src
            or "http.createServer" in src
            or "express()" in src
            or "ReactDOM.render" in src
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _build_js_function(
        self, node: Node, name: str, source_bytes: bytes,
        file_path: str, parent_class: Optional[str] = None,
    ) -> ParsedFunction:
        start = node.start_point[0] + 1
        end   = node.end_point[0] + 1
        is_async = any(c.type == "async" for c in node.children) or \
                   self.get_node_text(node, source_bytes).startswith("async")
        is_method = parent_class is not None
        is_private = name.startswith("_") or name.startswith("#")
        is_constructor = name in ("constructor",)
        qualified = f"{parent_class}.{name}" if parent_class else name
        body = self.get_node_text(node, source_bytes)
        calls = self._extract_calls_js(node, source_bytes)
        params = self._extract_params_js(node, source_bytes)

        return ParsedFunction(
            name=name, qualified_name=qualified, file_path=file_path,
            start_line=start, end_line=end, parameters=params,
            body_preview=body[:200],
            full_body=body if len(body) <= MAX_FUNCTION_BODY_CHARS else "[TRUNCATED]",
            parent_class=parent_class, is_method=is_method,
            is_constructor=is_constructor, is_private=is_private,
            is_async=is_async, calls=calls,
            complexity_score=self.calculate_complexity(node, source_bytes),
        )

    def _extract_calls_js(self, func_node: Node, source_bytes: bytes) -> list[str]:
        caps = self._safe_query(_CALL_QUERY, func_node)
        calls: list[str] = []
        seen: set[str] = set()
        for node, cap in caps:
            name = self.get_node_text(node, source_bytes)
            if name and name not in seen:
                seen.add(name)
                calls.append(name)
        return calls

    def _extract_params_js(self, func_node: Node, source_bytes: bytes) -> list[ParsedParameter]:
        params: list[ParsedParameter] = []
        for child in func_node.children:
            if child.type == "formal_parameters":
                for p in child.named_children:
                    if p.type == "identifier":
                        params.append(ParsedParameter(name=self.get_node_text(p, source_bytes)))
                    elif p.type == "rest_pattern":
                        inner = p.named_children[0] if p.named_children else p
                        params.append(ParsedParameter(name=self.get_node_text(inner, source_bytes), is_variadic=True))
                    elif p.type == "assignment_pattern":
                        left = p.child_by_field_name("left")
                        right = p.child_by_field_name("right")
                        name = self.get_node_text(left, source_bytes) if left else ""
                        default = self.get_node_text(right, source_bytes) if right else None
                        params.append(ParsedParameter(name=name, default_value=default))
                break
        return params

    def _find_parent_class_js(self, node: Node, source_bytes: bytes) -> Optional[str]:
        n = node.parent
        while n:
            if n.type == "class_declaration":
                name_n = n.child_by_field_name("name")
                return self.get_node_text(name_n, source_bytes) if name_n else None
            n = n.parent
        return None

    def _parse_es6_import(self, node: Node, source_bytes: bytes, file_path: str) -> list[ParsedImport]:
        line = node.start_point[0] + 1
        module = ""
        imported_items: list[str] = []
        aliases: dict[str, str] = {}

        for child in node.named_children:
            if child.type == "string":
                module = self.get_node_text(child, source_bytes).strip("\"'")
            elif child.type == "import_clause":
                for ic in child.named_children:
                    if ic.type == "identifier":
                        imported_items.append(self.get_node_text(ic, source_bytes))
                    elif ic.type == "named_imports":
                        for ni in ic.named_children:
                            if ni.type == "import_specifier":
                                name_n  = ni.child_by_field_name("name")
                                alias_n = ni.child_by_field_name("alias")
                                item    = self.get_node_text(name_n,  source_bytes) if name_n  else ""
                                alias   = self.get_node_text(alias_n, source_bytes) if alias_n else ""
                                if item:
                                    imported_items.append(item)
                                if alias and item:
                                    aliases[alias] = item
                    elif ic.type == "namespace_import":
                        inner = ic.named_children[-1] if ic.named_children else None
                        if inner:
                            aliases[self.get_node_text(inner, source_bytes)] = "*"

        if not module:
            return []

        is_stdlib, is_third, is_local = self.resolve_import_type(module, "JavaScript")
        return [ParsedImport(
            file_path=file_path, line_number=line,
            import_type="relative" if module.startswith(".") else "absolute",
            module=module, imported_items=imported_items, aliases=aliases,
            is_stdlib=is_stdlib, is_third_party=is_third, is_local=is_local,
        )]
