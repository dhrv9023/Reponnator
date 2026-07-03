"""
parsing/languages/java_parser.py — Java Parser

Handles .java files. Extracts classes, interfaces, methods,
constructors, Java annotations (as decorators), and import statements.
"""

from __future__ import annotations

from parsing import ParsedClass, ParsedFunction, ParsedImport, ParsedParameter
from parsing.base_parser import BaseParser
from config import MAX_FUNCTION_BODY_CHARS
from utils.logger import get_logger

logger = get_logger(__name__)


class JavaParser(BaseParser):
    """Java language parser."""

    language_name  = "java"
    language_label = "Java"

    def extract_functions(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedFunction]:
        fns: list[ParsedFunction] = []

        # Method declarations
        for node, cap in self._safe_query(
            "(method_declaration name: (identifier) @name) @method", tree.root_node
        ):
            if cap == "method":
                name_n = node.child_by_field_name("name")
                if name_n:
                    fns.append(self._build_java_method(node, self.get_node_text(name_n, source_bytes), source_bytes, file_path))

        # Constructor declarations
        for node, cap in self._safe_query(
            "(constructor_declaration name: (identifier) @name) @ctor", tree.root_node
        ):
            if cap == "ctor":
                name_n = node.child_by_field_name("name")
                if name_n:
                    fn = self._build_java_method(node, self.get_node_text(name_n, source_bytes), source_bytes, file_path)
                    fn.is_constructor = True
                    fns.append(fn)

        return fns

    def extract_classes(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedClass]:
        classes: list[ParsedClass] = []

        # Classes
        for node, cap in self._safe_query(
            "(class_declaration name: (identifier) @name) @class", tree.root_node
        ):
            if cap == "class":
                name_n = node.child_by_field_name("name")
                if not name_n:
                    continue
                name = self.get_node_text(name_n, source_bytes)
                src = self.get_node_text(node, source_bytes)
                superclass = node.child_by_field_name("superclass")
                bases = [self.get_node_text(superclass, source_bytes)] if superclass else []
                ifaces = node.child_by_field_name("interfaces")
                iface_list: list[str] = []
                if ifaces:
                    for ch in ifaces.named_children:
                        if ch.type == "type_list":
                            for t in ch.named_children:
                                iface_list.append(self.get_node_text(t, source_bytes))
                decorators = self._get_java_annotations(node, source_bytes)
                classes.append(ParsedClass(
                    name=name, qualified_name=name, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    docstring=self.get_docstring(node, source_bytes),
                    base_classes=bases, implemented_interfaces=iface_list,
                    is_abstract="abstract" in src[:src.index("{") if "{" in src else 50],
                    decorators=decorators,
                ))

        # Interfaces
        for node, cap in self._safe_query(
            "(interface_declaration name: (identifier) @name) @iface", tree.root_node
        ):
            if cap == "iface":
                name_n = node.child_by_field_name("name")
                if not name_n:
                    continue
                name = self.get_node_text(name_n, source_bytes)
                classes.append(ParsedClass(
                    name=name, qualified_name=name, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    is_interface=True,
                ))

        return classes

    def extract_imports(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedImport]:
        imports: list[ParsedImport] = []
        for node, cap in self._safe_query("(import_declaration) @import", tree.root_node):
            if cap == "import":
                src = self.get_node_text(node, source_bytes)
                # "import java.util.List;" → "java.util.List"
                module = src.replace("import", "").replace(";", "").replace("static", "").strip()
                is_stdlib, is_third, is_local = self.resolve_import_type(module, "Java")
                imports.append(ParsedImport(
                    file_path=file_path, line_number=node.start_point[0] + 1,
                    import_type="absolute", module=module,
                    is_stdlib=is_stdlib, is_third_party=is_third, is_local=is_local,
                ))
        return imports

    def extract_global_variables(self, tree, source_bytes: bytes, file_path: str) -> list[str]:
        # Java global vars are class-level fields — return empty for module level
        return []

    def detect_entry_point(self, tree, source_bytes: bytes, file_path: str) -> bool:
        src = source_bytes.decode("utf-8", errors="replace")
        return (
            "public static void main" in src
            or "@SpringBootApplication" in src
        )

    def _build_java_method(self, node, name: str, source_bytes: bytes, file_path: str) -> ParsedFunction:
        src = self.get_node_text(node, source_bytes)
        is_static  = "static " in src[:100]
        is_private = "private " in src[:100]
        is_async   = False  # Java doesn't have async keyword
        parent_class = self._find_parent_class_java(node, source_bytes)
        qualified  = f"{parent_class}.{name}" if parent_class else name
        annotations = self._get_java_annotations(node, source_bytes)
        params = self._extract_java_params(node, source_bytes)
        body = src
        return ParsedFunction(
            name=name, qualified_name=qualified, file_path=file_path,
            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
            parameters=params,
            body_preview=body[:200],
            full_body=body if len(body) <= MAX_FUNCTION_BODY_CHARS else "[TRUNCATED]",
            parent_class=parent_class, is_method=parent_class is not None,
            is_static=is_static, is_private=is_private, is_async=is_async,
            decorators=annotations,
            complexity_score=self.calculate_complexity(node, source_bytes),
        )

    def _find_parent_class_java(self, node, source_bytes: bytes):
        n = node.parent
        while n:
            if n.type == "class_declaration":
                name_n = n.child_by_field_name("name")
                return self.get_node_text(name_n, source_bytes) if name_n else None
            n = n.parent
        return None

    def _get_java_annotations(self, node, source_bytes: bytes) -> list[str]:
        anns: list[str] = []
        parent = node.parent
        if parent is None:
            return anns
        for child in parent.children:
            if child.id == node.id:
                break
            if child.type in ("marker_annotation", "annotation"):
                text = self.get_node_text(child, source_bytes).lstrip("@")
                anns.append(text.split("(")[0].strip())
        return anns

    def _extract_java_params(self, node, source_bytes: bytes) -> list[ParsedParameter]:
        params: list[ParsedParameter] = []
        fp = node.child_by_field_name("parameters")
        if fp is None:
            return params
        for child in fp.named_children:
            if child.type == "formal_parameter":
                name_n = child.child_by_field_name("name")
                type_n = child.child_by_field_name("type")
                name   = self.get_node_text(name_n, source_bytes) if name_n else ""
                ann    = self.get_node_text(type_n,  source_bytes) if type_n  else None
                params.append(ParsedParameter(name=name, type_annotation=ann))
            elif child.type == "spread_parameter":
                params.append(ParsedParameter(name="...", is_variadic=True))
        return params
