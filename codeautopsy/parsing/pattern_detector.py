"""
parsing/pattern_detector.py — Architectural Pattern Detection

Analyzes the repository structure (file paths, import patterns, function
names) to detect common software architectural patterns.

Each pattern returns a confidence score (0.0–1.0) and a list of evidence
strings explaining why the pattern was detected.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from config import ARCHITECTURAL_PATTERN_SIGNALS
from parsing import DependencyMap, ParsedFile
from utils.logger import get_logger

logger = get_logger(__name__)


def detect_patterns(
    parsed_files: list[ParsedFile],
    dependency_map: DependencyMap,
    repo_file_paths: list[str],
) -> list[dict]:
    """
    Detect architectural patterns in a repository.

    Checks all configured patterns from ``ARCHITECTURAL_PATTERN_SIGNALS``
    plus deeper structural analysis for each.

    Args:
        parsed_files:    All ParsedFile objects.
        dependency_map:  Built dependency map.
        repo_file_paths: All file paths in the repo (from Phase 1 manifest).

    Returns:
        List of detected pattern dicts, sorted by confidence descending.
        Each dict has: pattern, confidence (float), evidence (list[str]).
    """
    all_paths_text = "\n".join(repo_file_paths).lower()
    import_modules = {
        imp.module.lower()
        for pf in parsed_files
        for imp in pf.imports
    }
    func_names = {
        fn.name.lower()
        for pf in parsed_files
        for fn in pf.functions
    }

    detectors = [
        _detect_mvc,
        _detect_layered,
        _detect_rest_api,
        _detect_event_driven,
        _detect_microservices,
        _detect_cli,
        _detect_plugin,
        _detect_frontend_component,
        _detect_library,
    ]

    results: list[dict] = []
    for detector in detectors:
        try:
            result = detector(
                parsed_files, dependency_map, repo_file_paths,
                all_paths_text, import_modules, func_names,
            )
            if result and result.get("confidence", 0) >= 0.20:
                results.append(result)
        except Exception as exc:
            logger.debug("Pattern detector error: %s", exc)

    results.sort(key=lambda x: x["confidence"], reverse=True)

    logger.info(
        "Pattern detection: %d patterns detected: %s",
        len(results),
        ", ".join(f"{r['pattern']} ({r['confidence']:.0%})" for r in results),
    )
    return results


# ---------------------------------------------------------------------------
# Individual pattern detectors
# ---------------------------------------------------------------------------

def _detect_mvc(pf, dep_map, all_paths, paths_text, imports, funcs) -> dict:
    evidence: list[str] = []
    score = 0

    dirs = _count_matching_dirs(all_paths, ["models", "views", "controllers", "controller"])
    for d in ["models", "views", "controllers"]:
        if d in paths_text:
            score += 1
            evidence.append(f"Found '{d}/' directory")

    # Django signals
    if "models.py" in paths_text and "views.py" in paths_text and "urls.py" in paths_text:
        score += 3
        evidence.append("Django MVC pattern (models.py + views.py + urls.py)")

    # Rails
    if "app/models" in paths_text and "app/views" in paths_text:
        score += 3
        evidence.append("Rails MVC pattern (app/models + app/views)")

    # Import-level evidence
    if "django.db" in str(imports) or "flask_sqlalchemy" in str(imports):
        score += 1
        evidence.append("ORM framework import detected (MVC data layer)")

    return {"pattern": "MVC", "confidence": min(score / 6, 1.0), "evidence": evidence}


def _detect_layered(pf, dep_map, all_paths, paths_text, imports, funcs) -> dict:
    evidence: list[str] = []
    score = 0

    for layer in ["services", "repositories", "handlers", "usecases"]:
        if layer in paths_text:
            score += 1.5
            evidence.append(f"Found '{layer}/' directory")

    # Service imports repository — strong layered signal
    for parsed_file in pf:
        if "service" in parsed_file.file_path.lower():
            for imp in parsed_file.imports:
                if "repository" in imp.module.lower() or "repo" in imp.module.lower():
                    score += 2
                    evidence.append(
                        f"Service file imports repository: {parsed_file.file_path}"
                    )
                    break

    # Function name patterns
    service_fns = sum(1 for f in funcs if any(w in f for w in ("service", "usecase", "handler")))
    repo_fns    = sum(1 for f in funcs if any(w in f for w in ("repository", "repo", "dao")))
    if service_fns and repo_fns:
        score += 2
        evidence.append(f"Service-style ({service_fns}) and repository-style ({repo_fns}) function names")

    return {"pattern": "Layered Architecture", "confidence": min(score / 7, 1.0), "evidence": evidence}


def _detect_rest_api(pf, dep_map, all_paths, paths_text, imports, funcs) -> dict:
    evidence: list[str] = []
    score = 0

    for path_sig in ["routes", "endpoints", "api", "routers"]:
        if path_sig in paths_text:
            score += 1
            evidence.append(f"Found '{path_sig}/' directory")

    # Framework imports
    rest_frameworks = ["flask", "fastapi", "django.rest", "express", "spring", "gin", "echo"]
    for fw in rest_frameworks:
        if any(fw in m for m in imports):
            score += 2
            evidence.append(f"REST framework import detected: {fw}")
            break

    # Route decorators in functions
    route_decorators = sum(
        1 for parsed_file in pf
        for fn in parsed_file.functions
        for d in fn.decorators
        if any(w in d.lower() for w in ("route", "get", "post", "put", "delete", "patch"))
    )
    if route_decorators:
        score += min(route_decorators / 5, 2)
        evidence.append(f"{route_decorators} route decorator(s) found")

    # Serializers (Django REST)
    if "serializers" in paths_text or "serializer" in str(imports):
        score += 1
        evidence.append("Serializer pattern detected (REST API data transformation layer)")

    return {"pattern": "REST API", "confidence": min(score / 6, 1.0), "evidence": evidence}


def _detect_event_driven(pf, dep_map, all_paths, paths_text, imports, funcs) -> dict:
    evidence: list[str] = []
    score = 0

    for path_sig in ["events", "handlers", "listeners", "subscribers", "publishers"]:
        if path_sig in paths_text:
            score += 1.5
            evidence.append(f"Found '{path_sig}/' directory")

    # Message queue imports
    mq_libs = ["celery", "kafka", "rabbitmq", "redis", "pika", "kombu", "confluent"]
    for lib in mq_libs:
        if any(lib in m for m in imports):
            score += 2
            evidence.append(f"Message queue library import: {lib}")

    # Event-related function names
    event_fns = sum(1 for f in funcs if any(w in f for w in ("on_", "handle_", "emit", "publish", "subscribe", "dispatch")))
    if event_fns:
        score += min(event_fns / 3, 2)
        evidence.append(f"{event_fns} event-style function name(s)")

    return {"pattern": "Event-driven", "confidence": min(score / 6, 1.0), "evidence": evidence}


def _detect_microservices(pf, dep_map, all_paths, paths_text, imports, funcs) -> dict:
    evidence: list[str] = []
    score = 0

    if "docker-compose" in paths_text:
        score += 3
        evidence.append("docker-compose file detected")

    if "kubernetes" in paths_text or "k8s" in paths_text or "helm" in paths_text:
        score += 3
        evidence.append("Kubernetes/Helm configuration detected")

    # Multiple independent main files in subdirectories
    main_files = [p for p in all_paths if p.split("/")[-1] in ("main.py", "main.go", "server.js", "main.rs") and "/" in p]
    if len(main_files) >= 2:
        score += 2
        evidence.append(f"{len(main_files)} independent entry point files found (microservices)")

    # Service-to-service HTTP calls
    http_imports = sum(1 for m in imports if m in ("requests", "httpx", "axios", "http", "https"))
    if http_imports:
        score += 1
        evidence.append("HTTP client imports suggest service-to-service calls")

    return {"pattern": "Microservices", "confidence": min(score / 7, 1.0), "evidence": evidence}


def _detect_cli(pf, dep_map, all_paths, paths_text, imports, funcs) -> dict:
    evidence: list[str] = []
    score = 0

    for path_sig in ["cli", "commands", "cmd"]:
        if path_sig in paths_text:
            score += 1.5
            evidence.append(f"Found '{path_sig}/' directory")

    cli_libs = ["click", "argparse", "typer", "docopt", "cobra", "commander", "clap"]
    for lib in cli_libs:
        if any(lib in m for m in imports):
            score += 2.5
            evidence.append(f"CLI framework import: {lib}")

    # sys.argv usage
    if "sys" in imports and "argv" in funcs:
        score += 1
        evidence.append("sys.argv usage detected")

    return {"pattern": "CLI Application", "confidence": min(score / 5, 1.0), "evidence": evidence}


def _detect_plugin(pf, dep_map, all_paths, paths_text, imports, funcs) -> dict:
    evidence: list[str] = []
    score = 0

    for path_sig in ["plugins", "extensions", "addons"]:
        if path_sig in paths_text:
            score += 2
            evidence.append(f"Found '{path_sig}/' directory")

    plugin_fns = sum(1 for f in funcs if any(w in f for w in ("register", "plugin", "extension", "hook")))
    if plugin_fns:
        score += min(plugin_fns, 2)
        evidence.append(f"{plugin_fns} plugin registration function name(s)")

    return {"pattern": "Plugin/Extension", "confidence": min(score / 4, 1.0), "evidence": evidence}


def _detect_frontend_component(pf, dep_map, all_paths, paths_text, imports, funcs) -> dict:
    evidence: list[str] = []
    score = 0

    for path_sig in ["components", "pages", "views", "widgets"]:
        if path_sig in paths_text:
            score += 1.5
            evidence.append(f"Found '{path_sig}/' directory")

    jsx_tsx_count = sum(1 for p in all_paths if p.endswith((".jsx", ".tsx")))
    if jsx_tsx_count > 0:
        score += min(jsx_tsx_count / 5, 2)
        evidence.append(f"{jsx_tsx_count} JSX/TSX component file(s)")

    ui_libs = ["react", "vue", "@angular", "svelte", "preact"]
    for lib in ui_libs:
        if any(lib in m for m in imports):
            score += 2
            evidence.append(f"UI framework import: {lib}")
            break

    return {"pattern": "Frontend Component", "confidence": min(score / 5, 1.0), "evidence": evidence}


def _detect_library(pf, dep_map, all_paths, paths_text, imports, funcs) -> dict:
    evidence: list[str] = []
    score = 0

    # Package entrypoints
    if "__init__.py" in paths_text or "index.ts" in paths_text or "index.js" in paths_text:
        score += 2
        evidence.append("Module exports packaged entrypoint (__init__.py or index.ts)")

    # Standard keywords for libraries
    libs_terms = ["serializer", "signer", "encoding", "decoding", "crypto", "utils", "helper", "compat"]
    found_terms = [t for t in libs_terms if t in paths_text]
    if found_terms:
        score += len(found_terms) * 0.5
        evidence.append(f"Found library/utility filename keywords: {', '.join(found_terms)}")

    # Packaging configuration files
    if "setup.py" in paths_text or "pyproject.toml" in paths_text or "package.json" in paths_text:
        score += 1.5
        evidence.append("Package configuration file detected (setup.py/pyproject.toml/package.json)")

    # Exposes functions/methods
    if len(funcs) > 20:
        score += 1.5
        evidence.append(f"High function and method density ({len(funcs)} functions/methods) suggesting utility codebase")

    return {"pattern": "Library/Utility", "confidence": min(score / 5, 1.0), "evidence": evidence}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _count_matching_dirs(paths: list[str], keywords: list[str]) -> int:
    """Count how many unique directory names match any keyword."""
    dirs: set[str] = set()
    for p in paths:
        parts = PurePosixPath(p).parts
        for part in parts[:-1]:
            if part.lower() in keywords:
                dirs.add(part)
    return len(dirs)
