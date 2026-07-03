"""
parsing/languages/generic_parser.py — Regex-based Fallback Parser

Used for any language without a tree-sitter grammar in our registry.
Less accurate than the AST-based parsers but captures basic structure.
All results are marked with parse_method="regex_fallback" in parse_errors.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from parsing import ParsedClass, ParsedFunction, ParsedImport
from parsing.base_parser import BaseParser
from utils.logger import get_logger

logger = get_logger(__name__)

_FUNC_RE   = re.compile(
    r"(?:^|\n)[ \t]*(?:(?:pub|public|private|protected|static|async|def|func?|fn|void|int|string|bool|auto)\s+)*"
    r"(\w+)\s*\(([^)]*)\)",
    re.MULTILINE,
)
_CLASS_RE  = re.compile(
    r"(?:^|\n)[ \t]*(?:abstract\s+)?(?:class|struct|interface|trait|enum)\s+(\w+)",
    re.MULTILINE,
)
_IMPORT_RE = re.compile(
    r"(?:^|\n)[ \t]*(?:import|require|include|use|using|from|#include)\s+[\"'<]?([^\s\"';>]+)",
    re.MULTILINE,
)


class GenericParser(BaseParser):
    """
    Regex-based fallback parser for unsupported languages.

    Produces lower-fidelity results than AST-based parsers but never
    raises — always returns a valid ParsedFile.
    """

    language_name  = ""  # No tree-sitter grammar
    language_label = "Generic"

    def _ensure_parser(self) -> None:
        """No-op: generic parser uses regex, not tree-sitter."""
        pass

    def parse_file(self, file_path: str, source_code: str) -> object:
        """Override parse_file to use regex pipeline instead of tree-sitter."""
        from parsing import ParsedFile
        logger.warning("Using regex fallback parser for %r", file_path)
        total_lines = source_code.count("\n") + 1
        parse_errors = ["Using regex fallback parser (no tree-sitter grammar available)."]

        if not source_code.strip():
            return ParsedFile(
                file_path=file_path, language=self.language_label,
                sha="", size_bytes=len(source_code.encode()), total_lines=total_lines,
                parse_success=True,
            )

        functions = self._regex_functions(source_code, file_path)
        classes   = self._regex_classes(source_code, file_path)
        imports   = self._regex_imports(source_code, file_path)

        return ParsedFile(
            file_path=file_path,
            language=self.language_label,
            sha="",
            size_bytes=len(source_code.encode("utf-8", errors="replace")),
            total_lines=total_lines,
            functions=functions,
            classes=classes,
            imports=imports,
            parse_errors=parse_errors,
            parse_success=True,  # Partial success with regex
        )

    # The following are no-ops — parse_file is overridden
    def extract_functions(self, tree, source_bytes, file_path):
        return []

    def extract_classes(self, tree, source_bytes, file_path):
        return []

    def extract_imports(self, tree, source_bytes, file_path):
        return []

    def extract_global_variables(self, tree, source_bytes, file_path):
        return []

    def detect_entry_point(self, tree, source_bytes, file_path):
        return False

    def _regex_functions(self, source: str, file_path: str) -> list[ParsedFunction]:
        fns: list[ParsedFunction] = []
        seen: set[str] = set()
        for m in _FUNC_RE.finditer(source):
            name = m.group(1)
            if name in seen or name in ("if", "for", "while", "switch", "return"):
                continue
            seen.add(name)
            line = source[:m.start()].count("\n") + 1
            fns.append(ParsedFunction(
                name=name, qualified_name=name, file_path=file_path,
                start_line=line, end_line=line + 5,
                body_preview="", full_body="",
            ))
        return fns

    def _regex_classes(self, source: str, file_path: str) -> list[ParsedClass]:
        classes: list[ParsedClass] = []
        seen: set[str] = set()
        for m in _CLASS_RE.finditer(source):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            line = source[:m.start()].count("\n") + 1
            classes.append(ParsedClass(
                name=name, qualified_name=name, file_path=file_path,
                start_line=line, end_line=line + 10,
            ))
        return classes

    def _regex_imports(self, source: str, file_path: str) -> list[ParsedImport]:
        imports: list[ParsedImport] = []
        seen: set[str] = set()
        for m in _IMPORT_RE.finditer(source):
            module = m.group(1).rstrip(">;")
            if not module or module in seen:
                continue
            seen.add(module)
            line = source[:m.start()].count("\n") + 1
            is_local = module.startswith(".") or module.startswith("/")
            imports.append(ParsedImport(
                file_path=file_path, line_number=line,
                import_type="relative" if is_local else "absolute",
                module=module, is_local=is_local,
                is_third_party=not is_local,
            ))
        return imports
