# Phase 2 — Language Parser Modules

---

## Overview

All language parsers live in `parsing/languages/`. Every parser:
- Extends `BaseParser` (from `parsing/base_parser.py`)
- Is instantiated **once** at import time in the registry (stateless, reused)
- Receives a tree-sitter `tree` object, raw `source_bytes`, and `file_path`
- Returns standard dataclasses (`ParsedFunction`, `ParsedClass`, `ParsedImport`)

---

## `parsing/__init__.py` — Shared Dataclasses

**Role:** Single source of truth for all Phase 2 data structures. Every module in Phase 2 imports from here.

### Dataclasses defined

| Dataclass | Fields | Purpose |
|-----------|--------|---------|
| `ParsedParameter` | `name`, `type_annotation`, `default_value`, `is_variadic` | One function parameter |
| `ParsedFunction` | `name`, `qualified_name`, `file_path`, `start_line`, `end_line`, `parameters`, `return_type`, `docstring`, `body_preview`, `full_body`, `parent_class`, `is_method`, `is_constructor`, `is_private`, `is_static`, `is_async`, `decorators`, `calls`, `complexity_score` | Complete function representation |
| `ParsedClass` | `name`, `qualified_name`, `file_path`, `start_line`, `end_line`, `docstring`, `base_classes`, `implemented_interfaces`, `methods`, `class_variables`, `instance_variables`, `is_abstract`, `is_interface`, `decorators` | Complete class representation |
| `ParsedImport` | `file_path`, `line_number`, `import_type`, `module`, `imported_items`, `aliases`, `is_stdlib`, `is_third_party`, `is_local`, `is_conditional` | One import statement |
| `ParsedFile` | `file_path`, `language`, `sha`, `size_bytes`, `total_lines`, `functions`, `classes`, `imports`, `global_variables`, `module_docstring`, `is_entry_point`, `has_main_block`, `has_exports`, `parse_errors`, `parse_success` | Complete parse result for one file |
| `DependencyEdge` | `from_file`, `to_file`, `to_module`, `dependency_type`, `imported_items`, `line_number` | One directed import edge |
| `CallEdge` | `caller_file`, `caller_function`, `caller_qualified`, `callee_name`, `callee_resolved`, `call_line`, `is_resolved` | One directed call edge |
| `DependencyMap` | `repo_owner`, `repo_name`, `edges`, `external_dependencies`, `local_files`, `adjacency`, `reverse_adjacency` | Full cross-file import graph |
| `CallGraph` | `repo_owner`, `repo_name`, `edges`, `nodes`, `adjacency`, `reverse_adjacency` | Full function call graph |
| `ParseManifest` | `codeautopsy_version`, `parse_timestamp`, `repo_owner`, `repo_name`, `total_files_parsed`, `total_files_failed`, `total_functions_extracted`, `total_classes_extracted`, `total_imports_extracted`, `total_call_edges`, `total_dependency_edges`, `parse_duration_seconds`, `detected_patterns`, `entry_points`, `errors` | Parse run summary |

### JSON Serialization

```python
from parsing import to_json, save_json, load_json

# Serialize any dataclass (including nested)
json_str = to_json(parsed_file)

# Write directly to disk (creates parent dirs)
save_json(parsed_file, Path("parsed/files/abc123.json"))

# Load back from disk
data = load_json(Path("parsed/files/abc123.json"))  # returns dict
```

The `_DataclassEncoder` handles:
- Nested dataclasses → `dataclasses.asdict()` recursively
- `datetime` → ISO 8601 string
- `Path` → string
- `set` / `frozenset` → sorted list

---

## `parsing/base_parser.py` — Abstract Base Class

**Role:** Provides the shared parse pipeline and all helper utilities. Language parsers only implement the five abstract extraction methods.

### `parse_file(file_path, source_code)` → `ParsedFile`

The main entry point. Called by the orchestrator for each file. Never raises — all errors go into `ParsedFile.parse_errors`.

**Execution order:**
1. Check for minified file (any line > 10,000 chars → skip)
2. Check for empty file (return empty ParsedFile immediately)
3. Encode source to UTF-8 bytes (latin-1 fallback on `UnicodeEncodeError`)
4. Lazy-initialize the tree-sitter parser
5. Parse with SIGALRM timeout (30 seconds)
6. Check `tree.root_node.has_error` → add warning to `parse_errors` but continue
7. Call all five `extract_*` methods via `_safe_extract()` (each individually guarded)
8. Detect main block and exports via fast source-text search
9. Extract module docstring from AST root
10. Assemble and return `ParsedFile`

### Shared Utilities

| Method | Signature | Purpose |
|--------|-----------|---------|
| `get_node_text` | `(node, source_bytes) → str` | Safe byte-slice to decoded string |
| `get_docstring` | `(node, source_bytes) → Optional[str]` | First `string` node in function/class body |
| `calculate_complexity` | `(func_node, source_bytes) → int` | Count branching keywords (≥ 1) |
| `resolve_import_type` | `(module, language, known_local?) → (bool, bool, bool)` | Classify as (stdlib, third_party, local) |
| `_safe_query` | `(query_string, root_node) → list[tuple]` | Run tree-sitter query, return `[]` on failure |

---

## `parsing/languages/python_parser.py` — Python Parser

**Files handled:** `.py`, `.pyi`, `.pyw`
**Grammar:** `get_parser("python")` from `tree-sitter-languages`

### What it extracts

#### Functions
- All `function_definition` nodes (regular, nested, class methods)
- Lambda expressions (auto-named `lambda_line_{N}`)
- Async functions (`async def`) → `is_async=True`
- Private functions (single `_` prefix, not dunder) → `is_private=True`
- Dunder methods (`__init__`, `__str__`) — `is_constructor` only for `__init__`
- Static/class methods via `@staticmethod`, `@classmethod` → `is_static=True`
- Decorators collected from parent node siblings
- Parameters with type annotations and default values
- Return type from `-> annotation`
- Docstrings (first expression statement in body)
- All `call` nodes within the function body → `calls` list
- Complexity score from branching keyword count

**Qualified names:** `parent_class.method_name` for methods, bare `name` for module-level functions

#### Classes
- All `class_definition` nodes
- Base classes from `superclasses` field
- `is_abstract` if: `@abstractmethod` appears in body, or `ABC` is in base classes
- Decorators from parent node siblings
- All method qualified names collected
- Class-level assignments → `class_variables`
- `self.x = …` in `__init__` → `instance_variables`

#### Imports
- `import os`, `import pathlib.Path` → `import_type="absolute"`
- `from pathlib import Path` → `import_type="absolute"`, `imported_items=["Path"]`
- `from .utils import helper` → `import_type="relative"`, `is_local=True`
- `from * import *` → `imported_items=["*"]`
- Aliases: `import numpy as np` → `aliases={"np": "numpy"}`
- Conditional imports (inside `if`/`try` blocks) → `is_conditional=True`

#### Global Variables
- Module-level `identifier = …` assignments

#### Entry Point Detection
- Returns `True` if `if __name__` and `__main__` both in source
- OR if filename is one of: `main.py`, `app.py`, `server.py`, `run.py`, `cli.py`, `manage.py`, `wsgi.py`, `asgi.py`, `__main__.py`

### Tree-sitter Queries Used

```python
_FUNC_QUERY  = "(function_definition name: (identifier) @func.name) @func.def"
_CLASS_QUERY = "(class_definition name: (identifier) @class.name) @class.def"
_IMPORT_QUERY = "[(import_statement) @import.simple (import_from_statement) @import.from]"
_CALL_QUERY  = "[(call function: (identifier) @call.direct) (call function: (attribute attribute: (identifier) @call.method))]"
```

---

## `parsing/languages/javascript_parser.py` — JavaScript Parser

**Files handled:** `.js`, `.mjs`, `.cjs`, `.jsx`
**Grammar:** `get_parser("javascript")`

### What it extracts

#### Functions
1. **Function declarations** — `function fetchData(url) { … }` → name from `function_declaration`
2. **Arrow functions** — `const myFunc = (x) => x + 1` → name from `variable_declarator`, body from `arrow_function`
3. **Function expressions** — `const fn = function(x) { … }` → name from `variable_declarator`, body from `function`
4. **Class methods** — `method_definition` nodes inside `class_declaration`

All functions: `is_async` from `async` keyword, `is_private` from `_`/`#` prefix, `is_constructor` for `constructor` methods.

#### Classes
- `class_declaration` with `name` field
- Heritage via `class_heritage` child nodes → `base_classes`
- All `method_definition` names collected

#### Imports
- **ES6:** `import React from 'react'`, `import { useState } from 'react'`, `import * as Utils from './utils'`
- **CommonJS:** `const path = require('path')` detected via call query + `require` function name check
- All imports classified as stdlib (Node builtins) / third-party / local

#### Exports Detection
- `module.exports = …` or any `export` keyword → `has_exports=True` on `ParsedFile`

### Key Query Fix
`function_expression` is not a valid node type in tree-sitter's JavaScript grammar at 0.21.x — the correct type is `function`. The query correctly uses:
```
(variable_declarator name: (identifier) @name value: [(arrow_function)(function)] @body) @arrow_decl
```

---

## `parsing/languages/typescript_parser.py` — TypeScript Parser

**Files handled:** `.ts` (TypeScriptParser), `.tsx` (TSXParser)
**Grammar:** `get_parser("typescript")` / `get_parser("tsx")`

**Extends:** `JavaScriptParser` — inherits all JS extraction and adds:

### Additional Extractions

#### Interfaces
- `interface_declaration` nodes → `ParsedClass` with `is_interface=True`
- Interface heritage from `extends_clause`

#### Enums
- `enum_declaration` nodes → `ParsedClass` with `decorators=["enum"]`

#### Abstract Classes
- Source-text check for `abstract class` on the class declaration line → `cls.is_abstract=True`

#### Access Modifiers
- Source-text check for `private ` keyword on method line → `fn.is_private=True`

#### TSXParser
- Identical to TypeScriptParser but uses `tsx` grammar for JSX template syntax in `.tsx` files

---

## `parsing/languages/java_parser.py` — Java Parser

**Files handled:** `.java`
**Grammar:** `get_parser("java")`

### What it extracts

#### Methods & Constructors
- `method_declaration` → `ParsedFunction`
- `constructor_declaration` → `ParsedFunction` with `is_constructor=True`
- Access modifiers from source text prefix: `private`, `static`
- Parent class via walking up to `class_declaration` ancestor

#### Classes & Interfaces
- `class_declaration` → `ParsedClass`
  - Superclass from `superclass` field → `base_classes`
  - Interfaces from `interfaces > type_list` → `implemented_interfaces`
  - `abstract` keyword in text → `is_abstract=True`
- `interface_declaration` → `ParsedClass` with `is_interface=True`
- Java annotations (`@Service`, `@Override`) collected as `decorators`

#### Imports
- `import_declaration` nodes
- Module string extracted by stripping `import`, `static`, and `;`
- `java.*`, `javax.*` → not stdlib for our purposes (they are third-party JDK unless classified)

#### Entry Point Detection
- `public static void main` in source → True
- `@SpringBootApplication` → True (Spring Boot entry)

#### Parameters
- `formal_parameter` with `name` and `type` fields → `ParsedParameter`
- Variadic `...` → `is_variadic=True`

---

## `parsing/languages/go_parser.py` — Go Parser

**Files handled:** `.go`
**Grammar:** `get_parser("go")`

### What it extracts

#### Functions and Methods
- `function_declaration` → bare functions
- `method_declaration` → functions with receiver → `parent_class` set to receiver type
- Receiver extracted from `parameter_declaration` inside `receiver` field
- Pointer receivers (`*MyStruct`) have `*` stripped
- Goroutine detection: `" go "` or `"\ngo "` in body → `is_async=True` (approximation)
- Unexported (lowercase first letter) → `is_private=True`

#### Types as Classes
- `type_declaration > type_spec > struct_type` → `ParsedClass` (struct as class analog)
- `type_declaration > type_spec > interface_type` → `ParsedClass` with `is_interface=True`

#### Imports
- `import_declaration` with `import_spec` → each string path extracted
- Go stdlib: paths with no dots and no slashes (e.g. `fmt`, `os`, `io`, `net/http`)
- Third-party: `github.com/…`, `golang.org/…`, `gopkg.in/…`
- Local: relative paths or paths matching the module

#### Global Variables
- `var_declaration` and `const_declaration` identifiers

#### Entry Point Detection
- `func main()` in source or filename is `main.go`

---

## `parsing/languages/rust_parser.py` — Rust Parser

**Files handled:** `.rs`
**Grammar:** `get_parser("rust")`

### What it extracts

#### Functions
- `function_item` nodes
- `pub ` prefix check in text → `is_private = "pub " not in prefix`
- `async ` keyword → `is_async=True`
- Parent `impl_item` → `parent_class` from `type` field
- `attribute_item` nodes before the function → `decorators`
- Constructor detection: name in (`new`, `with_capacity`, `default`)

#### Types
- `struct_item` → `ParsedClass`
- `enum_item` → `ParsedClass` with `decorators=["enum"]`
- `trait_item` → `ParsedClass` with `is_interface=True`, `is_abstract=True`

#### Derives (treated as decorators)
- `attribute_item` containing `derive(…)` → derives unpacked individually
- Example: `#[derive(Debug, Clone)]` → `decorators=["Debug", "Clone"]`

#### Imports
- `use_declaration` nodes → module string extracted
- `std::`, `core::`, `alloc::` → `is_stdlib=True`
- `crate::`, `super::`, `self::` → `is_local=True`

#### Globals
- `const_item` and `static_item` names

#### Entry Point Detection
- `fn main()` in source or filename is `main.rs`

---

## `parsing/languages/cpp_parser.py` — C and C++ Parser

**Files handled:**
- C: `.c`, `.h` → grammar `"c"`
- C++: `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx` → grammar `"cpp"`

The grammar is selected at construction time:
```python
CppParser(file_extension=".c")    # uses "c" grammar
CppParser(file_extension=".cpp")  # uses "cpp" grammar (handles both C and C++)
```

### What it extracts

#### Functions
- `function_definition` nodes
- Name extracted by walking the `declarator` chain recursively to find the deepest `identifier` or `qualified_identifier`
- C++ scoped names (`MyClass::method`) split on `::` → `parent_class="MyClass"`, `name="method"`
- Access specifier heuristic: if inside `private:` block → `is_private=True`
- `is_constructor` if function name equals parent class name

#### Classes and Structs
- `class_specifier` and `struct_specifier` nodes
- Base classes from `base_clause > base_class_clause > type_identifier`
- Pure virtual functions (`= 0` in text) → `is_abstract=True`

#### Includes
- `preproc_include` nodes
- `#include <stdio.h>` → `module="stdio.h"`, `is_stdlib=True`
- `#include "myfile.h"` → `module="myfile.h"`, `is_local=True`
- Known third-party prefixes (`boost/`, `gtest/`, `eigen/`, etc.) override stdlib classification

#### Macros
- `preproc_def` names → `global_variables` list

#### Entry Point Detection
- `int main(` in source text

---

## `parsing/languages/generic_parser.py` — Regex Fallback Parser

**Files handled:** Any language without a tree-sitter grammar in the registry
**Grammar:** None (regex only)

### Design

The generic parser overrides `parse_file()` entirely — it never calls tree-sitter at all. It uses compiled Python regex patterns to extract approximate function, class, and import information.

All results are marked in `parse_errors`:
```
"Using regex fallback parser (no tree-sitter grammar available)."
```

`parse_success` is still `True` — the regex extraction is partial but valid.

### Regex Patterns Used

```python
# Functions: matches common patterns across C-like and Python-like languages
_FUNC_RE = re.compile(
    r"(?:pub|public|private|protected|static|async|def|func?|fn|…)\s+(\w+)\s*\(…"
)

# Classes: class, struct, interface, trait, enum keywords
_CLASS_RE = re.compile(
    r"(?:abstract\s+)?(?:class|struct|interface|trait|enum)\s+(\w+)"
)

# Imports: import, require, include, use, using, from, #include
_IMPORT_RE = re.compile(
    r"(?:import|require|include|use|using|from|#include)\s+[\"'<]?([^\s\"';>]+)"
)
```

### When is the generic parser used?

Shell scripts (`.sh`), Ruby (`.rb`), PHP (`.php`), Swift (`.swift`), Kotlin (`.kt`), Scala (`.scala`), and any other language not in the registry. A `WARNING` log entry is emitted for every file that falls back to regex.

---

## `parsing/parser_registry.py` — Registry

**Role:** Single lookup table from language name → parser instance.

### `get_parser_for_language(language, file_path="")` → `BaseParser`

Lookup order:
1. **Extension override** (highest priority) — for `.tsx`, `.jsx`, `.mjs`, `.h`, `.hpp`
2. **Language registry** — match against Phase 1 manifest's `"language"` field
3. **Generic parser** (fallback) — with `WARNING` log entry

```python
# Examples:
get_parser_for_language("Python")           # → PythonParser()
get_parser_for_language("TypeScript", "App.tsx")  # → TSXParser() (extension override)
get_parser_for_language("Ruby")             # → GenericParser() + warning
```

### `list_supported_languages()` → `list[str]`

Returns all languages with dedicated AST parsers (currently 8):
`["C", "C++", "Go", "Java", "JavaScript", "Python", "Rust", "TypeScript"]`

---

## `utils/file_hasher.py` — Hashing Utilities

**Role:** Generates short, deterministic hash strings for cache keys.

| Function | Hash | Length | Use |
|----------|------|--------|-----|
| `hash_file_path(path)` | MD5 | 12 chars | Safe flat filenames for output files |
| `hash_content(content)` | SHA-256 | 16 chars | Content-based cache invalidation |

```python
from utils.file_hasher import hash_file_path, hash_content

# Map any repo path to a safe filename
hash_file_path("src/models/user.py")   # → "3f2a1b8c9d4e"
hash_file_path("src/models/user.py")   # → "3f2a1b8c9d4e"  (deterministic)

# Content hash for cache invalidation
hash_content("def foo(): pass")        # → "4a7b2c8d1e3f9a0b"
```

The output directory uses the Phase 1 SHA (from manifest.json) as the filename, not these hashes — but these functions are available for Phase 3 to build its own cache layer.
