"""
parsing/languages/typescript_parser.py — TypeScript/TSX Parser

Extends JavaScriptParser. Adds TypeScript-specific patterns:
interfaces, type aliases, enums, abstract classes, access modifiers,
and generic type parameters.
"""

from __future__ import annotations

from parsing import ParsedClass, ParsedFunction, ParsedImport
from parsing.languages.javascript_parser import JavaScriptParser
from utils.logger import get_logger

logger = get_logger(__name__)


class TypeScriptParser(JavaScriptParser):
    """TypeScript/TSX language parser — extends JavaScript parser."""

    language_name  = "typescript"
    language_label = "TypeScript"

    def extract_classes(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedClass]:
        """Extends JS class extraction with interfaces, enums, abstract classes."""
        classes = super().extract_classes(tree, source_bytes, file_path)

        # Interfaces
        for node, cap in self._safe_query(
            "(interface_declaration name: (type_identifier) @name) @iface",
            tree.root_node,
        ):
            if cap == "iface":
                name_n = node.child_by_field_name("name")
                if not name_n:
                    continue
                name = self.get_node_text(name_n, source_bytes)

                # Heritage (extends for interfaces)
                bases: list[str] = []
                heritage = node.child_by_field_name("extends_clause")
                if heritage:
                    for ch in heritage.named_children:
                        bases.append(self.get_node_text(ch, source_bytes))

                classes.append(ParsedClass(
                    name=name, qualified_name=name, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    base_classes=bases,
                    is_interface=True,
                    is_abstract=False,
                ))

        # Enums
        for node, cap in self._safe_query(
            "(enum_declaration name: (identifier) @name) @enum",
            tree.root_node,
        ):
            if cap == "enum":
                name_n = node.child_by_field_name("name")
                if not name_n:
                    continue
                name = self.get_node_text(name_n, source_bytes)
                classes.append(ParsedClass(
                    name=name, qualified_name=name, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    decorators=["enum"],
                ))

        # Abstract class detection — patch existing classes
        src = source_bytes.decode("utf-8", errors="replace")
        for cls in classes:
            if not cls.is_interface:
                line_start = cls.start_line - 1
                lines = src.splitlines()
                if 0 <= line_start < len(lines):
                    line_text = lines[line_start]
                    if "abstract class" in line_text:
                        cls.is_abstract = True

        return classes

    def extract_functions(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedFunction]:
        """Extends JS function extraction with TS access modifiers."""
        fns = super().extract_functions(tree, source_bytes, file_path)

        # Patch is_private based on TypeScript access modifiers
        src = source_bytes.decode("utf-8", errors="replace")
        lines = src.splitlines()
        for fn in fns:
            idx = fn.start_line - 1
            if 0 <= idx < len(lines):
                line = lines[idx]
                if "private " in line:
                    fn.is_private = True
                elif "public " in line or "protected " in line:
                    # keep as-is (public = not private, protected = not private)
                    pass

        return fns

    def detect_entry_point(self, tree, source_bytes: bytes, file_path: str) -> bool:
        fname = file_path.split("/")[-1].lower()
        src = source_bytes.decode("utf-8", errors="replace")
        return (
            fname in ("index.ts", "index.tsx", "server.ts", "app.ts", "main.ts")
            or "process.argv" in src
        )


class TSXParser(TypeScriptParser):
    """TSX (TypeScript + JSX) parser."""

    language_name  = "tsx"
    language_label = "TypeScript"
