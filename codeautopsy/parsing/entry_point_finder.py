"""
parsing/entry_point_finder.py — Repository Entry Point Detection

Identifies files that are the "start" of execution — where the program
begins. Uses a weighted multi-signal approach: each signal adds to a
confidence score that determines HIGH / MEDIUM / LOW confidence.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from parsing import DependencyMap, ParsedFile
from utils.logger import get_logger

logger = get_logger(__name__)

# Filename signals for each confidence tier
_HIGH_FILENAMES = frozenset({
    "main.py", "__main__.py", "manage.py", "wsgi.py", "asgi.py",
    "main.js", "index.js", "server.js", "app.js",
    "main.ts", "index.ts", "server.ts", "app.ts",
    "main.go", "main.rs", "main.c", "main.cpp",
    "Application.java", "Main.java",
})

_MEDIUM_FILENAMES = frozenset({
    "app.py", "server.py", "run.py", "cli.py", "start.py",
    "app.ts", "server.ts", "cli.ts",
    "index.tsx", "app.tsx",
})

# Source text signals that indicate a file "starts" something
_WEB_FRAMEWORK_SIGNALS = (
    "Flask(__name__)",
    "FastAPI()",
    "app = Flask",
    "app = FastAPI",
    "express()",
    "createServer(",
    "app.listen(",
    "gin.New()",
    "gin.Default()",
    "fiber.New()",
    "http.ListenAndServe",
)

_CLI_SIGNALS = (
    "argparse.ArgumentParser",
    "click.group",
    "click.command",
    "typer.Typer",
    "@click",
    "cobra.Command",
    "commander.Command",
    "process.argv",
)


def find_entry_points(
    parsed_files: list[ParsedFile],
    dependency_map: DependencyMap,
) -> list[dict]:
    """
    Identify repository entry points with confidence levels.

    Each candidate is scored using multiple signals. Files with higher
    total scores are reported with higher confidence.

    Args:
        parsed_files:   All ParsedFile objects from the parse run.
        dependency_map: Built dependency map (to check what imports what).

    Returns:
        List of entry point dicts, sorted by confidence (HIGH > MEDIUM > LOW).
        Each dict has keys: file_path, confidence, signals, entry_functions.
    """
    imported_files: set[str] = set()
    for importers in dependency_map.reverse_adjacency.values():
        if importers:
            # This file IS imported by others — less likely to be an entry
            pass
    # Files that nothing imports (not in reverse_adj with non-empty list)
    not_imported: set[str] = {
        fp for fp, importers in dependency_map.reverse_adjacency.items()
        if not importers
    }

    results: list[dict] = []

    for pf in parsed_files:
        score   = 0
        signals: list[str] = []
        entry_functions: list[str] = []

        fname = PurePosixPath(pf.file_path).name
        is_root_level = "/" not in pf.file_path

        # ---- HIGH confidence signals ----

        if pf.has_main_block:
            score += 3
            signals.append("has_main_block")

        if fname in _HIGH_FILENAMES:
            score += 3
            signals.append(f"filename_is_{fname}")

        if pf.is_entry_point:
            score += 2
            signals.append("parser_flagged_entry_point")

        # File not imported by anyone but imports others = top of dependency tree
        if pf.file_path in not_imported:
            imports_others = bool(dependency_map.adjacency.get(pf.file_path))
            if imports_others:
                score += 2
                signals.append("not_imported_by_others_but_imports_others")

        # Java main method
        for fn in pf.functions:
            if fn.name == "main" or fn.is_constructor and fn.name == "main":
                if pf.language == "Java" and fn.is_static:
                    score += 3
                    signals.append("java_main_method")
                    entry_functions.append(fn.qualified_name)
                elif fn.name == "main":
                    score += 2
                    signals.append("has_main_function")
                    entry_functions.append(fn.qualified_name)

        # ---- MEDIUM confidence signals ----

        if fname in _MEDIUM_FILENAMES:
            score += 2
            signals.append(f"filename_medium_{fname}")

        if is_root_level:
            score += 1
            signals.append("root_level_file")

        # Web framework or CLI instantiation
        file_content = "\n".join(
            fn.full_body for fn in pf.functions if fn.full_body != "[TRUNCATED]"
        )
        for sig in _WEB_FRAMEWORK_SIGNALS:
            if sig in file_content:
                score += 2
                signals.append(f"web_framework_{sig.split('(')[0].replace('.','_')}")
                break

        for sig in _CLI_SIGNALS:
            if sig in file_content:
                score += 2
                signals.append("cli_setup")
                break

        # ---- LOW confidence signals ----

        if not pf.has_exports and pf.language in ("JavaScript", "TypeScript"):
            score += 1
            signals.append("no_exports_js")

        # Only include if it has at least one signal
        if score == 0:
            continue

        # Map score to confidence tier
        if score >= 5:
            confidence = "high"
        elif score >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        results.append({
            "file_path":       pf.file_path,
            "confidence":      confidence,
            "confidence_score": score,
            "signals":         signals,
            "entry_functions": entry_functions,
        })

    # Sort: high → medium → low, then by score descending
    _order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda x: (_order[x["confidence"]], -x["confidence_score"]))

    logger.info(
        "Entry point detection: %d candidates found (%d high confidence).",
        len(results),
        sum(1 for r in results if r["confidence"] == "high"),
    )

    return results
