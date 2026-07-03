"""
rag/response_formatter.py — Response Formatting and Citation

Formats LLM responses with:
- Citation extraction from answer + context
- Confidence assessment
- Structured RAGResponse output
"""

import logging
import re
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import HIGH_CONFIDENCE_THRESHOLD, MEDIUM_CONFIDENCE_THRESHOLD

from rag import (
    ProcessedQuery,
    RetrievedContext,
    RetrievedChunk,
    Citation,
    RAGResponse,
    QueryType
)
from rag.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """
    Formats LLM responses with citations and confidence assessment.
    
    Usage:
        formatter = ResponseFormatter()
        response = formatter.format(question, raw_answer, context, ...)
    """
    
    def format(
        self,
        question: str,
        raw_answer: str,
        context: RetrievedContext,
        query: ProcessedQuery,
        session_id: str,
        turn_number: int,
        model_used: str,
        response_time: float,
        llm_client: Optional[LLMClient] = None
    ) -> RAGResponse:
        """
        Format a complete RAG response.
        
        Args:
            question: Original question
            raw_answer: LLM-generated answer
            context: Retrieved context
            query: Processed query
            session_id: Conversation session ID
            turn_number: Turn number in conversation
            model_used: Model name
            response_time: Response time in seconds
            llm_client: Optional LLM client for confidence assessment
        
        Returns:
            RAGResponse with citations and confidence
        """
        # STEP 1: Extract citations
        citations = self._extract_citations(raw_answer, context)
        
        # STEP 2: Assess confidence
        avg_score = self._calculate_avg_score(context.primary_chunks)
        confidence, confidence_reason = self._assess_confidence(
            question,
            raw_answer,
            len(context.primary_chunks),
            avg_score,
            len(citations)
        )
        
        # STEP 3: Format final answer with citation block
        formatted_answer = self._format_answer_with_citations(raw_answer, citations)
        
        response = RAGResponse(
            question=question,
            answer=formatted_answer,
            citations=citations,
            confidence=confidence,
            confidence_reason=confidence_reason,
            query_type=query.query_type,
            chunks_retrieved=len(context.primary_chunks),
            chunks_used_in_context=context.total_chunks,
            model_used=model_used,
            response_time_seconds=response_time,
            session_id=session_id,
            turn_number=turn_number
        )
        
        logger.info(
            f"Response formatted: confidence={confidence}, "
            f"citations={len(citations)}, tokens={context.total_tokens}"
        )
        
        return response
    
    def format_no_context(
        self,
        question: str,
        session_id: str,
        turn_number: int
    ) -> RAGResponse:
        """
        Format response when no relevant chunks found.
        
        Args:
            question: Original question
            session_id: Session ID
            turn_number: Turn number
        
        Returns:
            RAGResponse with low confidence
        """
        # Generate suggestions based on question
        suggestions = self._generate_suggestions(question)
        
        answer = (
            "I couldn't find relevant code for this question. "
            "The codebase may not contain what you're looking for, "
            "or try rephrasing.\n\n"
            f"Related things you could ask:\n"
            f"• {suggestions[0]}\n"
            f"• {suggestions[1]}"
        )
        
        response = RAGResponse(
            question=question,
            answer=answer,
            citations=[],
            confidence="low",
            confidence_reason="No relevant code found",
            query_type=QueryType.GENERAL,
            chunks_retrieved=0,
            chunks_used_in_context=0,
            model_used="none",
            response_time_seconds=0.0,
            session_id=session_id,
            turn_number=turn_number
        )
        
        return response
    
    def _extract_citations(
        self,
        answer: str,
        context: RetrievedContext
    ) -> list[Citation]:
        """
        Extract citations from answer based on context chunks.
        
        A chunk is cited if:
        - Its function/class name appears in answer
        - Its file path appears in answer
        - Key terms from its content appear in answer
        """
        citations = []
        seen_chunks = set()
        
        # Get all chunks (primary + expanded)
        all_chunks = context.primary_chunks + context.expanded_chunks
        
        for chunk in all_chunks:
            # Skip if already cited
            if chunk.chunk_id in seen_chunks:
                continue
            
            # Check if chunk is referenced in answer
            if self._is_chunk_referenced(answer, chunk):
                citation = self._create_citation(chunk, answer)
                citations.append(citation)
                seen_chunks.add(chunk.chunk_id)
        
        # Sort by relevance (combined_score)
        citations.sort(key=lambda c: self._get_chunk_score(c.chunk_id, all_chunks), reverse=True)
        
        # Limit to top 10 citations
        return citations[:10]
    
    def _is_chunk_referenced(self, answer: str, chunk: RetrievedChunk) -> bool:
        """Check if chunk is referenced in answer."""
        answer_lower = answer.lower()
        
        # Check function name
        function_name = chunk.metadata.get('qualified_name', '')
        if function_name and len(function_name) > 3:
            # Match as whole word
            pattern = r'\b' + re.escape(function_name.lower()) + r'\b'
            if re.search(pattern, answer_lower):
                return True
        
        # Check class name
        class_name = chunk.metadata.get('class_name', '')
        if class_name and len(class_name) > 3:
            pattern = r'\b' + re.escape(class_name.lower()) + r'\b'
            if re.search(pattern, answer_lower):
                return True
        
        # Check file path (just filename)
        file_path = chunk.metadata.get('file_path', '')
        if file_path:
            filename = Path(file_path).name
            if filename.lower() in answer_lower:
                return True
        
        # Check key terms from content (extract identifiers)
        content = chunk.content
        identifiers = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b', content)
        # Check if multiple identifiers appear
        matches = sum(1 for ident in identifiers if ident.lower() in answer_lower)
        if matches >= 2:
            return True
        
        return False
    
    def _create_citation(self, chunk: RetrievedChunk, answer: str) -> Citation:
        """Create a Citation object from a chunk."""
        file_path = chunk.metadata.get('file_path', 'unknown')
        function_name = chunk.metadata.get('qualified_name')
        class_name = chunk.metadata.get('class_name')
        start_line = chunk.metadata.get('start_line', 0)
        end_line = chunk.metadata.get('end_line', 0)
        chunk_id = chunk.chunk_id
        
        # Determine relevance note
        chunk_type = chunk.metadata.get('chunk_type', '')
        if chunk_type == 'FUNCTION':
            relevance = f"Function implementation"
        elif chunk_type == 'METHOD':
            relevance = f"Method implementation"
        elif chunk_type == 'CLASS_SUMMARY':
            relevance = f"Class definition"
        elif chunk_type == 'FILE_SUMMARY':
            relevance = f"Module overview"
        else:
            relevance = f"Code reference"
        
        return Citation(
            file_path=file_path,
            function_name=function_name,
            class_name=class_name,
            start_line=start_line,
            end_line=end_line,
            chunk_id=chunk_id,
            relevance=relevance
        )
    
    def _get_chunk_score(self, chunk_id: str, chunks: list[RetrievedChunk]) -> float:
        """Get combined score for a chunk."""
        for chunk in chunks:
            if chunk.chunk_id == chunk_id:
                return chunk.combined_score
        return 0.0
    
    def _calculate_avg_score(self, chunks: list[RetrievedChunk]) -> float:
        """Calculate average combined score of chunks."""
        if not chunks:
            return 0.0
        return sum(c.combined_score for c in chunks) / len(chunks)
    
    def _assess_confidence(
        self,
        question: str,
        answer: str,
        chunks_found: int,
        avg_score: float,
        num_citations: int
    ) -> tuple[str, str]:
        """
        Assess confidence in the answer.
        
        Returns:
            Tuple of (confidence_level, reason)
        """
        # Rule-based assessment
        
        # No chunks found
        if chunks_found == 0:
            return "low", "No relevant code found"
        
        # Check for uncertainty phrases in answer
        uncertainty_phrases = [
            "i don't know", "not sure", "unclear", "cannot determine",
            "don't have enough", "insufficient context"
        ]
        answer_lower = answer.lower()
        if any(phrase in answer_lower for phrase in uncertainty_phrases):
            return "low", "Answer expresses uncertainty"
        
        # Start with score-based confidence
        if avg_score >= HIGH_CONFIDENCE_THRESHOLD:
            confidence = "high"
            reason = f"High relevance score ({avg_score:.2f})"
        elif avg_score >= MEDIUM_CONFIDENCE_THRESHOLD:
            confidence = "medium"
            reason = f"Medium relevance score ({avg_score:.2f})"
        else:
            confidence = "low"
            reason = f"Low relevance score ({avg_score:.2f})"
        
        # Downgrade if no citations despite having context
        if num_citations == 0 and chunks_found > 0:
            if confidence == "high":
                confidence = "medium"
            elif confidence == "medium":
                confidence = "low"
            reason = "No specific code citations found"
        
        # Check for hedging words
        hedging_words = ["might", "probably", "possibly", "perhaps", "maybe"]
        if any(word in answer_lower for word in hedging_words):
            # Downgrade one level
            if confidence == "high":
                confidence = "medium"
                reason = "Answer contains hedging language"
            elif confidence == "medium":
                confidence = "low"
                reason = "Answer contains hedging language"
        
        # Upgrade if many high-quality citations
        if num_citations >= 3 and avg_score >= MEDIUM_CONFIDENCE_THRESHOLD:
            if confidence == "medium":
                confidence = "high"
                reason = f"Multiple relevant citations ({num_citations})"
        
        return confidence, reason
    
    def _format_answer_with_citations(
        self,
        answer: str,
        citations: list[Citation]
    ) -> str:
        """
        Format answer with citation block appended.
        
        Does NOT modify the LLM's answer text.
        """
        if not citations:
            return answer
        
        # Build citation block
        citation_lines = ["\n\n---\n📍 Sources:"]
        
        for citation in citations:
            # Format: • file.py:10-20 — function_name
            line_range = f"{citation.start_line}-{citation.end_line}"
            
            if citation.function_name:
                name = citation.function_name
            elif citation.class_name:
                name = citation.class_name
            else:
                name = "(file summary)"
            
            citation_lines.append(
                f"• {citation.file_path}:{line_range} — {name}"
            )
        
        return answer + "\n".join(citation_lines)
    
    def _generate_suggestions(self, question: str) -> list[str]:
        """Generate alternative question suggestions."""
        # Simple heuristic-based suggestions
        suggestions = [
            "What files are in this repository?",
            "What are the main classes or functions?"
        ]
        
        # Try to extract entities from question
        entities = re.findall(r'\b[A-Z][a-zA-Z0-9]*\b', question)
        if entities:
            suggestions[0] = f"Where is {entities[0]} defined?"
        
        return suggestions


# Test function
def test_response_formatter():
    """Test the response formatter."""
    print("Testing Response Formatter...")
    print("=" * 60)
    
    try:
        from rag import ProcessedQuery, RetrievedChunk, RetrievedContext, QueryType
        
        # Create mock data
        mock_chunk = RetrievedChunk(
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
        )
        
        mock_query = ProcessedQuery(
            original="How does authentication work?",
            cleaned="how does authentication work?",
            query_type=QueryType.HOW_DOES,
            expanded_queries=[],
            hyde_document=None,
            extracted_entities=[],
            keywords=["authentication"],
            is_multi_hop=False,
            is_graph_query=False
        )
        
        mock_context = RetrievedContext(
            query=mock_query,
            primary_chunks=[mock_chunk],
            expanded_chunks=[],
            total_chunks=1,
            total_tokens=150,
            context_text="Mock context",
            source_files=["auth/middleware.py"]
        )
        
        # Test formatting
        formatter = ResponseFormatter()
        
        raw_answer = (
            "Authentication is handled by the authenticate function in "
            "auth/middleware.py. It verifies user credentials by calling "
            "verify_password."
        )
        
        response = formatter.format(
            question="How does authentication work?",
            raw_answer=raw_answer,
            context=mock_context,
            query=mock_query,
            session_id="test123",
            turn_number=1,
            model_used="gemini",
            response_time=1.5
        )
        
        print("✓ Response formatter initialized")
        print()
        print(f"Confidence: {response.confidence}")
        print(f"Reason: {response.confidence_reason}")
        print(f"Citations: {len(response.citations)}")
        print()
        print("Answer preview:")
        print("-" * 60)
        print(response.answer[:300])
        print("...")
        print()
        
        print("✓ Response formatting test passed!")
        return True
    
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_response_formatter()
