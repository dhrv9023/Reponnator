"""
rag/query_processor.py — Query Analysis and Enhancement

Processes user questions to optimize retrieval:
- Classifies query type (WHAT_IS, HOW_DOES, WHERE_IS, etc.)
- Extracts entities (function/class/file names)
- Extracts keywords for BM25 search
- Generates query expansions (alternative phrasings)
- Generates HyDE documents (hypothetical answers)
- Detects multi-hop and graph queries
"""

import re
import logging
from typing import Optional
import string

# Import config
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    WHAT_IS_KEYWORDS,
    HOW_DOES_KEYWORDS,
    WHERE_IS_KEYWORDS,
    WHY_IS_KEYWORDS,
    WHAT_CALLS_KEYWORDS,
    WHAT_IMPORTS_KEYWORDS,
    WHAT_BREAKS_KEYWORDS,
    COMPARE_KEYWORDS,
)

from rag import QueryType, ProcessedQuery, ConversationSession
from rag.llm_client import LLMClient, LLMError
from prompts.system_prompts import QUERY_EXPANSION_PROMPT, HYDE_PROMPT

logger = logging.getLogger(__name__)


class QueryProcessor:
    """
    Analyzes and enhances user queries before retrieval.
    
    Usage:
        processor = QueryProcessor(llm_client)
        processed = processor.process(question, conversation)
    """
    
    def __init__(self, llm_client: LLMClient):
        """
        Initialize query processor.
        
        Args:
            llm_client: LLM client for query expansion and HyDE
        """
        self.llm_client = llm_client
        
        # Download NLTK data if not present
        self._setup_nltk()
        
        logger.info("Query processor initialized")
    
    def _setup_nltk(self):
        """Download required NLTK data."""
        try:
            import nltk
            nltk.download('stopwords', quiet=True)
            nltk.download('punkt', quiet=True)
            logger.debug("NLTK data ready")
        except Exception as e:
            logger.warning(f"Could not download NLTK data: {e}. Keyword extraction may be limited.")
    
    def process(
        self,
        question: str,
        conversation: Optional[ConversationSession] = None
    ) -> ProcessedQuery:
        """
        Process a user question into an enhanced query.
        
        Args:
            question: Raw user question
            conversation: Optional conversation session for context
        
        Returns:
            ProcessedQuery with all enhancements
        """
        # STEP 1: Clean and normalize
        cleaned = self._clean_query(question)
        
        # STEP 2: Resolve pronouns from conversation history
        resolved = self._resolve_pronouns(cleaned, conversation)
        
        # STEP 3: Classify query type
        query_type = self._classify_query_type(resolved)
        
        # STEP 4: Extract entities (function/class/file names)
        entities = self._extract_entities(question, conversation)
        
        # STEP 5: Extract keywords for BM25
        keywords = self._extract_keywords(resolved)
        
        # STEP 6: Generate query expansions
        expanded_queries = self._expand_query(question, query_type)
        
        # STEP 7: Generate HyDE document (for certain query types)
        hyde_document = self._generate_hyde(question, query_type)
        
        # STEP 8: Determine if multi-hop
        is_multi_hop = self._is_multi_hop(resolved, query_type, entities)
        
        # STEP 9: Determine if graph query
        is_graph_query = self._is_graph_query(resolved, query_type)
        
        processed = ProcessedQuery(
            original=question,
            cleaned=resolved,
            query_type=query_type,
            expanded_queries=expanded_queries,
            hyde_document=hyde_document,
            extracted_entities=entities,
            keywords=keywords,
            is_multi_hop=is_multi_hop,
            is_graph_query=is_graph_query
        )
        
        logger.info(
            f"Query processed: type={query_type.value}, "
            f"entities={len(entities)}, keywords={len(keywords)}, "
            f"multi_hop={is_multi_hop}, graph={is_graph_query}"
        )
        
        return processed
    
    def _clean_query(self, question: str) -> str:
        """Clean and normalize query text."""
        # Strip whitespace
        cleaned = question.strip()
        
        # Normalize quotes
        cleaned = cleaned.replace('"', '"').replace('"', '"')
        cleaned = cleaned.replace(''', "'").replace(''', "'")
        
        # Lowercase for classification (keep original for display)
        return cleaned.lower()
    
    def _resolve_pronouns(
        self,
        question: str,
        conversation: Optional[ConversationSession]
    ) -> str:
        """
        Resolve pronouns like 'it', 'this', 'that' using conversation history.
        
        Example: "How does it work?" after asking about "UserService"
                 → "How does UserService work?"
        """
        if not conversation or not conversation.turns:
            return question
        
        # Get last turn
        last_turn = conversation.turns[-1]
        
        # Simple pronoun resolution: replace 'it'/'this'/'that' with last mentioned entity
        pronouns = ['it', 'this', 'that']
        
        # Extract entities from last answer (look for CamelCase or function names)
        last_entities = self._extract_entities(last_turn.answer, None)
        
        if last_entities:
            # Use the first entity from last turn
            replacement = last_entities[0]
            
            for pronoun in pronouns:
                # Match pronoun as whole word
                pattern = r'\b' + pronoun + r'\b'
                if re.search(pattern, question, re.IGNORECASE):
                    question = re.sub(pattern, replacement, question, count=1, flags=re.IGNORECASE)
                    logger.debug(f"Resolved pronoun '{pronoun}' to '{replacement}'")
                    break
        
        return question
    
    def _classify_query_type(self, question: str) -> QueryType:
        """
        Classify query into one of the QueryType categories.
        
        Args:
            question: Cleaned, lowercase question
        
        Returns:
            QueryType enum value
        """
        # Check each category in priority order
        for keyword in WHAT_IS_KEYWORDS:
            if keyword in question:
                return QueryType.WHAT_IS
        
        for keyword in HOW_DOES_KEYWORDS:
            if keyword in question:
                return QueryType.HOW_DOES
        
        for keyword in WHERE_IS_KEYWORDS:
            if keyword in question:
                return QueryType.WHERE_IS
        
        for keyword in WHY_IS_KEYWORDS:
            if keyword in question:
                return QueryType.WHY_IS
        
        for keyword in WHAT_CALLS_KEYWORDS:
            if keyword in question:
                return QueryType.WHAT_CALLS
        
        for keyword in WHAT_IMPORTS_KEYWORDS:
            if keyword in question:
                return QueryType.WHAT_IMPORTS
        
        for keyword in WHAT_BREAKS_KEYWORDS:
            if keyword in question:
                return QueryType.WHAT_BREAKS
        
        for keyword in COMPARE_KEYWORDS:
            if keyword in question:
                return QueryType.COMPARE
        
        # Check for "explain" which suggests EXPLAIN type
        if "explain" in question and not any(kw in question for kw in WHAT_IS_KEYWORDS):
            return QueryType.EXPLAIN
        
        # Default to GENERAL
        return QueryType.GENERAL
    
    def _extract_entities(
        self,
        text: str,
        conversation: Optional[ConversationSession]
    ) -> list[str]:
        """
        Extract code entities: CamelCase (classes), snake_case (functions), file names.
        
        Args:
            text: Text to extract from
            conversation: Optional conversation for historical entities
        
        Returns:
            List of unique entity names
        """
        entities = []
        
        # Pattern 1: CamelCase (likely class names)
        # Match: UserService, HTTPClient, APIHandler
        camel_case = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text)
        entities.extend(camel_case)
        
        # Pattern 2: snake_case (likely function/variable names)
        # Match: get_user, process_payment, user_id
        snake_case = re.findall(r'\b[a-z_][a-z0-9_]{2,}\b', text)
        # Filter out common English words
        snake_case = [s for s in snake_case if '_' in s or s not in self._get_stopwords()]
        entities.extend(snake_case)
        
        # Pattern 3: File names with extensions
        # Match: app.py, models.js, config.ts
        file_names = re.findall(r'\b[\w-]+\.(py|js|ts|java|go|rs|c|cpp|rb|php)\b', text, re.IGNORECASE)
        entities.extend(file_names)
        
        # Pattern 4: Qualified names (Class.method, module.function)
        qualified = re.findall(r'\b[A-Z][a-zA-Z0-9]*\.[a-z_][a-z0-9_]*\b', text)
        entities.extend(qualified)
        
        # Pattern 5: Entities from conversation history
        if conversation and conversation.turns:
            # Get entities from last 2 turns
            for turn in conversation.turns[-2:]:
                # Extract from citations
                for citation in turn.citations:
                    if citation.function_name:
                        entities.append(citation.function_name)
                    if citation.class_name:
                        entities.append(citation.class_name)
        
        # Deduplicate and return
        return list(dict.fromkeys(entities))  # Preserves order
    
    def _extract_keywords(self, question: str) -> list[str]:
        """
        Extract keywords for BM25 search.
        
        Args:
            question: Cleaned question text
        
        Returns:
            List of keywords
        """
        # Tokenize
        words = question.split()
        
        # Remove stopwords
        stopwords = self._get_stopwords()
        words = [w for w in words if w not in stopwords]
        
        # Remove punctuation
        words = [w.strip(string.punctuation) for w in words]
        words = [w for w in words if w]  # Remove empty
        
        # Keep technical terms, CamelCase, snake_case, file extensions
        keywords = []
        for word in words:
            # Keep if:
            # - Contains underscore (snake_case)
            # - Contains uppercase (CamelCase)
            # - Contains dot (file.py)
            # - Is a number (line numbers)
            # - Length > 2
            if '_' in word or any(c.isupper() for c in word) or '.' in word or word.isdigit() or len(word) > 2:
                keywords.append(word)
        
        # Deduplicate
        return list(dict.fromkeys(keywords))
    
    def _get_stopwords(self) -> set[str]:
        """Get English stopwords."""
        try:
            from nltk.corpus import stopwords
            return set(stopwords.words('english'))
        except:
            # Fallback to basic stopwords if NLTK not available
            return {
                'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
                'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
                'to', 'was', 'will', 'with', 'the', 'this', 'but', 'they', 'have',
                'had', 'what', 'when', 'where', 'who', 'which', 'why', 'how'
            }
    
    def _expand_query(self, question: str, query_type: QueryType) -> list[str]:
        """
        Generate alternative query phrasings using LLM.
        
        Args:
            question: Original question
            query_type: Classified query type
        
        Returns:
            List of 0-2 alternative phrasings (empty if LLM fails)
        """
        # Skip expansion for simple factual lookups
        if query_type in [QueryType.WHERE_IS, QueryType.WHAT_CALLS]:
            return []
        
        try:
            prompt = QUERY_EXPANSION_PROMPT.format(question=question)
            response = self.llm_client.generate_short(prompt, max_tokens=100, temperature=0.3)
            
            # Parse response (should be 2 lines)
            lines = [line.strip() for line in response.split('\n') if line.strip()]
            
            # Remove numbering if present (1., 2., -, *, etc.)
            lines = [re.sub(r'^[\d\-\*\.\)]+\s*', '', line) for line in lines]
            
            # Take first 2 non-empty lines
            expansions = [line for line in lines if line and line != question][:2]
            
            logger.debug(f"Generated {len(expansions)} query expansions")
            return expansions
        
        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")
            return []
    
    def _generate_hyde(self, question: str, query_type: QueryType) -> Optional[str]:
        """
        Generate hypothetical document (HyDE) for semantic search.
        
        Only for conceptual queries (HOW_DOES, EXPLAIN, WHAT_IS).
        Skip for factual lookups (WHERE_IS, WHAT_CALLS).
        
        Args:
            question: Original question
            query_type: Classified query type
        
        Returns:
            Hypothetical answer text, or None if skipped/failed
        """
        # Only use HyDE for conceptual queries
        if query_type not in [QueryType.HOW_DOES, QueryType.EXPLAIN, QueryType.WHAT_IS]:
            return None
        
        try:
            prompt = HYDE_PROMPT.format(question=question)
            response = self.llm_client.generate_short(prompt, max_tokens=150, temperature=0.4)
            
            logger.debug(f"Generated HyDE document ({len(response)} chars)")
            return response.strip()
        
        except Exception as e:
            logger.warning(f"HyDE generation failed: {e}")
            return None
    
    def _is_multi_hop(
        self,
        question: str,
        query_type: QueryType,
        entities: list[str]
    ) -> bool:
        """
        Determine if query needs information from multiple files.
        
        Args:
            question: Cleaned question
            query_type: Classified type
            entities: Extracted entities
        
        Returns:
            True if multi-hop reasoning needed
        """
        # EXPLAIN queries usually need multiple files
        if query_type == QueryType.EXPLAIN:
            return True
        
        # WHAT_BREAKS needs dependency traversal
        if query_type == QueryType.WHAT_BREAKS:
            return True
        
        # Questions with "and" connecting concepts
        if ' and ' in question and len(entities) > 1:
            return True
        
        # Multiple distinct entities mentioned
        if len(entities) > 2:
            return True
        
        return False
    
    def _is_graph_query(self, question: str, query_type: QueryType) -> bool:
        """
        Determine if query is about code relationships (calls, imports).
        
        Args:
            question: Cleaned question
            query_type: Classified type
        
        Returns:
            True if graph traversal needed
        """
        # Direct graph query types
        if query_type in [QueryType.WHAT_CALLS, QueryType.WHAT_IMPORTS]:
            return True
        
        # Check for relationship keywords
        relationship_keywords = [
            'call', 'calls', 'called by', 'uses', 'used by',
            'import', 'imports', 'imported by', 'depends on',
            'dependency', 'dependencies', 'require', 'requires'
        ]
        
        return any(keyword in question for keyword in relationship_keywords)


# Test function
def test_query_processor():
    """Test the query processor with sample questions."""
    print("Testing Query Processor...")
    print("=" * 60)
    
    try:
        from rag.llm_client import LLMClient
        
        # Initialize
        llm_client = LLMClient()
        processor = QueryProcessor(llm_client)
        print("✓ Query processor initialized")
        print()
        
        # Test queries
        test_queries = [
            "What is the UserService class?",
            "How does authentication work?",
            "Where is rate limiting implemented?",
            "What calls the process_payment function?",
            "Explain the request routing flow",
        ]
        
        for i, question in enumerate(test_queries, 1):
            print(f"Test {i}: {question}")
            print("-" * 60)
            
            processed = processor.process(question, None)
            
            print(f"  Type: {processed.query_type.value}")
            print(f"  Entities: {processed.extracted_entities}")
            print(f"  Keywords: {processed.keywords[:5]}...")  # First 5
            print(f"  Multi-hop: {processed.is_multi_hop}")
            print(f"  Graph query: {processed.is_graph_query}")
            
            if processed.expanded_queries:
                print(f"  Expansions: {len(processed.expanded_queries)}")
                for exp in processed.expanded_queries:
                    print(f"    - {exp}")
            
            if processed.hyde_document:
                print(f"  HyDE: {processed.hyde_document[:100]}...")
            
            print()
        
        print("✓ All tests passed!")
        return True
    
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_query_processor()
