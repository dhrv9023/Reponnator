"""
parsing/languages/rust_parser.py — Rust Language Parser

Handles .rs files. Extracts fn items (including pub/async/unsafe),
impl block methods, struct/enum/trait types, use declarations,
and derive macros as decorators.
"""

from __future__ import annotations

from parsing import ParsedClass, ParsedFunction, ParsedImport, ParsedParameter
from parsing.base_parser import BaseParser
from config import MAX_FUNCTION_BODY_CHARS
from utils.logger import get_logger

logger = get_logger(__name__)


class RustParser(BaseParser):
    """Rust language parser."""

    language_name  = "rust"
    language_label = "Rust"

    def extract_functions(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedFunction]:
        fns: list[ParsedFunction] = []

        for node, cap in self._safe_query(
            "(function_item name: (identifier) @name) @func", tree.root_node
        ):
            if cap == "func":
                name_n = node.child_by_field_name("name")
                if not name_n:
                    continue
                name = self.get_node_text(name_n, source_bytes)
                src  = self.get_node_text(node, source_bytes)

                # public if "pub " precedes fn
                is_private = "pub " not in src.split("fn")[0]
                is_async   = "async " in src[:50]

                parent_class = self._find_parent_impl(node, source_bytes)
                qualified    = f"{parent_class}.{name}" if parent_class else name

                calls: list[str] = []
                seen: set[str] = set()
                for cn, cc in self._safe_query(
                    "(call_expression function: [(identifier) @c (field_expression field: (field_identifier) @c)]) @call",
                    node,
                ):
                    if cc == "c":
                        t = self.get_node_text(cn, source_bytes)
                        if t and t not in seen:
                            seen.add(t)
                            calls.append(t)

                # Decorators from attribute_items before this function
                decorators = self._get_rust_attributes(node, source_bytes)

                fns.append(ParsedFunction(
                    name=name, qualified_name=qualified, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    body_preview=src[:200],
                    full_body=src if len(src) <= MAX_FUNCTION_BODY_CHARS else "[TRUNCATED]",
                    parent_class=parent_class, is_method=parent_class is not None,
                    is_constructor=name in ("new", "with_capacity", "default"),
                    is_private=is_private, is_async=is_async,
                    decorators=decorators, calls=calls,
                    complexity_score=self.calculate_complexity(node, source_bytes),
                ))

        return fns

    def extract_classes(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedClass]:
        classes: list[ParsedClass] = []

        # Structs
        for node, cap in self._safe_query(
            "(struct_item name: (type_identifier) @name) @struct", tree.root_node
        ):
            if cap == "struct":
                name_n = node.child_by_field_name("name")
                if not name_n:
                    continue
                name = self.get_node_text(name_n, source_bytes)
                derives = self._get_rust_derives(node, source_bytes)
                classes.append(ParsedClass(
                    name=name, qualified_name=name, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    decorators=derives,
                ))

        # Enums
        for node, cap in self._safe_query(
            "(enum_item name: (type_identifier) @name) @enum", tree.root_node
        ):
            if cap == "enum":
                name_n = node.child_by_field_name("name")
                if not name_n:
                    continue
                name = self.get_node_text(name_n, source_bytes)
                derives = self._get_rust_derives(node, source_bytes)
                classes.append(ParsedClass(
                    name=name, qualified_name=name, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    decorators=["enum"] + derives,
                ))

        # Traits (interfaces)
        for node, cap in self._safe_query(
            "(trait_item name: (type_identifier) @name) @trait", tree.root_node
        ):
            if cap == "trait":
                name_n = node.child_by_field_name("name")
                if not name_n:
                    continue
                name = self.get_node_text(name_n, source_bytes)
                classes.append(ParsedClass(
                    name=name, qualified_name=name, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    is_interface=True, is_abstract=True,
                ))

        return classes

    def extract_imports(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedImport]:
        imports: list[ParsedImport] = []
        for node, cap in self._safe_query("(use_declaration) @use", tree.root_node):
            if cap == "use":
                src = self.get_node_text(node, source_bytes)
                module = src.replace("use ", "").replace(";", "").strip()
                is_stdlib, is_third, is_local = self.resolve_import_type(module, "Rust")
                imports.append(ParsedImport(
                    file_path=file_path,
                    line_number=node.start_point[0] + 1,
                    import_type="absolute", module=module,
                    is_stdlib=is_stdlib, is_third_party=is_third, is_local=is_local,
                ))
        return imports

    def extract_global_variables(self, tree, source_bytes: bytes, file_path: str) -> list[str]:
        names: list[str] = []
        for node, cap in self._safe_query(
            "(const_item name: (identifier) @name) @const", tree.root_node
        ):
            if cap == "name":
                names.append(self.get_node_text(node, source_bytes))
        for node, cap in self._safe_query(
            "(static_item name: (identifier) @name) @static", tree.root_node
        ):
            if cap == "name":
                names.append(self.get_node_text(node, source_bytes))
        return names

    def detect_entry_point(self, tree, source_bytes: bytes, file_path: str) -> bool:
        src = source_bytes.decode("utf-8", errors="replace")
        fname = file_path.split("/")[-1].lower()
        return "fn main()" in src or fname == "main.rs"

    def _find_parent_impl(self, node, source_bytes: bytes):
        n = node.parent
        while n:
            if n.type == "impl_item":
                type_n = n.child_by_field_name("type")
                return self.get_node_text(type_n, source_bytes) if type_n else None
            n = n.parent
        return None

    def _get_rust_attributes(self, node, source_bytes: bytes) -> list[str]:
        attrs: list[str] = []
        parent = node.parent
        if not parent:
            return attrs
        for child in parent.children:
            if child.id == node.id:
                break
            if child.type == "attribute_item":
                text = self.get_node_text(child, source_bytes).strip("#[]").strip()
                attrs.append(text)
        return attrs

    def _get_rust_derives(self, node, source_bytes: bytes) -> list[str]:
        derives: list[str] = []
        for attr in self._get_rust_attributes(node, source_bytes):
            if attr.startswith("derive"):
                # "derive(Debug, Clone)" → ["Debug", "Clone"]
                inner = attr[len("derive"):].strip("()").strip()
                derives.extend([d.strip() for d in inner.split(",")])
        return derives
