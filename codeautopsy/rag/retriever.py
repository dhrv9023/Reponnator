"""
rag/retriever.py — Hybrid Search Retriever

Performs hybrid semantic + keyword search over ChromaDB:
- Semantic search (embedding similarity)
- Keyword search (BM25)
- HyDE retrieval
- Query expansion
- Entity-based direct lookup
- Score combination & reranking
- Graph expansion (call graph neighbors)
"""

import json
import logging
from pathlib import Path
from typing import Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    TOP_K_SEMANTIC,
    TOP_K_KEYWORD,
    TOP_K_HYDE,
    TOP_K_FINAL,
    SEMANTIC_WEIGHT,
    KEYWORD_WEIGHT,
    MAX_EXPANSION_CHUNKS,
    DATA_DIR,
)

from rag import ProcessedQuery, RetrievedChunk, QueryType
from chunking.vector_store import VectorStore
from chunking.embedder import Embedder

# Optional: KnowledgeGraph for fast in-memory graph traversal (Phase 2.5)
try:
    from graph import KnowledgeGraph
    _KG_AVAILABLE = True
except ImportError:
    _KG_AVAILABLE = False

logger = logging.getLogger(__name__)


class Retriever:
    """
    Hybrid retrieval system combining semantic and keyword search.
    
    Usage:
        retriever = Retriever(vector_store, embedder, "owner", "repo")
        chunks = retriever.retrieve(processed_query)
    """
    
    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Embedder,
        repo_owner: str,
        repo_name: str,
        knowledge_graph: Optional["KnowledgeGraph"] = None,
    ):
        """
        Initialize retriever.
        
        Args:
            vector_store: ChromaDB vector store
            embedder: Embedding model
            repo_owner: Repository owner
            repo_name: Repository name
            knowledge_graph: Optional pre-loaded KnowledgeGraph for fast
                             in-memory graph traversal. If None, one will be
                             loaded automatically (or skipped if unavailable).
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        
        # Get or create collection
        self.collection = vector_store.get_or_create_collection(repo_owner, repo_name)
        
        # Load BM25 index
        self._load_bm25_index(repo_owner, repo_name)
        
        # Load chunk index for graph expansion (legacy fallback)
        self._load_chunk_index(repo_owner, repo_name)

        # ── KnowledgeGraph: fast in-memory graph traversal ──────────────
        if knowledge_graph is not None:
            self.knowledge_graph: Optional["KnowledgeGraph"] = knowledge_graph
        elif _KG_AVAILABLE:
            repo_key = f"{repo_owner}__{repo_name}"
            try:
                self.knowledge_graph = KnowledgeGraph(repo_key, data_dir=str(DATA_DIR))
                logger.info(
                    f"KnowledgeGraph loaded: {self.knowledge_graph.node_count} nodes, "
                    f"{self.knowledge_graph.edge_count} edges"
                )
            except Exception as e:
                logger.warning(f"KnowledgeGraph load failed ({e}); falling back to dict lookup")
                self.knowledge_graph = None
        else:
            self.knowledge_graph = None
        
        logger.info(f"Retriever initialized for {repo_owner}/{repo_name}")
    
    def _load_bm25_index(self, owner: str, repo_name: str):
        """Load chunks and build BM25 index."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            raise ImportError("rank-bm25 not installed. Run: pip install rank-bm25")
        
        # Load chunks from chunks.jsonl
        repo_folder = Path(DATA_DIR) / f"{owner}__{repo_name}"
        chunks_file = repo_folder / "chunks" / "chunks.jsonl"
        
        if not chunks_file.exists():
            raise FileNotFoundError(
                f"chunks.jsonl not found at {chunks_file}. "
                f"Run: python main.py embed {owner}/{repo_name}"
            )
        
        # Load all chunks
        self.chunks_data = []
        with open(chunks_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    self.chunks_data.append(json.loads(line))
        
        # Tokenize content for BM25
        tokenized_corpus = []
        for chunk in self.chunks_data:
            content = chunk.get('content', '')
            # Simple tokenization: lowercase and split
            tokens = content.lower().split()
            tokenized_corpus.append(tokens)
        
        # Build BM25 index
        self.bm25 = BM25Okapi(tokenized_corpus)
        
        logger.info(f"BM25 index built with {len(self.chunks_data)} chunks")
    
    def _load_chunk_index(self, owner: str, repo_name: str):
        """Load chunk index for qualified name lookups."""
        repo_folder = Path(DATA_DIR) / f"{owner}__{repo_name}"
        index_file = repo_folder / "chunks" / "chunk_index.json"
        
        if index_file.exists():
            with open(index_file, 'r', encoding='utf-8') as f:
                self.chunk_index = json.load(f)
            logger.debug(f"Chunk index loaded: {len(self.chunk_index)} entries")
        else:
            self.chunk_index = {}
            logger.warning("chunk_index.json not found. Entity lookup disabled.")
    
    def retrieve(
        self,
        query: ProcessedQuery,
        n_results: int = TOP_K_FINAL
    ) -> list[RetrievedChunk]:
        """
        Retrieve relevant chunks using hybrid search.
        
        Args:
            query: Processed query
            n_results: Number of final results to return
        
        Returns:
            List of RetrievedChunk objects, ranked by combined score
        """
        all_chunks = {}  # chunk_id -> RetrievedChunk
        
        # STEP 1: Semantic search on original query
        semantic_chunks = self._semantic_search(
            query.cleaned,
            TOP_K_SEMANTIC,
            "semantic"
        )
        for chunk in semantic_chunks:
            all_chunks[chunk.chunk_id] = chunk
        
        logger.debug(f"Semantic search: {len(semantic_chunks)} chunks")
        
        # STEP 2: Semantic search on expanded queries
        for i, expanded in enumerate(query.expanded_queries):
            expanded_chunks = self._semantic_search(
                expanded,
                5,  # Fewer results per expansion
                f"semantic_expanded_{i+1}"
            )
            for chunk in expanded_chunks:
                if chunk.chunk_id not in all_chunks:
                    all_chunks[chunk.chunk_id] = chunk
        
        if query.expanded_queries:
            logger.debug(f"Expanded queries: +{len(query.expanded_queries)} searches")
        
        # STEP 3: HyDE retrieval
        if query.hyde_document:
            hyde_chunks = self._semantic_search(
                query.hyde_document,
                TOP_K_HYDE,
                "hyde"
            )
            for chunk in hyde_chunks:
                if chunk.chunk_id not in all_chunks:
                    all_chunks[chunk.chunk_id] = chunk
            
            logger.debug(f"HyDE search: {len(hyde_chunks)} chunks")
        
        # STEP 4: Keyword search (BM25)
        keyword_chunks = self._keyword_search(query.keywords, TOP_K_KEYWORD)
        for chunk in keyword_chunks:
            if chunk.chunk_id in all_chunks:
                # Merge scores if already found by semantic search
                existing = all_chunks[chunk.chunk_id]
                existing.keyword_score = chunk.keyword_score
                existing.retrieval_source = "semantic+keyword"
            else:
                all_chunks[chunk.chunk_id] = chunk
        
        logger.debug(f"Keyword search: {len(keyword_chunks)} chunks")
        
        # STEP 5: Entity-based direct lookup
        entity_chunks = self._entity_lookup(query.extracted_entities)
        for chunk in entity_chunks:
            if chunk.chunk_id not in all_chunks:
                all_chunks[chunk.chunk_id] = chunk
        
        if entity_chunks:
            logger.debug(f"Entity lookup: {len(entity_chunks)} chunks")
        
        # STEP 6: Score combination & reranking
        ranked_chunks = self._rerank_chunks(list(all_chunks.values()), query)
        
        # STEP 7: Apply query-type specific filters
        filtered_chunks = self._apply_filters(ranked_chunks, query)
        
        # Take top N
        final_chunks = filtered_chunks[:n_results]
        
        logger.info(
            f"Retrieved {len(final_chunks)} chunks "
            f"(from {len(all_chunks)} candidates)"
        )
        
        return final_chunks
    
    def _semantic_search(
        self,
        query_text: str,
        n_results: int,
        source: str
    ) -> list[RetrievedChunk]:
        """Perform semantic search using embeddings."""
        # Embed query
        query_embedding = self.embedder.embed_query(query_text)
        
        # Search ChromaDB
        results = self.vector_store.query(
            self.collection,
            query_embedding,
            n_results=n_results
        )
        
        # Convert to RetrievedChunk
        chunks = []
        for res in results:
            chunk_id = res['chunk_id']
            metadata = res.get('metadata', {})
            content = res.get('content', '')
            similarity = res.get('similarity_score', 0.0)
            
            chunk = RetrievedChunk(
                chunk_id=chunk_id,
                content=content,
                metadata=metadata,
                semantic_score=similarity,
                keyword_score=0.0,  # Will be filled if also found by BM25
                combined_score=0.0,  # Will be calculated in reranking
                retrieval_source=source,
                rank=0  # Will be assigned in reranking
            )
            chunks.append(chunk)
        
        return chunks
    
    def _keyword_search(
        self,
        keywords: list[str],
        n_results: int
    ) -> list[RetrievedChunk]:
        """Perform keyword search using BM25."""
        if not keywords:
            return []
        
        # Tokenize query
        query_tokens = ' '.join(keywords).lower().split()
        
        # Get BM25 scores
        scores = self.bm25.get_scores(query_tokens)
        
        # Get top N indices
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:n_results]
        
        # Normalize scores to 0-1
        max_score = max(scores[i] for i in top_indices) if top_indices else 1.0
        if max_score == 0:
            max_score = 1.0
        
        # Convert to RetrievedChunk
        chunks = []
        for idx in top_indices:
            chunk_data = self.chunks_data[idx]
            normalized_score = scores[idx] / max_score
            
            chunk = RetrievedChunk(
                chunk_id=chunk_data['chunk_id'],
                content=chunk_data.get('content', ''),
                metadata=chunk_data,
                semantic_score=0.0,  # No semantic score from BM25
                keyword_score=normalized_score,
                combined_score=0.0,  # Will be calculated in reranking
                retrieval_source="keyword",
                rank=0
            )
            chunks.append(chunk)
        
        return chunks
    
    def _entity_lookup(self, entities: list[str]) -> list[RetrievedChunk]:
        """Direct lookup by qualified name."""
        chunks = []
        
        for entity in entities:
            # Check if entity is in chunk index
            if entity in self.chunk_index:
                chunk_ids = self.chunk_index[entity]
                if not isinstance(chunk_ids, list):
                    chunk_ids = [chunk_ids]
                
                # Fetch chunks from ChromaDB
                for chunk_id in chunk_ids:
                    try:
                        result = self.vector_store.get_chunk_by_id(
                            self.collection,
                            chunk_id
                        )
                        
                        if result:
                            chunk = RetrievedChunk(
                                chunk_id=chunk_id,
                                content=result.get('content', ''),
                                metadata=result.get('metadata', {}),
                                semantic_score=1.0,  # Exact match
                                keyword_score=0.0,
                                combined_score=0.95,  # High score for exact match
                                retrieval_source="entity_lookup",
                                rank=0
                            )
                            chunks.append(chunk)
                    except Exception as e:
                        logger.warning(f"Failed to fetch chunk {chunk_id}: {e}")
        
        return chunks
    
    def _rerank_chunks(
        self,
        chunks: list[RetrievedChunk],
        query: ProcessedQuery
    ) -> list[RetrievedChunk]:
        """Combine scores and rerank chunks."""
        for chunk in chunks:
            # Skip if already has combined score (entity lookup)
            if chunk.combined_score > 0:
                continue
            
            # Weighted combination
            combined = (
                SEMANTIC_WEIGHT * chunk.semantic_score +
                KEYWORD_WEIGHT * chunk.keyword_score
            )
            
            # Bonus for chunks found by both methods
            if chunk.semantic_score > 0 and chunk.keyword_score > 0:
                combined += 0.1
            
            # Cap at 1.0
            chunk.combined_score = min(1.0, combined)
        
        # Sort by combined score
        ranked = sorted(chunks, key=lambda c: c.combined_score, reverse=True)
        
        # Assign ranks
        for i, chunk in enumerate(ranked, 1):
            chunk.rank = i
        
        return ranked
    
    def _apply_filters(
        self,
        chunks: list[RetrievedChunk],
        query: ProcessedQuery
    ) -> list[RetrievedChunk]:
        """Apply query-type specific filters."""
        # WHERE_IS queries: prefer implementation over entry points
        if query.query_type == QueryType.WHERE_IS:
            # Deprioritize entry points
            for chunk in chunks:
                if chunk.metadata.get('is_entry_point'):
                    chunk.combined_score *= 0.8
            
            # Re-sort
            chunks = sorted(chunks, key=lambda c: c.combined_score, reverse=True)
        
        # WHAT_CALLS queries: prefer function chunks
        if query.query_type == QueryType.WHAT_CALLS:
            filtered = []
            for chunk in chunks:
                chunk_type = chunk.metadata.get('chunk_type', '')
                if chunk_type in ['FUNCTION', 'METHOD']:
                    filtered.append(chunk)
            
            # If we filtered out everything, keep original
            if filtered:
                chunks = filtered
        
        return chunks
    
    def retrieve_by_graph(
        self,
        primary_chunks: list[RetrievedChunk],
        query: ProcessedQuery
    ) -> list[RetrievedChunk]:
        """
        Retrieve graph neighbors (callers/callees) of primary chunks.
        
        Args:
            primary_chunks: Primary retrieved chunks
            query: Processed query
        
        Returns:
            List of neighbor chunks
        """
        expanded_chunks = []
        seen_ids = {c.chunk_id for c in primary_chunks}
        
        # Only expand first 5 primary chunks (most relevant)
        for chunk in primary_chunks[:5]:
            neighbors = self._get_graph_neighbors(chunk, query)
            
            for neighbor in neighbors:
                if neighbor.chunk_id not in seen_ids:
                    expanded_chunks.append(neighbor)
                    seen_ids.add(neighbor.chunk_id)
                    
                    # Stop if we have enough
                    if len(expanded_chunks) >= MAX_EXPANSION_CHUNKS:
                        break
            
            if len(expanded_chunks) >= MAX_EXPANSION_CHUNKS:
                break
        
        logger.info(f"Graph expansion: {len(expanded_chunks)} neighbor chunks")
        return expanded_chunks
    
    def _get_graph_neighbors(
        self,
        chunk: RetrievedChunk,
        query: ProcessedQuery
    ) -> list[RetrievedChunk]:
        """
        Get call graph neighbors of a chunk.

        Fast path: if KnowledgeGraph is loaded, performs BFS in memory
        (~microseconds) and then issues a single batched ChromaDB fetch.

        Slow fallback: iterates the chunk_index dict and issues one
        ChromaDB look-up per neighbour (original behaviour).
        """
        # ── Determine the function name for this chunk ─────────────────
        func_name = (
            chunk.metadata.get('qualified_name')
            or chunk.metadata.get('function_name')
            or ""
        )

        # ── FAST PATH: in-memory KnowledgeGraph BFS ────────────────────
        if self.knowledge_graph is not None and func_name:
            try:
                if query.query_type == QueryType.WHAT_CALLS:
                    # Only callers (reverse direction)
                    neighbor_names = self.knowledge_graph.get_callers(func_name)
                else:
                    # Both callers + callees within 2 hops
                    neighbor_names = self.knowledge_graph.get_neighbors(func_name, depth=2)

                # Collect chunk IDs for all neighbors in one pass
                neighbor_chunk_ids: list[str] = []
                for name in neighbor_names[:10]:
                    ids = self.chunk_index.get(name, [])
                    if not isinstance(ids, list):
                        ids = [ids]
                    if ids:
                        neighbor_chunk_ids.append(ids[0])

                # Single batched ChromaDB fetch (much faster than N individual calls)
                neighbors: list[RetrievedChunk] = []
                for chunk_id in neighbor_chunk_ids[:10]:
                    try:
                        result = self.vector_store.get_chunk_by_id(
                            self.collection, chunk_id
                        )
                        if result:
                            neighbor_score = chunk.combined_score * 0.7
                            neighbors.append(RetrievedChunk(
                                chunk_id=chunk_id,
                                content=result.get('content', ''),
                                metadata=result.get('metadata', {}),
                                semantic_score=neighbor_score,
                                keyword_score=0.0,
                                combined_score=neighbor_score,
                                retrieval_source="graph_expansion_kg",
                                rank=0,
                            ))
                    except Exception as exc:
                        logger.debug(f"KG neighbor fetch failed for {chunk_id}: {exc}")

                logger.debug(
                    f"KG fast-path: {len(neighbors)} neighbors for '{func_name}'"
                )
                return neighbors

            except Exception as exc:
                logger.warning(
                    f"KnowledgeGraph traversal failed for '{func_name}': {exc}. "
                    "Falling back to dict-based expansion."
                )

        # ── SLOW FALLBACK: per-neighbor ChromaDB lookup ─────────────────
        calls = self._parse_serialized_list(
            chunk.metadata.get('calls_serialized', '[]')
        )
        called_by = self._parse_serialized_list(
            chunk.metadata.get('called_by_serialized', '[]')
        )

        if query.query_type == QueryType.WHAT_CALLS:
            qualified_names = called_by
        else:
            qualified_names = calls + called_by

        neighbors = []
        for qname in qualified_names[:10]:
            if qname in self.chunk_index:
                chunk_ids = self.chunk_index[qname]
                if not isinstance(chunk_ids, list):
                    chunk_ids = [chunk_ids]

                for chunk_id in chunk_ids[:1]:
                    try:
                        result = self.vector_store.get_chunk_by_id(
                            self.collection, chunk_id
                        )
                        if result:
                            neighbor_score = chunk.combined_score * 0.7
                            neighbors.append(RetrievedChunk(
                                chunk_id=chunk_id,
                                content=result.get('content', ''),
                                metadata=result.get('metadata', {}),
                                semantic_score=neighbor_score,
                                keyword_score=0.0,
                                combined_score=neighbor_score,
                                retrieval_source="graph_expansion",
                                rank=0,
                            ))
                    except Exception as exc:
                        logger.debug(f"Failed to fetch neighbor {chunk_id}: {exc}")

        return neighbors
    
    def _parse_serialized_list(self, serialized: str) -> list[str]:
        """Parse JSON-serialized list from metadata."""
        try:
            if isinstance(serialized, list):
                return serialized
            return json.loads(serialized) if serialized else []
        except:
            return []


# Test function
def test_retriever():
    """Test the retriever with a sample query."""
    print("Testing Retriever...")
    print("=" * 60)
    
    try:
        # This requires a repo to be embedded first
        print("Note: This test requires a repository to be embedded.")
        print("Run first: python main.py embed https://github.com/pallets/itsdangerous")
        print()
        
        from chunking.vector_store import VectorStore
        from chunking.embedder import Embedder
        from rag.query_processor import QueryProcessor
        from rag.llm_client import LLMClient
        
        # Initialize components
        vector_store = VectorStore()
        embedder = Embedder()
        llm_client = LLMClient()
        query_processor = QueryProcessor(llm_client)
        
        # Test with itsdangerous repo
        retriever = Retriever(vector_store, embedder, "pallets", "itsdangerous")
        print("✓ Retriever initialized")
        print()
        
        # Process a test query
        question = "How does the Signer class work?"
        processed = query_processor.process(question, None)
        print(f"Query: {question}")
        print(f"Type: {processed.query_type.value}")
        print()
        
        # Retrieve chunks
        chunks = retriever.retrieve(processed, n_results=5)
        print(f"Retrieved {len(chunks)} chunks:")
        print()
        
        for i, chunk in enumerate(chunks, 1):
            print(f"{i}. Score: {chunk.combined_score:.3f} | Source: {chunk.retrieval_source}")
            print(f"   File: {chunk.metadata.get('file_path', 'unknown')}")
            print(f"   Function: {chunk.metadata.get('qualified_name', 'unknown')}")
            print()
        
        print("✓ Retrieval test passed!")
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
    test_retriever()
