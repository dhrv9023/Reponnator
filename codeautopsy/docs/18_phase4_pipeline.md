# Phase 4: RAG Q&A Layer — Pipeline & Execution

**Status**: ✅ Complete  
**Total Lines**: 3,100+  
**Components**: 8 modules

---

## 1. End-to-End Pipeline Flow

### High-Level Execution

```
[User Starts Interactive Chat]
       │
       ▼
1. Initialize RAGPipeline
   ├─ Validate Phase 1-3 outputs
   ├─ Load ChromaDB collection
   ├─ Initialize all components
   └─ Create/load session
       │
       ▼
2. User enters question
       │
       ▼
3. QueryProcessor.process(question)
   ├─ Clean & normalize
   ├─ Resolve pronouns (from history)
   ├─ Classify query type (10 types)
   ├─ Extract entities
   ├─ Extract keywords
   ├─ Generate query expansions (LLM)
   ├─ Generate HyDE document (LLM)
   ├─ Detect multi-hop
   └─ Detect graph query
       │
       ▼
4. Retriever.retrieve(processed_query)
   ├─ Semantic search (original)
   ├─ Semantic search (expansions)
   ├─ HyDE search
   ├─ Keyword search (BM25)
   ├─ Entity lookup
   ├─ Score combination & reranking
   └─ Apply query-type filters
       │
       ▼
5. [If graph query] Retriever.retrieve_by_graph()
   ├─ Extract call graph neighbors
   ├─ Fetch neighbor chunks
   └─ Limit to MAX_EXPANSION_CHUNKS
       │
       ▼
6. ContextBuilder.build(retrieved_chunks)
   ├─ Calculate token budget
   ├─ Prioritize chunks
   ├─ Greedy selection (fill budget)
   ├─ Deduplicate sub-chunks
   ├─ Group by file
   └─ Format with headers
       │
       ▼
7. LLMClient.generate(system_prompt, context)
   ├─ Build full prompt
   ├─ Call Gemini or Ollama
   ├─ Handle rate limiting
   ├─ Retry on failure
   └─ Return generated answer
       │
       ▼
8. ResponseFormatter.format(answer, context)
   ├─ Extract citations
   ├─ Assess confidence
   └─ Generate confidence reason
       │
       ▼
9. ConversationManager.add_turn(session, ...)
   ├─ Create ConversationTurn
   ├─ Append to session
   └─ Save to disk
       │
       ▼
10. Return RAGResponse
       │
       ▼
11. Display answer with citations & confidence
       │
       ▼
12. [Loop] User enters next question
```

---

## 2. Detailed Component Flows

### 2.1 Query Processing Flow

```
Raw Question: "What does the Signer class do?"
       │
       ▼
Clean & Normalize
├─ Lowercase: "what does the signer class do?"
├─ Remove extra spaces
└─ Trim punctuation
       │
       ▼
Resolve Pronouns (from history)
├─ Check if "it", "this", "that" in question
├─ Look up last entity from previous turn
└─ Replace if found
       │
       ▼
Classify Query Type
├─ Check keywords: "what", "does" → WHAT_IS
├─ Match against 10 types
└─ Return QueryType.WHAT_IS
       │
       ▼
Extract Entities
├─ Regex: CamelCase → "Signer"
├─ Regex: snake_case → (none)
├─ Regex: file paths → (none)
└─ Return ["Signer"]
       │
       ▼
Extract Keywords
├─ Tokenize: ["what", "does", "the", "signer", "class", "do"]
├─ Remove stopwords: ["signer", "class"]
└─ Return ["signer", "class"]
       │
       ▼
Generate Query Expansions (LLM)
├─ Prompt: "Rephrase: What does the Signer class do?"
├─ LLM returns: [
│    "Explain the purpose of Signer",
│    "What is the Signer class used for?"
│  ]
└─ Return expanded queries
       │
       ▼
Generate HyDE Document (LLM)
├─ Prompt: "Write a hypothetical answer to: What does the Signer class do?"
├─ LLM returns: "The Signer class is responsible for..."
└─ Return hypothetical document
       │
       ▼
Detect Multi-hop
├─ Check keywords: "between", "across", "flow" → No
├─ Check entity count: 1 entity → No
└─ Return is_multi_hop = False
       │
       ▼
Detect Graph Query
├─ Check keywords: "calls", "imports", "uses" → No
├─ Check query type: WHAT_IS → No
└─ Return is_graph_query = False
       │
       ▼
ProcessedQuery
{
  original: "What does the Signer class do?",
  cleaned: "what does the signer class do",
  query_type: QueryType.WHAT_IS,
  expanded_queries: ["Explain the purpose of Signer", ...],
  hyde_document: "The Signer class is responsible for...",
  extracted_entities: ["Signer"],
  keywords: ["signer", "class"],
  is_multi_hop: False,
  is_graph_query: False
}
```

### 2.2 Retrieval Flow

```
ProcessedQuery
       │
       ▼
Semantic Search (original query)
├─ Embed: "What does the Signer class do?"
├─ ChromaDB cosine search: TOP_K_SEMANTIC=15
├─ Results: [
│    (0.78, chunk_id_1, "class Signer: ..."),
│    (0.72, chunk_id_2, "def __init__(self): ..."),
│    ...
│  ]
└─ Return 15 chunks with semantic_score
       │
       ▼
Semantic Search (expanded queries)
├─ Embed: "Explain the purpose of Signer"
├─ ChromaDB cosine search: TOP_K_SEMANTIC=15
├─ Results: [
│    (0.75, chunk_id_3, "Signer is used for..."),
│    ...
│  ]
└─ Return 15 chunks with semantic_score
       │
       ▼
HyDE Search
├─ Embed: "The Signer class is responsible for..."
├─ ChromaDB cosine search: TOP_K_SEMANTIC=15
├─ Results: [
│    (0.71, chunk_id_4, "..."),
│    ...
│  ]
└─ Return 15 chunks with semantic_score
       │
       ▼
Keyword Search (BM25)
├─ Keywords: ["signer", "class"]
├─ BM25 score all chunks
├─ Top TOP_K_KEYWORD=10 chunks
├─ Results: [
│    (0.85, chunk_id_1, "class Signer: ..."),
│    (0.62, chunk_id_5, "..."),
│    ...
│  ]
└─ Return 10 chunks with keyword_score
       │
       ▼
Entity Lookup
├─ Entities: ["Signer"]
├─ Query chunk_index.json: "Signer" → chunk_id_1
├─ Fetch chunk_id_1 from ChromaDB
├─ Results: [
│    (0.95, chunk_id_1, "class Signer: ...")
│  ]
└─ Return 1 chunk with entity_score=0.95
       │
       ▼
Combine Scores
├─ Merge all results by chunk_id
├─ For each chunk:
│    combined_score = (
│      0.65 * semantic_score +
│      0.35 * keyword_score
│    )
│    if semantic_score > 0 and keyword_score > 0:
│      combined_score += 0.1
│    if retrieval_source == "entity_lookup":
│      combined_score = 0.95
├─ Sort by combined_score descending
└─ Return top TOP_K_FINAL=12 chunks
       │
       ▼
Apply Query-Type Filters
├─ Query type: WHAT_IS
├─ Filter: Prefer class_summary, file_summary chunks
├─ Reorder if needed
└─ Return filtered chunks
       │
       ▼
[If graph query] Graph Expansion
├─ For each primary chunk (up to 5):
│    ├─ Parse calls: ["sign", "unsign"]
│    ├─ Parse called_by: ["verify_signature"]
│    └─ Look up in chunk_index
├─ Fetch neighbor chunks
├─ Set neighbor_score = primary_score × 0.7
├─ Limit to MAX_EXPANSION_CHUNKS=6
└─ Return expanded chunks
       │
       ▼
list[RetrievedChunk]
[
  RetrievedChunk(
    chunk_id="...",
    content="class Signer: ...",
    semantic_score=0.78,
    keyword_score=0.85,
    combined_score=0.80,
    retrieval_source="entity_lookup",
    rank=1
  ),
  ...
]
```

### 2.3 Context Building Flow

```
Retrieved Chunks (12 chunks, ~5000 tokens total)
       │
       ▼
Calculate Token Budget
├─ Max tokens: 3000
├─ Conversation history: 3 turns (last 300 chars each)
├─ History tokens: ~200 tokens
├─ Context budget: 3000 - 200 = 2800 tokens
└─ Return (200, 2800)
       │
       ▼
Prioritize Chunks
├─ Priority 1: Entity lookup (0.95 score)
│    └─ chunk_id_1 (0.95)
├─ Priority 2: Semantic (by score)
│    └─ chunk_id_2 (0.78), chunk_id_3 (0.75), ...
├─ Priority 3: Graph expansion (by score)
│    └─ (none in this case)
└─ Priority 4: Keyword-only (by score)
       │
       ▼
Greedy Selection (fill budget)
├─ Add chunk_id_1: 150 tokens → total: 150
├─ Add chunk_id_2: 180 tokens → total: 330
├─ Add chunk_id_3: 160 tokens → total: 490
├─ Add chunk_id_4: 200 tokens → total: 690
├─ Add chunk_id_5: 190 tokens → total: 880
├─ Add chunk_id_6: 210 tokens → total: 1090
├─ Add chunk_id_7: 180 tokens → total: 1270
├─ Add chunk_id_8: 200 tokens → total: 1470
├─ Add chunk_id_9: 190 tokens → total: 1660
├─ Add chunk_id_10: 210 tokens → total: 1870
├─ Add chunk_id_11: 200 tokens → total: 2070
├─ Add chunk_id_12: 180 tokens → total: 2250
├─ Budget exhausted (2250 < 2800 but next chunk would exceed)
└─ Return 12 selected chunks
       │
       ▼
Deduplicate Sub-chunks
├─ Check for overlapping sub-chunks
├─ Keep highest-scoring version
└─ Return deduplicated chunks
       │
       ▼
Group by File
├─ src/itsdangerous/signer.py: [chunk_1, chunk_2, chunk_5]
├─ src/itsdangerous/encoding.py: [chunk_3, chunk_7]
├─ src/itsdangerous/serializer.py: [chunk_4, chunk_8, chunk_11]
└─ Sort by line number within each file
       │
       ▼
Format Context
├─ Add header: "=== src/itsdangerous/signer.py ==="
├─ Add chunk_1 with line numbers: "120-150"
├─ Add chunk_2 with line numbers: "151-180"
├─ Add separator: "---"
├─ Add header: "=== src/itsdangerous/encoding.py ==="
├─ Add chunk_3 with line numbers: "45-75"
├─ ...
└─ Return formatted context string
       │
       ▼
RetrievedContext
{
  query: ProcessedQuery(...),
  primary_chunks: [chunk_1, chunk_2, ...],
  expanded_chunks: [],
  total_chunks: 12,
  total_tokens: 2250,
  context_text: "=== src/itsdangerous/signer.py ===\n...",
  source_files: ["src/itsdangerous/signer.py", ...]
}
```

### 2.4 LLM Generation Flow

```
System Prompt + User Message + Context
       │
       ▼
Build Full Prompt
├─ System: "You are a code expert. Answer questions about the codebase..."
├─ Context: "=== src/itsdangerous/signer.py ===\nclass Signer: ..."
├─ User: "What does the Signer class do?"
└─ Full prompt: ~2500 tokens
       │
       ▼
[If Gemini]
├─ Check rate limit: 15 RPM (4s min interval)
├─ If needed, sleep
├─ Call genai.GenerativeModel("gemini-2.5-flash")
├─ Set temperature=0.1, max_tokens=1000
├─ Handle 403 "Access Denied" → Fallback to Ollama
├─ Retry up to 3 times on failure
└─ Return generated text
       │
       ▼
[If Ollama]
├─ Check connection: http://localhost:11434
├─ Call ollama.Client.chat()
├─ Set model="mistral", temperature=0.1
├─ Streaming disabled (full response)
├─ Retry up to 3 times on failure
└─ Return generated text
       │
       ▼
Generated Answer
"The Signer class is a core component of itsdangerous that provides
cryptographic signing and verification of data. It uses HMAC-based
algorithms to create signatures that can be used to verify the
authenticity and integrity of data. The class supports multiple
hashing algorithms and provides methods for signing and unsigning
data. It's commonly used in web frameworks to sign session cookies
and other sensitive data."
```

### 2.5 Response Formatting Flow

```
Generated Answer + Context
       │
       ▼
Extract Citations
├─ Look for patterns: "file:line", "src/...:123"
├─ Match against context chunks
├─ For each match:
│    ├─ Extract file_path
│    ├─ Extract line numbers
│    ├─ Find corresponding chunk
│    ├─ Extract content snippet
│    └─ Create Citation object
├─ Results: [
│    Citation(
│      file_path="src/itsdangerous/signer.py",
│      start_line=120,
│      end_line=150,
│      chunk_id="...",
│      content_snippet="class Signer: ...",
│      confidence=0.95
│    ),
│    ...
│  ]
└─ Return citations
       │
       ▼
Assess Confidence
├─ Score-based:
│    avg_score = mean([0.95, 0.78, 0.75, ...])
│    if avg_score >= 0.75: confidence = "high"
│    elif avg_score >= 0.50: confidence = "medium"
│    else: confidence = "low"
├─ Rule-based checks:
│    if "I don't know" in answer: confidence = "low"
│    if "might" in answer: downgrade one level
│    if len(citations) == 0: downgrade one level
├─ Final: confidence = "high"
└─ Return confidence level
       │
       ▼
Generate Confidence Reason
├─ "High confidence: Answer is well-supported by 3 citations
│   from the codebase with average score 0.83"
└─ Return reason string
       │
       ▼
RAGResponse
{
  question: "What does the Signer class do?",
  answer: "The Signer class is a core component...",
  citations: [Citation(...), ...],
  confidence: "high",
  confidence_reason: "High confidence: Answer is well-supported...",
  query_type: QueryType.WHAT_IS,
  chunks_retrieved: 12,
  chunks_used_in_context: 12,
  model_used: "gemini",
  response_time_seconds: 3.5,
  session_id: "uuid",
  turn_number: 1
}
```

---

## 3. Multi-Turn Conversation Flow

```
Session Created: session_id="abc123"
       │
       ▼
Turn 1: "What does the Signer class do?"
├─ Process query
├─ Retrieve context
├─ Generate answer
├─ Format response
├─ Save turn to session
└─ Display answer
       │
       ▼
Turn 2: "How does it sign data?"
├─ Resolve pronoun: "it" → "Signer" (from Turn 1)
├─ Updated question: "How does Signer sign data?"
├─ Include Turn 1 in LLM context (last 300 chars)
├─ Process query
├─ Retrieve context
├─ Generate answer
├─ Format response
├─ Save turn to session
└─ Display answer
       │
       ▼
Turn 3: "What about verification?"
├─ Resolve pronoun: "What" → "Signer" (from Turn 2)
├─ Updated question: "How does Signer verify?"
├─ Include Turns 1-2 in LLM context
├─ Process query
├─ Retrieve context
├─ Generate answer
├─ Format response
├─ Save turn to session
└─ Display answer
       │
       ▼
... (max 20 turns)
       │
       ▼
Session Saved to Disk
data/repos/pallets__itsdangerous/conversations/abc123.json
```

---

## 4. Error Handling Flows

### 4.1 Missing Prerequisites

```
RAGPipeline.__init__()
       │
       ▼
Check Phase 1 output
├─ Look for: data/repos/{owner}__{repo}/manifest.json
├─ If missing: raise error "Phase 1 not run"
└─ If found: continue
       │
       ▼
Check Phase 2 output
├─ Look for: data/repos/{owner}__{repo}/parsed/parse_manifest.json
├─ If missing: raise error "Phase 2 not run"
└─ If found: continue
       │
       ▼
Check Phase 3 output
├─ Look for: data/repos/{owner}__{repo}/chunks/chunk_manifest.json
├─ If missing: raise error "Phase 3 not run"
└─ If found: continue
       │
       ▼
Load ChromaDB collection
├─ Try to get collection: "codeautopsy__{owner}__{repo}"
├─ If not found: raise error "ChromaDB collection not found"
└─ If found: continue
       │
       ▼
Pipeline initialized successfully
```

### 4.2 No Chunks Retrieved

```
Retriever.retrieve()
       │
       ▼
Semantic search: 0 results
Keyword search: 0 results
Entity lookup: 0 results
HyDE search: 0 results
       │
       ▼
Total retrieved: 0 chunks
       │
       ▼
Return early without calling LLM
       │
       ▼
RAGResponse
{
  answer: "I couldn't find relevant code to answer this question.",
  citations: [],
  confidence: "low",
  chunks_retrieved: 0,
  ...
}
```

### 4.3 LLM Rate Limit (Gemini)

```
LLMClient.generate()
       │
       ▼
Check rate limit: 15 RPM (4s min interval)
├─ Time since last request: 1s
├─ Min interval: 4s
├─ Need to wait: 3s
└─ Sleep(3s)
       │
       ▼
Call Gemini API
├─ Response: 200 OK
└─ Return answer
```

### 4.4 LLM Failure (Gemini 403)

```
LLMClient.generate()
       │
       ▼
Call Gemini API
├─ Response: 403 "Access Denied"
├─ Retry attempt 1: Sleep 2s, retry
├─ Response: 403 "Access Denied"
├─ Retry attempt 2: Sleep 2s, retry
├─ Response: 403 "Access Denied"
├─ Retry attempt 3: Failed
└─ Raise LLMAuthError
       │
       ▼
Catch error in RAGPipeline
├─ Log error
├─ Try fallback: Ollama
├─ If Ollama available: use it
├─ If Ollama unavailable: raise error
└─ Return error response
```

---

## 5. Performance Characteristics

### Latency Breakdown (Typical)

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
├─ Gemini: ~2-3s
└─ Ollama: ~3-5s

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

### Throughput

```
Gemini (15 RPM):      1 question per 4 seconds
Ollama (unlimited):   1 question per 3-5 seconds
```

---

## 6. CLI Integration

### Interactive Chat Command

```bash
$ python main.py chat https://github.com/pallets/itsdangerous

🤖 CodeAutopsy — Interactive Q&A
📦 Repository: pallets/itsdangerous
🔄 Session: abc123 (new)

Type 'help' for commands, 'quit' to exit

> What does the Signer class do?

The Signer class is a core component of itsdangerous that provides
cryptographic signing and verification of data...

📍 Citations:
  • src/itsdangerous/signer.py:120-150
  • src/itsdangerous/signer.py:151-180

✅ Confidence: high

> How does it sign data?

The Signer class uses HMAC-based algorithms to create signatures...

📍 Citations:
  • src/itsdangerous/signer.py:200-230

✅ Confidence: high

> stats

📊 Session Statistics:
  • Questions: 2
  • Avg Response Time: 3.2s
  • Avg Confidence: high
  • Total Chunks Retrieved: 24

> quit

👋 Session saved: abc123
```

---

## 7. Output Examples

### Example 1: WHAT_IS Query

**Question**: "What is URLSafeSerializer?"

**Answer**: "URLSafeSerializer is a subclass of Serializer that uses URL-safe encoding for serialized data. It encodes the serialized data using base64 URL-safe encoding, making it safe to use in URLs and cookies. The class inherits from Serializer and overrides the default encoding to use URLSafeTimedSerializer for timed serialization."

**Citations**:
- src/itsdangerous/url_safe.py:45-75
- src/itsdangerous/serializer.py:200-230

**Confidence**: high

---

### Example 2: HOW_DOES Query

**Question**: "How does timestamp verification work?"

**Answer**: "Timestamp verification works by comparing the current time with the timestamp embedded in the signed data. When unsigning a timed token, the TimestampSigner extracts the timestamp, converts it to seconds, and compares it with the current time. If the difference exceeds the max_age parameter, the signature is considered invalid and an exception is raised."

**Citations**:
- src/itsdangerous/timed.py:120-150
- src/itsdangerous/timed.py:151-180

**Confidence**: high

---

### Example 3: WHAT_CALLS Query

**Question**: "What calls the sign method?"

**Answer**: "The sign method is called by several functions including the dumps method in Serializer, which serializes and signs data. It's also called by the sign_bytes method in the Signer class. Additionally, the TimestampSigner.sign method calls the parent Signer.sign method to add the timestamp signature."

**Citations**:
- src/itsdangerous/signer.py:300-330
- src/itsdangerous/serializer.py:150-180

**Confidence**: medium

---

**Status**: Phase 4 Pipeline Complete ✅

