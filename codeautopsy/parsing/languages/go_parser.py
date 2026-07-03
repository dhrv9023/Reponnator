"""
parsing/languages/go_parser.py — Go Language Parser

Handles .go files. Extracts function declarations, methods with receivers,
struct types (as classes), interfaces, import declarations, and entry point
detection (func main in package main).
"""

from __future__ import annotations

from parsing import ParsedClass, ParsedFunction, ParsedImport, ParsedParameter
from parsing.base_parser import BaseParser
from config import MAX_FUNCTION_BODY_CHARS
from utils.logger import get_logger

logger = get_logger(__name__)


class GoParser(BaseParser):
    """Go language parser."""

    language_name  = "go"
    language_label = "Go"

    def extract_functions(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedFunction]:
        fns: list[ParsedFunction] = []

        # Regular function declarations
        for node, cap in self._safe_query(
            "(function_declaration name: (identifier) @name) @func", tree.root_node
        ):
            if cap == "func":
                name_n = node.child_by_field_name("name")
                if name_n:
                    fns.append(self._build_go_func(node, self.get_node_text(name_n, source_bytes), source_bytes, file_path))

        # Method declarations (with receiver)
        for node, cap in self._safe_query(
            "(method_declaration name: (field_identifier) @name) @method", tree.root_node
        ):
            if cap == "method":
                name_n = node.child_by_field_name("name")
                if not name_n:
                    continue
                name     = self.get_node_text(name_n, source_bytes)
                receiver = self._get_go_receiver(node, source_bytes)
                fns.append(self._build_go_func(node, name, source_bytes, file_path, parent_class=receiver))

        return fns

    def extract_classes(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedClass]:
        classes: list[ParsedClass] = []

        # Struct types
        for node, cap in self._safe_query(
            "(type_declaration (type_spec name: (type_identifier) @name type: (struct_type) @body)) @type",
            tree.root_node,
        ):
            if cap == "type":
                name_n = None
                for child, ccap in self._safe_query(
                    "(type_spec name: (type_identifier) @name) @ts", node
                ):
                    if ccap == "name":
                        name_n = child
                        break
                if not name_n:
                    continue
                name = self.get_node_text(name_n, source_bytes)
                # is_private: unexported = lowercase
                is_private = name[0].islower() if name else False
                classes.append(ParsedClass(
                    name=name, qualified_name=name, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    is_abstract=False, is_interface=False,
                ))

        # Interface types
        for node, cap in self._safe_query(
            "(type_declaration (type_spec name: (type_identifier) @name type: (interface_type))) @type",
            tree.root_node,
        ):
            if cap == "type":
                for child, ccap in self._safe_query(
                    "(type_spec name: (type_identifier) @name) @ts", node
                ):
                    if ccap == "name":
                        name = self.get_node_text(child, source_bytes)
                        classes.append(ParsedClass(
                            name=name, qualified_name=name, file_path=file_path,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            is_interface=True,
                        ))
                        break

        return classes

    def extract_imports(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedImport]:
        imports: list[ParsedImport] = []

        for node, cap in self._safe_query("(import_declaration) @import", tree.root_node):
            if cap == "import":
                for spec in self._safe_query(
                    '(import_spec path: (interpreted_string_literal) @path) @spec', node
                ):
                    spec_node, spec_cap = spec
                    if spec_cap == "path":
                        module = self.get_node_text(spec_node, source_bytes).strip('"')
                        is_stdlib, is_third, is_local = self.resolve_import_type(module, "Go")
                        imports.append(ParsedImport(
                            file_path=file_path,
                            line_number=spec_node.start_point[0] + 1,
                            import_type="absolute", module=module,
                            is_stdlib=is_stdlib, is_third_party=is_third, is_local=is_local,
                        ))

        return imports

    def extract_global_variables(self, tree, source_bytes: bytes, file_path: str) -> list[str]:
        names: list[str] = []
        for node, cap in self._safe_query(
            "(var_declaration (var_spec name: (identifier) @name)) @var", tree.root_node
        ):
            if cap == "name":
                names.append(self.get_node_text(node, source_bytes))
        for node, cap in self._safe_query(
            "(const_declaration (const_spec name: (identifier) @name)) @const", tree.root_node
        ):
            if cap == "name":
                names.append(self.get_node_text(node, source_bytes))
        return names

    def detect_entry_point(self, tree, source_bytes: bytes, file_path: str) -> bool:
        src = source_bytes.decode("utf-8", errors="replace")
        fname = file_path.split("/")[-1].lower()
        return "func main()" in src or fname == "main.go"

    def _build_go_func(
        self, node, name: str, source_bytes: bytes, file_path: str,
        parent_class=None
    ) -> ParsedFunction:
        # Unexported = starts with lowercase
        is_private = name[0].islower() if name else False
        # goroutine check: "go " keyword in body
        body_text  = self.get_node_text(node, source_bytes)
        is_async   = " go " in body_text or "\ngo " in body_text
        qualified  = f"{parent_class}.{name}" if parent_class else name

        # Calls
        calls: list[str] = []
        seen: set[str] = set()
        call_caps = self._safe_query(
            "(call_expression function: [(identifier) @call (selector_expression field: (field_identifier) @call)]) @c",
            node,
        )
        for cn, cc in call_caps:
            if cc == "call":
                t = self.get_node_text(cn, source_bytes)
                if t and t not in seen:
                    seen.add(t)
                    calls.append(t)

        return ParsedFunction(
            name=name, qualified_name=qualified, file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            body_preview=body_text[:200],
            full_body=body_text if len(body_text) <= MAX_FUNCTION_BODY_CHARS else "[TRUNCATED]",
            parent_class=parent_class, is_method=parent_class is not None,
            is_constructor=name in ("New", "new"),
            is_private=is_private, is_async=is_async,
            calls=calls,
            complexity_score=self.calculate_complexity(node, source_bytes),
        )

    def _get_go_receiver(self, method_node, source_bytes: bytes):
        """Extract the receiver type name from a method declaration."""
        recv = method_node.child_by_field_name("receiver")
        if recv is None:
            return None
        for child in recv.named_children:
            if child.type == "parameter_declaration":
                for sub in child.named_children:
                    if sub.type in ("type_identifier", "pointer_type"):
                        t = self.get_node_text(sub, source_bytes).lstrip("*")
                        return t
        return None
