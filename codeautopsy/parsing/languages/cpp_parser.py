"""
parsing/languages/cpp_parser.py — C and C++ Parser

Handles .c, .h, .cpp, .cc, .cxx, .hpp, .hxx files.
Uses the 'cpp' grammar for C++ files and 'c' grammar for pure C files.
Extracts function definitions, class/struct declarations, includes,
preprocessor macros, and entry point detection.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from parsing import ParsedClass, ParsedFunction, ParsedImport, ParsedParameter
from parsing.base_parser import BaseParser
from config import MAX_FUNCTION_BODY_CHARS
from utils.logger import get_logger

logger = get_logger(__name__)

# C++ grammar handles both C and C++ files in tree-sitter-languages
_CPP_EXTENSIONS = frozenset({".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h++"})
_C_EXTENSIONS   = frozenset({".c", ".h"})

# Known third-party C/C++ library prefix indicators
_KNOWN_THIRD_PARTY_PREFIXES = ("boost/", "gtest/", "eigen/", "opencv/", "qt")


class CppParser(BaseParser):
    """C and C++ language parser."""

    language_label = "C++"  # Used for C++ files; overridden for C below

    def __init__(self, file_extension: str = ".cpp") -> None:
        super().__init__()
        ext = file_extension.lower()
        if ext in _C_EXTENSIONS:
            self.language_name  = "c"
            self.language_label = "C"
        else:
            self.language_name  = "cpp"
            self.language_label = "C++"

    def extract_functions(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedFunction]:
        fns: list[ParsedFunction] = []

        for node, cap in self._safe_query(
            "(function_definition) @func", tree.root_node
        ):
            if cap != "func":
                continue
            try:
                # Extract function name from declarator
                name = self._extract_func_name(node, source_bytes)
                if not name:
                    continue
                src = self.get_node_text(node, source_bytes)
                parent_class = self._find_class_scope(name)
                if "::" in name:
                    parts = name.split("::")
                    parent_class = parts[-2] if len(parts) >= 2 else None
                    name = parts[-1]

                qualified = f"{parent_class}.{name}" if parent_class else name
                is_private = self._check_access_private(node, source_bytes)

                fns.append(ParsedFunction(
                    name=name, qualified_name=qualified, file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    body_preview=src[:200],
                    full_body=src if len(src) <= MAX_FUNCTION_BODY_CHARS else "[TRUNCATED]",
                    parent_class=parent_class, is_method=parent_class is not None,
                    is_constructor=name == parent_class if parent_class else False,
                    is_private=is_private,
                    complexity_score=self.calculate_complexity(node, source_bytes),
                ))
            except Exception as exc:
                logger.debug("Error building C/C++ function in %r: %s", file_path, exc)

        return fns

    def extract_classes(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedClass]:
        classes: list[ParsedClass] = []

        for type_kw in ("class_specifier", "struct_specifier"):
            for node, cap in self._safe_query(f"({type_kw} name: (type_identifier) @name) @type", tree.root_node):
                if cap == "type":
                    name_n = node.child_by_field_name("name")
                    if not name_n:
                        continue
                    name = self.get_node_text(name_n, source_bytes)
                    # Base classes
                    bases: list[str] = []
                    base_clause = node.child_by_field_name("base_clause")
                    if base_clause:
                        for ch in base_clause.named_children:
                            if ch.type == "base_class_clause":
                                for sub in ch.named_children:
                                    if sub.type == "type_identifier":
                                        bases.append(self.get_node_text(sub, source_bytes))
                    src_text = self.get_node_text(node, source_bytes)
                    is_abstract = "= 0" in src_text
                    classes.append(ParsedClass(
                        name=name, qualified_name=name, file_path=file_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        base_classes=bases,
                        is_abstract=is_abstract,
                    ))

        return classes

    def extract_imports(self, tree, source_bytes: bytes, file_path: str) -> list[ParsedImport]:
        imports: list[ParsedImport] = []
        for node, cap in self._safe_query("(preproc_include) @include", tree.root_node):
            if cap != "include":
                continue
            src = self.get_node_text(node, source_bytes)
            # #include <stdio.h> or #include "myfile.h"
            if "<" in src:
                module = src.split("<")[1].split(">")[0].strip()
                is_local = False
                is_stdlib = not any(module.startswith(p) for p in _KNOWN_THIRD_PARTY_PREFIXES)
                is_third  = not is_stdlib
            elif '"' in src:
                module    = src.split('"')[1]
                is_local  = True
                is_stdlib = False
                is_third  = False
            else:
                continue

            imports.append(ParsedImport(
                file_path=file_path, line_number=node.start_point[0] + 1,
                import_type="relative" if is_local else "absolute",
                module=module, is_stdlib=is_stdlib, is_third_party=is_third, is_local=is_local,
            ))

        return imports

    def extract_global_variables(self, tree, source_bytes: bytes, file_path: str) -> list[str]:
        names: list[str] = []
        for node, cap in self._safe_query("(preproc_def name: (identifier) @name) @def", tree.root_node):
            if cap == "name":
                names.append(self.get_node_text(node, source_bytes))
        return names

    def detect_entry_point(self, tree, source_bytes: bytes, file_path: str) -> bool:
        src = source_bytes.decode("utf-8", errors="replace")
        return "int main(" in src

    def _extract_func_name(self, node, source_bytes: bytes) -> str:
        """Extract the function name from a function_definition node."""
        declarator = node.child_by_field_name("declarator")
        if declarator is None:
            return ""
        # Walk into nested declarators to find the identifier
        return self._find_identifier_in_declarator(declarator, source_bytes)

    def _find_identifier_in_declarator(self, node, source_bytes: bytes) -> str:
        """Recursively find the deepest identifier in a declarator chain."""
        if node.type == "identifier":
            return self.get_node_text(node, source_bytes)
        if node.type == "qualified_identifier":
            return self.get_node_text(node, source_bytes)
        if node.type == "destructor_name":
            return self.get_node_text(node, source_bytes)
        for child in node.named_children:
            result = self._find_identifier_in_declarator(child, source_bytes)
            if result:
                return result
        return ""

    def _find_class_scope(self, func_name: str) -> str | None:
        """For C++ scoped names like MyClass::method, extract the class."""
        if "::" in func_name:
            return func_name.rsplit("::", 1)[0]
        return None

    def _check_access_private(self, node, source_bytes: bytes) -> bool:
        """Heuristic: walk up to find if inside private: section."""
        n = node.parent
        while n:
            if n.type in ("class_specifier", "struct_specifier"):
                return False  # give up at class boundary
            if n.type == "access_specifier":
                text = self.get_node_text(n, source_bytes).strip().lower()
                return text.startswith("private")
            n = n.parent
        return False
