# Phase 4: RAG Q&A Layer — Module Specifications

**Status**: ✅ Complete  
**Total Modules**: 8  
**Total Lines**: 3,100+

---

## Module Overview

| Module | File | Lines | Purpose |
|--------|------|-------|---------|
| **Dataclasses** | `rag/__init__.py` | 150+ | Core data structures |
| **LLM Client** | `rag/llm_client.py` | 400+ | Unified LLM abstraction |
| **Query Processor** | `rag/query_processor.py` | 450+ | Query analysis & enhancement |
| **Retriever** | `rag/retriever.py` | 500+ | Hybrid semantic + keyword search |
| **Context Builder** | `rag/context_builder.py` | 400+ | Optimal LLM context assembly |
| **Response Formatter** | `rag/response_formatter.py` | 400+ | Citation extraction & confidence |
| **Conversation Manager** | `rag/conversation.py` | 350+ | Multi-turn session management |
| **RAG Pipeline** | `rag/rag_pipeline.py` | 400+ | Full orchestration (main API) |

---

## 1. Dataclasses (`rag/__init__.py`)

### Purpose
Defines all data structures used throughout Phase 4.

### Key Classes

#### QueryType (Enum)
```python
class QueryType(Enum):
    WHAT_IS = "what_is"              # Describe entity
    HOW_DOES = "how_does"            # Explain mechanism
    WHERE_IS = "where_is"            # Locate code
    WHY_IS = "why_is"                # Explain reason
    WHAT_CALLS = "what_calls"        # Call relationships
    WHAT_IMPORTS = "what_imports"    # Dependencies
    WHAT_BREAKS = "what_breaks"      # Impact analysis
    COMPARE = "compare"              # Comparison
    EXPLAIN = "explain"              # Detailed walkthrough
    GENERAL = "general"              # Catch-all
```

#### ProcessedQuery
```python
@dataclass
class ProcessedQuery:
    original: str                     # User's exact question
    cleaned: str                      # Normalized question
    query_type: QueryType             # Classified type
    expanded_queries: list[str]       # 2-3 alternative phrasings
    hyde_document: Optional[str]      # Hypothetical answer
    extracted_entities: list[str]     # Function/class/file names
    keywords: list[str]               # BM25 keywords
    is_multi_hop: bool                # Needs multiple files?
    is_graph_query: bool              # About relationships?
```

#### RetrievedChunk
```python
@dataclass
class RetrievedChunk:
    chunk_id: str                     # UUID from ChromaDB
    content: str                      # Code snippet
    metadata: dict                    # Full metadata
    semantic_score: float             # 0-1 cosine similarity
    keyword_score: float              # 0-1 BM25 score
    combined_score: float             # Weighted combination
    retrieval_source: str             # "semantic", "keyword", etc.
    rank: int                         # 1-indexed rank
```

#### RetrievedContext
```python
@dataclass
class RetrievedContext:
    query: ProcessedQuery             # Original processed query
    primary_chunks: list[RetrievedChunk]  # Main results
    expanded_chunks: list[RetrievedChunk] # Graph expansion
    total_chunks: int                 # Count
    total_tokens: int                 # Token count
    context_text: str                 # Assembled text for LLM
    source_files: list[str]           # Unique files
```

#### Citation
```python
@dataclass
class Citation:
    file_path: str                    # e.g., "src/auth.py"
    start_line: int                   # Line number
    end_line: int                     # Line number
    chunk_id: str                     # UUID
    content_snippet: str              # 1-2 lines of code
    confidence: float                 # 0-1 confidence
```

#### RAGResponse
```python
@dataclass
class RAGResponse:
    question: str                     # User's question
    answer: str                       # LLM-generated answer
    citations: list[Citation]         # Grounded citations
    confidence: str                   # "high", "medium", "low"
    confidence_reason: str            # Explanation
    query_type: QueryType             # Classified type
    chunks_retrieved: int             # Total retrieved
    chunks_used_in_context: int       # Used in LLM context
    model_used: str                   # "gemini" or "ollama"
    response_time_seconds: float      # Latency
    session_id: str                   # Session UUID
    turn_number: int                  # Turn in session
```

#### ConversationTurn
```python
@dataclass
class ConversationTurn:
    turn_number: int                  # 1-indexed
    question: str                     # User question
    answer: str                       # LLM answer
    citations: list[Citation]         # Citations
    retrieved_chunk_ids: list[str]    # Chunks used
    timestamp: str                    # ISO 8601
    response_time_seconds: float      # Latency
```

#### ConversationSession
```python
@dataclass
class ConversationSession:
    session_id: str                   # UUID
    repo_owner: str                   # GitHub owner
    repo_name: str                    # GitHub repo
    created_at: str                   # ISO 8601
    last_active: str                  # ISO 8601
    total_questions: int              # Count
    turns: list[ConversationTurn]     # All turns
```

---

## 2. LLM Client (`rag/llm_client.py`)

### Purpose
Unified abstraction for Groq, Gemini, and Ollama LLM providers.

### Key Methods

#### `__init__(provider: str, api_key: Optional[str] = None)`
Initialize LLM client.
- **provider**: "groq", "gemini", or "ollama"
- **api_key**: Required for cloud providers (can also be read from environment via `GROQ_API_KEY` or `GEMINI_API_KEY`), ignored for Ollama
- **Raises**: ValueError if provider invalid or API key missing

#### `generate(system_prompt: str, user_message: str, max_tokens: int = 1000) -> str`
Generate LLM response.
- **system_prompt**: System instructions
- **user_message**: User query + context
- **max_tokens**: Max output length
- **Returns**: Generated text
- **Raises**: LLMError on failure

#### `_generate_groq(...) -> str`
Internal Groq implementation.
- High-speed cloud generation using Llama-3.3-70b-versatile.
- Direct HTTP REST adaptation with `requests` and standard library `urllib` fallbacks to avoid PEP 668 restrictions and SSL pip socket failures.
- Temperature: 0.1

#### `_generate_gemini(...) -> str`
Internal Gemini implementation.
- Rate limiting: 15 RPM (4s min interval)
- Retry logic: 3 attempts with 2s delay
- Temperature: 0.1 (deterministic)

#### `_generate_ollama(...) -> str`
Internal Ollama implementation.
- Model: Configurable (default: "mistral")
- Streaming: Disabled (full response)
- Temperature: 0.1

### Configuration

```python
# config.py
LLM_PROVIDER = "groq"             # "groq", "gemini", or "ollama"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "mistral"
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS = 1000
LLM_RETRY_ATTEMPTS = 3
LLM_RETRY_DELAY_SECONDS = 2.0
GEMINI_RATE_LIMIT_RPM = 15
```

### Error Handling

```python
class LLMError(Exception):
    """Base LLM error"""
    pass

class LLMRateLimitError(LLMError):
    """Rate limit exceeded"""
    pass

class LLMAuthError(LLMError):
    """Authentication failed"""
    pass

class LLMConnectionError(LLMError):
    """Connection failed"""
    pass
```

---

## 3. Query Processor (`rag/query_processor.py`)

### Purpose
Analyze and enhance user queries for better retrieval.

### Key Methods

#### `process(question: str, conversation_history: Optional[list[ConversationTurn]] = None) -> ProcessedQuery`
Main entry point.
- **question**: User's question
- **conversation_history**: Previous turns (for pronoun resolution)
- **Returns**: ProcessedQuery with all enhancements

#### `_classify_query_type(question: str) -> QueryType`
Classify into 10 query types.
- Uses keyword matching
- Falls back to GENERAL
- Deterministic

#### `_extract_entities(question: str) -> list[str]`
Extract function/class/file names.
- Regex patterns for CamelCase, snake_case
- Looks for common patterns (e.g., "User", "get_user")
- Returns list of entities

#### `_extract_keywords(question: str) -> list[str]`
Extract BM25 keywords.
- Tokenize by whitespace
- Remove stopwords (the, a, is, etc.)
- Lowercase
- Returns list of keywords

#### `_generate_query_expansions(question: str) -> list[str]`
Generate 2-3 alternative phrasings.
- Uses LLM to rephrase
- Captures different angles
- Returns list of expanded queries

#### `_generate_hyde_document(question: str) -> Optional[str]`
Generate hypothetical answer.
- Uses LLM to imagine answer
- Helps with semantic search
- Returns hypothetical document or None

#### `_detect_multi_hop(question: str, entities: list[str]) -> bool`
Detect if query needs multiple files.
- Keywords: "between", "across", "flow", "chain"
- Multiple entities
- Returns boolean

#### `_detect_graph_query(question: str) -> bool`
Detect if query is about relationships.
- Keywords: "calls", "imports", "uses", "depends"
- Query type: WHAT_CALLS, WHAT_IMPORTS
- Returns boolean

### Configuration

```python
# config.py
QUERY_EXPANSION_COUNT = 2
HYDE_ENABLED = True
ENTITY_EXTRACTION_ENABLED = True
KEYWORD_EXTRACTION_ENABLED = True
STOPWORDS = {"the", "a", "is", "are", "and", "or", ...}
```

---

## 4. Retriever (`rag/retriever.py`)

### Purpose
Hybrid semantic + keyword search with graph expansion.

### Key Methods

#### `retrieve(query: ProcessedQuery, top_k: int = 12) -> list[RetrievedChunk]`
Main retrieval method.
- Combines semantic, keyword, entity, HyDE searches
- Scores and reranks
- Returns top_k chunks

#### `_semantic_search(query_text: str, top_k: int) -> list[RetrievedChunk]`
Semantic search via ChromaDB.
- Embeds query using sentence-transformers
- Cosine similarity search
- Returns scored chunks

#### `_keyword_search(keywords: list[str], top_k: int) -> list[RetrievedChunk]`
BM25 keyword search.
- Uses rank_bm25 library
- Scores chunks by keyword overlap
- Returns scored chunks

#### `_entity_lookup(entities: list[str]) -> list[RetrievedChunk]`
Direct entity lookup.
- Queries chunk_index.json
- Fetches chunks by qualified name
- Returns high-confidence chunks

#### `_hyde_search(hyde_document: str, top_k: int) -> list[RetrievedChunk]`
HyDE (Hypothetical Document Embeddings).
- Embeds hypothetical answer
- Searches for similar chunks
- Returns scored chunks

#### `_combine_scores(results: dict[str, RetrievedChunk]) -> list[RetrievedChunk]`
Combine scores from multiple sources.
- Semantic: 65% weight
- Keyword: 35% weight
- Bonus for multi-source matches
- Returns reranked chunks

#### `retrieve_by_graph(primary_chunks: list[RetrievedChunk], max_expansion: int = 6) -> list[RetrievedChunk]`
Graph expansion for relationship queries.
- Extracts call graph neighbors
- Fetches neighbor chunks
- Limits to max_expansion
- Returns expanded chunks

### Configuration

```python
# config.py
TOP_K_SEMANTIC = 15
TOP_K_KEYWORD = 10
TOP_K_FINAL = 12
SEMANTIC_WEIGHT = 0.65
KEYWORD_WEIGHT = 0.35
MAX_EXPANSION_CHUNKS = 6
BM25_K1 = 1.5
BM25_B = 0.75
```

---

## 5. Context Builder (`rag/context_builder.py`)

### Purpose
Assemble optimal LLM context from retrieved chunks.

### Key Methods

#### `build(query: ProcessedQuery, retrieved_chunks: list[RetrievedChunk], max_tokens: int = 3000) -> RetrievedContext`
Main context building method.
- Prioritizes chunks
- Fills token budget
- Deduplicates
- Formats
- Returns RetrievedContext

#### `_calculate_token_budget(max_tokens: int, conversation_history: Optional[list[ConversationTurn]]) -> tuple[int, int]`
Calculate token allocation.
- History tokens: up to 800
- Context tokens: remaining
- Returns (history_budget, context_budget)

#### `_prioritize_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]`
Prioritize chunks by source.
- Priority 1: Entity lookup (0.95 score)
- Priority 2: Semantic (by score)
- Priority 3: Graph expansion (by score)
- Priority 4: Keyword-only (by score)
- Returns sorted chunks

#### `_greedy_selection(chunks: list[RetrievedChunk], token_budget: int) -> list[RetrievedChunk]`
Greedy token budget filling.
- Add chunks in priority order
- Stop when budget exhausted
- Always keep ≥1 chunk
- Returns selected chunks

#### `_deduplicate_subchunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]`
Remove duplicate sub-chunks.
- Keeps highest-scoring version
- Removes overlapping sub-chunks
- Returns deduplicated chunks

#### `_group_by_file(chunks: list[RetrievedChunk]) -> dict[str, list[RetrievedChunk]]`
Group chunks by file.
- Sorts by line number within file
- Returns dict of file → chunks

#### `_format_context(chunks: list[RetrievedChunk]) -> str`
Format chunks for LLM.
- Adds file headers
- Adds line numbers
- Adds chunk separators
- Returns formatted text

### Configuration

```python
# config.py
MAX_CONTEXT_TOKENS = 3000
HISTORY_TOKEN_BUDGET = 800
MIN_CONTEXT_CHUNKS = 1
MAX_CONTEXT_CHUNKS = 20
```

---

## 6. Response Formatter (`rag/response_formatter.py`)

### Purpose
Extract citations and assess confidence.

### Key Methods

#### `format(answer: str, context: RetrievedContext) -> tuple[list[Citation], str]`
Main formatting method.
- Extracts citations from answer
- Assesses confidence
- Returns (citations, confidence_reason)

#### `_extract_citations(answer: str, context: RetrievedContext) -> list[Citation]`
Extract citations from answer.
- Looks for file:line patterns
- Matches against context chunks
- Returns list of citations

#### `_assess_confidence(answer: str, citations: list[Citation], context: RetrievedContext) -> str`
Assess confidence level.
- Score-based: avg_score ≥ 0.75 → high
- Rule-based: uncertainty phrases → low
- Hedging words → downgrade
- No citations → downgrade
- Returns "high", "medium", or "low"

#### `_get_confidence_reason(confidence: str, citations: list[Citation], answer: str) -> str`
Generate confidence explanation.
- Explains why confidence is at this level
- References citations or lack thereof
- Returns explanation string

### Configuration

```python
# config.py
CONFIDENCE_HIGH_THRESHOLD = 0.75
CONFIDENCE_MEDIUM_THRESHOLD = 0.50
UNCERTAINTY_PHRASES = ["I don't know", "not sure", "unclear", ...]
HEDGING_WORDS = ["might", "probably", "possibly", ...]
```

---

## 7. Conversation Manager (`rag/conversation.py`)

### Purpose
Multi-turn session management with disk persistence.

### Key Methods

#### `create_session(repo_owner: str, repo_name: str) -> ConversationSession`
Create new session.
- Generates UUID
- Initializes metadata
- Saves to disk
- Returns session

#### `load_session(session_id: str, repo_owner: str, repo_name: str) -> ConversationSession`
Load session from disk.
- Reads JSON file
- Deserializes turns
- Returns session
- Raises FileNotFoundError if not found

#### `add_turn(session: ConversationSession, question: str, answer: str, citations: list[Citation], retrieved_chunk_ids: list[str], response_time: float) -> ConversationSession`
Add turn to session.
- Creates ConversationTurn
- Appends to session
- Saves to disk
- Returns updated session

#### `get_last_n_turns(session: ConversationSession, n: int = 3) -> list[ConversationTurn]`
Get last n turns.
- Returns most recent turns
- Used for context in next query
- Returns list of turns

#### `list_sessions(repo_owner: str, repo_name: str) -> list[str]`
List all session IDs.
- Scans conversations directory
- Returns list of session IDs

#### `delete_session(session_id: str, repo_owner: str, repo_name: str) -> bool`
Delete session.
- Removes JSON file
- Returns success boolean

### Storage Format

```
data/repos/{owner}__{repo}/conversations/
└── {session_id}.json
    {
      "session_id": "uuid",
      "repo_owner": "owner",
      "repo_name": "repo",
      "created_at": "2026-05-31T...",
      "last_active": "2026-05-31T...",
      "total_questions": 3,
      "turns": [
        {
          "turn_number": 1,
          "question": "...",
          "answer": "...",
          "citations": [...],
          "retrieved_chunk_ids": [...],
          "timestamp": "2026-05-31T...",
          "response_time_seconds": 3.5
        }
      ]
    }
```

---

## 8. RAG Pipeline (`rag/rag_pipeline.py`)

### Purpose
Main orchestrator and public API for Phase 4.

### Key Methods

#### `__init__(repo_owner: str, repo_name: str, llm_provider: str = "gemini", api_key: Optional[str] = None)`
Initialize pipeline.
- Validates Phase 1-3 outputs
- Initializes all components
- Loads ChromaDB collection
- Raises error if prerequisites missing

#### `ask(question: str, session_id: Optional[str] = None) -> RAGResponse`
Main public API.
- Processes question
- Retrieves context
- Generates answer
- Formats response
- Saves to session
- Returns RAGResponse

#### `_validate_prerequisites() -> bool`
Validate Phase 1-3 outputs.
- Checks manifest.json (Phase 1)
- Checks parse_manifest.json (Phase 2)
- Checks chunk_manifest.json (Phase 3)
- Raises error if missing

#### `_load_chromadb_collection() -> chromadb.Collection`
Load ChromaDB collection.
- Connects to persistent client
- Gets collection by name
- Raises error if not found

#### `_build_system_prompt(query_type: QueryType) -> str`
Build system prompt.
- Tailored to query type
- Includes instructions
- Includes context format
- Returns prompt string

#### `_resolve_session(session_id: Optional[str]) -> ConversationSession`
Resolve or create session.
- Loads existing session if ID provided
- Creates new session if not
- Returns session

### Configuration

```python
# config.py
RAG_PIPELINE_TIMEOUT_SECONDS = 30
RAG_PIPELINE_MAX_RETRIES = 3
```

---

## Integration Points

### Phase 3 Integration
- Reads ChromaDB collection
- Reads chunk_index.json
- Reads chunks.jsonl
- Reads chunk_manifest.json

### Phase 2 Integration
- Reads call_graph.json (for graph expansion)
- Reads dependency_map.json (for entity lookup)
- Reads entry_points.json (for prioritization)

### Phase 1 Integration
- Reads manifest.json (for validation)

---

## Error Handling

### Validation Errors
- Missing Phase 1-3 outputs
- Invalid repository
- ChromaDB connection failure

### Query Processing Errors
- Invalid query type
- Entity extraction failure
- Keyword extraction failure

### Retrieval Errors
- ChromaDB query failure
- BM25 index failure
- Graph expansion failure

### LLM Errors
- API key invalid
- Rate limit exceeded
- Connection timeout
- Generation failure

### Session Errors
- Session not found
- Session corrupted
- Disk write failure

---

**Status**: Phase 4 Modules Complete ✅

