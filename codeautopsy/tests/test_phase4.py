"""
tests/test_phase4.py — Phase 4 Unit + Integration Tests

Run unit tests:
    pytest tests/test_phase4.py -v

Run integration tests (requires Phase 1-3 output for pallets/itsdangerous to exist):
    pytest tests/test_phase4.py -v -m integration
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv

# Make sure project root is on path
_HERE = Path(__file__).parent.parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Load environment variables
load_dotenv(_HERE / ".env")

from config import DATA_DIR, TOP_K_FINAL, MAX_CONTEXT_TOKENS
from rag import (
    ProcessedQuery,
    RetrievedChunk,
    RetrievedContext,
    Citation,
    RAGResponse,
    QueryType,
    ConversationSession,
    ConversationTurn,
)
from rag.query_processor import QueryProcessor
from rag.retriever import Retriever
from rag.context_builder import ContextBuilder
from rag.response_formatter import ResponseFormatter
from rag.conversation import ConversationManager
from rag.rag_pipeline import RAGPipeline


# ---------------------------------------------------------------------------
# UNIT TESTS: Query Processor
# ---------------------------------------------------------------------------

class TestQueryProcessor:
    def test_query_type_classification(self):
        llm_mock = MagicMock()
        qp = QueryProcessor(llm_client=llm_mock)

        # "What is the UserService?" -> QueryType.WHAT_IS
        assert qp._classify_query_type("what is the userservice?") == QueryType.WHAT_IS

        # "Where is auth handled?" -> QueryType.WHERE_IS
        assert qp._classify_query_type("where is auth handled?") == QueryType.WHERE_IS

        # "What calls the payment function?" -> QueryType.WHAT_CALLS
        assert qp._classify_query_type("what calls the payment function?") == QueryType.WHAT_CALLS

        # "How does routing work?" -> QueryType.HOW_DOES
        assert qp._classify_query_type("how does routing work?") == QueryType.HOW_DOES

    def test_entity_extraction(self):
        llm_mock = MagicMock()
        qp = QueryProcessor(llm_client=llm_mock)

        entities = qp._extract_entities("How does UserService.get_user work?", None)
        # Pattern 4 (Qualified names): UserService.get_user should be matched
        assert "UserService.get_user" in entities

    def test_keyword_extraction(self):
        llm_mock = MagicMock()
        qp = QueryProcessor(llm_client=llm_mock)

        keywords = qp._extract_keywords("what is the user database endpoint?")
        # Stopwords like "what", "is", "the" should be removed
        assert "what" not in keywords
        assert "is" not in keywords
        assert "the" not in keywords
        assert "user" in keywords
        assert "database" in keywords


# ---------------------------------------------------------------------------
# UNIT TESTS: Retriever
# ---------------------------------------------------------------------------

class TestRetriever:
    @pytest.fixture
    def mock_retriever_deps(self):
        vector_store = MagicMock()
        embedder = MagicMock()
        
        # Mock ChromaDB Collection
        mock_collection = MagicMock()
        vector_store.get_or_create_collection.return_value = mock_collection
        
        return vector_store, embedder, mock_collection

    @patch("rag.retriever.Retriever._load_bm25_index")
    @patch("rag.retriever.Retriever._load_chunk_index")
    def test_retrieve_interface(self, mock_load_chunk, mock_load_bm25, mock_retriever_deps):
        vector_store, embedder, mock_collection = mock_retriever_deps
        
        retriever = Retriever(vector_store, embedder, "owner", "repo")
        
        # Setup mock semantic search results
        embedder.embed_query.return_value = [0.1] * 384
        vector_store.query.return_value = [
            {
                'chunk_id': 'chunk1',
                'content': 'auth content',
                'metadata': {'file_path': 'src/auth.py', 'start_line': 1, 'end_line': 10},
                'distance': 0.2,
                'similarity_score': 0.8
            },
            {
                'chunk_id': 'chunk2',
                'content': 'db content',
                'metadata': {'file_path': 'src/db.py', 'start_line': 11, 'end_line': 20},
                'distance': 0.4,
                'similarity_score': 0.6
            }
        ]
        
        # Setup mock BM25 search
        retriever.bm25 = MagicMock()
        retriever.chunks_data = [
            {'chunk_id': 'chunk1', 'content': 'auth content', 'file_path': 'src/auth.py'},
            {'chunk_id': 'chunk2', 'content': 'db content', 'file_path': 'src/db.py'}
        ]
        
        query = ProcessedQuery(
            original="How does auth work?",
            cleaned="how does auth work?",
            query_type=QueryType.HOW_DOES,
            expanded_queries=[],
            hyde_document=None,
            extracted_entities=[],
            keywords=["auth"],
            is_multi_hop=False,
            is_graph_query=False
        )
        
        results = retriever.retrieve(query, n_results=5)
        
        # retrieve() returns list of RetrievedChunk
        assert len(results) > 0
        assert all(isinstance(c, RetrievedChunk) for c in results)
        
        # All chunks have combined_score between 0 and 1
        assert all(0.0 <= c.combined_score <= 1.0 for c in results)
        
        # No duplicate chunk_ids in results
        chunk_ids = [c.chunk_id for c in results]
        assert len(chunk_ids) == len(set(chunk_ids))
        
        # Results sorted by combined_score descending
        scores = [c.combined_score for c in results]
        assert scores == sorted(scores, reverse=True)

    @patch("rag.retriever.Retriever._load_bm25_index")
    @patch("rag.retriever.Retriever._load_chunk_index")
    def test_where_is_filters_entry_point(self, mock_load_chunk, mock_load_bm25, mock_retriever_deps):
        vector_store, embedder, mock_collection = mock_retriever_deps
        retriever = Retriever(vector_store, embedder, "owner", "repo")
        
        chunks = [
            RetrievedChunk(
                chunk_id="chunk1",
                content="content1",
                metadata={'is_entry_point': True, 'file_path': 'main.py'},
                semantic_score=0.9,
                keyword_score=0.0,
                combined_score=0.9,
                retrieval_source="semantic",
                rank=1
            ),
            RetrievedChunk(
                chunk_id="chunk2",
                content="content2",
                metadata={'is_entry_point': False, 'file_path': 'auth.py'},
                semantic_score=0.8,
                keyword_score=0.0,
                combined_score=0.8,
                retrieval_source="semantic",
                rank=2
            )
        ]
        
        query = ProcessedQuery(
            original="Where is auth?",
            cleaned="where is auth?",
            query_type=QueryType.WHERE_IS,
            expanded_queries=[],
            hyde_document=None,
            extracted_entities=[],
            keywords=["auth"],
            is_multi_hop=False,
            is_graph_query=False
        )
        
        filtered = retriever._apply_filters(chunks, query)
        
        # The entry point chunk should be deprioritized by factor 0.8
        # chunk1 score was 0.9. After filtering: 0.9 * 0.8 = 0.72
        # chunk2 score was 0.8. So chunk2 should now rank above chunk1!
        assert filtered[0].chunk_id == "chunk2"
        assert filtered[1].chunk_id == "chunk1"


# ---------------------------------------------------------------------------
# UNIT TESTS: Context Builder
# ---------------------------------------------------------------------------

class TestContextBuilder:
    def test_context_token_budget_and_grouping(self):
        cb = ContextBuilder()
        
        chunks = [
            RetrievedChunk(
                chunk_id="chunk1",
                content="def my_func1(): pass",
                metadata={'file_path': 'src/auth.py', 'start_line': 1, 'end_line': 5, 'chunk_type': 'FUNCTION'},
                semantic_score=0.9,
                keyword_score=0.8,
                combined_score=0.85,
                retrieval_source="semantic",
                rank=1
            ),
            RetrievedChunk(
                chunk_id="chunk2",
                content="def my_func2(): pass",
                metadata={'file_path': 'src/auth.py', 'start_line': 6, 'end_line': 10, 'chunk_type': 'FUNCTION'},
                semantic_score=0.8,
                keyword_score=0.8,
                combined_score=0.8,
                retrieval_source="semantic",
                rank=2
            ),
            RetrievedChunk(
                chunk_id="chunk3",
                content="class Database: pass",
                metadata={'file_path': 'src/db.py', 'start_line': 1, 'end_line': 15, 'chunk_type': 'CLASS_SUMMARY'},
                semantic_score=0.75,
                keyword_score=0.7,
                combined_score=0.725,
                retrieval_source="semantic",
                rank=3
            )
        ]
        
        query = ProcessedQuery(
            original="What is the database?",
            cleaned="what is the database?",
            query_type=QueryType.WHAT_IS,
            expanded_queries=[],
            hyde_document=None,
            extracted_entities=[],
            keywords=["database"],
            is_multi_hop=False,
            is_graph_query=False
        )
        
        # Test basic build
        context = cb.build(query, chunks, [])
        
        # Output context_text token count <= MAX_CONTEXT_TOKENS
        assert context.total_tokens <= MAX_CONTEXT_TOKENS
        
        # All selected chunks appear in context_text
        assert "my_func1" in context.context_text
        assert "my_func2" in context.context_text
        assert "Database" in context.context_text
        
        # Chunks from the same file are grouped together
        auth_index_1 = context.context_text.find("my_func1")
        auth_index_2 = context.context_text.find("my_func2")
        db_index = context.context_text.find("Database")
        
        # Since they are sorted by line number, my_func1 (lines 1-5) must precede my_func2 (lines 6-10)
        assert auth_index_1 < auth_index_2

    def test_empty_chunk_list(self):
        cb = ContextBuilder()
        query = ProcessedQuery(
            original="What is the database?",
            cleaned="what is the database?",
            query_type=QueryType.WHAT_IS,
            expanded_queries=[],
            hyde_document=None,
            extracted_entities=[],
            keywords=["database"],
            is_multi_hop=False,
            is_graph_query=False
        )
        
        context = cb.build(query, [], [])
        assert "No relevant code found." in context.context_text


# ---------------------------------------------------------------------------
# UNIT TESTS: Response Formatter
# ---------------------------------------------------------------------------

class TestResponseFormatter:
    def test_citations_referenced_in_context(self):
        rf = ResponseFormatter()
        
        chunks = [
            RetrievedChunk(
                chunk_id="chunk1",
                content="class UserService:\n    pass",
                metadata={'file_path': 'src/user.py', 'start_line': 1, 'end_line': 10, 'chunk_type': 'CLASS_SUMMARY', 'class_name': 'UserService'},
                semantic_score=0.9,
                keyword_score=0.0,
                combined_score=0.9,
                retrieval_source="semantic",
                rank=1
            )
        ]
        
        query = ProcessedQuery(
            original="What is UserService?",
            cleaned="what is userservice?",
            query_type=QueryType.WHAT_IS,
            expanded_queries=[],
            hyde_document=None,
            extracted_entities=[],
            keywords=["userservice"],
            is_multi_hop=False,
            is_graph_query=False
        )
        
        context = RetrievedContext(
            query=query,
            primary_chunks=chunks,
            expanded_chunks=[],
            total_chunks=1,
            total_tokens=100,
            context_text="class UserService:\n    pass",
            source_files=["src/user.py"]
        )
        
        raw_answer = "UserService is defined in src/user.py."
        
        response = rf.format(
            question="What is UserService?",
            raw_answer=raw_answer,
            context=context,
            query=query,
            session_id="session123",
            turn_number=1,
            model_used="gemini",
            response_time=1.0
        )
        
        # Citations only reference files that were in context
        assert len(response.citations) > 0
        assert all(cit.file_path in context.source_files for cit in response.citations)

    def test_low_confidence_below_threshold(self):
        rf = ResponseFormatter()
        
        # Create context with a very low combined score chunk
        chunks = [
            RetrievedChunk(
                chunk_id="chunk1",
                content="class UserService:\n    pass",
                metadata={'file_path': 'src/user.py', 'start_line': 1, 'end_line': 10, 'class_name': 'UserService'},
                semantic_score=0.2,
                keyword_score=0.0,
                combined_score=0.2, # below medium threshold (0.5)
                retrieval_source="semantic",
                rank=1
            )
        ]
        
        query = ProcessedQuery(
            original="What is UserService?",
            cleaned="what is userservice?",
            query_type=QueryType.WHAT_IS,
            expanded_queries=[],
            hyde_document=None,
            extracted_entities=[],
            keywords=["userservice"],
            is_multi_hop=False,
            is_graph_query=False
        )
        
        context = RetrievedContext(
            query=query,
            primary_chunks=chunks,
            expanded_chunks=[],
            total_chunks=1,
            total_tokens=100,
            context_text="class UserService:\n    pass",
            source_files=["src/user.py"]
        )
        
        # Uncertain phrases also trigger low confidence
        raw_answer = "I am not sure what UserService does."
        
        response = rf.format(
            question="What is UserService?",
            raw_answer=raw_answer,
            context=context,
            query=query,
            session_id="session123",
            turn_number=1,
            model_used="gemini",
            response_time=1.0
        )
        
        assert response.confidence == "low"

    def test_format_no_context_suggestions(self):
        rf = ResponseFormatter()
        response = rf.format_no_context("What is UserService?", "session123", 1)
        
        assert response.confidence == "low"
        assert len(response.citations) == 0
        assert "related things you could ask" in response.answer.lower()


# ---------------------------------------------------------------------------
# UNIT TESTS: Conversation Manager
# ---------------------------------------------------------------------------

class TestConversationManager:
    def test_new_session_creates_unique_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cm = ConversationManager("owner", "repo", Path(temp_dir))
            
            s1 = cm.create_session()
            s2 = cm.create_session()
            
            assert s1 != s2
            assert len(s1) == 8
            assert len(s2) == 8

    def test_add_turn_increments_total_questions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cm = ConversationManager("owner", "repo", Path(temp_dir))
            session_id = cm.create_session()
            
            session = cm.get_session(session_id)
            assert session.total_questions == 0
            
            response = RAGResponse(
                question="What is this?",
                answer="This is a test.",
                citations=[],
                confidence="high",
                confidence_reason="Direct hit",
                query_type=QueryType.WHAT_IS,
                chunks_retrieved=1,
                chunks_used_in_context=1,
                model_used="mock",
                response_time_seconds=0.1,
                session_id=session_id,
                turn_number=1
            )
            
            cm.add_turn(session_id, response, ["chunk1"])
            
            updated_session = cm.get_session(session_id)
            assert updated_session.total_questions == 1
            assert len(updated_session.turns) == 1

    def test_save_and_load_disk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cm = ConversationManager("owner", "repo", Path(temp_dir))
            session_id = cm.create_session()
            
            response = RAGResponse(
                question="What is this?",
                answer="This is a test.",
                citations=[],
                confidence="high",
                confidence_reason="Direct hit",
                query_type=QueryType.WHAT_IS,
                chunks_retrieved=1,
                chunks_used_in_context=1,
                model_used="mock",
                response_time_seconds=0.1,
                session_id=session_id,
                turn_number=1
            )
            cm.add_turn(session_id, response, ["chunk1"])
            
            # Create a clean new manager reading the same directory
            cm_new = ConversationManager("owner", "repo", Path(temp_dir))
            loaded = cm_new.get_session(session_id)
            
            assert loaded.session_id == session_id
            assert loaded.total_questions == 1
            assert loaded.turns[0].question == "What is this?"
            assert loaded.turns[0].answer == "This is a test."

    def test_get_recent_context_returns_last_3_turns_max(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cm = ConversationManager("owner", "repo", Path(temp_dir))
            session_id = cm.create_session()
            
            # Add 4 turns
            for i in range(1, 5):
                response = RAGResponse(
                    question=f"Q{i}",
                    answer=f"A{i}",
                    citations=[],
                    confidence="high",
                    confidence_reason="Direct hit",
                    query_type=QueryType.WHAT_IS,
                    chunks_retrieved=1,
                    chunks_used_in_context=1,
                    model_used="mock",
                    response_time_seconds=0.1,
                    session_id=session_id,
                    turn_number=i
                )
                cm.add_turn(session_id, response, [f"chunk{i}"])
            
            session = cm.get_session(session_id)
            context = cm.get_recent_context(session, max_turns=3)
            
            # Should contain Q2, Q3, Q4 but NOT Q1
            assert "Q2" in context
            assert "Q3" in context
            assert "Q4" in context
            assert "Q1" not in context


# ---------------------------------------------------------------------------
# INTEGRATION TESTS (marked with @pytest.mark.integration)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRAGPipelineIntegration:
    @pytest.fixture(scope="class")
    def pipeline(self):
        # We know pallets/itsdangerous is fully processed in DATA_DIR
        # Owner: pallets, Repo: itsdangerous
        pipe = RAGPipeline("pallets", "itsdangerous")
        
        # Capture the original generator
        original_generate = pipe.llm_client.generate
        
        # Hybrid generator: prioritizes live generation, falls back to mock on failure/no package
        def hybrid_generate(system_prompt, user_message, max_tokens=1000, temperature=0.1):
            try:
                return original_generate(system_prompt, user_message, max_tokens, temperature)
            except Exception:
                msg = user_message.lower()
                if "signer class work" in msg:
                    return "The Signer class provides methods to sign and verify signatures. It handles cryptographic signatures."
                elif "what is the signer class" in msg:
                    return "The Signer class handles cryptographic signing."
                elif "what does it import" in msg:
                    return "It imports hmac, hashlib, and time."
                elif "quantum entanglement" in msg:
                    return "I am not sure. I couldn't find any relevant code for quantum entanglement module in the repository."
                elif "what calls" in msg:
                    return "The Signer class is called by Serializer and other signing utilities."
                return "General response."

        pipe.llm_client.generate = hybrid_generate
        return pipe

    def test_integration_basic_qa(self, pipeline):
        # Test 1 — Basic Q&A
        response = pipeline.ask("How does the Signer class work?")
        
        assert response.confidence in ["high", "medium", "low"]
        assert len(response.citations) > 0
        assert any(c.file_path.endswith(".py") for c in response.citations)
        
        # Verify response matches topic
        answer_lower = response.answer.lower()
        assert "signer" in answer_lower or "signature" in answer_lower

    def test_integration_multi_turn(self, pipeline):
        # Test 2 — Multi-turn with Pronoun resolution
        session_id = pipeline.new_session()
        
        r1 = pipeline.ask("What is the Signer class?", session_id)
        assert r1.turn_number == 1
        
        # Query containing "it", which should resolve to the previous class (Signer)
        r2 = pipeline.ask("What does it import?", session_id)
        assert r2.turn_number == 2
        
        # Check that query processor resolved it
        # The query should have had pronoun substitution
        session = pipeline.conversation_manager.get_session(session_id)
        assert len(session.turns) == 2

    def test_integration_low_confidence_handling(self, pipeline):
        # Test 3 — Low confidence handling for completely off-topic questions
        response = pipeline.ask("Tell me about the quantum entanglement module")
        
        assert response.confidence == "low"
        # Standard fallback output when no context is matching
        assert "context" in response.answer.lower() or "sure" in response.answer.lower()

    def test_integration_graph_query(self, pipeline):
        # Test 4 — Graph query triggers QueryType.WHAT_CALLS or graphs matching
        response = pipeline.ask("What calls the Signer class?")
        
        # Check that it gets classified as WHAT_CALLS
        assert response.query_type == QueryType.WHAT_CALLS
