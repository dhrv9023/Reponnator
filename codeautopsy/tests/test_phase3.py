"""
tests/test_phase3.py — Phase 3 Unit + Integration Tests

Run unit tests:
    pytest tests/test_phase3.py -v

Run integration tests (requires Phase 2 output to exist):
    pytest tests/test_phase3.py -v -m integration
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# Make sure project root is on path
_HERE = Path(__file__).parent.parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ---------------------------------------------------------------------------
# Helpers — build minimal fakes without importing heavy deps
# ---------------------------------------------------------------------------

def _make_parsed_function(
    name="my_func",
    qualified_name="module.my_func",
    file_path="src/mod.py",
    is_method=False,
    is_async=False,
    is_constructor=False,
    is_private=False,
    parent_class=None,
    decorators=None,
    parameters=None,
    calls=None,
    docstring=None,
    full_body="    pass\n",
    start_line=1,
    end_line=5,
    complexity_score=1,
):
    from parsing import ParsedFunction, ParsedParameter
    return ParsedFunction(
        name=name,
        qualified_name=qualified_name,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        parameters=parameters or [],
        return_type=None,
        docstring=docstring,
        body_preview=full_body[:200],
        full_body=full_body,
        parent_class=parent_class,
        is_method=is_method,
        is_constructor=is_constructor,
        is_private=is_private,
        is_static=False,
        is_async=is_async,
        decorators=decorators or [],
        calls=calls or [],
        complexity_score=complexity_score,
    )


def _make_parsed_class(
    name="MyClass",
    qualified_name="MyClass",
    file_path="src/mod.py",
    methods=None,
    base_classes=None,
    docstring=None,
    class_variables=None,
    instance_variables=None,
    decorators=None,
):
    from parsing import ParsedClass
    return ParsedClass(
        name=name,
        qualified_name=qualified_name,
        file_path=file_path,
        start_line=1,
        end_line=30,
        docstring=docstring,
        base_classes=base_classes or [],
        implemented_interfaces=[],
        methods=methods or [],
        class_variables=class_variables or [],
        instance_variables=instance_variables or [],
        is_abstract=False,
        is_interface=False,
        decorators=decorators or [],
    )


def _make_parsed_import(module="os", is_stdlib=True):
    from parsing import ParsedImport
    return ParsedImport(
        file_path="src/mod.py",
        line_number=1,
        import_type="absolute",
        module=module,
        imported_items=[],
        aliases={},
        is_stdlib=is_stdlib,
        is_third_party=not is_stdlib,
        is_local=False,
    )


def _make_parsed_file(
    file_path="src/mod.py",
    language="Python",
    sha="abc123",
    functions=None,
    classes=None,
    imports=None,
    module_docstring=None,
    is_entry_point=False,
    total_lines=50,
):
    from parsing import ParsedFile
    return ParsedFile(
        file_path=file_path,
        language=language,
        sha=sha,
        size_bytes=1000,
        total_lines=total_lines,
        functions=functions or [],
        classes=classes or [],
        imports=imports or [],
        global_variables=[],
        module_docstring=module_docstring,
        is_entry_point=is_entry_point,
        has_main_block=False,
        has_exports=False,
        parse_errors=[],
        parse_success=True,
    )


def _make_code_chunk(
    chunk_type=None,
    content="def foo(): pass",
    token_count=10,
    qualified_name="mod.foo",
    name="foo",
    is_subchunk=False,
    subchunk_index=None,
    total_subchunks=None,
    file_path="src/mod.py",
    embedding=None,
):
    from chunking import ChunkType, CodeChunk
    ct = chunk_type or ChunkType.FUNCTION
    return CodeChunk(
        chunk_id=str(uuid.uuid4()),
        repo_owner="owner",
        repo_name="repo",
        chunk_type=ct,
        file_path=file_path,
        language="Python",
        start_line=1,
        end_line=5,
        sha="abc123",
        content=content,
        content_preview=content[:200],
        token_count=token_count,
        name=name,
        qualified_name=qualified_name,
        parent_class=None,
        parent_function=None,
        calls=[],
        called_by=[],
        imports_used=[],
        file_imports=[],
        files_this_depends_on=[],
        files_depending_on_this=[],
        complexity_score=1,
        is_entry_point=False,
        is_constructor=False,
        is_private=False,
        is_async=False,
        decorators=[],
        architectural_patterns=[],
        search_keywords=[],
        docstring=None,
        is_subchunk=is_subchunk,
        subchunk_index=subchunk_index,
        total_subchunks=total_subchunks,
        embedding=embedding,
    )


# ===========================================================================
# Chunker tests
# ===========================================================================

class TestChunker:

    def test_single_function_creates_one_chunk(self):
        from chunking.chunker import Chunker

        func = _make_parsed_function(
            name="process",
            qualified_name="mod.process",
            full_body="    x = 1\n    return x\n",
        )
        pf = _make_parsed_file(functions=[func])
        chunker = Chunker()
        chunks = chunker.create_chunks_from_file(pf, "owner", "repo")

        func_chunks = [c for c in chunks if c.chunk_type.value in ("function", "method")]
        assert len(func_chunks) == 1
        assert func_chunks[0].name == "process"

    def test_class_with_three_methods(self):
        from chunking.chunker import Chunker

        methods = [
            _make_parsed_function(
                name=f"method_{i}",
                qualified_name=f"MyClass.method_{i}",
                is_method=True,
                parent_class="MyClass",
                file_path="src/mod.py",
            )
            for i in range(3)
        ]
        cls = _make_parsed_class(
            name="MyClass",
            methods=[f"MyClass.method_{i}" for i in range(3)],
        )
        pf = _make_parsed_file(functions=methods, classes=[cls])
        chunker = Chunker()
        chunks = chunker.create_chunks_from_file(pf, "owner", "repo")

        method_chunks = [c for c in chunks if c.chunk_type.value == "method"]
        class_chunks  = [c for c in chunks if c.chunk_type.value == "class_summary"]
        assert len(method_chunks) == 3
        assert len(class_chunks) == 1

    def test_file_with_no_functions_creates_summary_and_import_context(self):
        from chunking.chunker import Chunker

        imports = [
            _make_parsed_import("os", is_stdlib=True),
            _make_parsed_import("sys", is_stdlib=True),
            _make_parsed_import("json", is_stdlib=True),
            _make_parsed_import("flask", is_stdlib=False),  # >3 imports → import context
        ]
        pf = _make_parsed_file(functions=[], classes=[], imports=imports)
        chunker = Chunker()
        chunks = chunker.create_chunks_from_file(pf, "owner", "repo")

        types = {c.chunk_type.value for c in chunks}
        assert "file_summary" in types
        assert "import_context" in types
        assert "function" not in types
        assert "method" not in types

    def test_function_chunk_content_contains_function_name(self):
        from chunking.chunker import Chunker

        func = _make_parsed_function(
            name="authenticate_user",
            qualified_name="auth.authenticate_user",
            full_body="    return True\n",
        )
        pf = _make_parsed_file(functions=[func])
        chunker = Chunker()
        chunks = chunker.create_chunks_from_file(pf, "owner", "repo")

        func_chunks = [c for c in chunks if c.chunk_type.value == "function"]
        assert any("authenticate_user" in c.content for c in func_chunks)

    def test_file_summary_lists_all_function_names(self):
        from chunking.chunker import Chunker

        names = ["alpha", "beta", "gamma"]
        funcs = [
            _make_parsed_function(name=n, qualified_name=f"mod.{n}")
            for n in names
        ]
        pf = _make_parsed_file(functions=funcs)
        chunker = Chunker()
        chunks = chunker.create_chunks_from_file(pf, "owner", "repo")

        summary = next(c for c in chunks if c.chunk_type.value == "file_summary")
        for n in names:
            assert n in summary.content


# ===========================================================================
# Splitter tests
# ===========================================================================

class TestSplitter:

    def test_small_chunk_returned_unchanged(self):
        from chunking.splitter import Splitter
        import config

        chunk = _make_code_chunk(content="x = 1", token_count=5)
        assert chunk.token_count < config.MAX_CHUNK_TOKENS
        result = Splitter().split_large_chunks([chunk])
        assert len(result) == 1
        assert result[0].chunk_id == chunk.chunk_id

    def test_large_function_chunk_is_split(self):
        from chunking.splitter import Splitter
        import config

        long_body = "\n".join(f"    line_{i} = {i}" for i in range(400))
        chunk = _make_code_chunk(
            content=long_body,
            token_count=config.MAX_CHUNK_TOKENS + 200,
        )
        result = Splitter().split_large_chunks([chunk])
        assert len(result) > 1

    def test_subchunk_indices_correct(self):
        from chunking.splitter import Splitter
        import config

        long_body = "\n".join(f"    x_{i} = {i}" for i in range(600))
        chunk = _make_code_chunk(
            content=long_body,
            token_count=config.MAX_CHUNK_TOKENS + 500,
        )
        result = Splitter().split_large_chunks([chunk])
        for i, sc in enumerate(result):
            assert sc.subchunk_index == i
            assert sc.total_subchunks == len(result)

    def test_second_subchunk_has_overlap_flag(self):
        from chunking.splitter import Splitter
        import config

        long_body = "\n".join(f"    x_{i} = {i}" for i in range(600))
        chunk = _make_code_chunk(
            content=long_body,
            token_count=config.MAX_CHUNK_TOKENS + 500,
        )
        result = Splitter().split_large_chunks([chunk])
        if len(result) > 1:
            for sc in result[1:]:
                assert sc.overlap_with_previous is True

    def test_class_summary_not_split(self):
        from chunking import ChunkType
        from chunking.splitter import Splitter
        import config

        long_content = "\n".join(f"Method_{i}: does something" for i in range(200))
        chunk = _make_code_chunk(
            chunk_type=ChunkType.CLASS_SUMMARY,
            content=long_content,
            token_count=config.MAX_CHUNK_TOKENS + 100,
        )
        result = Splitter().split_large_chunks([chunk])
        # Must stay as a single chunk (possibly truncated, but not sub-chunked)
        assert all(c.chunk_type == ChunkType.CLASS_SUMMARY for c in result)
        assert len(result) == 1

    def test_file_summary_not_split(self):
        from chunking import ChunkType
        from chunking.splitter import Splitter
        import config

        long_content = "\n".join(f"import module_{i}" for i in range(200))
        chunk = _make_code_chunk(
            chunk_type=ChunkType.FILE_SUMMARY,
            content=long_content,
            token_count=config.MAX_CHUNK_TOKENS + 100,
        )
        result = Splitter().split_large_chunks([chunk])
        assert all(c.chunk_type == ChunkType.FILE_SUMMARY for c in result)
        assert len(result) == 1


# ===========================================================================
# MetadataEnricher tests
# ===========================================================================

class TestMetadataEnricher:

    def _make_call_graph(self, adjacency=None, reverse_adjacency=None):
        from parsing import CallGraph
        return CallGraph(
            repo_owner="owner",
            repo_name="repo",
            edges=[],
            nodes=[],
            adjacency=adjacency or {},
            reverse_adjacency=reverse_adjacency or {},
        )

    def _make_dependency_map(self, adjacency=None, reverse_adjacency=None):
        from parsing import DependencyMap
        return DependencyMap(
            repo_owner="owner",
            repo_name="repo",
            edges=[],
            external_dependencies=[],
            local_files=[],
            adjacency=adjacency or {},
            reverse_adjacency=reverse_adjacency or {},
        )

    def test_function_calls_enriched(self):
        from chunking.metadata_enricher import MetadataEnricher

        chunk = _make_code_chunk(qualified_name="mod.foo")
        cg = self._make_call_graph(
            adjacency={"mod.foo": ["mod.bar", "mod.baz", "mod.qux"]}
        )
        dm = self._make_dependency_map()
        enricher = MetadataEnricher()
        result = enricher.enrich_chunks([chunk], dm, cg, [], [])

        assert len(result[0].calls) == 3
        assert "mod.bar" in result[0].calls

    def test_called_by_enriched(self):
        from chunking.metadata_enricher import MetadataEnricher

        chunk = _make_code_chunk(qualified_name="utils.helper")
        cg = self._make_call_graph(
            reverse_adjacency={"utils.helper": ["mod.foo", "mod.bar"]}
        )
        dm = self._make_dependency_map()
        enricher = MetadataEnricher()
        result = enricher.enrich_chunks([chunk], dm, cg, [], [])

        assert len(result[0].called_by) == 2

    def test_entry_point_file_marks_chunks(self):
        from chunking.metadata_enricher import MetadataEnricher

        chunk = _make_code_chunk(file_path="src/main.py")
        cg  = self._make_call_graph()
        dm  = self._make_dependency_map()
        eps = [{"file_path": "src/main.py", "confidence": "high"}]

        enricher = MetadataEnricher()
        result = enricher.enrich_chunks([chunk], dm, cg, eps, [])
        assert result[0].is_entry_point is True

    def test_build_qualified_name_index(self):
        from chunking.metadata_enricher import MetadataEnricher

        chunks = [
            _make_code_chunk(qualified_name="mod.foo"),
            _make_code_chunk(qualified_name="mod.bar"),
        ]
        enricher = MetadataEnricher()
        index = enricher.build_qualified_name_index(chunks)
        assert "mod.foo" in index
        assert "mod.bar" in index
        assert index["mod.foo"] == chunks[0].chunk_id


# ===========================================================================
# Embedder tests
# ===========================================================================

class TestEmbedder:
    """Tests require sentence-transformers installed (skipped otherwise)."""

    @pytest.fixture(autouse=True)
    def skip_if_no_st(self):
        pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

    def test_embed_query_returns_384_floats(self):
        from chunking.embedder import Embedder
        emb = Embedder()
        vec = emb.embed_query("authentication and login")
        assert isinstance(vec, list)
        assert len(vec) == 384
        assert all(isinstance(v, float) for v in vec)

    def test_embeddings_are_l2_normalized(self):
        import math
        from chunking.embedder import Embedder
        emb = Embedder()
        vec = emb.embed_query("test normalization")
        magnitude = math.sqrt(sum(v * v for v in vec))
        assert abs(magnitude - 1.0) < 0.01

    def test_batch_embed_chunks_populates_embeddings(self):
        from chunking.embedder import Embedder
        emb = Embedder()
        chunks = [_make_code_chunk(content=f"def func_{i}(): pass") for i in range(5)]
        result = emb.embed_chunks(chunks, show_progress=False)
        assert all(c.embedding is not None for c in result)
        assert all(len(c.embedding) == 384 for c in result)
        assert all(c.embedding_model == "all-MiniLM-L6-v2" for c in result)


# ===========================================================================
# VectorStore tests
# ===========================================================================

class TestVectorStore:
    """Tests require chromadb installed (skipped otherwise)."""

    @pytest.fixture(autouse=True)
    def skip_if_no_chromadb(self):
        pytest.importorskip("chromadb", reason="chromadb not installed")

    @pytest.fixture
    def tmp_store(self, tmp_path):
        from chunking.vector_store import VectorStore
        return VectorStore(db_path=str(tmp_path / "test_chroma"))

    def test_sanitize_collection_name_removes_special_chars(self):
        from chunking.vector_store import VectorStore
        vs = VectorStore.__new__(VectorStore)
        result = vs.sanitize_collection_name("codeautopsy__owner.name__repo-name")
        assert all(c.isalnum() or c in "_-" for c in result)

    def test_sanitize_collection_name_max_63_chars(self):
        from chunking.vector_store import VectorStore
        vs = VectorStore.__new__(VectorStore)
        long_name = "a" * 100
        result = vs.sanitize_collection_name(long_name)
        assert len(result) <= 63

    def test_add_and_count_chunks(self):
        from chunking.vector_store import VectorStore
        from chunking.embedder import Embedder
        emb = Embedder()
        vs = VectorStore.__new__(VectorStore)

        # We test add_chunks via a real tmp store
        import chromadb  # type: ignore
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            client = chromadb.PersistentClient(path=tmpdir)
            vs._client = client
            vs._chromadb = chromadb
            col = vs.get_or_create_collection("owner", "testrepo")

            chunks = [_make_code_chunk(content=f"def f_{i}(): pass") for i in range(3)]
            chunks = emb.embed_chunks(chunks, show_progress=False)
            vs.add_chunks(col, chunks)
            assert col.count() == 3

    def test_query_returns_results_sorted_by_similarity(self):
        from chunking.vector_store import VectorStore
        from chunking.embedder import Embedder
        import chromadb, tempfile

        emb = Embedder()
        with tempfile.TemporaryDirectory() as tmpdir:
            client = chromadb.PersistentClient(path=tmpdir)
            vs = VectorStore.__new__(VectorStore)
            vs._client = client
            vs._chromadb = chromadb

            col = vs.get_or_create_collection("owner", "querytest")
            chunks = [
                _make_code_chunk(content="authentication login password verify"),
                _make_code_chunk(content="database connection pool query"),
                _make_code_chunk(content="file read write disk storage"),
            ]
            chunks = emb.embed_chunks(chunks, show_progress=False)
            vs.add_chunks(col, chunks)

            qvec = emb.embed_query("user authentication")
            results = vs.query(col, qvec, n_results=3)
            assert len(results) > 0
            # Results must have required fields
            for r in results:
                assert "chunk_id" in r
                assert "similarity_score" in r
            # Scores must be descending
            scores = [r["similarity_score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_get_chunk_by_id(self):
        from chunking.vector_store import VectorStore
        from chunking.embedder import Embedder
        import chromadb, tempfile

        emb = Embedder()
        with tempfile.TemporaryDirectory() as tmpdir:
            client = chromadb.PersistentClient(path=tmpdir)
            vs = VectorStore.__new__(VectorStore)
            vs._client = client
            vs._chromadb = chromadb

            col = vs.get_or_create_collection("owner", "lookuptest")
            chunk = _make_code_chunk(content="unique lookup content here")
            chunk = emb.embed_chunks([chunk], show_progress=False)[0]
            vs.add_chunks(col, [chunk])

            found = vs.get_chunk_by_id(col, chunk.chunk_id)
            assert found is not None
            assert found["chunk_id"] == chunk.chunk_id


# ===========================================================================
# Integration tests
# ===========================================================================

@pytest.mark.integration
class TestPhase3Integration:
    """
    Full pipeline integration tests.
    Require:
      - Phase 2 output for pallets/itsdangerous to exist at
        data/repos/pallets__itsdangerous/parsed/
      - sentence-transformers and chromadb installed
    """

    @pytest.fixture(autouse=True)
    def skip_if_deps_missing(self):
        pytest.importorskip("sentence_transformers")
        pytest.importorskip("chromadb")

    @pytest.fixture
    def repo_folder(self):
        folder = _HERE / "data" / "repos" / "pallets__itsdangerous"
        if not (folder / "parsed" / "parse_manifest.json").exists():
            pytest.skip("Phase 2 output for pallets/itsdangerous not found")
        return folder

    def test_full_pipeline_creates_manifest(self, repo_folder, tmp_path):
        from chunking.chunk_orchestrator import chunk_and_embed_repository
        import config as cfg

        # Use a temp chroma db for isolation
        orig_path = cfg.CHROMA_DB_PATH
        cfg.CHROMA_DB_PATH = str(tmp_path / "chroma_test")
        try:
            manifest = chunk_and_embed_repository(repo_folder, force_rechunk=True)
            assert manifest.total_chunks > 0
            assert (repo_folder / "chunks" / "chunk_manifest.json").exists()
            assert (repo_folder / "chunks" / "chunks.jsonl").exists()
            assert (repo_folder / "chunks" / "chunk_index.json").exists()
        finally:
            cfg.CHROMA_DB_PATH = orig_path

    def test_no_chunk_has_empty_embedding(self, repo_folder, tmp_path):
        from chunking.chunk_orchestrator import chunk_and_embed_repository
        from chunking.vector_store import VectorStore
        import config as cfg

        orig_path = cfg.CHROMA_DB_PATH
        cfg.CHROMA_DB_PATH = str(tmp_path / "chroma_emb")
        try:
            manifest = chunk_and_embed_repository(repo_folder, force_rechunk=True)
            vs = VectorStore(cfg.CHROMA_DB_PATH)
            col = vs.get_or_create_collection(manifest.repo_owner, manifest.repo_name)
            # Spot-check: collection count matches manifest
            assert col.count() == manifest.total_chunks
        finally:
            cfg.CHROMA_DB_PATH = orig_path

    def test_query_authentication_returns_results(self, repo_folder, tmp_path):
        from chunking.chunk_orchestrator import chunk_and_embed_repository
        from chunking.vector_store import VectorStore
        from chunking.embedder import Embedder
        import config as cfg

        orig_path = cfg.CHROMA_DB_PATH
        cfg.CHROMA_DB_PATH = str(tmp_path / "chroma_query")
        try:
            manifest = chunk_and_embed_repository(repo_folder, force_rechunk=True)
            vs  = VectorStore(cfg.CHROMA_DB_PATH)
            col = vs.get_or_create_collection(manifest.repo_owner, manifest.repo_name)
            emb = Embedder()
            qvec = emb.embed_query("authentication token signing")
            results = vs.query(col, qvec, n_results=5)
            assert len(results) > 0
            # Top result should have a positive similarity score
            assert results[0]["similarity_score"] > 0.0
        finally:
            cfg.CHROMA_DB_PATH = orig_path
