# Phase 2 Architecture & Design Decisions

---

## 1. Why Tree-sitter?

### The problem with regex-based parsing

Before Tree-sitter, the obvious alternative for code analysis is regex. Regex is:
- **Fast** to write, but wrong in every edge case (multiline strings, nested structures, type annotations with generics)
- **Brittle** — a single unusual Python construct breaks extraction for the whole file
- **Language-unaware** — it cannot understand scope, nesting, or syntax hierarchy

### Why Tree-sitter wins

Tree-sitter is a **production-grade incremental parsing library** used in GitHub, Neovim, Helix, and many other tools:

- Parses source code into a concrete syntax tree (CST) — every token has a position, type, and parent
- **Error-tolerant** — produces a partial tree even on syntax errors (unlike Python's `ast` module which crashes on invalid code)
- Grammars exist for 100+ languages — same API for all of them
- **Zero runtime language requirements** — no Python runtime needed to parse Python, no JVM to parse Java
- Nodes are query-able using an S-expression DSL, similar to CSS selectors for HTML

### tree-sitter vs tree-sitter-languages

`tree-sitter` is the engine. `tree-sitter-languages` is a **pre-compiled bundle of grammars** that works with tree-sitter 0.21.x on Python. Individual packages like `tree-sitter-python` are only available for tree-sitter 0.23+, which has a different API. We use the bundled approach for stability:

```python
from tree_sitter_languages import get_language, get_parser

parser   = get_parser("python")      # Ready to parse
language = get_language("python")    # For running queries
```

---

## 2. Parser Architecture

### Abstract Base Class (BaseParser)

All language parsers share a single abstract base class in `parsing/base_parser.py`. This design enforces:

1. **Uniform interface** — every parser has the same five abstract methods
2. **Shared fault tolerance** — encoding, timeout, minified-file detection, and error capture are implemented once in the base class and work for all languages
3. **DRY helpers** — docstring extraction, complexity scoring, and import classification are shared across all parsers

```
BaseParser (ABC)
├── parse_file()              ← concrete: orchestrates the full parse of one file
│   ├── encoding guard         (UTF-8 → latin-1 fallback)
│   ├── minified file guard    (skip files with lines > 10,000 chars)
│   ├── empty file guard       (return clean empty result, don't crash)
│   ├── _ensure_parser()       (lazy tree-sitter init, grammar loaded once)
│   ├── SIGALRM timeout        (30s per file, POSIX only)
│   ├── tree-sitter parse()
│   ├── _safe_extract() × 4   (each extract_* call individually guarded)
│   └── _safe_detect()         (entry point detection guarded)
│
├── get_node_text()           ← concrete: safe byte-slice to string
├── get_docstring()           ← concrete: finds first string in body
├── calculate_complexity()    ← concrete: counts branching keywords
├── resolve_import_type()     ← concrete: stdlib / third-party / local
├── _safe_query()             ← concrete: tree-sitter query, never raises
│
├── extract_functions()       ← ABSTRACT: must implement per language
├── extract_classes()         ← ABSTRACT: must implement per language
├── extract_imports()         ← ABSTRACT: must implement per language
├── extract_global_variables()← ABSTRACT: must implement per language
└── detect_entry_point()      ← ABSTRACT: must implement per language
```

### Why stateless parsers?

Each parser instance holds **no per-file state**. The tree-sitter parser object (`self._parser`) is initialized once lazily and reused across all files. Between `parse_file()` calls, nothing is carried over.

This is critical for correctness — if a parser held state from a previous file, it could contaminate extractions from the current one. It also makes parsers safe to reuse from the registry without any reset between calls.

### The Parser Registry

`parser_registry.py` maintains a global dict of pre-instantiated parsers:

```python
_REGISTRY = {
    "Python":     PythonParser(),      # instantiated once at import time
    "JavaScript": JavaScriptParser(),  # reused for every .js file
    "TypeScript": TypeScriptParser(),
    "Java":       JavaParser(),
    "Go":         GoParser(),
    "Rust":       RustParser(),
    "C":          CppParser(file_extension=".c"),
    "C++":        CppParser(file_extension=".cpp"),
}
```

Extension-level overrides handle edge cases:
- `.tsx` → `TSXParser` (TypeScript + JSX grammar)
- `.jsx` → `JavaScriptParser`
- `.mjs`, `.cjs` → `JavaScriptParser`
- `.h`, `.hpp` → `CppParser`

---

## 3. The "Parse One, Discard AST" Memory Strategy

Tree-sitter ASTs can be large for big files. The pipeline processes files sequentially:

1. Read source bytes
2. Parse → get AST tree
3. Extract all entities into Python dataclasses
4. **Let the tree go out of scope** — Python's garbage collector reclaims memory
5. Move to the next file

This is why the orchestrator processes files in a simple `for` loop rather than in parallel — parallel AST processing would hold all trees in memory simultaneously, which could exhaust RAM on large repositories.

The extracted dataclasses (ParsedFunction, ParsedClass, etc.) are lightweight — they hold strings and ints, not AST nodes.

---

## 4. Dataclass Contract Design

All Phase 2 data is represented as Python `@dataclass` instances defined in `parsing/__init__.py`. This single-file contract means:

- **Phase 3** knows exactly what fields to expect
- **Tests** can construct mock objects without importing complex modules
- **JSON serialization** is automatic via `dataclasses.asdict()`

### The Data Hierarchy

```
ParseManifest (one per repo/parse run)
├── metadata: owner, repo, timestamp, version, duration
├── counts: files, functions, classes, imports, call_edges, dep_edges
├── entry_points: list[str] (file paths)
└── detected_patterns: list[str] (pattern names)

DependencyMap (one per repo)
├── edges: list[DependencyEdge]
│   └── from_file → to_file, to_module, dependency_type, line_number
├── adjacency:         {file_path: [imported_file_paths]}
└── reverse_adjacency: {file_path: [files_that_import_it]}

CallGraph (one per repo)
├── edges: list[CallEdge]
│   └── caller_qualified → callee_name, callee_resolved, is_resolved
├── adjacency:         {function_qname: [called_qnames]}
└── reverse_adjacency: {function_qname: [callers]}

ParsedFile (one per source file)
├── functions: list[ParsedFunction]
│   ├── name, qualified_name, file_path, start_line, end_line
│   ├── parameters: list[ParsedParameter]
│   ├── return_type, docstring, body_preview, full_body
│   ├── parent_class, is_method, is_constructor, is_private, is_static, is_async
│   ├── decorators: list[str]
│   ├── calls: list[str]  ← raw callee names (not yet resolved)
│   └── complexity_score: int
├── classes: list[ParsedClass]
│   ├── name, qualified_name, file_path, start_line, end_line
│   ├── base_classes, implemented_interfaces
│   ├── methods, class_variables, instance_variables
│   ├── is_abstract, is_interface
│   └── decorators: list[str]
├── imports: list[ParsedImport]
│   ├── module, imported_items, aliases
│   ├── import_type: "absolute" | "relative" | "dynamic" | "star"
│   └── is_stdlib, is_third_party, is_local, is_conditional
└── metadata: language, sha, size_bytes, total_lines, parse_success, parse_errors
```

---

## 5. Complexity Scoring

Complexity is measured using a keyword-count heuristic inspired by cyclomatic complexity. For each function:

1. Start with score = 1 (the function itself)
2. For every occurrence of a branching keyword, add 1

The keyword set is language-specific, defined in `config.COMPLEXITY_KEYWORDS`:

```python
"Python": ["if", "elif", "for", "while", "try", "except", "with", "and", "or", "assert"]
"Go":     ["if", "else", "for", "switch", "select", "&&", "||"]
```

A complexity of 1 means the function is a straight-line path. A complexity of 10+ means the function has many conditional branches and may need refactoring. This score is exposed to Phase 3 for use in chunk prioritization.

---

## 6. Import Classification

Every import is classified into exactly one of three categories:

| Category | Meaning | Example |
|----------|---------|---------|
| `is_stdlib` | Part of the language's standard library | `os`, `pathlib`, `fmt`, `std::collections` |
| `is_third_party` | External package from a package manager | `flask`, `react`, `tokio`, `spring` |
| `is_local` | File within this repository | `./utils`, `../models`, relative imports |

The classification uses:
1. **Relative import detection** — any import starting with `.` is local
2. **Stdlib sets** — `config.STDLIB_MODULES_PYTHON` (80+ modules) and `config.STDLIB_MODULES_NODE` (30+ modules)
3. **Language-specific heuristics** — Go short paths (`fmt`, `os`), Rust `std::`, `core::`, Java `java.*`, `javax.*`
4. **Default** — anything not classified as stdlib or local is third-party

This classification feeds directly into the dependency builder, which uses it to decide whether to attempt local file resolution.

---

## 7. Dependency Resolution Strategy

When a file does `from .utils import helper`, the dependency builder tries to find what actual file `.utils` refers to. The resolution algorithm:

```
1. Normalize the module string (strip quotes, normalize slashes)
2. If starts with "." or "/" → relative import:
   a. Count leading dots to determine how many directories to go up
   b. Join with the importing file's directory
   c. Try candidates: base, base.py, base.js, base.ts, base/__init__.py, base/index.js
3. If absolute → convert dots to slashes ("pkg.sub" → "pkg/sub")
   a. Try direct path match
   b. Try stem index (last component only)
4. If still unresolved → edge has to_file=None, but is still recorded
```

Unresolved imports are kept in the graph because:
- They still tell us about third-party dependencies
- They may be resolved later by Phase 3 with more context

---

## 8. Call Graph Resolution Strategy

For each function's `calls` list (raw callee names from AST), the call graph builder attempts to resolve to a fully-qualified name:

```
Priority order:
1. Local import map — "UserService" → resolved via "from services import UserService"
2. Same-file functions — "helper" matches a function in the same file
3. Global name index — unambiguous match across all repo files
4. Method call resolution — "svc.process" → look up "process" in all files
5. Unresolved — edge created with is_resolved=False
```

Builtin names are never added to the graph. A hardcoded set of ~50 Python builtins and ~30 JS builtins (`print`, `len`, `console`, `setTimeout`, etc.) are filtered out before graph construction.

---

## 9. Fault Tolerance Design

Phase 2 is designed to **never crash the overall pipeline** due to a single bad file. Every extraction call is individually guarded:

| Failure Mode | Handling |
|-------------|---------|
| Encoding error (not UTF-8 or latin-1) | Logged, file skipped with `parse_success=False` |
| Tree-sitter parse timeout (> 30s) | `SIGALRM` fires, file marked as failed |
| Syntax errors in source | Tree-sitter produces partial tree; extraction continues with `parse_errors` noting the warning |
| Minified file (line > 10,000 chars) | Skipped entirely with explanation in `parse_errors` |
| Individual extraction crash | `_safe_extract()` logs the error and returns `[]`, other extractions proceed |
| Per-file JSON write failure | Logged; orchestrator continues to next file |
| Missing source file on disk | Logged; counted in `total_files_failed` |

The `parse_success` field on `ParsedFile` tells downstream consumers whether to trust this file's data. A file with `parse_success=False` will still appear in the dependency map and call graph — it just contributes zero nodes.

---

## 10. Caching Strategy

Phase 2 supports file-level and repo-level caching:

**Repo-level cache:** If `parsed/parse_manifest.json` already exists and `--force` is not set, the orchestrator returns the cached manifest immediately without re-parsing any file. This makes repeated `parse` commands instantaneous.

**Per-file output:** Each parsed file is saved as `parsed/files/{sha}.json` where `sha` comes from Phase 1's manifest. If the source file hasn't changed (same SHA), downstream phases can detect this and skip re-embedding.

**Force reparse:** `python main.py parse <url> --force` deletes nothing — it simply overwrites all output files and regenerates the manifest. Phase 1 data is never touched.
