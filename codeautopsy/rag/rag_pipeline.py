"""
rag/rag_pipeline.py — Full RAG Pipeline Orchestration

Main public API for Phase 4. Orchestrates the complete RAG flow:
1. Query processing
2. Hybrid retrieval
3. Graph expansion
4. Context building
5. LLM generation
6. Response formatting
7. Conversation management

This is the ONLY module that Phase 8 (FastAPI) should import.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR

from rag import RAGResponse
from rag.llm_client import LLMClient
from rag.query_processor import QueryProcessor
from rag.retriever import Retriever
from rag.context_builder import ContextBuilder
from rag.response_formatter import ResponseFormatter
from rag.conversation import ConversationManager

from chunking.vector_store import VectorStore
from chunking.embedder import Embedder

from prompts.system_prompts import CODE_QA_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    Complete RAG pipeline for code Q&A.
    
    This is the main public API for Phase 4.
    
    Usage:
        pipeline = RAGPipeline("owner", "repo")
        response = pipeline.ask("How does authentication work?")
    """
    
    def __init__(self, repo_owner: str, repo_name: str):
        """
        Initialize RAG pipeline for a repository.
        
        Args:
            repo_owner: Repository owner
            repo_name: Repository name
        
        Raises:
            FileNotFoundError: If Phase 1-3 outputs not found
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.repo_folder = Path(DATA_DIR) / f"{repo_owner}__{repo_name}"
        
        logger.info(f"Initializing RAG pipeline for {repo_owner}/{repo_name}")
        
        # Verify Phase 1-3 outputs exist
        self._verify_prerequisites()
        
        # Load repo metadata
        self._load_metadata()
        
        # Initialize all components
        self.vector_store = VectorStore()
        self.embedder = Embedder()
        self.llm_client = LLMClient()
        self.query_processor = QueryProcessor(self.llm_client)
        self.retriever = Retriever(
            self.vector_store,
            self.embedder,
            repo_owner,
            repo_name
        )
        self.context_builder = ContextBuilder()
        self.formatter = ResponseFormatter()
        self.conversation_manager = ConversationManager(
            repo_owner,
            repo_name,
            Path(DATA_DIR)
        )
        
        logger.info(f"RAG pipeline ready for {repo_owner}/{repo_name}")
    
    def _verify_prerequisites(self):
        """Verify Phase 1-3 outputs exist."""
        # Check Phase 1 output
        manifest_file = self.repo_folder / "manifest.json"
        if not manifest_file.exists():
            raise FileNotFoundError(
                f"Phase 1 output not found: {manifest_file}\n"
                f"Run: python main.py ingest {self.repo_owner}/{self.repo_name}"
            )
        
        # Check Phase 2 output
        parse_manifest = self.repo_folder / "parsed" / "parse_manifest.json"
        if not parse_manifest.exists():
            raise FileNotFoundError(
                f"Phase 2 output not found: {parse_manifest}\n"
                f"Run: python main.py parse {self.repo_owner}/{self.repo_name}"
            )
        
        # Check Phase 3 output
        chunk_manifest = self.repo_folder / "chunks" / "chunk_manifest.json"
        if not chunk_manifest.exists():
            raise FileNotFoundError(
                f"Phase 3 output not found: {chunk_manifest}\n"
                f"Run: python main.py embed {self.repo_owner}/{self.repo_name}"
            )
        
        logger.debug("Prerequisites verified: Phase 1-3 outputs found")
    
    def _load_metadata(self):
        """Load repository metadata from Phase 1-3."""
        # Load Phase 1 manifest
        with open(self.repo_folder / "manifest.json", 'r') as f:
            self.repo_metadata = json.load(f)
        
        # Load Phase 3 chunk manifest
        with open(self.repo_folder / "chunks" / "chunk_manifest.json", 'r') as f:
            self.chunk_manifest = json.load(f)
        
        # Load Phase 2 patterns (if available)
        patterns_file = self.repo_folder / "parsed" / "patterns.json"
        if patterns_file.exists():
            with open(patterns_file, 'r') as f:
                self.patterns = json.load(f)
        else:
            self.patterns = {}
        
        logger.debug("Metadata loaded from Phase 1-3")
    
    def ask(
        self,
        question: str,
        session_id: Optional[str] = None
    ) -> RAGResponse:
        """
        Ask a question about the codebase.
        
        Args:
            question: User's question
            session_id: Optional session ID for multi-turn conversation
        
        Returns:
            RAGResponse with answer and citations
        """
        logger.info(f"Processing question: {question[:100]}...")
        t_start = time.time()
        
        # 1. Get or create session
        if not session_id:
            session_id = self.conversation_manager.create_session()
            logger.debug(f"Created new session: {session_id}")
        
        session = self.conversation_manager.get_session(session_id)
        
        # 2. Process query
        processed_query = self.query_processor.process(question, session)
        logger.debug(f"Query type: {processed_query.query_type.value}")
        
        # 3. Retrieve primary chunks
        primary_chunks = self.retriever.retrieve(processed_query)
        
        # If no chunks found, return early
        if len(primary_chunks) == 0:
            logger.warning("No relevant chunks found")
            return self.formatter.format_no_context(
                question,
                session_id,
                session.total_questions + 1
            )
        
        # 4. Graph expansion (if needed)
        expanded_chunks = []
        if processed_query.is_graph_query or processed_query.is_multi_hop:
            logger.debug("Performing graph expansion")
            expanded_chunks = self.retriever.retrieve_by_graph(
                primary_chunks,
                processed_query
            )
        
        # 5. Build context
        context = self.context_builder.build(
            processed_query,
            primary_chunks,
            expanded_chunks,
            session
        )
        
        # 6. Build system prompt
        system_prompt = self._build_system_prompt(context)
        
        # 7. Build user message
        user_message = self._build_user_message(question, processed_query)
        
        # 8. Generate answer
        logger.debug("Generating LLM response...")
        raw_answer = self.llm_client.generate(system_prompt, user_message)
        
        response_time = time.time() - t_start
        
        # 9. Format response
        model_info = self.llm_client.get_model_info()
        response = self.formatter.format(
            question=question,
            raw_answer=raw_answer,
            context=context,
            query=processed_query,
            session_id=session_id,
            turn_number=session.total_questions + 1,
            model_used=f"{model_info['provider']}/{model_info['model_name']}",
            response_time=response_time,
            llm_client=self.llm_client
        )
        
        # 10. Save to conversation
        self.conversation_manager.add_turn(
            session_id,
            response,
            [c.chunk_id for c in primary_chunks]
        )
        
        logger.info(
            f"Response generated: confidence={response.confidence}, "
            f"time={response_time:.2f}s"
        )
        
        return response
    
    def _build_system_prompt(self, context) -> str:
        """Build system prompt with context."""
        # Get conversation history
        conversation_history = ""
        if context.query and hasattr(context.query, 'original'):
            # History is already in context_text from context_builder
            conversation_history = "(See previous conversation above)"
        
        # Format detected patterns
        detected_patterns = self._format_patterns()
        
        # Get primary language
        primary_language = self.repo_metadata.get('repo', {}).get(
            'primary_language',
            'Unknown'
        )
        
        # Fill template
        system_prompt = CODE_QA_SYSTEM_PROMPT.format(
            repo_owner=self.repo_owner,
            repo_name=self.repo_name,
            conversation_history=conversation_history,
            code_context=context.context_text,
            primary_language=primary_language,
            detected_patterns=detected_patterns
        )
        
        return system_prompt
    
    def _build_user_message(self, question: str, query) -> str:
        """Build user message with query-specific hints."""
        user_message = f"Question: {question}"
        
        # Add hints based on query type
        if query.query_type.value == "what_calls":
            user_message += (
                "\n\nFocus on call relationships shown in the context. "
                "List the functions that call the target function."
            )
        elif query.query_type.value == "what_imports":
            user_message += (
                "\n\nFocus on import statements and dependencies shown in the context."
            )
        elif query.query_type.value == "explain":
            user_message += (
                "\n\nProvide a comprehensive explanation of the flow, "
                "referencing specific functions and files."
            )
        
        return user_message
    
    def _format_patterns(self) -> str:
        """Format detected architectural patterns."""
        if not self.patterns or 'detected_patterns' not in self.patterns:
            return "None detected"
        
        detected = self.patterns['detected_patterns']
        if not detected:
            return "None detected"
        
        # Format as comma-separated list
        pattern_names = [p['pattern'] for p in detected]
        return ", ".join(pattern_names)
    
    def new_session(self) -> str:
        """
        Create a new conversation session.
        
        Returns:
            Session ID
        """
        return self.conversation_manager.create_session()
    
    def list_sessions(self) -> list[dict]:
        """
        List all conversation sessions for this repository.
        
        Returns:
            List of session summaries
        """
        return self.conversation_manager.list_sessions()
    
    def get_collection_stats(self) -> dict:
        """
        Get ChromaDB collection statistics.
        
        Returns:
            Dict with collection stats
        """
        collection = self.vector_store.get_or_create_collection(
            self.repo_owner,
            self.repo_name
        )
        return self.vector_store.get_collection_stats(collection)


# Test function
def test_rag_pipeline():
    """Test the RAG pipeline end-to-end."""
    print("Testing RAG Pipeline...")
    print("=" * 60)
    
    try:
        print("Note: This test requires a repository to be fully processed (Phase 1-3).")
        print("Run first: python main.py run https://github.com/pallets/itsdangerous")
        print()
        
        # Initialize pipeline
        pipeline = RAGPipeline("pallets", "itsdangerous")
        print("✓ RAG pipeline initialized")
        print()
        
        # Get collection stats
        stats = pipeline.get_collection_stats()
        print(f"Collection stats: {stats['count']} chunks")
        print()
        
        # Ask a question
        question = "What does the Signer class do?"
        print(f"Question: {question}")
        print("-" * 60)
        
        response = pipeline.ask(question)
        
        print(f"\nConfidence: {response.confidence}")
        print(f"Citations: {len(response.citations)}")
        print(f"Response time: {response.response_time_seconds:.2f}s")
        print()
        print("Answer:")
        print(response.answer[:500])
        if len(response.answer) > 500:
            print("...")
        print()
        
        print("✓ RAG pipeline test passed!")
        return True
    
    except FileNotFoundError as e:
        print(f"✗ {e}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_rag_pipeline()
