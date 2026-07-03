"""
ingestion/language_detector.py — Repository Language Analysis

Analyses the filtered list of code files to produce a structured breakdown
of language distribution, identifying the primary language, whether the repo
is a polyglot monorepo, and whether multiple languages are co-dominant.
"""

from typing import Any

from ingestion.file_filter import get_file_language
from utils.logger import get_logger

logger = get_logger(__name__)

# Thresholds for monorepo and multi-primary-language detection
_MONOREPO_THRESHOLD_PERCENT: float = 15.0      # each language ≥ 15% → monorepo
_MONOREPO_LANGUAGE_COUNT: int = 3              # need at least 3 qualifying languages
_MULTI_PRIMARY_TOLERANCE_PERCENT: float = 10.0 # top-2 within 10% → co-dominant


def detect_languages(file_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute language statistics for a list of code file descriptors.

    Args:
        file_list: List of dicts, each with at least the keys:
                   ``path`` (str) and ``size`` (int, bytes).
                   Typically sourced from the filtered FetchedFile collection.

    Returns:
        A dict with the following structure::

            {
                "primary_language": "Python",
                "languages": {
                    "Python": {
                        "file_count": 42,
                        "byte_count": 125000,
                        "percentage": 78.5
                    },
                    ...
                },
                "is_monorepo": False,
                "has_multiple_primary_languages": False,
                "total_files": 52,
                "total_bytes": 159200
            }

        Returns an empty-language dict gracefully when *file_list* is empty.
    """
    if not file_list:
        logger.warning("Language detection called with an empty file list.")
        return _empty_result()

    # -----------------------------------------------------------------------
    # Accumulate per-language counts
    # -----------------------------------------------------------------------
    lang_stats: dict[str, dict[str, int]] = {}

    for file_info in file_list:
        path      = file_info.get("path", "")
        size      = int(file_info.get("size", 0))
        language  = get_file_language(path)

        if language is None:
            logger.debug("No language mapping for path %r — skipping in stats.", path)
            continue

        if language not in lang_stats:
            lang_stats[language] = {"file_count": 0, "byte_count": 0}

        lang_stats[language]["file_count"] += 1
        lang_stats[language]["byte_count"] += size

    if not lang_stats:
        logger.warning(
            "No recognizable code files found in file list (%d entries).", len(file_list)
        )
        return _empty_result()

    total_bytes = sum(s["byte_count"] for s in lang_stats.values())
    total_files = sum(s["file_count"] for s in lang_stats.values())

    logger.debug(
        "Language accumulation complete: %d languages, %d files, %d bytes.",
        len(lang_stats), total_files, total_bytes,
    )

    # -----------------------------------------------------------------------
    # Compute percentages
    # -----------------------------------------------------------------------
    languages: dict[str, dict[str, Any]] = {}
    for lang, stats in lang_stats.items():
        pct = round(stats["byte_count"] / total_bytes * 100, 1) if total_bytes else 0.0
        languages[lang] = {
            "file_count": stats["file_count"],
            "byte_count": stats["byte_count"],
            "percentage": pct,
        }

    # -----------------------------------------------------------------------
    # Sort by byte count descending to find primary language
    # -----------------------------------------------------------------------
    sorted_langs = sorted(
        languages.items(),
        key=lambda kv: kv[1]["byte_count"],
        reverse=True,
    )

    primary_language = sorted_langs[0][0]

    # -----------------------------------------------------------------------
    # Monorepo detection: ≥3 languages each contributing ≥15% of total bytes
    # -----------------------------------------------------------------------
    qualifying = [
        lang for lang, data in sorted_langs
        if data["percentage"] >= _MONOREPO_THRESHOLD_PERCENT
    ]
    is_monorepo = len(qualifying) >= _MONOREPO_LANGUAGE_COUNT

    # -----------------------------------------------------------------------
    # Co-dominant detection: top-2 languages within 10% of each other
    # -----------------------------------------------------------------------
    has_multiple_primary = False
    if len(sorted_langs) >= 2:
        first_pct  = sorted_langs[0][1]["percentage"]
        second_pct = sorted_langs[1][1]["percentage"]
        has_multiple_primary = abs(first_pct - second_pct) <= _MULTI_PRIMARY_TOLERANCE_PERCENT

    logger.info(
        "Language analysis: primary=%r, languages=%r, is_monorepo=%s, "
        "multi_primary=%s",
        primary_language,
        list(languages.keys()),
        is_monorepo,
        has_multiple_primary,
    )

    return {
        "primary_language":             primary_language,
        "languages":                    dict(sorted_langs),
        "is_monorepo":                  is_monorepo,
        "has_multiple_primary_languages": has_multiple_primary,
        "total_files":                  total_files,
        "total_bytes":                  total_bytes,
    }


def _empty_result() -> dict[str, Any]:
    """Return a safe default result when no files are available."""
    return {
        "primary_language":               "Unknown",
        "languages":                      {},
        "is_monorepo":                    False,
        "has_multiple_primary_languages": False,
        "total_files":                    0,
        "total_bytes":                    0,
    }
