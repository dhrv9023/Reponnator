#!/usr/bin/env python3
"""
Quick Phase 3 test runner — run directly without pytest tooling issues.
Usage: python3 run_tests_p3.py
"""
import sys
import traceback
import uuid
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(_HERE))

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []


def test(name, fn):
    try:
        fn()
        print(f"  {PASS}  {name}")
        results.append((name, True, None))
    except Exception as e:
        print(f"  {FAIL}  {name}")
        print(f"         {type(e).__name__}: {e}")
        results.append((name, False, e))


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _func(name="foo", qname="mod.foo", file_path="src/mod.py",
          is_method=False, parent_class=None, body="    pass\n",
          is_constructor=False, is_private=False, is_async=False):
    from parsing import ParsedFunction
    return ParsedFunction(
        name=name, qualified_name=qname, file_path=file_path,
        start_line=1, end_line=5, parameters=[], return_type=None,
        docstring=None, body_preview=body[:200], full_body=body,
        parent_class=parent_class, is_method=is_method,
        is_constructor=is_constructor, is_private=is_private,
        is_static=False, is_async=is_async, decorators=[],
        calls=[], complexity_score=1,
    )


def _cls(name="MyClass", qname="MyClass", file_path="src/mod.py", methods=None):
    from parsing import ParsedClass
    return ParsedClass(
        name=name, qualified_name=qname, file_path=file_path,
        start_line=1, end_line=30, docstring=None, base_classes=[],
        implemented_interfaces=[], methods=methods or [],
        class_variables=[], instance_variables=[], is_abstract=False,
        is_interface=False, decorators=[],
    )


def _imp(module="os", is_stdlib=True):
    from parsing import ParsedImport
    return ParsedImport(
        file_path="src/mod.py", line_number=1, import_type="absolute",
        module=module, imported_items=[], aliases={},
        is_stdlib=is_stdlib, is_third_party=not is_stdlib,
        is_local=False, is_conditional=False,
    )


def _pf(file_path="src/mod.py", functions=None, classes=None, imports=None):
    from parsing import ParsedFile
    return ParsedFile(
        file_path=file_path, language="Python", sha="abc123",
        size_bytes=1000, total_lines=50,
        functions=functions or [], classes=classes or [],
        imports=imports or [], global_variables=[],
        module_docstring=None, is_entry_point=False,
        has_main_block=False, has_exports=False,
        parse_errors=[], parse_success=True,
    )


def _chunk(chunk_type=None, content="def foo(): pass", token_count=10,
           qname="mod.foo", name="foo", file_path="src/mod.py"):
    from chunking import ChunkType, CodeChunk
    ct = chunk_type or ChunkType.FUNCTION
    return CodeChunk(
        chunk_id=str(uuid.uuid4()), repo_owner="owner", repo_name="repo",
        chunk_type=ct, file_path=file_path, language="Python",
        start_line=1, end_line=5, sha="abc123",
        content=content, content_preview=content[:200],
        token_count=token_count, name=name, qualified_name=qname,
        parent_class=None, parent_function=None, calls=[], called_by=[],
        imports_used=[], file_imports=[], files_this_depends_on=[],
        files_depending_on_this=[], complexity_score=1,
        is_entry_point=False, is_constructor=False, is_private=False,
        is_async=False, decorators=[], architectural_patterns=[],
        search_keywords=[], docstring=None,
    )


# ─────────────────────────────────────────────────────────
# CHUNKER TESTS
# ─────────────────────────────────────────────────────────
print("\n── TestChunker ─────────────────────────────────")

def t_chunker_single_function():
    from chunking.chunker import Chunker
    pf = _pf(functions=[_func(name="process", qname="mod.process")])
    chunks = Chunker().create_chunks_from_file(pf, "owner", "repo")
    fc = [c for c in chunks if c.chunk_type.value in ("function","method")]
    assert len(fc) == 1
    assert fc[0].name == "process"

def t_chunker_class_with_3_methods():
    from chunking.chunker import Chunker
    methods = [_func(name=f"m{i}", qname=f"C.m{i}", is_method=True, parent_class="C") for i in range(3)]
    cls = _cls(methods=[f"C.m{i}" for i in range(3)])
    pf = _pf(functions=methods, classes=[cls])
    chunks = Chunker().create_chunks_from_file(pf, "owner", "repo")
    mc = [c for c in chunks if c.chunk_type.value == "method"]
    cc = [c for c in chunks if c.chunk_type.value == "class_summary"]
    assert len(mc) == 3, f"Expected 3 method chunks, got {len(mc)}"
    assert len(cc) == 1, f"Expected 1 class chunk, got {len(cc)}"

def t_chunker_no_funcs_has_summary_and_import_ctx():
    from chunking.chunker import Chunker
    imports = [_imp("os"), _imp("sys"), _imp("json"), _imp("flask", is_stdlib=False)]
    pf = _pf(imports=imports)
    chunks = Chunker().create_chunks_from_file(pf, "owner", "repo")
    types = {c.chunk_type.value for c in chunks}
    assert "file_summary" in types
    assert "import_context" in types
    assert "function" not in types

def t_chunker_content_has_func_name():
    from chunking.chunker import Chunker
    pf = _pf(functions=[_func(name="authenticate_user", qname="auth.authenticate_user")])
    chunks = Chunker().create_chunks_from_file(pf, "owner", "repo")
    fc = [c for c in chunks if c.chunk_type.value == "function"]
    assert any("authenticate_user" in c.content for c in fc)

def t_chunker_file_summary_lists_funcs():
    from chunking.chunker import Chunker
    names = ["alpha","beta","gamma"]
    funcs = [_func(name=n, qname=f"mod.{n}") for n in names]
    pf = _pf(functions=funcs)
    chunks = Chunker().create_chunks_from_file(pf, "owner", "repo")
    summary = next(c for c in chunks if c.chunk_type.value == "file_summary")
    for n in names:
        assert n in summary.content, f"{n} not found in file summary"

test("single function → one FUNCTION chunk", t_chunker_single_function)
test("class with 3 methods → 3 METHOD + 1 CLASS_SUMMARY", t_chunker_class_with_3_methods)
test("no functions → FILE_SUMMARY + IMPORT_CONTEXT", t_chunker_no_funcs_has_summary_and_import_ctx)
test("function chunk content has func name", t_chunker_content_has_func_name)
test("file summary lists all function names", t_chunker_file_summary_lists_funcs)


# ─────────────────────────────────────────────────────────
# SPLITTER TESTS
# ─────────────────────────────────────────────────────────
print("\n── TestSplitter ─────────────────────────────────")

def t_splitter_small_unchanged():
    from chunking.splitter import Splitter
    import config
    c = _chunk(token_count=5)
    result = Splitter().split_large_chunks([c])
    assert len(result) == 1
    assert result[0].chunk_id == c.chunk_id

def t_splitter_large_func_split():
    from chunking.splitter import Splitter
    import config
    body = "\n".join(f"    x_{i} = {i}" for i in range(400))
    c = _chunk(content=body, token_count=config.MAX_CHUNK_TOKENS + 200)
    result = Splitter().split_large_chunks([c])
    assert len(result) > 1, f"Expected >1 sub-chunks, got {len(result)}"

def t_splitter_subchunk_indices():
    from chunking.splitter import Splitter
    import config
    body = "\n".join(f"    x_{i} = {i}" for i in range(600))
    c = _chunk(content=body, token_count=config.MAX_CHUNK_TOKENS + 500)
    result = Splitter().split_large_chunks([c])
    for i, sc in enumerate(result):
        assert sc.subchunk_index == i, f"index mismatch at {i}"
        assert sc.total_subchunks == len(result)

def t_splitter_overlap_flag():
    from chunking.splitter import Splitter
    import config
    body = "\n".join(f"    x_{i} = {i}" for i in range(600))
    c = _chunk(content=body, token_count=config.MAX_CHUNK_TOKENS + 500)
    result = Splitter().split_large_chunks([c])
    if len(result) > 1:
        for sc in result[1:]:
            assert sc.overlap_with_previous is True

def t_splitter_class_summary_not_split():
    from chunking import ChunkType
    from chunking.splitter import Splitter
    import config
    body = "\n".join(f"Method_{i}: does stuff" for i in range(200))
    c = _chunk(chunk_type=ChunkType.CLASS_SUMMARY, content=body,
               token_count=config.MAX_CHUNK_TOKENS + 100)
    result = Splitter().split_large_chunks([c])
    assert all(sc.chunk_type == ChunkType.CLASS_SUMMARY for sc in result)
    assert len(result) == 1

def t_splitter_file_summary_not_split():
    from chunking import ChunkType
    from chunking.splitter import Splitter
    import config
    body = "\n".join(f"import module_{i}" for i in range(200))
    c = _chunk(chunk_type=ChunkType.FILE_SUMMARY, content=body,
               token_count=config.MAX_CHUNK_TOKENS + 100)
    result = Splitter().split_large_chunks([c])
    assert all(sc.chunk_type == ChunkType.FILE_SUMMARY for sc in result)
    assert len(result) == 1

test("small chunk returned unchanged", t_splitter_small_unchanged)
test("large FUNCTION chunk is split", t_splitter_large_func_split)
test("sub-chunk indices correct", t_splitter_subchunk_indices)
test("sub-chunks 2+ have overlap_with_previous=True", t_splitter_overlap_flag)
test("CLASS_SUMMARY never split", t_splitter_class_summary_not_split)
test("FILE_SUMMARY never split", t_splitter_file_summary_not_split)


# ─────────────────────────────────────────────────────────
# METADATA ENRICHER TESTS
# ─────────────────────────────────────────────────────────
print("\n── TestMetadataEnricher ─────────────────────────")

def _cg(adj=None, rev=None):
    from parsing import CallGraph
    return CallGraph(repo_owner="o", repo_name="r", edges=[], nodes=[],
                     adjacency=adj or {}, reverse_adjacency=rev or {})

def _dm(adj=None, rev=None):
    from parsing import DependencyMap
    return DependencyMap(repo_owner="o", repo_name="r", edges=[],
                         external_dependencies=[], local_files=[],
                         adjacency=adj or {}, reverse_adjacency=rev or {})

def t_enricher_calls():
    from chunking.metadata_enricher import MetadataEnricher
    c = _chunk(qname="mod.foo")
    cg = _cg(adj={"mod.foo": ["mod.bar","mod.baz","mod.qux"]})
    result = MetadataEnricher().enrich_chunks([c], _dm(), cg, [], [])
    assert len(result[0].calls) == 3
    assert "mod.bar" in result[0].calls

def t_enricher_called_by():
    from chunking.metadata_enricher import MetadataEnricher
    c = _chunk(qname="utils.helper")
    cg = _cg(rev={"utils.helper": ["a.foo","b.bar"]})
    result = MetadataEnricher().enrich_chunks([c], _dm(), cg, [], [])
    assert len(result[0].called_by) == 2

def t_enricher_entry_point():
    from chunking.metadata_enricher import MetadataEnricher
    c = _chunk(file_path="src/main.py")
    eps = [{"file_path": "src/main.py", "confidence": "high"}]
    result = MetadataEnricher().enrich_chunks([c], _dm(), _cg(), eps, [])
    assert result[0].is_entry_point is True

def t_enricher_index():
    from chunking.metadata_enricher import MetadataEnricher
    chunks = [_chunk(qname="mod.foo"), _chunk(qname="mod.bar")]
    index = MetadataEnricher().build_qualified_name_index(chunks)
    assert "mod.foo" in index
    assert "mod.bar" in index
    assert index["mod.foo"] == chunks[0].chunk_id

test("function calls list enriched from call graph", t_enricher_calls)
test("called_by list enriched from reverse adjacency", t_enricher_called_by)
test("entry point file marks chunk is_entry_point=True", t_enricher_entry_point)
test("build_qualified_name_index maps names to chunk_ids", t_enricher_index)


# ─────────────────────────────────────────────────────────
# VECTOR STORE TESTS (sanitize only — no ChromaDB instance needed)
# ─────────────────────────────────────────────────────────
print("\n── TestVectorStore.sanitize ─────────────────────")

def t_vs_sanitize_special_chars():
    from chunking.vector_store import VectorStore
    vs = VectorStore.__new__(VectorStore)
    result = vs.sanitize_collection_name("codeautopsy__owner.name__repo-name")
    assert all(ch.isalnum() or ch in "_-" for ch in result), f"Bad chars in: {result}"

def t_vs_sanitize_max_63():
    from chunking.vector_store import VectorStore
    vs = VectorStore.__new__(VectorStore)
    result = vs.sanitize_collection_name("a" * 100)
    assert len(result) <= 63

def t_vs_sanitize_starts_alnum():
    from chunking.vector_store import VectorStore
    vs = VectorStore.__new__(VectorStore)
    result = vs.sanitize_collection_name("__starts_with_underscore")
    assert result[0].isalnum(), f"Does not start with alnum: {result}"

test("sanitize removes special chars", t_vs_sanitize_special_chars)
test("sanitize truncates to 63 chars", t_vs_sanitize_max_63)
test("sanitize ensures starts with alnum", t_vs_sanitize_starts_alnum)


# ─────────────────────────────────────────────────────────
# CHROMADB + EMBEDDER TESTS (require models)
# ─────────────────────────────────────────────────────────
print("\n── TestEmbedder + ChromaDB (live) ───────────────")

def t_embedder_query_384_floats():
    from chunking.embedder import Embedder
    emb = Embedder()
    vec = emb.embed_query("authentication and login")
    assert isinstance(vec, list), "embedding should be list"
    assert len(vec) == 384, f"Expected 384 dims, got {len(vec)}"
    assert all(isinstance(v, float) for v in vec)

def t_embedder_l2_normalized():
    import math
    from chunking.embedder import Embedder
    emb = Embedder()
    vec = emb.embed_query("normalization test")
    mag = math.sqrt(sum(v*v for v in vec))
    assert abs(mag - 1.0) < 0.01, f"Magnitude {mag:.4f} not close to 1.0"

def t_embedder_batch_100_chunks():
    from chunking.embedder import Embedder
    emb = Embedder()
    chunks = [_chunk(content=f"def func_{i}(): pass") for i in range(10)]
    result = emb.embed_chunks(chunks, show_progress=False)
    assert all(c.embedding is not None for c in result)
    assert all(len(c.embedding) == 384 for c in result)
    assert all(c.embedding_model == "all-MiniLM-L6-v2" for c in result)

def t_chromadb_add_query():
    import tempfile, chromadb
    from chunking.vector_store import VectorStore
    from chunking.embedder import Embedder
    emb = Embedder()
    with tempfile.TemporaryDirectory() as tmpdir:
        client = chromadb.PersistentClient(path=tmpdir)
        vs = VectorStore.__new__(VectorStore)
        vs._client = client
        vs._chromadb = chromadb
        col = vs.get_or_create_collection("owner", "testrepo")
        chunks = [
            _chunk(content="authentication login password verify user"),
            _chunk(content="database connection pool query sql"),
            _chunk(content="file read write disk io storage"),
        ]
        chunks = emb.embed_chunks(chunks, show_progress=False)
        vs.add_chunks(col, chunks)
        assert col.count() == 3, f"Expected 3, got {col.count()}"
        qvec = emb.embed_query("user authentication")
        results = vs.query(col, qvec, n_results=3)
        assert len(results) > 0
        scores = [r["similarity_score"] for r in results]
        assert scores == sorted(scores, reverse=True), "Results not sorted by similarity"
        print(f"    [top result similarity: {scores[0]:.3f}]")

def t_chromadb_get_by_id():
    import tempfile, chromadb
    from chunking.vector_store import VectorStore
    from chunking.embedder import Embedder
    emb = Embedder()
    with tempfile.TemporaryDirectory() as tmpdir:
        client = chromadb.PersistentClient(path=tmpdir)
        vs = VectorStore.__new__(VectorStore)
        vs._client = client
        vs._chromadb = chromadb
        col = vs.get_or_create_collection("owner", "lookuptest")
        c = _chunk(content="unique chunk for lookup test")
        c = emb.embed_chunks([c], show_progress=False)[0]
        vs.add_chunks(col, [c])
        found = vs.get_chunk_by_id(col, c.chunk_id)
        assert found is not None
        assert found["chunk_id"] == c.chunk_id

test("embed_query returns 384 floats", t_embedder_query_384_floats)
test("embeddings are L2 normalized (magnitude ≈ 1.0)", t_embedder_l2_normalized)
test("batch embed 10 chunks populates all embeddings", t_embedder_batch_100_chunks)
test("chromadb: add 3 chunks + query sorted by similarity", t_chromadb_add_query)
test("chromadb: get_chunk_by_id returns correct chunk", t_chromadb_get_by_id)


# ─────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────
total  = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed

print(f"\n{'─'*52}")
print(f"  Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ⚠️  {failed} FAILED")
    for name, ok, err in results:
        if not ok:
            print(f"    ✗ {name}: {err}")
else:
    print("  ✅ All tests passed!")
print(f"{'─'*52}\n")
sys.exit(0 if failed == 0 else 1)
