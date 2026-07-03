"""
parsing/parse_orchestrator.py — Phase 2 Main Orchestration

Ties together all parsers, builders, and detectors into a single
pipeline that takes a Phase 1 repo folder and produces a complete
parsed/ output directory.

This is the Phase 2 equivalent of ingestion/file_fetcher.py.
"""

from __future__ import annotations

import dataclasses
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config
from parsing import ParsedFile, ParseManifest, save_json, load_json
from parsing.call_graph_builder import build_call_graph
from parsing.dependency_builder import build_dependency_map
from parsing.entry_point_finder import find_entry_points
from parsing.parser_registry import get_parser_for_language
from parsing.pattern_detector import detect_patterns
from utils.logger import get_logger

logger = get_logger(__name__)


def parse_repository(
    repo_folder: Path,
    force_reparse: bool = False,
) -> ParseManifest:
    """
    Run the full Phase 2 parse pipeline on a previously-fetched repository.

    Reads Phase 1 output from ``repo_folder/manifest.json`` and
    ``repo_folder/files/``, writes all parsed output to
    ``repo_folder/parsed/``.

    Args:
        repo_folder:   Path to the Phase 1 repo folder
                       (e.g. ``data/repos/pallets__flask``).
        force_reparse: If True, re-parse even if parsed/ already exists.

    Returns:
        A :class:`~parsing.ParseManifest` summary of the parse run.

    Raises:
        FileNotFoundError: If Phase 1 output (manifest.json) is missing.
        ValueError:        If manifest.json is malformed.
    """
    start_time = time.monotonic()

    # -----------------------------------------------------------------------
    # Load Phase 1 manifest
    # -----------------------------------------------------------------------
    manifest_path = repo_folder / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Phase 1 output not found at {manifest_path}.\n"
            "Run:  python main.py ingest <repo-url>"
        )

    try:
        phase1 = load_json(manifest_path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed manifest.json at {manifest_path}: {exc}") from exc

    owner     = phase1.get("repo", {}).get("owner", "unknown")
    repo_name = phase1.get("repo", {}).get("name", "unknown")
    files_dir = repo_folder / "files"

    logger.info("Starting parse of %s/%s", owner, repo_name)

    # -----------------------------------------------------------------------
    # Cache check
    # -----------------------------------------------------------------------
    parsed_dir          = repo_folder / config.PARSED_DIR_NAME
    parse_manifest_path = parsed_dir / config.PARSE_MANIFEST_FILENAME

    if parse_manifest_path.exists() and not force_reparse:
        logger.info(
            "Repository already parsed. Use --force to reparse. "
            "Loading cached parse manifest."
        )
        cached = load_json(parse_manifest_path)
        return _dict_to_manifest(cached)

    # -----------------------------------------------------------------------
    # Set up output directories
    # -----------------------------------------------------------------------
    (parsed_dir / "files").mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Parse every file
    # -----------------------------------------------------------------------
    file_entries     = phase1.get("files", [])
    total            = len(file_entries)
    parsed_files:    list[ParsedFile] = []
    errors:          list[str]        = []
    total_functions  = 0
    total_classes    = 0
    total_imports    = 0

    logger.info("Starting parse of %s/%s (%d files)", owner, repo_name, total)

    for idx, entry in enumerate(file_entries, start=1):
        file_path = entry.get("path", "")
        language  = entry.get("language", "Unknown")
        sha       = entry.get("sha", "")

        if idx == 1 or idx % 25 == 0 or idx == total:
            logger.info(
                "Parsed %d/%d files | %d functions | %d classes found so far",
                idx - 1, total, total_functions, total_classes,
            )

        # Read source code
        source_path = files_dir / file_path
        if not source_path.exists():
            msg = f"Source file missing on disk: {source_path}"
            logger.warning(msg)
            errors.append(msg)
            continue

        try:
            source_code = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            msg = f"Cannot read {file_path}: {exc}"
            logger.error(msg)
            errors.append(msg)
            continue

        # Get parser
        parser = get_parser_for_language(language, file_path)

        # Parse
        try:
            parsed = parser.parse_file(file_path, source_code)
        except Exception as exc:
            msg = f"Critical parse failure for {file_path!r}: {exc}"
            logger.error(msg)
            errors.append(msg)
            # Create empty failed ParsedFile
            from parsing import ParsedFile as PF
            parsed = PF(
                file_path=file_path, language=language, sha=sha,
                size_bytes=entry.get("size_bytes", 0),
                total_lines=0, parse_errors=[msg], parse_success=False,
            )

        # Stamp SHA from manifest (parsers set it to "")
        parsed.sha = sha

        parsed_files.append(parsed)
        total_functions += len(parsed.functions)
        total_classes   += len(parsed.classes)
        total_imports   += len(parsed.imports)

        # Save per-file JSON (named by SHA for cache-key compatibility)
        file_key  = sha if sha else f"nosha_{idx}"
        out_path  = parsed_dir / "files" / f"{file_key}.json"
        try:
            save_json(dataclasses.asdict(parsed), out_path)
        except OSError as exc:
            logger.error("Cannot write parsed file %s: %s", out_path, exc)

    logger.info(
        "Parsed %d/%d files | %d functions | %d classes found so far",
        total, total, total_functions, total_classes,
    )

    # -----------------------------------------------------------------------
    # Build dependency map
    # -----------------------------------------------------------------------
    logger.info("Building dependency map…")
    dep_map = build_dependency_map(parsed_files, owner, repo_name)
    save_json(dataclasses.asdict(dep_map), parsed_dir / "dependency_map.json")

    # -----------------------------------------------------------------------
    # Build call graph
    # -----------------------------------------------------------------------
    logger.info("Building call graph…")
    call_graph = build_call_graph(parsed_files, dep_map, owner, repo_name)
    save_json(dataclasses.asdict(call_graph), parsed_dir / "call_graph.json")

    # -----------------------------------------------------------------------
    # Find entry points
    # -----------------------------------------------------------------------
    logger.info("Finding entry points…")
    entry_points = find_entry_points(parsed_files, dep_map)
    save_json(entry_points, parsed_dir / "entry_points.json")

    # -----------------------------------------------------------------------
    # Detect architectural patterns
    # -----------------------------------------------------------------------
    logger.info("Detecting architectural patterns…")
    repo_all_paths = [f.get("path", "") for f in file_entries]
    patterns = detect_patterns(parsed_files, dep_map, repo_all_paths)
    save_json(patterns, parsed_dir / "patterns.json")

    # -----------------------------------------------------------------------
    # Build and save ParseManifest
    # -----------------------------------------------------------------------
    duration      = time.monotonic() - start_time
    failed_count  = sum(1 for pf in parsed_files if not pf.parse_success)
    ep_files      = [ep["file_path"] for ep in entry_points if ep["confidence"] == "high"]
    detected_pats = [p["pattern"] for p in patterns if p["confidence"] >= 0.40]

    manifest = ParseManifest(
        codeautopsy_version=config.CODEAUTOPSY_VERSION,
        parse_timestamp=datetime.now(timezone.utc).isoformat(),
        repo_owner=owner,
        repo_name=repo_name,
        total_files_parsed=len(parsed_files),
        total_files_failed=failed_count,
        total_functions_extracted=total_functions,
        total_classes_extracted=total_classes,
        total_imports_extracted=total_imports,
        total_call_edges=len(call_graph.edges),
        total_dependency_edges=len(dep_map.edges),
        parse_duration_seconds=round(duration, 2),
        detected_patterns=detected_pats,
        entry_points=ep_files,
        errors=errors,
    )

    save_json(dataclasses.asdict(manifest), parse_manifest_path)

    logger.info(
        "Parse complete: %d files | %d functions | %d classes | "
        "%d imports | %d call edges | %.1f seconds",
        len(parsed_files), total_functions, total_classes,
        total_imports, len(call_graph.edges), duration,
    )

    return manifest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _dict_to_manifest(d: dict) -> ParseManifest:
    """Reconstruct a ParseManifest from a plain dict (loaded from JSON)."""
    return ParseManifest(
        codeautopsy_version=d.get("codeautopsy_version", ""),
        parse_timestamp=d.get("parse_timestamp", ""),
        repo_owner=d.get("repo_owner", ""),
        repo_name=d.get("repo_name", ""),
        total_files_parsed=d.get("total_files_parsed", 0),
        total_files_failed=d.get("total_files_failed", 0),
        total_functions_extracted=d.get("total_functions_extracted", 0),
        total_classes_extracted=d.get("total_classes_extracted", 0),
        total_imports_extracted=d.get("total_imports_extracted", 0),
        total_call_edges=d.get("total_call_edges", 0),
        total_dependency_edges=d.get("total_dependency_edges", 0),
        parse_duration_seconds=d.get("parse_duration_seconds", 0),
        detected_patterns=d.get("detected_patterns", []),
        entry_points=d.get("entry_points", []),
        errors=d.get("errors", []),
    )
