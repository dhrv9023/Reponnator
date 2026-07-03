"""
config.py — CodeAutopsy Phase 1 + 2 + 3 Configuration

Central source of truth for all constants, paths, and tuning parameters.
No magic strings or numbers anywhere else in the codebase.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Project versioning
# ---------------------------------------------------------------------------
CODEAUTOPSY_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Supported programming language extensions
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS: dict[str, list[str]] = {
    "Python":      [".py", ".pyi", ".pyw"],
    "JavaScript":  [".js", ".mjs", ".cjs", ".jsx"],
    "TypeScript":  [".ts", ".tsx"],
    "Java":        [".java"],
    "Go":          [".go"],
    "Rust":        [".rs"],
    "C":           [".c", ".h"],
    "C++":         [".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h++"],
    "Ruby":        [".rb", ".rake", ".gemspec"],
    "PHP":         [".php", ".php3", ".php4", ".php5", ".phtml"],
    "Swift":       [".swift"],
    "Kotlin":      [".kt", ".kts"],
    "Scala":       [".scala", ".sc"],
    "Shell":       [".sh", ".bash", ".zsh", ".fish", ".ksh"],
    "R":           [".r", ".R"],
    "Elixir":      [".ex", ".exs"],
    "Haskell":     [".hs", ".lhs"],
    "Lua":         [".lua"],
    "Perl":        [".pl", ".pm", ".perl"],
    "Dart":        [".dart"],
    "C#":          [".cs"],
    "F#":          [".fs", ".fsi", ".fsx"],
    "Clojure":     [".clj", ".cljs", ".cljc"],
    "Erlang":      [".erl", ".hrl"],
    "Julia":       [".jl"],
    "Nim":         [".nim"],
    "Zig":         [".zig"],
    "OCaml":       [".ml", ".mli"],
}

# Build reverse lookup: extension → language name  (all lowercase keys)
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ext.lower(): lang
    for lang, exts in SUPPORTED_EXTENSIONS.items()
    for ext in exts
}

# ---------------------------------------------------------------------------
# Directory names that are always ignored (matched against any path component)
# ---------------------------------------------------------------------------
IGNORED_DIRECTORIES: frozenset[str] = frozenset({
    # JavaScript / Node
    "node_modules",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "bower_components",
    # Python
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "venv",
    "env",
    ".env",
    ".venv",
    "eggs",
    "wheels",
    ".eggs",
    ".tox",
    # Build / dist outputs
    "dist",
    "build",
    "target",
    "out",
    "bin",
    "obj",
    "_build",
    "output",
    # Test fixtures / snapshots
    "__mocks__",
    "fixtures",
    "snapshots",
    "__fixtures__",
    # Coverage
    "coverage",
    ".coverage",
    "htmlcoverage",
    ".nyc_output",
    # IDE / OS
    ".git",
    ".idea",
    ".vscode",
    ".vs",
    ".DS_Store",
    ".Trash",
    # Dependency caches
    "vendor",
    "packages",
    ".gradle",
    ".m2",
    ".cargo",
    # Temporary / misc
    "tmp",
    "temp",
    ".cache",
    "log",
    "logs",
})

# ---------------------------------------------------------------------------
# File patterns to ignore (glob-style, matched against filename only)
# ---------------------------------------------------------------------------
IGNORED_FILE_PATTERNS: list[str] = [
    # Minified / compiled assets
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.bundle.js",
    "*.chunk.js",
    # Lock files
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "composer.lock",
    "Gemfile.lock",
    "cargo.lock",
    "*.sum",           # go.sum
    # Module definition files (go.mod is the intentional exception — keep it)
    # "*.mod",   # intentionally commented out — go.mod should be kept
    # Compiled objects and archives
    "*.pyc",
    "*.pyo",
    "*.class",
    "*.o",
    "*.a",
    "*.so",
    "*.dll",
    "*.dylib",
    "*.exe",
    "*.wasm",
    # Generated files
    "*.pb.go",
    "*.generated.*",
    "*_gen.go",
    "*.g.dart",
    # Other
    ".DS_Store",
    "Thumbs.db",
    "*.orig",
    "*.rej",
]

# ---------------------------------------------------------------------------
# File-size and volume limits
# ---------------------------------------------------------------------------
MAX_FILE_SIZE_BYTES: int = 500_000          # 500 KB per file
MAX_REPO_FILES: int = 5_000                 # warn threshold, not hard stop
MAX_TOTAL_SIZE_BYTES: int = 50_000_000      # 50 MB total across all files

# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------
GITHUB_API_BASE_URL: str = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS: int = 30
MAX_RETRIES: int = 3
RETRY_DELAY_SECONDS: float = 2.0
RATE_LIMIT_BUFFER: int = 10  # pause if fewer than this many requests remain

# ---------------------------------------------------------------------------
# Filesystem paths  (relative to the codeautopsy/ package root)
# ---------------------------------------------------------------------------
_PACKAGE_ROOT: Path = Path(__file__).parent.resolve()
DATA_DIR: Path = _PACKAGE_ROOT / "data" / "repos"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FORMAT: str = "[%(asctime)s] [%(levelname)-8s] [%(name)s] — %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%dT%H:%M:%S"
LOG_LEVEL_DEFAULT: str = "INFO"

# ---------------------------------------------------------------------------
# Binary content detection
# ---------------------------------------------------------------------------
BINARY_DETECTION_SAMPLE_BYTES: int = 8_000   # inspect first N bytes
BINARY_NULL_BYTE_THRESHOLD: float = 0.01     # >1% null bytes → binary
BINARY_NONPRINTABLE_THRESHOLD: float = 0.30  # >30% non-printable → binary

# ===========================================================================
# Phase 2 — Parsing Configuration
# ===========================================================================

# ---------------------------------------------------------------------------
# Python standard-library module names
# (used to classify imports as stdlib vs third-party vs local)
# ---------------------------------------------------------------------------
STDLIB_MODULES_PYTHON: frozenset[str] = frozenset({
    "abc", "ast", "asyncio", "base64", "binascii", "builtins", "calendar",
    "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs", "codeop",
    "collections", "colorsys", "compileall", "concurrent", "configparser",
    "contextlib", "contextvars", "copy", "copyreg", "cProfile", "csv",
    "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "doctest", "email", "encodings", "enum", "errno",
    "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch", "fractions",
    "ftplib", "functools", "gc", "getopt", "getpass", "gettext", "glob",
    "grp", "gzip", "hashlib", "heapq", "hmac", "html", "http", "idlelib",
    "imaplib", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "lib2to3", "linecache", "locale", "logging",
    "lzma", "mailbox", "marshal", "math", "mimetypes", "mmap", "modulefinder",
    "multiprocessing", "netrc", "nis", "nntplib", "numbers", "operator",
    "optparse", "os", "ossaudiodev", "pathlib", "pdb", "pickle",
    "pickletools", "pipes", "pkgutil", "platform", "plistlib", "poplib",
    "posix", "posixpath", "pprint", "profile", "pstats", "pty", "pwd",
    "py_compile", "pyclbr", "pydoc", "queue", "quopri", "random", "re",
    "readline", "reprlib", "resource", "rlcompleter", "runpy", "sched",
    "secrets", "select", "selectors", "shelve", "shlex", "shutil", "signal",
    "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver",
    "spwd", "sqlite3", "sre_compile", "sre_constants", "sre_parse", "ssl",
    "stat", "statistics", "string", "stringprep", "struct", "subprocess",
    "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny",
    "tarfile", "telnetlib", "tempfile", "termios", "test", "textwrap",
    "threading", "time", "timeit", "tkinter", "token", "tokenize",
    "trace", "traceback", "tracemalloc", "tty", "turtle", "turtledemo",
    "types", "typing", "unicodedata", "unittest", "urllib", "uu",
    "uuid", "venv", "warnings", "wave", "weakref", "webbrowser",
    "wsgiref", "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile",
    "zipimport", "zlib", "zoneinfo", "_thread",
})

# ---------------------------------------------------------------------------
# Node.js built-in module names
# ---------------------------------------------------------------------------
STDLIB_MODULES_NODE: frozenset[str] = frozenset({
    "assert", "async_hooks", "buffer", "child_process", "cluster",
    "console", "constants", "crypto", "dgram", "diagnostics_channel",
    "dns", "domain", "events", "fs", "http", "http2", "https",
    "inspector", "module", "net", "os", "path", "perf_hooks",
    "process", "punycode", "querystring", "readline", "repl",
    "stream", "string_decoder", "timers", "tls", "trace_events",
    "tty", "url", "util", "v8", "vm", "wasi", "worker_threads",
    "zlib",
})

# ---------------------------------------------------------------------------
# Parsing limits
# ---------------------------------------------------------------------------
MAX_FUNCTION_BODY_CHARS: int     = 50_000  # truncate full_body beyond this
MAX_FILE_PARSE_TIMEOUT_SECONDS: int = 30   # abandon parse of one file
MINIFIED_LINE_LENGTH_THRESHOLD: int = 10_000  # skip if any line is this long

# ---------------------------------------------------------------------------
# Complexity counting: branching keywords per language
# ---------------------------------------------------------------------------
COMPLEXITY_KEYWORDS: dict[str, list[str]] = {
    "Python":     ["if", "elif", "for", "while", "try", "except", "with",
                   "and", "or", "assert"],
    "JavaScript": ["if", "else", "for", "while", "try", "catch", "switch",
                   "&&", "||", "??"],
    "TypeScript": ["if", "else", "for", "while", "try", "catch", "switch",
                   "&&", "||", "??"],
    "Java":       ["if", "else", "for", "while", "try", "catch", "switch",
                   "&&", "||"],
    "Go":         ["if", "else", "for", "switch", "select", "&&", "||"],
    "Rust":       ["if", "else", "for", "while", "loop", "match",
                   "&&", "||"],
    "C":          ["if", "else", "for", "while", "do", "switch",
                   "&&", "||"],
    "C++":        ["if", "else", "for", "while", "do", "switch", "try",
                   "catch", "&&", "||"],
    "Ruby":       ["if", "elsif", "unless", "while", "until", "for",
                   "rescue", "&&", "||"],
    "PHP":        ["if", "elseif", "else", "for", "foreach", "while",
                   "try", "catch", "&&", "||"],
    "Swift":      ["if", "else", "for", "while", "switch", "guard",
                   "catch", "&&", "||"],
    "Kotlin":     ["if", "else", "for", "while", "when", "try", "catch",
                   "&&", "||"],
}

# ---------------------------------------------------------------------------
# Entry point detection patterns per language
# ---------------------------------------------------------------------------
ENTRY_POINT_PATTERNS: dict[str, list[str]] = {
    "Python": [
        "if __name__", "def main", "app.run", "uvicorn.run",
        "manage.py", "wsgi.py", "asgi.py", "main.py", "app.py",
        "server.py", "run.py", "cli.py", "__main__.py",
    ],
    "JavaScript": [
        "index.js", "server.js", "app.js", "main.js",
        "bin/", "process.argv",
    ],
    "TypeScript": [
        "index.ts", "server.ts", "app.ts", "main.ts",
        "bin/", "process.argv",
    ],
    "Java": [
        "public static void main", "SpringApplication.run",
        "Application.java", "Main.java",
    ],
    "Go": [
        "func main()", "main.go",
    ],
    "Rust": [
        "fn main()", "main.rs",
    ],
    "C":   ["int main(", "main.c"],
    "C++": ["int main(", "main.cpp", "main.cc"],
}

# ---------------------------------------------------------------------------
# Architectural pattern signals: pattern name → path/content signals
# ---------------------------------------------------------------------------
ARCHITECTURAL_PATTERN_SIGNALS: dict[str, list[str]] = {
    "MVC": [
        "models/", "views/", "controllers/",
        "model.py", "view.py", "controller.py",
        "models.py", "views.py", "urls.py",          # Django
        "app/models", "app/views", "app/controllers", # Rails
    ],
    "Layered": [
        "services/", "repositories/", "handlers/",
        "service.py", "repository.py", "handler.py",
        "services.py", "repositories.py",
    ],
    "Microservices": [
        "services/", "gateway/", "docker-compose",
        "kubernetes/", "k8s/", "helm/",
    ],
    "Event-driven": [
        "events/", "handlers/", "listeners/",
        "subscribers/", "publishers/", "queue/",
        "celery", "kafka", "rabbitmq", "pubsub",
    ],
    "REST API": [
        "routes/", "endpoints/", "api/",
        "router.py", "routes.py", "serializers/",
        "@app.get", "@app.post", "@GetMapping", "@PostMapping",
    ],
    "CLI": [
        "cli/", "commands/", "click", "argparse", "typer",
        "cobra", "commander", "sys.argv",
    ],
    "Plugin/Extension": [
        "plugins/", "extensions/",
        "register_plugin", "add_extension",
    ],
    "Frontend Component": [
        "components/", "pages/",
        ".jsx", ".tsx",
        "ReactDOM", "createRoot", "Vue", "NgModule",
    ],
}

# ---------------------------------------------------------------------------
# Parsing output directory name (relative to repo folder)
# ---------------------------------------------------------------------------
PARSED_DIR_NAME: str = "parsed"
PARSE_MANIFEST_FILENAME: str = "parse_manifest.json"

# ===========================================================================
# Phase 3 — Chunking + Embedding Configuration
# ===========================================================================

# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------
EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS: int = 384       # all-MiniLM-L6-v2 output size
EMBEDDING_BATCH_SIZE: int = 64        # chunks per encode() call
MAX_EMBEDDING_TOKENS: int = 256       # model wordpiece token limit

# ---------------------------------------------------------------------------
# Chunking limits
# ---------------------------------------------------------------------------
MAX_CHUNK_TOKENS: int          = 200  # target tokens per chunk (stay under model limit)
CHUNK_OVERLAP_TOKENS: int      = 40   # overlap tokens between sub-chunks
MIN_CHUNK_TOKENS: int          = 10   # skip chunks smaller than this
MAX_CONTENT_PREVIEW_CHARS: int = 200  # length of content_preview field

# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------
CHROMA_DB_PATH: str           = str(_PACKAGE_ROOT / "data" / "chroma_db")
CHROMA_COLLECTION_PREFIX: str = "codeautopsy"
# Full collection name format: codeautopsy__{owner}__{repo}

# ---------------------------------------------------------------------------
# Content templates — used by chunker.py to build chunk text
# Fill {placeholders} are replaced by _fill_template()
# ---------------------------------------------------------------------------
FUNCTION_CONTENT_TEMPLATE: str = """\
File: {file_path}
Language: {language}
Function: {qualified_name}
{decorators_line}
{signature_line}

{docstring_block}

{body}
""".strip()

CLASS_SUMMARY_CONTENT_TEMPLATE: str = """\
File: {file_path}
Language: {language}
Class: {qualified_name}
{base_classes_line}

{docstring_block}

Methods: {methods_list}
Attributes: {attributes_list}
""".strip()

FILE_SUMMARY_CONTENT_TEMPLATE: str = """\
File: {file_path}
Language: {language}
Module Summary for: {qualified_name}

Imports: {imports_summary}
Classes defined: {classes_list}
Functions defined: {functions_list}
Entry point: {is_entry_point}
{module_docstring_block}
""".strip()

IMPORT_CONTEXT_CONTENT_TEMPLATE: str = """\
File: {file_path}
Import dependencies for: {file_path}

External libraries used: {third_party_imports}
Local modules imported: {local_imports}
Standard library used: {stdlib_imports}
""".strip()


# ===========================================================================
# Phase 4 — RAG Q&A Layer Configuration
# ===========================================================================

# ---------------------------------------------------------------------------
# LLM Configuration
# ---------------------------------------------------------------------------
LLM_PROVIDER: str = "gemini"           # "ollama", "gemini", or "groq" (default: gemini)
                                       # Read from .env: LLM_PROVIDER
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLLAMA_MODEL: str = "mistral"          # or "codellama", "llama3"
                                       # Read from .env: OLLAMA_MODEL
GEMINI_MODEL: str = "gemini-flash-latest"  # Free tier model (stable)
GEMINI_RPM_LIMIT: int = 15             # Gemini free tier rate limit
GROQ_MODEL: str = "llama-3.3-70b-versatile" # Default Groq model

# ---------------------------------------------------------------------------
# RAG Configuration
# ---------------------------------------------------------------------------
TOP_K_SEMANTIC: int = 15               # chunks retrieved by semantic search
TOP_K_KEYWORD: int = 10                # chunks retrieved by BM25
TOP_K_HYDE: int = 8                    # chunks retrieved by HyDE
TOP_K_FINAL: int = 12                  # chunks after reranking + dedup
                                       # sent to context builder

GRAPH_EXPANSION_DEPTH: int = 1         # how many hops to expand graph
                                       # 1 = include direct callers/callees
MAX_EXPANSION_CHUNKS: int = 6          # max chunks added by graph expansion

# ---------------------------------------------------------------------------
# Context Window Management
# ---------------------------------------------------------------------------
MAX_CONTEXT_TOKENS: int = 3000         # max tokens in assembled context
                                       # conservative limit for all models
MAX_ANSWER_TOKENS: int = 1000          # max tokens in LLM answer
CONTEXT_CHUNK_SEPARATOR: str = "\n\n---\n\n"

# ---------------------------------------------------------------------------
# Hybrid Search Weights
# ---------------------------------------------------------------------------
SEMANTIC_WEIGHT: float = 0.65          # weight for semantic similarity score
KEYWORD_WEIGHT: float = 0.35           # weight for BM25 score

# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------
MAX_CONVERSATION_TURNS: int = 20       # max turns per session
MAX_HISTORY_TOKENS: int = 800          # max tokens from history to include
                                       # in each subsequent turn's context

# ---------------------------------------------------------------------------
# Confidence thresholds
# ---------------------------------------------------------------------------
HIGH_CONFIDENCE_THRESHOLD: float = 0.75   # avg combined_score for high confidence
MEDIUM_CONFIDENCE_THRESHOLD: float = 0.50

# ---------------------------------------------------------------------------
# Query classification keywords
# ---------------------------------------------------------------------------
WHAT_IS_KEYWORDS: list[str] = [
    "what is", "what are", "describe", "explain what",
    "tell me about", "what does"
]
HOW_DOES_KEYWORDS: list[str] = [
    "how does", "how do", "how is", "how are",
    "how to", "walk me through", "explain how"
]
WHERE_IS_KEYWORDS: list[str] = [
    "where is", "where are", "where does", "find",
    "locate", "which file", "which function"
]
WHY_IS_KEYWORDS: list[str] = [
    "why is", "why are", "why does", "why was",
    "reason for", "purpose of", "rationale"
]
WHAT_CALLS_KEYWORDS: list[str] = [
    "what calls", "who calls", "what uses",
    "what depends on", "callers of"
]
WHAT_IMPORTS_KEYWORDS: list[str] = [
    "what imports", "what does it import",
    "dependencies of", "what requires"
]
WHAT_BREAKS_KEYWORDS: list[str] = [
    "what breaks", "what would break",
    "impact of removing", "what depends on",
    "side effects of changing"
]
COMPARE_KEYWORDS: list[str] = [
    "compare", "difference between", "vs", "versus",
    "similar to", "how does X differ"
]

# ===========================================================================
# Phase 5 — LangGraph Agent (Call Graph Traversal) Configuration
# ===========================================================================

# ---------------------------------------------------------------------------
# Traversal limits
# ---------------------------------------------------------------------------
MAX_TRAVERSAL_DEPTH: int = 6           # max hops from entry point
MAX_TRAVERSAL_NODES: int = 500         # stop if graph grows beyond this
DEFAULT_LLM_BUDGET: int = 30           # max LLM analysis calls per traversal

# ---------------------------------------------------------------------------
# Hub node detection
# ---------------------------------------------------------------------------
HUB_NODE_THRESHOLD: int = 5            # called by >= 5 nodes = hub

# ---------------------------------------------------------------------------
# LLM analysis eligibility (only these get deep LLM analysis)
# ---------------------------------------------------------------------------
ANALYZE_ENTRY_POINTS: bool = True      # always analyze entry points
ANALYZE_HUBS: bool = True              # analyze hub nodes
ANALYZE_DEPTH_THRESHOLD: int = 3       # analyze nodes at depth <= 3
ANALYZE_CROSS_LAYER: bool = True       # analyze nodes that cross layers
MIN_COMPLEXITY_FOR_ANALYSIS: int = 3   # only analyze if complexity >= 3

# ---------------------------------------------------------------------------
# Architectural layer detection — file path signals
# ---------------------------------------------------------------------------
LAYER_SIGNALS: dict[str, list[str]] = {
    "entry":      ["main", "app", "server", "index", "run",
                   "start", "cli", "manage", "wsgi", "asgi"],
    "controller": ["controller", "handler", "router", "route",
                   "endpoint", "view", "resource"],
    "service":    ["service", "usecase", "business", "logic",
                   "manager", "processor", "orchestrator"],
    "repository": ["repository", "repo", "dao", "store",
                   "database", "db", "storage", "persistence"],
    "model":      ["model", "entity", "schema", "domain",
                   "struct", "type", "dto", "record"],
    "utility":    ["util", "helper", "common", "shared",
                   "lib", "tool", "mixin", "base"],
    "config":     ["config", "setting", "env", "constant",
                   "conf", "cfg"],
    "middleware": ["middleware", "interceptor", "filter",
                   "guard", "auth", "cors", "logging"],
    "external":   []  # assigned to unresolved/external calls
}

# ---------------------------------------------------------------------------
# Traversal output
# ---------------------------------------------------------------------------
TRAVERSAL_OUTPUT_DIR: str = "traversal"
