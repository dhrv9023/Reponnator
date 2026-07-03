# Phase 4: RAG Q&A Layer — Architecture

**Status**: ✅ Complete  
**Components**: 8 major modules  
**Total Lines**: 3,100+

---

## System Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     User Question                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                    Query Processor
                    (10 query types, entity extraction,
                     query expansion, HyDE)
                         │
                    ┌────┴────┐
                    │         │
              Retriever   Graph Expander
              (Hybrid:    (Call graph
               Semantic    neighbors)
               + BM25)
                    │         │
                    └────┬────┘
                         │
                  Context Builder
                  (Token budget, prioritization,
                   deduplication, formatting)
                         │
                    LLM Client
                    (Gemini / Ollama)
                         │
              Response Formatter
              (Citation extraction,
               confidence assessment)
                         │
              Conversation Manager
              (Session persistence)
                         │
                    RAGResponse
```

---

## Component Interactions

### 1. Query Processing Pipeline

```
Raw Question
    ↓
Clean & Normalize
    ↓
Resolve Pronouns (from history)
    ↓
Classify Query Type (10 types)
    ↓
Extract Entities (CamelCase, snake_case, files)
    ↓
Extract Keywords (for BM25, remove stopwords)
    ↓
Generate Query Expansions (LLM)
    ↓
Generate HyDE Document (LLM)
    ↓
Detect Multi-hop (needs multiple files?)
    ↓
Detect Graph Query (about relationships?)
    ↓
ProcessedQuery
```

### 2. Retrieval Pipeline

```
ProcessedQuery
    ↓
Semantic Search (original query)
    ↓
Semantic Search (expanded queries)
    ↓
HyDE Retrieval (if applicable)
    ↓
Keyword Search (BM25)
    ↓
Entity Lookup (direct qualified name)
    ↓
Score Combination & Reranking
    ↓
Apply Query-Type Filters
    ↓
Graph Expansion (if needed)
    ↓
list[RetrievedChunk]
```

### 3. Context Assembly Pipeline

```
Retrieved Chunks
    ↓
Calculate Token Budget
    ↓
Prioritize Chunks
    (Entity > Semantic > Graph > Keyword)
    ↓
Greedy Selection (fill budget)
    ↓
Deduplicate Sub-chunks
    ↓
Group by File
    ↓
Sort by Line Number
    ↓
Format with Headers
    ↓
RetrievedContext
```

### 4. Response Generation Pipeline

```
System Prompt + User Message + Context
    ↓
LLM Generation
    ↓
Raw Answer
    ↓
Extract Citations
    ↓
Assess Confidence
    ↓
Format with Citation Block
    ↓
RAGResponse
```

---

## Data Structures

### ProcessedQuery
```python
@dataclass
class ProcessedQuery:
    original: str                 # User's exact question
    cleaned: str                  # Normalized question
    query_type: QueryType         # Classified type (10 types)
    expanded_queries: list[str]   # 2-3 alternative phrasings
    hyde_document: Optional[str]  # Hypothetical answer
    extracted_entities: list[str] # Function/class/file names
    keywords: list[str]           # BM25 keywords
    is_multi_hop: bool            # Needs multiple files?
    is_graph_query: bool          # About relationships?
```

### RetrievedChunk
```python
@dataclass
class RetrievedChunk:
    chunk_id: str
    content: str
    metadata: dict                # Full metadata from ChromaDB
    semantic_score: float         # 0-1 cosine similarity
    keyword_score: float          # 0-1 BM25 score
    combined_score: float         # Weighted combination
    retrieval_source: str         # "semantic", "keyword", etc.
    rank: int                     # 1-indexed rank
```

### RetrievedContext
```python
@dataclass
class RetrievedContext:
    query: ProcessedQuery
    primary_chunks: list[RetrievedChunk]
    expanded_chunks: list[RetrievedChunk]
    total_chunks: int
    total_tokens: int
    context_text: str             # Assembled text for LLM
    source_files: list[str]       # Unique files
```

### RAGResponse
```python
@dataclass
class RAGResponse:
    question: str
    answer: str                   # LLM-generated answer
    citations: list[Citation]     # Grounded citations
    confidence: str               # "high", "medium", "low"
    confidence_reason: str
    query_type: QueryType
    chunks_retrieved: int
    chunks_used_in_context: int
    model_used: str
    response_time_seconds: float
    session_id: str
    turn_number: int
```

---

## Hybrid Search Strategy

### Semantic Search (65% weight)
- Embed query using sentence-transformers
- Search ChromaDB for similar embeddings
- Returns TOP_K_SEMANTIC chunks
- Captures conceptual similarity

### Keyword Search (35% weight)
- Tokenize query into keywords
- Score chunks using BM25
- Returns TOP_K_KEYWORD chunks
- Captures exact term matches

### Score Combination
```python
combined_score = (
    SEMANTIC_WEIGHT * semantic_score +
    KEYWORD_WEIGHT * keyword_score
)

# Bonus for chunks found by both methods
if semantic_score > 0 and keyword_score > 0:
    combined_score += 0.1

# Entity lookup gets highest priority
if retrieval_source == "entity_lookup":
    combined_score = 0.95
```

---

## Query Type Classification

| Type | Keywords | Example |
|------|----------|---------|
| **WHAT_IS** | "what is", "describe", "tell me about" | "What is UserService?" |
| **HOW_DOES** | "how does", "how to", "explain how" | "How does auth work?" |
| **WHERE_IS** | "where is", "find", "locate" | "Where is rate limiting?" |
| **WHY_IS** | "why is", "reason for", "purpose" | "Why is caching used?" |
| **WHAT_CALLS** | "what calls", "who calls", "uses" | "What calls payment()?" |
| **WHAT_IMPORTS** | "what imports", "dependencies" | "What does models.py import?" |
| **WHAT_BREAKS** | "what breaks", "impact of removing" | "What breaks if I remove X?" |
| **COMPARE** | "compare", "difference", "vs" | "Compare User vs Admin" |
| **EXPLAIN** | "explain", "walk through" | "Explain the auth flow" |
| **GENERAL** | Other questions | Catch-all |

---

## Token Budget Management

```
Total Budget: 3000 tokens

├─ Conversation History: up to 800 tokens
│  └─ Last 3 turns (truncated to 300 chars each)
│
└─ Code Context: remaining budget
   ├─ Priority 1: Entity lookup chunks (0.95 score)
   ├─ Priority 2: Primary semantic chunks (by score)
   ├─ Priority 3: Graph expansion chunks (by score)
   └─ Priority 4: Keyword-only chunks (by score)

Greedy Selection:
- Add chunks in priority order
- Stop when budget exhausted
- Always keep ≥1 chunk
```

---

## Confidence Assessment

### Rule-Based Checks
1. **No chunks found** → Low
2. **Uncertainty phrases** ("I don't know", "not sure") → Low
3. **Hedging words** ("might", "probably") → Downgrade one level
4. **No citations** despite context → Downgrade one level

### Score-Based Levels
```python
if avg_score >= 0.75:
    confidence = "high"
elif avg_score >= 0.50:
    confidence = "medium"
else:
    confidence = "low"
```

### Final Assessment
```python
# Start with score-based level
# Apply rule-based downgrades
# Upgrade if multiple high-quality citations
```

---

## Multi-turn Conversation Flow

```
Session Created
    ↓
Turn 1: Question → Answer → Save
    ↓
Turn 2: Question (with history context)
    ├─ Resolve pronouns from Turn 1
    ├─ Include Turn 1 in LLM context
    └─ Answer → Save
    ↓
Turn 3: Question (with history context)
    ├─ Resolve pronouns from Turn 2
    ├─ Include Turns 1-2 in LLM context
    └─ Answer → Save
    ↓
... (max 20 turns)
    ↓
Session Saved to Disk
```

---

## Graph Expansion Strategy

### When to Expand
- Query type is WHAT_CALLS or WHAT_IMPORTS
- Query is multi-hop (needs multiple files)
- Question contains relationship keywords

### Expansion Process
```
Primary Chunks (most relevant)
    ↓
For each primary chunk (up to 5):
    ├─ Parse calls (functions this calls)
    ├─ Parse called_by (functions that call this)
    └─ Look up neighbors in chunk_index
    ↓
Fetch neighbor chunks from ChromaDB
    ↓
Set neighbor score = primary_score × 0.7
    ↓
Limit to MAX_EXPANSION_CHUNKS (6 total)
    ↓
Expanded Chunks
```

---

## LLM Integration

### Ollama (Local)
```python
client = ollama.Client(host="http://localhost:11434")
response = client.chat(
    model="mistral",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ],
    options={"temperature": 0.1, "num_predict": 1000}
)
```

### Gemini (Cloud)
```python
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-2.5-flash")
response = model.generate_content(
    full_prompt,
    generation_config=GenerationConfig(
        max_output_tokens=1000,
        temperature=0.1
    )
)
```

### Rate Limiting (Gemini)
```python
# Gemini free tier: 15 RPM
min_interval = 60.0 / 15  # 4 seconds
if time_since_last_request < min_interval:
    sleep(min_interval - time_since_last_request)
```

---

## Session Persistence

### Storage Format
```
data/repos/{owner}__{repo}/conversations/
└── {session_id}.json
    ├── session_id
    ├── repo_owner
    ├── repo_name
    ├── created_at
    ├── last_active
    ├── total_questions
    └── turns[]
        ├── turn_number
        ├── question
        ├── answer
        ├── citations[]
        ├── retrieved_chunk_ids[]
        └── timestamp
```

### Lifecycle
1. Create session → Save to disk
2. Add turn → Update session → Save to disk
3. Load session → Deserialize from JSON
4. Trim old turns → Keep last 20 → Save

---

## Error Handling

### Missing Prerequisites
- Check Phase 1 output (manifest.json)
- Check Phase 2 output (parse_manifest.json)
- Check Phase 3 output (chunk_manifest.json)
- Clear error messages with fix instructions

### No Chunks Retrieved
- Return early without calling LLM
- Provide helpful suggestions
- Save API quota

### LLM Failures
- Retry up to 3 times with 2s delay
- Handle rate limiting (Gemini)
- Clear error messages

### Session Not Found
- Load from disk if exists
- Create new session if not
- Warn user

---

## Performance Characteristics

### Latency Breakdown
```
Query Processing:     ~0.5s
├─ Clean & normalize: ~0.05s
├─ Classify type:     ~0.05s
├─ Extract entities:  ~0.05s
├─ Extract keywords:  ~0.05s
├─ Query expansion:   ~0.15s (LLM)
└─ HyDE generation:   ~0.15s (LLM)

Retrieval:            ~0.2s
├─ Semantic search:   ~0.1s
├─ Keyword search:    ~0.05s
└─ Reranking:         ~0.05s

Context Building:     ~0.1s
├─ Prioritization:    ~0.02s
├─ Selection:         ~0.05s
└─ Formatting:        ~0.03s

LLM Generation:       ~2-5s (depends on answer length)

Response Formatting:  ~0.1s
├─ Citation extract:  ~0.05s
└─ Confidence assess: ~0.05s

Total:                ~3-6s per question
```

### Memory Usage
```
BM25 Index:           ~50MB (5000 chunks)
ChromaDB:             Lazy loading (~10MB active)
Context:              ~10KB per query
Session:              ~1KB per turn
Total:                <100MB typical
```

---

## Design Principles

1. **Grounded in Code** - Every claim traceable to source
2. **Transparent** - Clear confidence levels and reasoning
3. **Fault-Tolerant** - Graceful degradation on errors
4. **Efficient** - Token budget management, lazy loading
5. **Extensible** - Pluggable LLM providers, modular design
6. **User-Friendly** - Interactive CLI, session persistence

---

**Status**: Phase 4 Architecture Complete ✅
