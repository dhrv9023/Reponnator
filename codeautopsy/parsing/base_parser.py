"""
parsing/base_parser.py — Abstract Base Class for All Language Parsers

Every language-specific parser extends BaseParser and must implement the
five abstract extraction methods.  The concrete shared logic in this class
handles: parser initialisation, encoding, minified-file detection, timeout
management, tree-sitter error suppression, docstring extraction, complexity
scoring, and import-type classification.

All parsers are designed to be stateless and reused across many files —
they hold no per-file state between calls to parse_file().
"""

from __future__ import annotations

import re
import signal
import warnings
from abc import ABC, abstractmethod
from typing import Optional

from tree_sitter import Node

from config import (
    COMPLEXITY_KEYWORDS,
    MAX_FILE_PARSE_TIMEOUT_SECONDS,
    MAX_FUNCTION_BODY_CHARS,
    MINIFIED_LINE_LENGTH_THRESHOLD,
    STDLIB_MODULES_NODE,
    STDLIB_MODULES_PYTHON,
)
from parsing import (
    ParsedClass,
    ParsedFile,
    ParsedFunction,
    ParsedImport,
    ParsedParameter,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# Suppress the FutureWarning from tree_sitter_languages about the old
# Language(path, name) constructor that it uses internally.
warnings.filterwarnings("ignore", category=FutureWarning, module="tree_sitter")


def _timeout_handler(signum: int, frame: object) -> None:
    """SIGALRM handler that raises TimeoutError for parse timeouts."""
    raise TimeoutError("Tree-sitter parse timed out")


class BaseParser(ABC):
    """
    Abstract base class for all CodeAutopsy language parsers.

    Subclasses must implement the five abstract ``extract_*`` methods.
    They receive the parsed tree-sitter ``tree`` object, the raw source
    bytes, and the file path string.

    The concrete ``parse_file`` method orchestrates the full pipeline:
    encoding → parse → extract → assemble ParsedFile.
    """

    # Subclasses set this to the tree-sitter language name string
    # (e.g. "python", "javascript") used with get_parser / get_language.
    language_name: str = ""

    # Human-readable name matching Phase 1 manifest "language" field
    language_label: str = ""

    def __init__(self) -> None:
        self._parser = None
        self._language = None

    def _ensure_parser(self) -> None:
        """Lazily initialise the tree-sitter parser on first use."""
        if self._parser is not None:
            return
        try:
            from tree_sitter_languages import get_language, get_parser
            self._language = get_language(self.language_name)
            self._parser = get_parser(self.language_name)
        except Exception as exc:
            logger.error(
                "Failed to load tree-sitter grammar for %r: %s",
                self.language_name, exc,
            )
            raise

    # -----------------------------------------------------------------------
    # Abstract methods — must be implemented by each language parser
    # -----------------------------------------------------------------------

    @abstractmethod
    def extract_functions(
        self,
        tree: object,
        source_bytes: bytes,
        file_path: str,
    ) -> list[ParsedFunction]:
        """Extract all functions and methods from the parsed AST."""

    @abstractmethod
    def extract_classes(
        self,
        tree: object,
        source_bytes: bytes,
        file_path: str,
    ) -> list[ParsedClass]:
        """Extract all classes, interfaces, structs, and enums."""

    @abstractmethod
    def extract_imports(
        self,
        tree: object,
        source_bytes: bytes,
        file_path: str,
    ) -> list[ParsedImport]:
        """Extract all import / require / include statements."""

    @abstractmethod
    def extract_global_variables(
        self,
        tree: object,
        source_bytes: bytes,
        file_path: str,
    ) -> list[str]:
        """Extract module-level constant and global variable names."""

    @abstractmethod
    def detect_entry_point(
        self,
        tree: object,
        source_bytes: bytes,
        file_path: str,
    ) -> bool:
        """Return True if this file is likely a program entry point."""

    # -----------------------------------------------------------------------
    # Concrete shared logic
    # -----------------------------------------------------------------------

    def parse_file(self, file_path: str, source_code: str) -> ParsedFile:
        """
        Parse one source file and return a fully-populated ParsedFile.

        This is the main entry point called by the orchestrator for each file.
        It is designed to never raise — all errors are captured into
        ``ParsedFile.parse_errors`` and ``ParsedFile.parse_success``.

        Args:
            file_path:   Relative path of the file within the repository.
            source_code: Decoded text content of the file.

        Returns:
            A :class:`~parsing.ParsedFile` instance. ``parse_success`` will
            be ``False`` if a critical error prevented extraction.
        """
        parse_errors: list[str] = []
        total_lines = source_code.count("\n") + 1

        # ------------------------------------------------------------------
        # Guard: minified file detection
        # ------------------------------------------------------------------
        max_line_len = max((len(ln) for ln in source_code.splitlines()), default=0)
        if max_line_len > MINIFIED_LINE_LENGTH_THRESHOLD:
            msg = (
                f"Skipping {file_path!r}: likely minified "
                f"(longest line = {max_line_len:,} chars)."
            )
            logger.warning(msg)
            return ParsedFile(
                file_path=file_path,
                language=self.language_label,
                sha="",
                size_bytes=len(source_code.encode("utf-8")),
                total_lines=total_lines,
                parse_errors=[msg],
                parse_success=False,
            )

        # ------------------------------------------------------------------
        # Guard: empty file
        # ------------------------------------------------------------------
        if not source_code.strip():
            return ParsedFile(
                file_path=file_path,
                language=self.language_label,
                sha="",
                size_bytes=0,
                total_lines=total_lines,
                parse_success=True,
            )

        # ------------------------------------------------------------------
        # Encode to bytes for tree-sitter
        # ------------------------------------------------------------------
        try:
            source_bytes = source_code.encode("utf-8")
        except UnicodeEncodeError:
            try:
                source_bytes = source_code.encode("latin-1")
            except UnicodeEncodeError as exc:
                msg = f"Encoding error in {file_path!r}: {exc}"
                logger.error(msg)
                return ParsedFile(
                    file_path=file_path,
                    language=self.language_label,
                    sha="",
                    size_bytes=0,
                    total_lines=total_lines,
                    parse_errors=[msg],
                    parse_success=False,
                )

        # ------------------------------------------------------------------
        # Initialise parser
        # ------------------------------------------------------------------
        try:
            self._ensure_parser()
        except Exception as exc:
            msg = f"Parser unavailable for {self.language_label}: {exc}"
            parse_errors.append(msg)
            return ParsedFile(
                file_path=file_path,
                language=self.language_label,
                sha="",
                size_bytes=len(source_bytes),
                total_lines=total_lines,
                parse_errors=parse_errors,
                parse_success=False,
            )

        # ------------------------------------------------------------------
        # Tree-sitter parse with timeout
        # ------------------------------------------------------------------
        tree = None
        try:
            # Use SIGALRM for timeout on POSIX; no-op on Windows
            use_timeout = hasattr(signal, "SIGALRM")
            if use_timeout:
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(MAX_FILE_PARSE_TIMEOUT_SECONDS)
            try:
                tree = self._parser.parse(source_bytes)
            finally:
                if use_timeout:
                    signal.alarm(0)  # cancel alarm
        except TimeoutError:
            msg = (
                f"Parse timeout ({MAX_FILE_PARSE_TIMEOUT_SECONDS}s) "
                f"for {file_path!r}."
            )
            logger.warning(msg)
            parse_errors.append(msg)
            return ParsedFile(
                file_path=file_path,
                language=self.language_label,
                sha="",
                size_bytes=len(source_bytes),
                total_lines=total_lines,
                parse_errors=parse_errors,
                parse_success=False,
            )
        except Exception as exc:
            msg = f"tree-sitter parse failed for {file_path!r}: {exc}"
            logger.error(msg)
            parse_errors.append(msg)
            return ParsedFile(
                file_path=file_path,
                language=self.language_label,
                sha="",
                size_bytes=len(source_bytes),
                total_lines=total_lines,
                parse_errors=parse_errors,
                parse_success=False,
            )

        # ------------------------------------------------------------------
        # Check for syntax errors in the AST
        # ------------------------------------------------------------------
        if tree.root_node.has_error:
            msg = f"Syntax errors detected in {file_path!r} — partial extraction."
            logger.warning(msg)
            parse_errors.append(msg)
            # Continue — tree-sitter produces partial trees on syntax errors

        # ------------------------------------------------------------------
        # Extract all entities  (each call is individually guarded)
        # ------------------------------------------------------------------
        functions        = self._safe_extract(self.extract_functions,        tree, source_bytes, file_path, "functions")
        classes          = self._safe_extract(self.extract_classes,           tree, source_bytes, file_path, "classes")
        imports          = self._safe_extract(self.extract_imports,           tree, source_bytes, file_path, "imports")
        global_vars      = self._safe_extract(self.extract_global_variables,  tree, source_bytes, file_path, "global_variables")
        is_entry         = self._safe_detect(self.detect_entry_point,         tree, source_bytes, file_path)

        # ------------------------------------------------------------------
        # Detect main block and exports from source text (fast, no AST)
        # ------------------------------------------------------------------
        has_main_block = self._detect_main_block(source_code, file_path)
        has_exports    = self._detect_exports(source_code, file_path)
        module_doc     = self._get_module_docstring(tree, source_bytes)

        # ------------------------------------------------------------------
        # Determine overall parse success
        # ------------------------------------------------------------------
        parse_success = not any(
            "timeout" in e.lower() or "parse failed" in e.lower()
            for e in parse_errors
        )

        logger.debug(
            "Parsed %r: %d functions, %d classes, %d imports.",
            file_path, len(functions), len(classes), len(imports),
        )

        return ParsedFile(
            file_path=file_path,
            language=self.language_label,
            sha="",            # filled in by orchestrator from manifest
            size_bytes=len(source_bytes),
            total_lines=total_lines,
            functions=functions,
            classes=classes,
            imports=imports,
            global_variables=global_vars,
            module_docstring=module_doc,
            is_entry_point=is_entry,
            has_main_block=has_main_block,
            has_exports=has_exports,
            parse_errors=parse_errors,
            parse_success=parse_success,
        )

    # -----------------------------------------------------------------------
    # Helper utilities (concrete, available to all subclasses)
    # -----------------------------------------------------------------------

    def get_node_text(self, node: Node, source_bytes: bytes) -> str:
        """
        Return the source text corresponding to an AST node.

        Args:
            node:         A tree-sitter Node.
            source_bytes: Raw UTF-8 bytes of the file.

        Returns:
            Decoded string slice, empty string on any error.
        """
        try:
            return source_bytes[node.start_byte:node.end_byte].decode(
                "utf-8", errors="replace"
            )
        except Exception:
            return ""

    def get_docstring(self, node: Node, source_bytes: bytes) -> Optional[str]:
        """
        Extract the docstring from a function or class node.

        Looks for the first expression statement containing a string literal
        as the first child of the body block.

        Args:
            node:         The function_definition or class_definition node.
            source_bytes: Raw file bytes.

        Returns:
            Cleaned docstring text or ``None``.
        """
        # Find body child
        body = None
        for child in node.children:
            if child.type in ("block", "statement_block", "class_body",
                              "declaration_list", "field_declaration_list"):
                body = child
                break

        if body is None:
            return None

        # First named child of body
        for child in body.named_children:
            # Python: expression_statement > string_node
            if child.type == "expression_statement":
                for sub in child.named_children:
                    if sub.type in ("string", "concatenated_string"):
                        raw = self.get_node_text(sub, source_bytes)
                        return _clean_docstring(raw)
            # Some grammars put string directly
            if child.type in ("string", "string_literal"):
                raw = self.get_node_text(child, source_bytes)
                return _clean_docstring(raw)
            break  # only check first statement

        return None

    def calculate_complexity(
        self,
        func_node: Node,
        source_bytes: bytes,
    ) -> int:
        """
        Count branching keywords in a function body to estimate complexity.

        Uses ``COMPLEXITY_KEYWORDS`` from config.  A higher score means more
        conditional paths and is a proxy for cyclomatic complexity.

        Args:
            func_node:    The function definition AST node.
            source_bytes: Raw file bytes.

        Returns:
            Integer complexity score (≥ 1, since the function itself counts).
        """
        keywords = COMPLEXITY_KEYWORDS.get(self.language_label, [])
        if not keywords:
            return 1

        body_text = self.get_node_text(func_node, source_bytes)
        score = 1  # base complexity
        for kw in keywords:
            # Count whole-word occurrences (avoid matching substrings)
            if re.search(r"\b" + re.escape(kw) + r"\b", body_text):
                score += len(re.findall(r"\b" + re.escape(kw) + r"\b", body_text))
        return score

    def resolve_import_type(
        self,
        module_name: str,
        language: str,
        known_local_modules: Optional[set[str]] = None,
    ) -> tuple[bool, bool, bool]:
        """
        Classify an import as stdlib / third-party / local.

        Args:
            module_name:         The module name string (e.g. ``"os.path"``).
            language:            Language label (``"Python"``, ``"JavaScript"``…).
            known_local_modules: Optional set of known local module names for
                                 more accurate local classification.

        Returns:
            Tuple ``(is_stdlib, is_third_party, is_local)``.
            Exactly one will be ``True`` (stdlib wins over third-party).
        """
        # Relative imports are always local
        if module_name.startswith("."):
            return (False, False, True)

        root = module_name.split(".")[0].split("/")[0]

        if language == "Python":
            if root in STDLIB_MODULES_PYTHON:
                return (True, False, False)
        elif language in ("JavaScript", "TypeScript"):
            if root in STDLIB_MODULES_NODE:
                return (True, False, False)

        # Heuristic: local modules don't contain hyphens (npm convention)
        # and are not scoped packages (@org/pkg)
        if known_local_modules and root in known_local_modules:
            return (False, False, True)

        # Scoped packages (@org/pkg) are third-party
        if module_name.startswith("@"):
            return (False, True, False)

        # Java-style: com.*, org.*, io.*, net.* → likely third-party
        if language == "Java":
            if root in ("java", "javax", "sun", "com", "org", "io", "net"):
                is_local = root == "com" and bool(known_local_modules)
                return (False, not is_local, is_local)

        # Go standard library: no dots in short paths (fmt, os, etc.)
        if language == "Go":
            if "." not in module_name and "/" not in module_name:
                return (True, False, False)
            if module_name.startswith("github.com/") or \
               module_name.startswith("golang.org/") or \
               module_name.startswith("gopkg.in/"):
                return (False, True, False)

        # Rust: std::, core::, alloc:: → stdlib
        if language == "Rust":
            if root in ("std", "core", "alloc"):
                return (True, False, False)
            if root in ("crate", "super", "self"):
                return (False, False, True)

        # Default: third-party
        return (False, True, False)

    def _safe_query(self, query_string: str, root_node: Node) -> list[tuple]:
        """
        Execute a tree-sitter query, returning an empty list on any error.

        Args:
            query_string: S-expression query string.
            root_node:    Root node of the parsed tree.

        Returns:
            List of ``(Node, capture_name)`` tuples or ``[]`` on failure.
        """
        try:
            q = self._language.query(query_string)
            return q.captures(root_node)
        except Exception as exc:
            logger.debug("Query failed: %s — %s", query_string[:60], exc)
            return []

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _safe_extract(
        self,
        method,
        tree,
        source_bytes: bytes,
        file_path: str,
        kind: str,
    ) -> list:
        """Call an extract method, returning [] and logging on any exception."""
        try:
            result = method(tree, source_bytes, file_path)
            return result if result is not None else []
        except Exception as exc:
            logger.warning(
                "Error extracting %s from %r: %s", kind, file_path, exc
            )
            return []

    def _safe_detect(
        self,
        method,
        tree,
        source_bytes: bytes,
        file_path: str,
    ) -> bool:
        """Call a detect method, returning False and logging on any exception."""
        try:
            return bool(method(tree, source_bytes, file_path))
        except Exception as exc:
            logger.debug("Error in detect_entry_point for %r: %s", file_path, exc)
            return False

    def _detect_main_block(self, source_code: str, file_path: str) -> bool:
        """Fast source-text check for language-appropriate main block patterns."""
        lang = self.language_label
        if lang == "Python":
            return 'if __name__' in source_code and '__main__' in source_code
        if lang in ("JavaScript", "TypeScript"):
            return "process.argv" in source_code or "require.main" in source_code
        if lang == "Java":
            return "public static void main" in source_code
        if lang == "Go":
            return "func main()" in source_code
        if lang == "Rust":
            return "fn main()" in source_code
        if lang in ("C", "C++"):
            return "int main(" in source_code
        return False

    def _detect_exports(self, source_code: str, file_path: str) -> bool:
        """Fast source-text check for export statements."""
        lang = self.language_label
        if lang in ("JavaScript", "TypeScript"):
            return (
                "module.exports" in source_code
                or "export default" in source_code
                or "export const" in source_code
                or "export function" in source_code
                or "export class" in source_code
            )
        return False

    def _get_module_docstring(
        self, tree, source_bytes: bytes
    ) -> Optional[str]:
        """Extract the module-level docstring (first string in the file body)."""
        try:
            root = tree.root_node
            for child in root.named_children:
                if child.type == "expression_statement":
                    for sub in child.named_children:
                        if sub.type in ("string", "concatenated_string"):
                            raw = self.get_node_text(sub, source_bytes)
                            return _clean_docstring(raw)
                break
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _clean_docstring(raw: str) -> str:
    """
    Strip quotes and normalize whitespace from a raw docstring literal.

    Args:
        raw: The raw string literal text as it appears in source code
             (e.g. ``'\"\"\"This is a docstring.\"\"\"'``).

    Returns:
        Cleaned plain text, or empty string if stripping yields nothing.
    """
    # Remove triple quotes (various styles)
    for q in ('"""', "'''", '"""', "'''"):
        if raw.startswith(q):
            raw = raw[len(q):]
            if raw.endswith(q):
                raw = raw[: -len(q)]
            break
    else:
        # Single quotes
        raw = raw.strip("\"'")

    # Normalize indent
    lines = raw.strip().splitlines()
    if len(lines) > 1:
        # Remove common leading whitespace
        stripped = [l.rstrip() for l in lines]
        return "\n".join(stripped).strip()
    return raw.strip()
