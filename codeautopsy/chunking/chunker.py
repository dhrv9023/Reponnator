"""
chunking/chunker.py — Phase 3 Chunk Creation

Transforms ParsedFile objects (Phase 2 output) into CodeChunk objects.
Creates four chunk types per file:
  1. FUNCTION / METHOD chunks  — one per extracted function
  2. CLASS_SUMMARY chunks      — one per class (no method bodies)
  3. FILE_SUMMARY chunk        — one per file (always)
  4. IMPORT_CONTEXT chunk      — one per file with >3 imports

This is the most critical module in Phase 3: chunk quality directly
determines the accuracy of all downstream RAG queries.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Optional

from utils.logger import get_logger
import config
from chunking import ChunkType, CodeChunk
from parsing import ParsedFile, ParsedFunction, ParsedClass, ParsedImport

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Stop words for keyword extraction
# ---------------------------------------------------------------------------
_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "is", "in", "of", "to", "for",
    "with", "this", "that", "it", "at", "by", "from", "on", "as",
    "be", "was", "are", "has", "have", "had", "do", "does", "did",
    "not", "but", "if", "else", "return", "def", "class", "import",
    "self", "cls", "none", "true", "false", "pass", "raise", "yield",
    "lambda", "async", "await", "try", "except", "finally", "with",
    "while", "for", "break", "continue",
})


# ===========================================================================
# Public API
# ===========================================================================

class Chunker:
    """Creates all chunk types from ParsedFile objects."""

    def create_chunks_from_file(
        self,
        parsed_file: ParsedFile,
        repo_owner: str,
        repo_name: str,
    ) -> list[CodeChunk]:
        """
        Create all chunk types for one parsed source file.

        Returns a list of CodeChunks in this order:
          function/method chunks → class summary chunks →
          file summary chunk → import context chunk (if applicable).
        """
        chunks: list[CodeChunk] = []

        if len(parsed_file.functions) > 500:
            logger.warning(
                "Large file: %s has %d functions — processing all",
                parsed_file.file_path, len(parsed_file.functions),
            )

        # STEP 1 — Function / Method chunks
        for func in parsed_file.functions:
            try:
                chunk = self._create_function_chunk(func, parsed_file, repo_owner, repo_name)
                if chunk is not None:
                    chunks.append(chunk)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to create function chunk for %s in %s: %s",
                    func.qualified_name, parsed_file.file_path, exc,
                )

        # STEP 2 — Class summary chunks
        for cls in parsed_file.classes:
            try:
                chunk = self._create_class_chunk(cls, parsed_file, repo_owner, repo_name)
                if chunk is not None:
                    chunks.append(chunk)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to create class chunk for %s in %s: %s",
                    cls.qualified_name, parsed_file.file_path, exc,
                )

        # STEP 3 — File summary chunk (always)
        try:
            chunks.append(
                self._create_file_summary_chunk(parsed_file, repo_owner, repo_name)
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to create file summary for %s: %s",
                parsed_file.file_path, exc,
            )

        # STEP 4 — Import context chunk (only if >3 imports)
        if len(parsed_file.imports) > 3:
            try:
                ic = self._create_import_context_chunk(parsed_file, repo_owner, repo_name)
                if ic is not None:
                    chunks.append(ic)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to create import context for %s: %s",
                    parsed_file.file_path, exc,
                )

        return chunks


    # -----------------------------------------------------------------------
    # STEP 1 helpers — function / method chunks
    # -----------------------------------------------------------------------

    def _create_function_chunk(
        self,
        func: ParsedFunction,
        parsed_file: ParsedFile,
        repo_owner: str,
        repo_name: str,
    ) -> Optional[CodeChunk]:
        """Build a FUNCTION or METHOD chunk from a ParsedFunction."""

        # Build content pieces
        decorators_line = "\n".join(f"@{d}" for d in func.decorators) if func.decorators else ""
        signature_line  = _build_signature(func)
        docstring_block = f'"""{func.docstring}"""' if func.docstring else ""
        body            = (func.full_body or "").replace("\x00", "")  # strip null bytes

        content = _fill_template(
            config.FUNCTION_CONTENT_TEMPLATE,
            file_path       = parsed_file.file_path,
            language        = parsed_file.language,
            qualified_name  = func.qualified_name,
            decorators_line = decorators_line,
            signature_line  = signature_line,
            docstring_block = docstring_block,
            body            = body,
        )

        if not content.strip():
            logger.warning(
                "Empty content for function %s in %s — skipping",
                func.qualified_name, parsed_file.file_path,
            )
            return None

        token_count = _count_tokens(content, chunk_id=func.qualified_name)
        if token_count < config.MIN_CHUNK_TOKENS:
            return None  # too small to be useful

        chunk_type = ChunkType.METHOD if func.is_method else ChunkType.FUNCTION
        keywords   = _extract_keywords(func, docstring=func.docstring)

        return CodeChunk(
            chunk_id        = str(uuid.uuid4()),
            repo_owner      = repo_owner,
            repo_name       = repo_name,
            chunk_type      = chunk_type,
            file_path       = parsed_file.file_path,
            language        = parsed_file.language,
            start_line      = func.start_line,
            end_line        = func.end_line,
            sha             = parsed_file.sha,
            content         = content,
            content_preview = content[:config.MAX_CONTENT_PREVIEW_CHARS],
            token_count     = token_count,
            name            = func.name,
            qualified_name  = func.qualified_name,
            parent_class    = func.parent_class if func.is_method else None,
            parent_function = None,
            calls           = list(func.calls),
            called_by       = [],           # enriched later
            imports_used    = [],           # enriched later
            file_imports    = [imp.module for imp in parsed_file.imports],
            files_this_depends_on   = [],   # enriched later
            files_depending_on_this = [],   # enriched later
            complexity_score       = func.complexity_score,
            is_entry_point         = parsed_file.is_entry_point,
            is_constructor         = func.is_constructor,
            is_private             = func.is_private,
            is_async               = func.is_async,
            decorators             = list(func.decorators),
            architectural_patterns = [],   # enriched later
            search_keywords        = keywords,
            docstring              = func.docstring,
        )

    # -----------------------------------------------------------------------
    # STEP 2 helpers — class summary chunks
    # -----------------------------------------------------------------------

    def _create_class_chunk(
        self,
        cls: ParsedClass,
        parsed_file: ParsedFile,
        repo_owner: str,
        repo_name: str,
    ) -> Optional[CodeChunk]:
        """Build a CLASS_SUMMARY chunk from a ParsedClass."""

        base_classes_line = (
            f"Extends: {', '.join(cls.base_classes)}" if cls.base_classes else ""
        )
        docstring_block = f'"""{cls.docstring}"""' if cls.docstring else ""

        # Method list: short qualified name → just method name
        methods_list = ", ".join(
            m.split(".")[-1] for m in cls.methods
        ) if cls.methods else "none"

        all_attrs = list(cls.class_variables) + list(cls.instance_variables)
        attributes_list = ", ".join(all_attrs) if all_attrs else "none"

        content = _fill_template(
            config.CLASS_SUMMARY_CONTENT_TEMPLATE,
            file_path       = parsed_file.file_path,
            language        = parsed_file.language,
            qualified_name  = cls.qualified_name,
            base_classes_line = base_classes_line,
            docstring_block = docstring_block,
            methods_list    = methods_list,
            attributes_list = attributes_list,
        )

        if not content.strip():
            return None

        token_count = _count_tokens(content, chunk_id=cls.qualified_name)
        if token_count < config.MIN_CHUNK_TOKENS:
            return None

        # Keyword extraction for classes
        parts = re.split(r"[._\s]+", cls.qualified_name)
        kw_set = {p.lower() for p in parts if len(p) > 2 and p.lower() not in _STOP_WORDS}
        if cls.docstring:
            kw_set.update(_words_from_text(cls.docstring, max_words=10))
        kw_set.update(m.split(".")[-1].lower() for m in cls.methods[:5])
        keywords = list(kw_set)[:20]

        return CodeChunk(
            chunk_id        = str(uuid.uuid4()),
            repo_owner      = repo_owner,
            repo_name       = repo_name,
            chunk_type      = ChunkType.CLASS_SUMMARY,
            file_path       = parsed_file.file_path,
            language        = parsed_file.language,
            start_line      = cls.start_line,
            end_line        = cls.end_line,
            sha             = parsed_file.sha,
            content         = content,
            content_preview = content[:config.MAX_CONTENT_PREVIEW_CHARS],
            token_count     = token_count,
            name            = cls.name,
            qualified_name  = cls.qualified_name,
            parent_class    = None,
            parent_function = None,
            calls           = [],
            called_by       = [],
            imports_used    = [],
            file_imports    = [imp.module for imp in parsed_file.imports],
            files_this_depends_on   = [],
            files_depending_on_this = [],
            complexity_score        = 0,
            is_entry_point          = parsed_file.is_entry_point,
            is_constructor          = False,
            is_private              = cls.name.startswith("_"),
            is_async                = False,
            decorators              = list(cls.decorators),
            architectural_patterns  = [],
            search_keywords         = keywords,
            docstring               = cls.docstring,
        )

    # -----------------------------------------------------------------------
    # STEP 3 helpers — file summary chunk
    # -----------------------------------------------------------------------

    def _create_file_summary_chunk(
        self,
        parsed_file: ParsedFile,
        repo_owner: str,
        repo_name: str,
    ) -> CodeChunk:
        """Build a FILE_SUMMARY chunk — always exactly one per file."""

        imports_summary = "\n".join(
            _format_import(imp) for imp in parsed_file.imports
        ) if parsed_file.imports else "none"

        classes_list = ", ".join(cls.name for cls in parsed_file.classes) or "none"
        top_level_funcs = [
            f.name for f in parsed_file.functions if not f.is_method
        ]
        functions_list = ", ".join(top_level_funcs) or "none"

        module_docstring_block = (
            f'"""{parsed_file.module_docstring}"""'
            if parsed_file.module_docstring else ""
        )

        content = _fill_template(
            config.FILE_SUMMARY_CONTENT_TEMPLATE,
            file_path             = parsed_file.file_path,
            language              = parsed_file.language,
            qualified_name        = parsed_file.file_path,
            imports_summary       = imports_summary,
            classes_list          = classes_list,
            functions_list        = functions_list,
            is_entry_point        = str(parsed_file.is_entry_point),
            module_docstring_block = module_docstring_block,
        )

        token_count = _count_tokens(content, chunk_id=parsed_file.file_path)

        # keywords: path parts + class names + top-level function names
        path_parts = re.split(r"[/_.\-]", parsed_file.file_path)
        kw_set = {p.lower() for p in path_parts
                  if len(p) > 2 and p.lower() not in _STOP_WORDS}
        kw_set.update(cls.name.lower() for cls in parsed_file.classes)
        kw_set.update(f.lower() for f in top_level_funcs[:10])
        if parsed_file.module_docstring:
            kw_set.update(_words_from_text(parsed_file.module_docstring, max_words=8))
        keywords = list(kw_set)[:20]

        file_name = Path(parsed_file.file_path).name

        return CodeChunk(
            chunk_id        = str(uuid.uuid4()),
            repo_owner      = repo_owner,
            repo_name       = repo_name,
            chunk_type      = ChunkType.FILE_SUMMARY,
            file_path       = parsed_file.file_path,
            language        = parsed_file.language,
            start_line      = 1,
            end_line        = parsed_file.total_lines or 1,
            sha             = parsed_file.sha,
            content         = content,
            content_preview = content[:config.MAX_CONTENT_PREVIEW_CHARS],
            token_count     = token_count,
            name            = file_name,
            qualified_name  = parsed_file.file_path,
            parent_class    = None,
            parent_function = None,
            calls           = [],
            called_by       = [],
            imports_used    = [imp.module for imp in parsed_file.imports],
            file_imports    = [imp.module for imp in parsed_file.imports],
            files_this_depends_on   = [],
            files_depending_on_this = [],
            complexity_score        = 0,
            is_entry_point          = parsed_file.is_entry_point,
            is_constructor          = False,
            is_private              = False,
            is_async                = False,
            decorators              = [],
            architectural_patterns  = [],
            search_keywords         = keywords,
            docstring               = parsed_file.module_docstring,
        )

    # -----------------------------------------------------------------------
    # STEP 4 helpers — import context chunk
    # -----------------------------------------------------------------------

    def _create_import_context_chunk(
        self,
        parsed_file: ParsedFile,
        repo_owner: str,
        repo_name: str,
    ) -> Optional[CodeChunk]:
        """Build an IMPORT_CONTEXT chunk for files with >3 imports."""

        stdlib_imports    = [imp.module for imp in parsed_file.imports if imp.is_stdlib]
        third_party       = [imp.module for imp in parsed_file.imports if imp.is_third_party]
        local_imports     = [imp.module for imp in parsed_file.imports if imp.is_local]

        content = _fill_template(
            config.IMPORT_CONTEXT_CONTENT_TEMPLATE,
            file_path          = parsed_file.file_path,
            third_party_imports = ", ".join(third_party) or "none",
            local_imports       = ", ".join(local_imports) or "none",
            stdlib_imports      = ", ".join(stdlib_imports) or "none",
        )

        if not content.strip():
            return None

        token_count = _count_tokens(content, chunk_id=f"import:{parsed_file.file_path}")
        if token_count < config.MIN_CHUNK_TOKENS:
            return None

        kw_set = set()
        for imp in parsed_file.imports:
            parts = imp.module.replace("-", "_").split(".")
            kw_set.update(p.lower() for p in parts if len(p) > 2)
        keywords = list(kw_set)[:20]

        file_name = Path(parsed_file.file_path).name

        return CodeChunk(
            chunk_id        = str(uuid.uuid4()),
            repo_owner      = repo_owner,
            repo_name       = repo_name,
            chunk_type      = ChunkType.IMPORT_CONTEXT,
            file_path       = parsed_file.file_path,
            language        = parsed_file.language,
            start_line      = 1,
            end_line        = parsed_file.total_lines or 1,
            sha             = parsed_file.sha,
            content         = content,
            content_preview = content[:config.MAX_CONTENT_PREVIEW_CHARS],
            token_count     = token_count,
            name            = f"{file_name} imports",
            qualified_name  = f"{parsed_file.file_path}::imports",
            parent_class    = None,
            parent_function = None,
            calls           = [],
            called_by       = [],
            imports_used    = [imp.module for imp in parsed_file.imports],
            file_imports    = [imp.module for imp in parsed_file.imports],
            files_this_depends_on   = [],
            files_depending_on_this = [],
            complexity_score        = 0,
            is_entry_point          = parsed_file.is_entry_point,
            is_constructor          = False,
            is_private              = False,
            is_async                = False,
            decorators              = [],
            architectural_patterns  = [],
            search_keywords         = keywords,
            docstring               = None,
        )


# ===========================================================================
# Private helpers
# ===========================================================================

def _build_signature(func: ParsedFunction) -> str:
    """Reconstruct a human-readable function signature."""
    params = []
    for p in func.parameters:
        part = p.name
        if p.type_annotation:
            part += f": {p.type_annotation}"
        if p.default_value is not None:
            part += f" = {p.default_value}"
        params.append(part)

    params_str = ", ".join(params)
    ret = f" -> {func.return_type}" if func.return_type else ""
    prefix = "async def" if func.is_async else "def"
    return f"{prefix} {func.name}({params_str}){ret}:"


def _fill_template(template: str, **kwargs) -> str:
    """Fill a template string, replacing missing keys with empty strings."""
    result = template
    for key, value in kwargs.items():
        placeholder = "{" + key + "}"
        result = result.replace(placeholder, str(value) if value is not None else "")
    return result.strip()


def _count_tokens(content: str, chunk_id: str = "") -> int:
    """Count tokens using tiktoken; fall back to character estimate."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(content))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "tiktoken failed on chunk %s (%s) — using estimate", chunk_id, exc
        )
        return len(content) // 4


def _extract_keywords(func: ParsedFunction, docstring: Optional[str] = None) -> list[str]:
    """Extract search keywords from a function's metadata."""
    kw_set: set[str] = set()

    # Split qualified name + function name
    parts = re.split(r"[._\s]+", func.qualified_name)
    kw_set.update(p.lower() for p in parts if len(p) > 2 and p.lower() not in _STOP_WORDS)

    # Parameter names
    for p in func.parameters:
        if p.name and len(p.name) > 2 and p.name.lower() not in _STOP_WORDS:
            kw_set.add(p.name.lower())

    # Decorator names (strip @)
    for d in func.decorators:
        clean = d.lstrip("@").split("(")[0].lower()
        if len(clean) > 2:
            kw_set.add(clean)

    # First meaningful words from docstring
    if docstring:
        kw_set.update(_words_from_text(docstring, max_words=10))

    return list(kw_set)[:20]


def _words_from_text(text: str, max_words: int = 10) -> list[str]:
    """Extract meaningful words from free text."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", text)
    return [
        w.lower() for w in words
        if w.lower() not in _STOP_WORDS
    ][:max_words]


def _format_import(imp: ParsedImport) -> str:
    """Format an import for display in file summary."""
    if imp.imported_items:
        items = ", ".join(imp.imported_items)
        return f"from {imp.module} import {items}"
    return f"import {imp.module}"
