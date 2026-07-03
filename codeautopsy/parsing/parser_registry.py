"""
parsing/parser_registry.py — Language-to-Parser Registry

Maps Phase 1 language labels (as they appear in manifest.json "language" fields)
to the correct parser instance.  Each parser is instantiated once and reused
across all files — parsers are stateless between parse_file() calls.
"""

from __future__ import annotations

from parsing.base_parser import BaseParser
from parsing.languages.cpp_parser import CppParser
from parsing.languages.generic_parser import GenericParser
from parsing.languages.go_parser import GoParser
from parsing.languages.java_parser import JavaParser
from parsing.languages.javascript_parser import JavaScriptParser
from parsing.languages.python_parser import PythonParser
from parsing.languages.rust_parser import RustParser
from parsing.languages.typescript_parser import TSXParser, TypeScriptParser
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Registry: Phase 1 language label → parser instance
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, BaseParser] = {
    "Python":     PythonParser(),
    "JavaScript": JavaScriptParser(),
    "TypeScript": TypeScriptParser(),
    "Java":       JavaParser(),
    "Go":         GoParser(),
    "Rust":       RustParser(),
    # C and C++ share the CppParser but with different grammars
    "C":          CppParser(file_extension=".c"),
    "C++":        CppParser(file_extension=".cpp"),
}

# Extension-to-parser overrides (for edge cases like .tsx, .jsx)
_EXTENSION_REGISTRY: dict[str, BaseParser] = {
    ".tsx": TSXParser(),
    ".jsx": JavaScriptParser(),
    ".mjs": JavaScriptParser(),
    ".cjs": JavaScriptParser(),
    ".h":   CppParser(file_extension=".h"),
    ".hpp": CppParser(file_extension=".hpp"),
}

_GENERIC = GenericParser()


def get_parser_for_language(language: str, file_path: str = "") -> BaseParser:
    """
    Return the appropriate parser for a given language label.

    Checks extension-specific overrides first, then the language registry,
    then falls back to the generic regex parser.

    Args:
        language:  Language label from Phase 1 manifest (e.g. ``"Python"``).
        file_path: Optional file path for extension-based override lookup.

    Returns:
        A :class:`~parsing.base_parser.BaseParser` instance ready for use.
    """
    # Extension override (highest priority)
    if file_path:
        ext = "." + file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        if ext in _EXTENSION_REGISTRY:
            return _EXTENSION_REGISTRY[ext]

    # Language registry
    if language in _REGISTRY:
        return _REGISTRY[language]

    logger.warning(
        "No parser registered for language %r (file: %r). "
        "Using regex fallback.",
        language, file_path,
    )
    return _GENERIC


def list_supported_languages() -> list[str]:
    """Return all language labels with dedicated parsers."""
    return sorted(_REGISTRY.keys())
