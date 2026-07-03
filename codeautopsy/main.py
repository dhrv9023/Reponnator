"""
main.py — CodeAutopsy Phase 1 + Phase 2 + Phase 3 Entry Point

Subcommand-based CLI that supports:
  ingest  — Phase 1: fetch a GitHub repo
  parse   — Phase 2: parse a previously-fetched repo
  embed   — Phase 3: chunk + embed a parsed repo into ChromaDB
  run     — Phase 1 + Phase 2 + Phase 3 back to back
  list    — list all fetched repos

Backward-compatible: positional-only URL (no subcommand) routes to ingest.

Usage:
    python main.py ingest https://github.com/pallets/flask
    python main.py parse  https://github.com/pallets/flask
    python main.py embed  https://github.com/pallets/flask
    python main.py run    https://github.com/pallets/flask
    python main.py list
    python main.py https://github.com/pallets/flask  # backward compat → ingest
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


# ---------------------------------------------------------------------------
# Module-level globals — populated lazily by _import_modules()
# ---------------------------------------------------------------------------
config             = None
logger_mod         = None
url_parser         = None
github_client_mod  = None
file_fetcher       = None
storage            = None
parse_orchestrator = None
chunk_orchestrator = None


def _import_modules() -> None:
    """Late-import all project modules with a clean error on missing deps."""
    global config, logger_mod, url_parser, github_client_mod, file_fetcher, storage
    global parse_orchestrator, chunk_orchestrator
    try:
        import config as _config
        import utils.logger as _logger_mod
        import ingestion.url_parser as _url_parser
        import ingestion.github_client as _github_client_mod
        import ingestion.file_fetcher as _file_fetcher
        import ingestion.storage as _storage
        import parsing.parse_orchestrator as _po
        import chunking.chunk_orchestrator as _co
        config              = _config
        logger_mod          = _logger_mod
        url_parser          = _url_parser
        github_client_mod   = _github_client_mod
        file_fetcher        = _file_fetcher
        storage             = _storage
        parse_orchestrator  = _po
        chunk_orchestrator  = _co
    except ImportError as exc:
        _fatal(
            f"Missing dependency: {exc}\n"
            "Run:  pip install -r requirements.txt"
        )


# ---------------------------------------------------------------------------
# CLI builder
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="codeautopsy",
        description="CodeAutopsy — GitHub repository ingestion and code analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py ingest https://github.com/pallets/flask\n"
            "  python main.py parse  pallets/flask\n"
            "  python main.py run    https://github.com/pallets/flask\n"
            "  python main.py list\n"
            "\n"
            "Backward-compatible (no subcommand = ingest):\n"
            "  python main.py https://github.com/pallets/flask\n"
        ),
    )

    sub = ap.add_subparsers(dest="command")

    # -- ingest --
    p_ingest = sub.add_parser("ingest", help="Phase 1: fetch a GitHub repository.")
    p_ingest.add_argument("repo_url", help="GitHub repository URL.")
    p_ingest.add_argument("--branch", metavar="BRANCH", default=None)
    p_ingest.add_argument("--force",  action="store_true", help="Re-fetch even if cached.")
    p_ingest.add_argument("--debug",  action="store_true")

    # -- parse --
    p_parse = sub.add_parser("parse", help="Phase 2: parse a fetched repository.")
    p_parse.add_argument("repo_url", help="GitHub repository URL (must be fetched first).")
    p_parse.add_argument("--force",  action="store_true", help="Re-parse even if cached.")
    p_parse.add_argument("--debug",  action="store_true")

    # -- embed --
    p_embed = sub.add_parser("embed", help="Phase 3: chunk + embed a parsed repository.")
    p_embed.add_argument("repo_url", help="GitHub repository URL (must be parsed first).")
    p_embed.add_argument("--force",  action="store_true", help="Re-embed even if cached.")
    p_embed.add_argument("--debug",  action="store_true")

    # -- run --
    p_run = sub.add_parser("run", help="Phase 1 + Phase 2 + Phase 3: ingest, parse, embed.")
    p_run.add_argument("repo_url", help="GitHub repository URL.")
    p_run.add_argument("--branch", metavar="BRANCH", default=None)
    p_run.add_argument("--force",  action="store_true", help="Re-fetch, re-parse, and re-embed.")
    p_run.add_argument("--debug",  action="store_true")

    # -- chat --
    p_chat = sub.add_parser("chat", help="Phase 4: Interactive Q&A about the codebase.")
    p_chat.add_argument("repo_url", help="GitHub repository URL (must be embedded first).")
    p_chat.add_argument("--session", metavar="SESSION_ID", default=None, help="Resume existing session.")
    p_chat.add_argument("--debug",  action="store_true")

    # -- traverse --
    p_traverse = sub.add_parser("traverse", help="Phase 5: Call graph traversal with LangGraph agent.")
    p_traverse.add_argument("repo_url", help="GitHub repository URL (must be embedded first).")
    p_traverse.add_argument("--depth", metavar="DEPTH", type=int, default=6, help="Max BFS depth (default: 6).")
    p_traverse.add_argument("--budget", metavar="BUDGET", type=int, default=30, help="Max LLM calls (default: 30).")
    p_traverse.add_argument("--force",  action="store_true", help="Re-traverse even if cached.")
    p_traverse.add_argument("--debug",  action="store_true")

    # -- diagram --
    p_diagram = sub.add_parser("diagram", help="Phase 6: Generate interactive Mermaid.js architecture diagram.")
    p_diagram.add_argument("repo_url", help="GitHub repository URL (must be parsed first).")
    p_diagram.add_argument("--force",  action="store_true", help="Re-generate even if cached.")
    p_diagram.add_argument("--debug",  action="store_true")

    # -- story --
    p_story = sub.add_parser("story", help="Phase 7: Generate architectural story with Repponator.")
    p_story.add_argument("repo_url", help="GitHub repository URL (must be parsed first).")
    p_story.add_argument("--force",  action="store_true", help="Re-generate even if cached.")
    p_story.add_argument("--debug",  action="store_true")

    # -- list --
    sub.add_parser("list", help="List all previously fetched repositories.")

    # Backward-compat: no subcommand + positional URL → treat as ingest
    # Use a different dest so it doesn't overwrite the subcommand's repo_url
    ap.add_argument("_compat_repo_url", nargs="?", metavar="REPO_URL",
                    help=argparse.SUPPRESS)
    ap.add_argument("--branch",  metavar="BRANCH", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--force",   action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--list",    action="store_true",  help=argparse.SUPPRESS)
    ap.add_argument("--debug",   action="store_true",  help=argparse.SUPPRESS)

    return ap


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _fatal(message: str) -> None:
    print(f"\n❌  Error: {message}\n", file=sys.stderr)
    sys.exit(1)


def _format_bytes(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes //= 1024
    return f"{num_bytes:.1f} TB"


def _enable_debug() -> None:
    import logging
    logging.getLogger().setLevel(logging.DEBUG)
    for name, lg in logging.Logger.manager.loggerDict.items():
        if isinstance(lg, logging.Logger):
            lg.setLevel(logging.DEBUG)


def _resolve_repo_folder(owner: str, repo_name: str, data_dir: Path) -> Path:
    """Return the expected Phase 1 repo folder path."""
    return data_dir / f"{owner}__{repo_name}"


# ---------------------------------------------------------------------------
# Ingest command (Phase 1)
# ---------------------------------------------------------------------------

def _cmd_ingest(args) -> None:
    """Run Phase 1 ingestion pipeline."""
    data_dir: Path = config.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    try:
        parsed = url_parser.parse_github_url(args.repo_url)
    except ValueError as exc:
        _fatal(str(exc))

    branch  = getattr(args, "branch", None) or parsed.branch
    owner   = parsed.owner
    repo_nm = parsed.repo_name

    print(f"\n🔍  CodeAutopsy — ingesting {parsed.normalized_url}\n")

    if _check_cache(owner, repo_nm, data_dir, getattr(args, "force", False)):
        return

    try:
        from dotenv import load_dotenv
        import os
        load_dotenv(_HERE / ".env")
        token  = os.getenv("GITHUB_TOKEN") or None
        client = github_client_mod.GitHubClient(token=token)
    except github_client_mod.GitHubClientError as exc:
        _fatal(str(exc))
    except Exception as exc:
        _fatal(f"Could not initialise GitHub client: {exc}")

    try:
        result = file_fetcher.fetch_repository(
            github_client=client, owner=owner, repo_name=repo_nm, branch=branch,
        )
    except github_client_mod.RepoNotFoundError as exc:
        _fatal(str(exc))
    except github_client_mod.RepoPrivateError as exc:
        _fatal(str(exc))
    except github_client_mod.GitHubClientError as exc:
        _fatal(f"GitHub API error: {exc}")
    except KeyboardInterrupt:
        _fatal("Ingestion interrupted by user.")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).critical("Unexpected error during ingestion", exc_info=True)
        _fatal(f"Unexpected error: {type(exc).__name__}: {exc}")

    try:
        repo_folder = storage.save_fetch_result(result, data_dir)
    except OSError as exc:
        if exc.errno == 28:
            _fatal("Disk is full. Free up space and re-run with --force.")
        _fatal(f"Failed to save results: {exc}")
    except Exception as exc:
        _fatal(f"Failed to save results: {exc}")

    _print_ingest_summary(result, repo_folder)


# ---------------------------------------------------------------------------
# Parse command (Phase 2)
# ---------------------------------------------------------------------------

def _cmd_parse(args) -> None:
    """Run Phase 2 parse pipeline on a previously-fetched repo."""
    data_dir: Path = config.DATA_DIR

    try:
        parsed = url_parser.parse_github_url(args.repo_url)
    except ValueError as exc:
        _fatal(str(exc))

    owner   = parsed.owner
    repo_nm = parsed.repo_name

    repo_folder = _resolve_repo_folder(owner, repo_nm, data_dir)
    if not (repo_folder / "manifest.json").exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been fetched yet.\n"
            f"Run first:  python main.py ingest {args.repo_url}"
        )

    print(f"\n🔬  CodeAutopsy — parsing {owner}/{repo_nm}\n")

    try:
        manifest = parse_orchestrator.parse_repository(
            repo_folder=repo_folder,
            force_reparse=getattr(args, "force", False),
        )
    except FileNotFoundError as exc:
        _fatal(str(exc))
    except KeyboardInterrupt:
        _fatal("Parse interrupted by user.")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).critical("Unexpected error during parse", exc_info=True)
        _fatal(f"Unexpected error: {type(exc).__name__}: {exc}")

    _print_parse_summary(manifest, repo_folder)


# ---------------------------------------------------------------------------
# Embed command (Phase 3)
# ---------------------------------------------------------------------------

def _cmd_embed(args) -> None:
    """Run Phase 3 chunk-and-embed pipeline on a previously-parsed repo."""
    data_dir: Path = config.DATA_DIR

    try:
        parsed = url_parser.parse_github_url(args.repo_url)
    except ValueError as exc:
        _fatal(str(exc))

    owner   = parsed.owner
    repo_nm = parsed.repo_name

    repo_folder = _resolve_repo_folder(owner, repo_nm, data_dir)

    # Check Phase 1 exists
    if not (repo_folder / "manifest.json").exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been fetched yet.\n"
            f"Run first:  python main.py ingest {args.repo_url}"
        )

    # Check Phase 2 exists
    parse_manifest = (
        repo_folder / config.PARSED_DIR_NAME / config.PARSE_MANIFEST_FILENAME
    )
    if not parse_manifest.exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been parsed yet.\n"
            f"Run first:  python main.py parse {args.repo_url}"
        )

    print(f"\n🧩  CodeAutopsy — embedding {owner}/{repo_nm}\n")

    try:
        manifest = chunk_orchestrator.chunk_and_embed_repository(
            repo_folder=repo_folder,
            force_rechunk=getattr(args, "force", False),
        )
    except FileNotFoundError as exc:
        _fatal(str(exc))
    except RuntimeError as exc:
        _fatal(str(exc))
    except KeyboardInterrupt:
        _fatal("Embedding interrupted by user.")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).critical("Unexpected error during embedding", exc_info=True)
        _fatal(f"Unexpected error: {type(exc).__name__}: {exc}")

    _print_chunk_summary(manifest, repo_folder)


# ---------------------------------------------------------------------------
# Run command (Phase 1 + Phase 2 + Phase 3 + Phase 5)
# ---------------------------------------------------------------------------

def _cmd_run(args) -> None:
    """Phase 1 then Phase 2 then Phase 3 then Phase 5 in sequence."""
    print("\n🚀  CodeAutopsy — full pipeline (ingest → parse → embed → traverse)\n")
    _cmd_ingest(args)
    # After ingest, run parse (force=False since ingest just produced fresh data)
    setattr(args, "force", False)
    _cmd_parse(args)
    # After parse, run embed
    _cmd_embed(args)
    # After embed, run traverse
    setattr(args, "depth", 6)
    setattr(args, "budget", 30)
    _cmd_traverse(args)


# ---------------------------------------------------------------------------
# Traverse command (Phase 5)
# ---------------------------------------------------------------------------

def _cmd_traverse(args) -> None:
    """Run Phase 5 call graph traversal."""
    data_dir: Path = config.DATA_DIR

    try:
        parsed = url_parser.parse_github_url(args.repo_url)
    except ValueError as exc:
        _fatal(str(exc))

    owner   = parsed.owner
    repo_nm = parsed.repo_name

    repo_folder = _resolve_repo_folder(owner, repo_nm, data_dir)

    # Check Phase 1-3 exist
    if not (repo_folder / "manifest.json").exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been fetched yet.\n"
            f"Run first:  python main.py run {args.repo_url}"
        )

    parse_manifest = repo_folder / config.PARSED_DIR_NAME / config.PARSE_MANIFEST_FILENAME
    if not parse_manifest.exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been parsed yet.\n"
            f"Run first:  python main.py run {args.repo_url}"
        )

    chunk_manifest = repo_folder / "chunks" / "chunk_manifest.json"
    if not chunk_manifest.exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been embedded yet.\n"
            f"Run first:  python main.py run {args.repo_url}"
        )

    # Initialize traversal orchestrator
    try:
        from agent.traversal_orchestrator import TraversalOrchestrator
        orchestrator = TraversalOrchestrator(owner, repo_nm)
    except Exception as exc:
        _fatal(f"Failed to initialize traversal orchestrator: {exc}")

    # Run traversal
    try:
        graph = orchestrator.traverse(
            max_depth=getattr(args, "depth", 6),
            llm_budget=getattr(args, "budget", 30),
            force_retraverse=getattr(args, "force", False)
        )
    except KeyboardInterrupt:
        _fatal("Traversal interrupted by user.")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).critical("Unexpected error during traversal", exc_info=True)
        _fatal(f"Unexpected error: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Diagram command (Phase 6)
# ---------------------------------------------------------------------------

def _cmd_diagram(args) -> None:
    """Run Phase 6 Mermaid diagram generation."""
    data_dir: Path = config.DATA_DIR

    try:
        parsed = url_parser.parse_github_url(args.repo_url)
    except ValueError as exc:
        _fatal(str(exc))

    owner   = parsed.owner
    repo_nm = parsed.repo_name

    repo_folder = _resolve_repo_folder(owner, repo_nm, data_dir)

    # Check Phase 1-2 exist
    if not (repo_folder / "manifest.json").exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been fetched yet.\n"
            f"Run first:  python main.py run {args.repo_url}"
        )

    parse_manifest = repo_folder / config.PARSED_DIR_NAME / config.PARSE_MANIFEST_FILENAME
    if not parse_manifest.exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been parsed yet.\n"
            f"Run first:  python main.py parse {args.repo_url}"
        )

    # Check if already generated
    diagram_folder = repo_folder / "diagram"
    mermaid_path = diagram_folder / "mermaid_diagram.mmd"
    
    if mermaid_path.exists() and not getattr(args, "force", False):
        print(f"\n✅  Diagram already generated for {owner}/{repo_nm}")
        print(f"    Location: {diagram_folder}")
        print(f"    Use --force to regenerate\n")
        return

    print(f"\n📊  CodeAutopsy — generating diagram for {owner}/{repo_nm}\n")

    # Generate diagram
    try:
        from diagram.mermaid_generator import generate_mermaid_diagram
        mermaid_code, metadata = generate_mermaid_diagram(repo_folder)
    except KeyboardInterrupt:
        _fatal("Diagram generation interrupted by user.")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).critical("Unexpected error during diagram generation", exc_info=True)
        _fatal(f"Unexpected error: {type(exc).__name__}: {exc}")

    # Print summary
    _print_diagram_summary(metadata, diagram_folder)


# ---------------------------------------------------------------------------
# Story command (Phase 7)
# ---------------------------------------------------------------------------

def _cmd_story(args) -> None:
    """Run Phase 7 Repponator story generation."""
    data_dir: Path = config.DATA_DIR

    try:
        parsed = url_parser.parse_github_url(args.repo_url)
    except ValueError as exc:
        _fatal(str(exc))

    owner   = parsed.owner
    repo_nm = parsed.repo_name

    repo_folder = _resolve_repo_folder(owner, repo_nm, data_dir)

    # Check Phase 1-2 exist
    if not (repo_folder / "manifest.json").exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been fetched yet.\n"
            f"Run first:  python main.py run {args.repo_url}"
        )

    parse_manifest = repo_folder / config.PARSED_DIR_NAME / config.PARSE_MANIFEST_FILENAME
    if not parse_manifest.exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been parsed yet.\n"
            f"Run first:  python main.py parse {args.repo_url}"
        )

    # Check if already generated
    story_folder = repo_folder / "story"
    story_path = story_folder / "story_output.json"
    
    if story_path.exists() and not getattr(args, "force", False):
        print(f"\n✅  Story already generated for {owner}/{repo_nm}")
        print(f"    Location: {story_folder}")
        print(f"    Use --force to regenerate\n")
        return

    print(f"\n📖  CodeAutopsy — generating architectural story for {owner}/{repo_nm}\n")

    # Generate story
    try:
        from story.repponator import generate_architectural_story
        story, metadata = generate_architectural_story(repo_folder, force=getattr(args, "force", False))
    except KeyboardInterrupt:
        _fatal("Story generation interrupted by user.")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).critical("Unexpected error during story generation", exc_info=True)
        _fatal(f"Unexpected error: {type(exc).__name__}: {exc}")

    # Print summary
    _print_story_summary(story, metadata, story_folder)


# ---------------------------------------------------------------------------
# List command
# ---------------------------------------------------------------------------

def _cmd_list() -> None:
    data_dir: Path = config.DATA_DIR
    repos = storage.list_fetched_repos(data_dir)
    if not repos:
        print("No repositories have been fetched yet.")
        print("Run:  python main.py ingest <github-url>")
        return

    print(f"\n{'Full Name':<35} {'Language':<15} {'Files':>7} {'Fetched At'}")
    print("─" * 80)
    for r in repos:
        mark = "" if r.get("is_complete") else " ⚠ incomplete"
        print(
            f"{r['full_name']:<35} {r['primary_language']:<15} "
            f"{r['total_files_fetched']:>7,}   {r['fetch_timestamp'][:19]}{mark}"
        )
    print()


# ---------------------------------------------------------------------------
# Summary printers
# ---------------------------------------------------------------------------

def _print_ingest_summary(result, repo_folder: Path) -> None:
    lang     = result.language_analysis.get("primary_language", "Unknown")
    langs    = result.language_analysis.get("languages", {})
    lang_pct = f" ({langs[lang]['percentage']:.1f}%)" if lang in langs else ""
    size_str = _format_bytes(result.total_bytes_fetched)
    files_str = f"{result.total_files_fetched:,} fetched / {result.total_files_in_repo:,} total"
    saved_to  = str(repo_folder.relative_to(Path.cwd())) if repo_folder.is_relative_to(Path.cwd()) else str(repo_folder)

    width = 52
    def row(label: str, value: str) -> str:
        content = f"  {label:<12}: {value}"
        return f"║{content:<{width}}║"

    print()
    print("╔" + "═" * width + "╗")
    print(f"║{'  CodeAutopsy — Ingestion Complete':<{width}}║")
    print("╠" + "═" * width + "╣")
    print(row("Repo",     f"{result.owner}/{result.repo_name}"))
    print(row("Branch",   result.branch))
    print(row("Language", f"{lang}{lang_pct}"))
    print(row("Files",    files_str))
    print(row("Size",     size_str))
    print(row("Time",     f"{result.fetch_duration_seconds:.1f} seconds"))
    print(row("Saved to", saved_to))
    print("╚" + "═" * width + "╝")
    print()

    if result.warnings:
        print("⚠️  Warnings:")
        for w in result.warnings:
            print(f"   • {w}")
        print()
    if result.errors:
        print(f"⚠️  {len(result.errors)} non-fatal error(s) — see fetch.log for details.")
        print()


def _print_parse_summary(manifest, repo_folder: Path) -> None:
    saved_to  = str(repo_folder.relative_to(Path.cwd())) if repo_folder.is_relative_to(Path.cwd()) else str(repo_folder)
    patterns  = ", ".join(manifest.detected_patterns) if manifest.detected_patterns else "None detected"
    ep        = manifest.entry_points[0] if manifest.entry_points else "None detected"

    width = 52
    def row(label: str, value: str) -> str:
        content = f"  {label:<12}: {value}"
        return f"║{content:<{width}}║"

    print()
    print("╔" + "═" * width + "╗")
    print(f"║{'  CodeAutopsy — Parse Complete':<{width}}║")
    print("╠" + "═" * width + "╣")
    print(row("Repo",       f"{manifest.repo_owner}/{manifest.repo_name}"))
    print(row("Files",      f"{manifest.total_files_parsed:,} parsed / {manifest.total_files_failed} failed"))
    print(row("Functions",  f"{manifest.total_functions_extracted:,} extracted"))
    print(row("Classes",    f"{manifest.total_classes_extracted:,} extracted"))
    print(row("Imports",    f"{manifest.total_imports_extracted:,} extracted"))
    print(row("Call Edges", f"{manifest.total_call_edges:,} mapped"))
    print(row("Patterns",   patterns))
    print(row("Entry Point", ep))
    print(row("Time",       f"{manifest.parse_duration_seconds:.1f} seconds"))
    print(row("Saved to",   f"{saved_to}/parsed/"))
    print("╚" + "═" * width + "╝")
    print()

    if manifest.errors:
        print(f"⚠️  {len(manifest.errors)} non-fatal error(s) during parse.")
        print()


def _print_chunk_summary(manifest, repo_folder: Path) -> None:
    saved_to = (
        str(repo_folder.relative_to(Path.cwd()))
        if repo_folder.is_relative_to(Path.cwd())
        else str(repo_folder)
    )
    cbt = manifest.chunks_by_type

    def _get(key: str) -> int:
        return cbt.get(key, 0)

    width = 52
    def row(label: str, value: str) -> str:
        content = f"  {label:<16}: {value}"
        return f"║{content:<{width}}║"

    print()
    print("╔" + "═" * width + "╗")
    print(f"║{'  CodeAutopsy — Embedding Complete':<{width}}║")
    print("╠" + "═" * width + "╣")
    print(row("Repo",           f"{manifest.repo_owner}/{manifest.repo_name}"))
    print(row("Total Chunks",   f"{manifest.total_chunks:,}"))
    print(row("Functions",      f"{_get('function') + _get('method'):,}"))
    print(row("Classes",        f"{_get('class_summary'):,}"))
    print(row("File Summaries", f"{_get('file_summary'):,}"))
    print(row("Import Context", f"{_get('import_context'):,}"))
    print(row("Sub-chunks",     f"{_get('function_subchunk'):,}"))
    print(row("Total Tokens",   f"{manifest.total_tokens:,}"))
    print(row("Avg Tokens",     f"{manifest.average_tokens_per_chunk} per chunk"))
    print(row("Model",          f"{manifest.embedding_model} ({manifest.embedding_dimensions}-dim)"))
    print(row("ChromaDB",       manifest.chroma_collection_name))
    print(row("Embed Time",     f"{manifest.embed_duration_seconds:.1f} seconds"))
    print(row("Saved to",       f"{saved_to}/chunks/"))
    print("╚" + "═" * width + "╝")
    print()

    if manifest.errors:
        print(f"⚠️  {len(manifest.errors)} non-fatal error(s) during embedding.")
        print()


def _print_diagram_summary(metadata: dict, diagram_folder: Path) -> None:
    """Print diagram generation summary."""
    saved_to = (
        str(diagram_folder.relative_to(Path.cwd()))
        if diagram_folder.is_relative_to(Path.cwd())
        else str(diagram_folder)
    )
    
    entry_points = sum(1 for n in metadata['nodes'] if n['type'] == 'entry_point')
    core_utils = sum(1 for n in metadata['nodes'] if n['type'] == 'core_utility')
    modules = sum(1 for n in metadata['nodes'] if n['type'] == 'module')
    
    width = 52
    def row(label: str, value: str) -> str:
        content = f"  {label:<16}: {value}"
        return f"║{content:<{width}}║"

    print()
    print("╔" + "═" * width + "╗")
    print(f"║{'  CodeAutopsy — Diagram Complete':<{width}}║")
    print("╠" + "═" * width + "╣")
    print(row("Repo",           f"{metadata['repo_owner']}/{metadata['repo_name']}"))
    print(row("Total Nodes",    f"{metadata['total_nodes']:,}"))
    print(row("Total Edges",    f"{metadata['total_edges']:,}"))
    print(row("Entry Points",   f"{entry_points}"))
    print(row("Core Utilities", f"{core_utils}"))
    print(row("Modules",        f"{modules}"))
    
    # Handle patterns (can be list of strings or dicts)
    patterns_list = metadata.get('patterns', [])
    if patterns_list:
        if isinstance(patterns_list[0], dict):
            pattern_names = [p.get('pattern', '') for p in patterns_list[:3]]
        else:
            pattern_names = patterns_list[:3]
        patterns_str = ', '.join(pattern_names) if pattern_names else 'None'
    else:
        patterns_str = 'None'
    
    print(row("Patterns",       patterns_str))
    print(row("Saved to",       saved_to))
    print("╚" + "═" * width + "╝")
    print()
    print(f"📊  View diagram: Open {saved_to}/mermaid_diagram.mmd in Mermaid Live Editor")
    print(f"    https://mermaid.live/\n")


def _print_story_summary(story, metadata, story_folder: Path) -> None:
    """Print story generation summary."""
    saved_to = (
        str(story_folder.relative_to(Path.cwd()))
        if story_folder.is_relative_to(Path.cwd())
        else str(story_folder)
    )
    
    width = 52
    def row(label: str, value: str) -> str:
        content = f"  {label:<16}: {value}"
        return f"║{content:<{width}}║"

    print()
    print("╔" + "═" * width + "╗")
    print(f"║{'  CodeAutopsy — Story Complete':<{width}}║")
    print("╠" + "═" * width + "╣")
    print(row("Repo",           f"{metadata.repo_owner}/{metadata.repo_name}"))
    print(row("Primary Commit", story.primary_commitment[:30] + "..."))
    print(row("Key Modules",    f"{len(story.key_modules)}"))
    print(row("Model",          metadata.model_used))
    print(row("Duration",       f"{metadata.generation_duration_seconds:.1f}s"))
    print(row("Tokens",         f"{metadata.prompt_tokens + metadata.completion_tokens:,}"))
    print(row("Saved to",       saved_to))
    print("╚" + "═" * width + "╝")
    print()
    print(f"📖  Story preview:")
    print(f"    {story.primary_commitment}\n")
    print(f"    Founding Metaphor: {story.founding_metaphor}\n")


# ---------------------------------------------------------------------------
# Cache check (Phase 1)
# ---------------------------------------------------------------------------

def _check_cache(owner: str, repo_name: str, data_dir: Path, force: bool) -> bool:
    repos     = storage.list_fetched_repos(data_dir)
    full_name = f"{owner}/{repo_name}"
    cached    = next((r for r in repos if r["full_name"].lower() == full_name.lower()), None)

    if cached is None:
        return False

    if not cached.get("is_complete"):
        print(f"⚠️  Previous fetch of {full_name!r} appears incomplete. Re-fetching…\n")
        return False

    if force:
        print(f"♻️   --force set. Re-fetching {full_name!r}…\n")
        return False

    print(
        f"✅  Repository {full_name!r} was already fetched at "
        f"{cached['fetch_timestamp'][:19]}.\n"
        f"    Files fetched : {cached['total_files_fetched']:,}\n"
        f"    Primary lang  : {cached['primary_language']}\n"
        f"    Saved at      : {cached['repo_folder']}\n\n"
        "    Use --force to re-fetch, or run 'parse' to continue to Phase 2."
    )
    return True


# ---------------------------------------------------------------------------
# Chat command (Phase 4)
# ---------------------------------------------------------------------------

def _cmd_chat(args) -> None:
    """Run Phase 4 interactive Q&A session."""
    try:
        from colorama import init, Fore, Style
        init(autoreset=True)
    except ImportError:
        # Fallback if colorama not installed
        class Fore:
            GREEN = CYAN = YELLOW = RED = MAGENTA = BLUE = ""
        class Style:
            BRIGHT = RESET_ALL = ""
    
    data_dir: Path = config.DATA_DIR

    try:
        parsed = url_parser.parse_github_url(args.repo_url)
    except ValueError as exc:
        _fatal(str(exc))

    owner   = parsed.owner
    repo_nm = parsed.repo_name

    repo_folder = _resolve_repo_folder(owner, repo_nm, data_dir)

    # Check Phase 1-3 exist
    if not (repo_folder / "manifest.json").exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been fetched yet.\n"
            f"Run first:  python main.py run {args.repo_url}"
        )

    parse_manifest = repo_folder / config.PARSED_DIR_NAME / config.PARSE_MANIFEST_FILENAME
    if not parse_manifest.exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been parsed yet.\n"
            f"Run first:  python main.py run {args.repo_url}"
        )

    chunk_manifest = repo_folder / "chunks" / "chunk_manifest.json"
    if not chunk_manifest.exists():
        _fatal(
            f"Repository {owner}/{repo_nm!r} has not been embedded yet.\n"
            f"Run first:  python main.py run {args.repo_url}"
        )

    # Initialize RAG pipeline
    try:
        from rag.rag_pipeline import RAGPipeline
        pipeline = RAGPipeline(owner, repo_nm)
    except Exception as exc:
        _fatal(f"Failed to initialize RAG pipeline: {exc}")

    # Get collection stats
    try:
        stats = pipeline.get_collection_stats()
        chunk_count = stats.get('count', 0)
    except:
        chunk_count = "unknown"

    # Get or create session
    session_id = getattr(args, "session", None)
    if session_id:
        try:
            pipeline.conversation_manager.get_session(session_id)
            print(f"{Fore.GREEN}Resuming session: {session_id}")
        except:
            print(f"{Fore.YELLOW}Session {session_id} not found. Creating new session...")
            session_id = pipeline.new_session()
    else:
        session_id = pipeline.new_session()

    # Get model info
    model_info = pipeline.llm_client.get_model_info()
    model_name = f"{model_info['provider']}/{model_info['model_name']}"

    # Print welcome banner
    print()
    print(f"{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗")
    print(f"{Fore.CYAN}║  {Style.BRIGHT}CodeAutopsy Q&A{Style.RESET_ALL} — {Fore.GREEN}github.com/{owner}/{repo_nm}{Fore.CYAN}{'':>{60-len(owner)-len(repo_nm)-30}}║")
    print(f"{Fore.CYAN}║  Chunks: {chunk_count} | Model: {model_name} | Session: {session_id}{'':>{60-len(str(chunk_count))-len(model_name)-len(session_id)-35}}║")
    print(f"{Fore.CYAN}║  Type 'quit' to exit | 'stats' for info | 'help' for commands{'':>2}║")
    print(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"{Fore.YELLOW}Ask anything about this codebase:")
    print()

    # Interactive loop
    while True:
        try:
            # Get question
            question = input(f"{Fore.MAGENTA}❯ {Style.RESET_ALL}").strip()
            
            if not question:
                continue
            
            # Handle special commands
            if question.lower() in ['quit', 'exit', 'q']:
                print(f"\n{Fore.GREEN}Goodbye! Session saved: {session_id}\n")
                break
            
            elif question.lower() == 'help':
                print(f"\n{Fore.CYAN}Available commands:")
                print(f"  {Fore.GREEN}quit{Style.RESET_ALL}     - Exit the chat")
                print(f"  {Fore.GREEN}stats{Style.RESET_ALL}    - Show collection statistics")
                print(f"  {Fore.GREEN}history{Style.RESET_ALL}  - Show conversation history")
                print(f"  {Fore.GREEN}new{Style.RESET_ALL}      - Start a new session")
                print(f"  {Fore.GREEN}sessions{Style.RESET_ALL} - List all sessions")
                print(f"  {Fore.GREEN}help{Style.RESET_ALL}     - Show this help\n")
                continue
            
            elif question.lower() == 'stats':
                stats = pipeline.get_collection_stats()
                print(f"\n{Fore.CYAN}Collection Statistics:")
                print(f"  Total chunks: {stats.get('count', 0):,}")
                print(f"  Collection: {stats.get('name', 'unknown')}\n")
                continue
            
            elif question.lower() == 'history':
                session = pipeline.conversation_manager.get_session(session_id)
                if not session.turns:
                    print(f"\n{Fore.YELLOW}No conversation history yet.\n")
                else:
                    print(f"\n{Fore.CYAN}Conversation History ({len(session.turns)} turns):")
                    for turn in session.turns:
                        print(f"\n{Fore.MAGENTA}Q{turn.turn_number}: {turn.question}")
                        answer_preview = turn.answer[:150] + "..." if len(turn.answer) > 150 else turn.answer
                        print(f"{Fore.GREEN}A{turn.turn_number}: {answer_preview}")
                    print()
                continue
            
            elif question.lower() == 'new':
                session_id = pipeline.new_session()
                print(f"\n{Fore.GREEN}New session created: {session_id}\n")
                continue
            
            elif question.lower() == 'sessions':
                sessions = pipeline.list_sessions()
                if not sessions:
                    print(f"\n{Fore.YELLOW}No sessions found.\n")
                else:
                    print(f"\n{Fore.CYAN}Available Sessions:")
                    for sess in sessions[:10]:  # Show last 10
                        print(f"  {Fore.GREEN}{sess['session_id']}{Style.RESET_ALL} - "
                              f"{sess['total_questions']} questions - "
                              f"{sess['last_active'][:19]}")
                    print()
                continue
            
            # Process question
            print(f"{Fore.CYAN}🔍 Searching...{Style.RESET_ALL}", end="\r")
            
            try:
                response = pipeline.ask(question, session_id)
                
                # Clear "Searching..." line
                print(" " * 50, end="\r")
                
                # Print response
                print(f"\n{Fore.CYAN}{'━' * 60}")
                print(f"{Fore.CYAN}📖 Answer ({Fore.GREEN}{response.confidence.upper()}{Fore.CYAN} confidence | "
                      f"{response.response_time_seconds:.1f}s | {response.chunks_retrieved} chunks)")
                print(f"{Fore.CYAN}{'━' * 60}{Style.RESET_ALL}\n")
                
                print(response.answer)
                print()
                
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Interrupted. Type 'quit' to exit.\n")
                continue
            except Exception as exc:
                print(f"\n{Fore.RED}Error: {exc}\n")
                if getattr(args, "debug", False):
                    import traceback
                    traceback.print_exc()
                continue
        
        except KeyboardInterrupt:
            print(f"\n\n{Fore.GREEN}Goodbye! Session saved: {session_id}\n")
            break
        except EOFError:
            print(f"\n\n{Fore.GREEN}Goodbye! Session saved: {session_id}\n")
            break


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments and dispatch to the correct command handler."""
    ap   = _build_parser()
    args = ap.parse_args()

    _import_modules()

    if getattr(args, "debug", False):
        _enable_debug()

    # ------------------------------------------------------------------
    # Backward compatibility: positional URL with no subcommand → ingest
    # ------------------------------------------------------------------
    if args.command is None:
        if getattr(args, "list", False):
            _cmd_list()
            return
        compat_url = getattr(args, "_compat_repo_url", None)
        if compat_url:
            args.repo_url = compat_url
            args.command = "ingest"
        else:
            ap.print_help()
            sys.exit(1)

    if args.command == "ingest":
        _cmd_ingest(args)
    elif args.command == "parse":
        _cmd_parse(args)
    elif args.command == "embed":
        _cmd_embed(args)
    elif args.command == "run":
        _cmd_run(args)
    elif args.command == "chat":
        _cmd_chat(args)
    elif args.command == "traverse":
        _cmd_traverse(args)
    elif args.command == "diagram":
        _cmd_diagram(args)
    elif args.command == "story":
        _cmd_story(args)
    elif args.command == "list":
        _cmd_list()
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
