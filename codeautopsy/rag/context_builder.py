"""
rag/context_builder.py — Context Assembly for LLM

Assembles retrieved chunks into optimal LLM context:
- Respects token budget (MAX_CONTEXT_TOKENS)
- Prioritizes chunks by relevance
- Groups by file and sorts by line number
- Deduplicates sub-chunks
- Formats with clear structure
- Includes conversation history
"""

import logging
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    MAX_CONTEXT_TOKENS,
    MAX_HISTORY_TOKENS,
    CONTEXT_CHUNK_SEPARATOR,
)

from rag import ProcessedQuery, RetrievedChunk, RetrievedContext, ConversationSession

try:
    import tiktoken
except ImportError:
    raise ImportError("tiktoken not installed. Run: pip install tiktoken")

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Assembles retrieved chunks into optimal LLM context.
    
    Usage:
        builder = ContextBuilder()
        context = builder.build(query, primary_chunks, expanded_chunks, conversation)
    """
    
    def __init__(self):
        """Initialize context builder with tokenizer."""
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        logger.info("Context builder initialized")
    
    def build(
        self,
        query: ProcessedQuery,
        primary_chunks: list[RetrievedChunk],
        expanded_chunks: list[RetrievedChunk],
        conversation: Optional[ConversationSession] = None
    ) -> RetrievedContext:
        """
        Build context from retrieved chunks.
        
        Args:
            query: Processed query
            primary_chunks: Directly retrieved chunks
            expanded_chunks: Graph-expanded chunks
            conversation: Optional conversation session
        
        Returns:
            RetrievedContext with assembled text
        """
        # STEP 1: Calculate token budget
        history_text = self._build_history_text(conversation) if conversation else ""
        history_tokens = self._count_tokens(history_text)
        history_tokens = min(history_tokens, MAX_HISTORY_TOKENS)
        
        remaining_budget = MAX_CONTEXT_TOKENS - history_tokens
        
        logger.debug(
            f"Token budget: {MAX_CONTEXT_TOKENS} total, "
            f"{history_tokens} history, {remaining_budget} for chunks"
        )
        
        # STEP 2: Prioritize chunks
        prioritized = self._prioritize_chunks(primary_chunks, expanded_chunks)
        
        # STEP 3: Fill context greedily
        selected_chunks = self._select_chunks(prioritized, remaining_budget)
        
        # STEP 4: Deduplicate sub-chunks
        selected_chunks = self._deduplicate_subchunks(selected_chunks)
        
        # STEP 5: Group and format context text
        context_text = self._format_context(selected_chunks)
        
        # STEP 6: Build RetrievedContext
        source_files = list(set(
            chunk.metadata.get('file_path', 'unknown')
            for chunk in selected_chunks
        ))
        
        total_tokens = history_tokens + self._count_tokens(context_text)
        
        context = RetrievedContext(
            query=query,
            primary_chunks=primary_chunks,
            expanded_chunks=expanded_chunks,
            total_chunks=len(selected_chunks),
            total_tokens=total_tokens,
            context_text=context_text,
            source_files=source_files
        )
        
        logger.info(
            f"Context built: {len(selected_chunks)} chunks, "
            f"{total_tokens} tokens, {len(source_files)} files"
        )
        
        return context
    
    def _prioritize_chunks(
        self,
        primary: list[RetrievedChunk],
        expanded: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """
        Prioritize chunks for context inclusion.
        
        Priority order:
        1. Entity lookup chunks (combined_score = 0.95)
        2. Primary semantic chunks (by combined_score desc)
        3. Graph expansion chunks (by combined_score desc)
        4. Keyword-only chunks (by combined_score desc)
        """
        all_chunks = primary + expanded
        
        # Sort by:
        # 1. Entity lookup first (retrieval_source = "entity_lookup")
        # 2. Then by combined_score descending
        def sort_key(chunk: RetrievedChunk):
            is_entity = 1 if chunk.retrieval_source == "entity_lookup" else 0
            return (is_entity, chunk.combined_score)
        
        prioritized = sorted(all_chunks, key=sort_key, reverse=True)
        
        return prioritized
    
    def _select_chunks(
        self,
        chunks: list[RetrievedChunk],
        budget: int
    ) -> list[RetrievedChunk]:
        """
        Greedily select chunks within token budget.
        
        Args:
            chunks: Prioritized chunks
            budget: Remaining token budget
        
        Returns:
            Selected chunks
        """
        selected = []
        used_tokens = 0
        
        for chunk in chunks:
            # Format chunk to get actual token count
            formatted = self._format_chunk(chunk)
            chunk_tokens = self._count_tokens(formatted)
            
            # Check if it fits
            if used_tokens + chunk_tokens > budget:
                logger.debug(
                    f"Skipping chunk (would exceed budget): "
                    f"{chunk_tokens} tokens, {used_tokens}/{budget} used"
                )
                continue
            
            selected.append(chunk)
            used_tokens += chunk_tokens
            
            logger.debug(
                f"Selected chunk: {chunk_tokens} tokens, "
                f"{used_tokens}/{budget} used"
            )
        
        # Always keep at least 1 chunk even if over budget
        if not selected and chunks:
            selected = [chunks[0]]
            logger.warning("No chunks fit budget, keeping highest-ranked chunk")
        
        return selected
    
    def _deduplicate_subchunks(
        self,
        chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """
        Remove sub-chunks if parent function is also selected.
        
        If both a sub-chunk and its parent function are selected,
        keep only the parent (it contains full context).
        """
        # Group by parent function
        parent_functions = set()
        subchunks = []
        regular_chunks = []
        
        for chunk in chunks:
            is_subchunk = chunk.metadata.get('is_subchunk', False)
            parent_function = chunk.metadata.get('parent_function')
            
            if is_subchunk:
                subchunks.append(chunk)
            else:
                regular_chunks.append(chunk)
                if parent_function:
                    parent_functions.add(parent_function)
        
        # Filter out sub-chunks whose parent is present
        filtered_subchunks = [
            chunk for chunk in subchunks
            if chunk.metadata.get('parent_function') not in parent_functions
        ]
        
        deduplicated = regular_chunks + filtered_subchunks
        
        if len(deduplicated) < len(chunks):
            logger.debug(
                f"Deduplicated {len(chunks) - len(deduplicated)} sub-chunks"
            )
        
        return deduplicated
    
    def _format_context(self, chunks: list[RetrievedChunk]) -> str:
        """
        Format chunks into structured context text.
        
        Groups by file, sorts by line number, formats with headers.
        """
        if not chunks:
            return "No relevant code found."
        
        # Group by file
        by_file = {}
        for chunk in chunks:
            file_path = chunk.metadata.get('file_path', 'unknown')
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(chunk)
        
        # Sort chunks within each file by start_line
        for file_path in by_file:
            by_file[file_path].sort(
                key=lambda c: c.metadata.get('start_line', 0)
            )
        
        # Format each chunk
        formatted_chunks = []
        for file_path, file_chunks in by_file.items():
            for chunk in file_chunks:
                formatted = self._format_chunk(chunk)
                formatted_chunks.append(formatted)
        
        # Join with separator
        context_text = CONTEXT_CHUNK_SEPARATOR.join(formatted_chunks)
        
        return context_text
    
    def _format_chunk(self, chunk: RetrievedChunk) -> str:
        """
        Format a single chunk for LLM context.
        
        Returns formatted string with appropriate header.
        """
        chunk_type = chunk.metadata.get('chunk_type', 'UNKNOWN')
        file_path = chunk.metadata.get('file_path', 'unknown')
        start_line = chunk.metadata.get('start_line', 0)
        end_line = chunk.metadata.get('end_line', 0)
        qualified_name = chunk.metadata.get('qualified_name', 'unknown')
        
        # Get content (prefer full content over preview)
        content = chunk.content
        if not content and 'content' in chunk.metadata:
            content = chunk.metadata['content']
        
        # Format based on chunk type
        if chunk_type in ['FUNCTION', 'METHOD']:
            header = (
                f"📁 File: {file_path} | Lines {start_line}-{end_line}\n"
                f"🔧 Function: {qualified_name}"
            )
        elif chunk_type == 'CLASS_SUMMARY':
            header = (
                f"📁 File: {file_path}\n"
                f"🏗️ Class: {qualified_name}"
            )
        elif chunk_type == 'FILE_SUMMARY':
            header = f"📁 Module Overview: {file_path}"
        elif chunk_type == 'IMPORT_CONTEXT':
            header = f"📦 Imports: {file_path}"
        else:
            header = f"📄 {file_path} | Lines {start_line}-{end_line}"
        
        return f"{header}\n\n{content}"
    
    def _build_history_text(self, conversation: ConversationSession) -> str:
        """
        Build conversation history text.
        
        Takes last 3 turns, truncates answers to 300 chars.
        """
        if not conversation or not conversation.turns:
            return ""
        
        # Take last 3 turns
        recent_turns = conversation.turns[-3:]
        
        history_parts = []
        for turn in recent_turns:
            # Truncate answer
            answer = turn.answer
            if len(answer) > 300:
                answer = answer[:297] + "..."
            
            history_parts.append(
                f"Previous Q: {turn.question}\n"
                f"Previous A: {answer}"
            )
        
        return "\n\n".join(history_parts)
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        if not text:
            return 0
        
        try:
            tokens = self.tokenizer.encode(text)
            return len(tokens)
        except Exception as e:
            logger.warning(f"Token counting failed: {e}. Using char estimate.")
            # Fallback: rough estimate (1 token ≈ 4 chars)
            return len(text) // 4


# Test function
def test_context_builder():
    """Test the context builder."""
    print("Testing Context Builder...")
    print("=" * 60)
    
    try:
        from rag import ProcessedQuery, RetrievedChunk, QueryType
        
        # Create mock chunks
        mock_chunks = [
            RetrievedChunk(
                chunk_id="chunk1",
                content="def authenticate(user, password):\n    return verify_password(user, password)",
                metadata={
                    'file_path': 'auth/middleware.py',
                    'start_line': 10,
                    'end_line': 20,
                    'qualified_name': 'authenticate',
                    'chunk_type': 'FUNCTION'
                },
                semantic_score=0.9,
                keyword_score=0.7,
                combined_score=0.85,
                retrieval_source="semantic",
                rank=1
            ),
            RetrievedChunk(
                chunk_id="chunk2",
                content="class User:\n    def __init__(self, username):\n        self.username = username",
                metadata={
                    'file_path': 'models/user.py',
                    'start_line': 5,
                    'end_line': 15,
                    'qualified_name': 'User',
                    'chunk_type': 'CLASS_SUMMARY'
                },
                semantic_score=0.8,
                keyword_score=0.6,
                combined_score=0.75,
                retrieval_source="semantic",
                rank=2
            )
        ]
        
        # Create mock query
        mock_query = ProcessedQuery(
            original="How does authentication work?",
            cleaned="how does authentication work?",
            query_type=QueryType.HOW_DOES,
            expanded_queries=[],
            hyde_document=None,
            extracted_entities=[],
            keywords=["authentication", "work"],
            is_multi_hop=False,
            is_graph_query=False
        )
        
        # Build context
        builder = ContextBuilder()
        context = builder.build(mock_query, mock_chunks, [], None)
        
        print("✓ Context builder initialized")
        print()
        print(f"Total chunks: {context.total_chunks}")
        print(f"Total tokens: {context.total_tokens}")
        print(f"Source files: {context.source_files}")
        print()
        print("Context text preview:")
        print("-" * 60)
        print(context.context_text[:500])
        print("..." if len(context.context_text) > 500 else "")
        print()
        
        print("✓ Context building test passed!")
        return True
    
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_context_builder()
