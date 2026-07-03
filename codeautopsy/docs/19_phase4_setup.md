# Phase 4: RAG Q&A Layer — Setup & Configuration

**Status**: ✅ Complete  
**Prerequisites**: Phases 1, 2, 3 complete

---

## Quick Start

### 1. Install Dependencies

```bash
cd codeautopsy
pip install -r requirements.txt
```

**Phase 4 Dependencies:**
- `ollama` - Local LLM client (optional)
- `google-generativeai` - Gemini API client (optional)
- `rank-bm25` - BM25 keyword search
- `nltk` - Natural language processing
- `colorama` - Terminal colors

---

## 2. Choose Your LLM Provider

Phase 4 supports **3 LLM providers**. Choose one:

### Option 1: Groq (Recommended - Fast & Free)

**Pros:**
- ✅ **Free tier**: 30 requests/minute (best free tier)
- ✅ **Very fast**: 100-300 tokens/second
- ✅ **No setup**: Cloud-based, works immediately
- ✅ **Reliable**: No 403 errors

**Setup:**

1. Get free API key from: https://console.groq.com/keys
2. Add to `.env`:

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

**Available Models:**
- `llama-3.3-70b-versatile` (recommended - best quality)
- `llama-3.1-70b-versatile`
- `mixtral-8x7b-32768`
- `gemma-7b-it`

---

### Option 2: Gemini (Cloud, Free)

**Pros:**
- ✅ Free tier available
- ✅ No local setup required
- ✅ Good quality responses

**Cons:**
- ⚠️ Rate limit: 15 requests/minute (slower than Groq)
- ⚠️ May return 403 errors on some API keys

**Setup:**

1. Get free API key from: https://aistudio.google.com/app/apikey
2. Add to `.env`:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
```

---

### Option 3: Ollama (Local, Private)

**Pros:**
- ✅ Completely local (no API keys)
- ✅ Unlimited requests
- ✅ Private (data never leaves your machine)

**Cons:**
- ⚠️ Requires local installation
- ⚠️ Slower than cloud options
- ⚠️ Requires ~8GB RAM

**Setup:**

1. Install Ollama:
   - **macOS/Linux**: `curl -fsSL https://ollama.ai/install.sh | sh`
   - **Windows**: Download from https://ollama.ai

2. Pull a model:
```bash
ollama pull mistral
```

3. Start Ollama server:
```bash
ollama serve
```

4. Configure `.env`:
```bash
LLM_PROVIDER=ollama
OLLAMA_MODEL=mistral
```

**Available Models:**
- `mistral` (recommended - 7B params, fast)
- `codellama` (optimized for code)
- `llama3` (8B params, high quality)

---

## 3. Configure Environment

Create or edit `.env` file in `codeautopsy/` directory:

```bash
# Choose ONE provider (groq recommended)
LLM_PROVIDER=groq

# Groq Configuration (if using Groq)
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Gemini Configuration (if using Gemini)
# GEMINI_API_KEY=your_gemini_api_key_here

# Ollama Configuration (if using Ollama)
# OLLAMA_MODEL=mistral

# Optional: GitHub token for Phase 1
# GITHUB_TOKEN=your_github_token_here
```

---

## 4. Verify Setup

Test your LLM configuration:

```bash
python3 -m rag.llm_client
```

**Expected output:**
```
Testing LLM Client...
============================================================
✓ LLM initialized: groq / llama-3.3-70b-versatile

Testing short generation...
Response: Hello from CodeAutopsy!

Testing full generation with system prompt...
Response: A function in Python is a reusable block of code...

✓ All tests passed!
```

---

## 5. Process a Repository

Run the full pipeline (Phases 1-4):

```bash
python main.py run https://github.com/pallets/itsdangerous
```

**What happens:**
1. **Phase 1**: Fetch repository from GitHub
2. **Phase 2**: Parse code with tree-sitter
3. **Phase 3**: Chunk and embed code
4. **Phase 4**: Ready for Q&A

**Output:**
```
╔══════════════════════════════════════════════════════════╗
║  CodeAutopsy — Pipeline Complete                         ║
╠══════════════════════════════════════════════════════════╣
║  Repo            : pallets/itsdangerous                  ║
║  Files fetched   : 15                                    ║
║  Functions parsed: 101                                   ║
║  Chunks embedded : 201                                   ║
║  Ready for Q&A   : ✓                                     ║
╚══════════════════════════════════════════════════════════╝
```

---

## 6. Start Interactive Q&A

```bash
python main.py chat https://github.com/pallets/itsdangerous
```

**Interactive session:**
```
🤖 CodeAutopsy — Interactive Q&A
📦 Repository: pallets/itsdangerous
🔄 Session: abc123 (new)

Type 'help' for commands, 'quit' to exit

> What does the Signer class do?

The Signer class is a core component of itsdangerous that provides
cryptographic signing and verification of data. It uses HMAC-based
algorithms to create signatures that can be used to verify the
authenticity and integrity of data.

📍 Citations:
  • src/itsdangerous/signer.py:120-150
  • src/itsdangerous/signer.py:200-230

✅ Confidence: high
⏱️  Response time: 3.2s

> How does it sign data?

The Signer class uses HMAC (Hash-based Message Authentication Code)
with a secret key to generate signatures...

📍 Citations:
  • src/itsdangerous/signer.py:250-280

✅ Confidence: high
⏱️  Response time: 2.8s

> quit

👋 Session saved: abc123
```

---

## 7. Special Commands

While in interactive chat:

| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `stats` | Show session statistics |
| `history` | Show conversation history |
| `new` | Start new session |
| `sessions` | List all sessions |
| `quit` | Exit (saves session) |

---

## Configuration Options

### RAG Parameters

Edit `config.py` to tune retrieval:

```python
# Retrieval
TOP_K_SEMANTIC = 15        # Semantic search results
TOP_K_KEYWORD = 10         # BM25 keyword results
TOP_K_FINAL = 12           # Final reranked results

# Context
MAX_CONTEXT_TOKENS = 3000  # Max tokens in LLM context
MAX_ANSWER_TOKENS = 1000   # Max tokens in answer

# Hybrid search weights
SEMANTIC_WEIGHT = 0.65     # Semantic similarity weight
KEYWORD_WEIGHT = 0.35      # BM25 keyword weight

# Conversation
MAX_CONVERSATION_TURNS = 20
MAX_HISTORY_TOKENS = 800
```

### LLM Parameters

```python
# Gemini
GEMINI_MODEL = "gemini-flash-latest"
GEMINI_RPM_LIMIT = 15

# Groq
GROQ_MODEL = "llama-3.3-70b-versatile"

# Ollama
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "mistral"
```

---

## Troubleshooting

### Issue: "GROQ_API_KEY not set"

**Solution:**
1. Get API key from https://console.groq.com/keys
2. Add to `.env`: `GROQ_API_KEY=your_key_here`
3. Restart terminal

---

### Issue: "Ollama not running"

**Solution:**
```bash
# Start Ollama server
ollama serve

# In another terminal, verify it's running
ollama list
```

---

### Issue: "Gemini 403 Access Denied"

**Solution:**
1. Verify API key is correct
2. Check quota at https://aistudio.google.com
3. **Recommended**: Switch to Groq instead:
   ```bash
   LLM_PROVIDER=groq
   GROQ_API_KEY=your_groq_key
   ```

---

### Issue: "No chunks retrieved"

**Cause:** Phase 3 not run or ChromaDB empty

**Solution:**
```bash
# Run full pipeline
python main.py run https://github.com/owner/repo

# Or run Phase 3 only
python main.py embed https://github.com/owner/repo
```

---

### Issue: "Rate limit exceeded"

**Gemini:** Wait 60 seconds or switch to Groq (30 RPM vs 15 RPM)

**Groq:** Wait 60 seconds (free tier: 30 RPM)

**Ollama:** No rate limits (local)

---

## Performance Tips

### 1. Use Groq for Speed
Groq is 2-3x faster than Gemini and has better rate limits.

### 2. Reduce Context Size
Lower `MAX_CONTEXT_TOKENS` for faster responses:
```python
MAX_CONTEXT_TOKENS = 2000  # Default: 3000
```

### 3. Use Ollama for Unlimited Queries
No rate limits, but requires local setup.

### 4. Adjust Retrieval
Fewer chunks = faster responses:
```python
TOP_K_FINAL = 8  # Default: 12
```

---

## Advanced Usage

### Programmatic API

```python
from rag.rag_pipeline import RAGPipeline

# Initialize
pipeline = RAGPipeline(
    repo_owner="pallets",
    repo_name="itsdangerous"
)

# Ask a question
response = pipeline.ask("What does the Signer class do?")

print(response.answer)
print(f"Confidence: {response.confidence}")
print(f"Citations: {len(response.citations)}")
```

### Custom System Prompts

Edit `prompts/system_prompts.py` to customize LLM behavior.

### Session Management

```python
from rag.conversation import ConversationManager

manager = ConversationManager()

# Load existing session
session = manager.load_session(
    session_id="abc123",
    repo_owner="pallets",
    repo_name="itsdangerous"
)

# Get history
last_3_turns = manager.get_last_n_turns(session, n=3)
```

---

## Testing

### Unit Tests

```bash
pytest tests/test_phase4.py -v
```

### Integration Test

```bash
# Process a small repo
python main.py run https://github.com/pallets/itsdangerous

# Test Q&A
python main.py chat https://github.com/pallets/itsdangerous
```

---

## Next Steps

1. ✅ **Phase 4 Complete** - RAG Q&A working
2. 🔄 **Phase 5** - LangGraph agent for call graph traversal
3. 🔄 **Phase 6** - Interactive web visualization

---

## Provider Comparison

| Feature | Groq | Gemini | Ollama |
|---------|------|--------|--------|
| **Setup** | API key only | API key only | Local install |
| **Speed** | ⚡⚡⚡ Very fast | ⚡⚡ Fast | ⚡ Moderate |
| **Rate Limit** | 30 RPM | 15 RPM | Unlimited |
| **Quality** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Privacy** | Cloud | Cloud | Local |
| **Cost** | Free | Free | Free |
| **Reliability** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

**Recommendation:** Use **Groq** for best balance of speed, reliability, and ease of setup.

---

## Resources

- **Groq Console**: https://console.groq.com
- **Gemini API**: https://aistudio.google.com
- **Ollama**: https://ollama.ai
- **Phase 4 Docs**: `15_phase4_index.md`, `16_phase4_architecture.md`

---

**Status**: Phase 4 Setup Guide Complete ✅

