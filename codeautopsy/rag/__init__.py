"""
rag/__init__.py — Phase 4 RAG Q&A Layer Dataclasses

Shared dataclasses for the RAG pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class QueryType(Enum):
    """Classification of user query intent."""
    WHAT_IS = "what_is"           # "What is the UserService?"
    HOW_DOES = "how_does"         # "How does auth work?"
    WHERE_IS = "where_is"         # "Where is rate limiting handled?"
    WHY_IS = "why_is"             # "Why is caching implemented here?"
    WHAT_CALLS = "what_calls"     # "What calls the payment function?"
    WHAT_IMPORTS = "what_imports" # "What does models.py import?"
    WHAT_BREAKS = "what_breaks"   # "What would break if I remove X?"
    COMPARE = "compare"           # "Compare UserService and AdminService"
    EXPLAIN = "explain"           # "Explain the auth flow end to end"
    GENERAL = "general"           # catch-all for other questions


@dataclass
class ProcessedQuery:
    """Enhanced query after processing."""
    original: str                 # exactly what user typed
    cleaned: str                  # lowercased, stripped
    query_type: QueryType         # classified query type
    expanded_queries: list[str]   # 2-3 query variants for multi-query retrieval
    hyde_document: Optional[str]  # hypothetical answer for HyDE retrieval
    extracted_entities: list[str] # file names, function names, class names mentioned
    keywords: list[str]           # key technical terms for BM25
    is_multi_hop: bool            # needs info from multiple files to answer
    is_graph_query: bool          # about relationships (what calls, what imports)


@dataclass
class RetrievedChunk:
    """A single chunk retrieved from the vector store."""
    chunk_id: str
    content: str
    metadata: dict                # full metadata from ChromaDB
    semantic_score: float         # cosine similarity 0-1
    keyword_score: float          # BM25 score normalized 0-1
    combined_score: float         # weighted combination
    retrieval_source: str         # "semantic", "keyword", "graph_expansion", "hyde"
    rank: int                     # 1-indexed rank in final results


@dataclass
class RetrievedContext:
    """Assembled context ready for LLM."""
    query: ProcessedQuery
    primary_chunks: list[RetrievedChunk]    # directly retrieved
    expanded_chunks: list[RetrievedChunk]   # from graph expansion
    total_chunks: int
    total_tokens: int
    context_text: str            # assembled text to send to LLM
    source_files: list[str]      # unique files represented in context


@dataclass
class Citation:
    """A grounded citation to source code."""
    file_path: str
    function_name: Optional[str]
    class_name: Optional[str]
    start_line: int
    end_line: int
    chunk_id: str
    relevance: str               # brief note on why this was cited


@dataclass
class RAGResponse:
    """Complete response from the RAG pipeline."""
    question: str
    answer: str                  # LLM-generated answer
    citations: list[Citation]    # grounded citations
    confidence: str              # "high", "medium", "low"
    confidence_reason: str       # why this confidence level
    query_type: QueryType
    chunks_retrieved: int
    chunks_used_in_context: int
    model_used: str
    response_time_seconds: float
    session_id: str
    turn_number: int             # which turn in conversation


@dataclass
class ConversationTurn:
    """A single turn in a conversation."""
    turn_number: int
    question: str
    answer: str
    citations: list[Citation]
    retrieved_chunk_ids: list[str]
    timestamp: str


@dataclass
class ConversationSession:
    """A multi-turn conversation session."""
    session_id: str
    repo_owner: str
    repo_name: str
    created_at: str
    last_active: str
    turns: list[ConversationTurn] = field(default_factory=list)
    total_questions: int = 0
