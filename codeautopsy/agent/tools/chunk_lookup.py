"""
agent/tools/chunk_lookup.py — ChromaDB Chunk Lookup Tool

Fetches code chunks from ChromaDB by qualified function name.
"""

import sys
from pathlib import Path
from typing import Optional
import logging

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from chunking.vector_store import VectorStore
from config import CHROMA_DB_PATH, CHROMA_COLLECTION_PREFIX

logger = logging.getLogger(__name__)

# Singleton vector store instance
_vector_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get or create singleton VectorStore instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore(CHROMA_DB_PATH)
    return _vector_store_instance


def chunk_lookup(
    qualified_name: str,
    repo_owner: str,
    repo_name: str
) -> Optional[dict]:
    """
    Fetches a code chunk from ChromaDB by its qualified function name.
    
    Args:
        qualified_name: e.g., "UserService.get_user"
        repo_owner: e.g., "pallets"
        repo_name: e.g., "itsdangerous"
    
    Returns:
        Dict with chunk data, or None if not found:
        {
            "chunk_id": "uuid",
            "content": "function code...",
            "file_path": "src/...",
            "language": "Python",
            "complexity_score": 4,
            "is_entry_point": False,
            "is_private": False,
            "calls_serialized": "func1,func2",
            "called_by_serialized": "func3,func4",
            "start_line": 120,
            "end_line": 150,
            "qualified_name": "UserService.get_user"
        }
    """
    try:
        vector_store = get_vector_store()
        collection_name = f"{CHROMA_COLLECTION_PREFIX}__{repo_owner}__{repo_name}"
        
        # Get collection
        try:
            collection = vector_store.client.get_collection(name=collection_name)
        except Exception as e:
            logger.warning(f"Collection not found: {collection_name}")
            return None
        
        # Query by qualified name
        results = collection.get(
            where={"qualified_name": {"$eq": qualified_name}},
            include=["metadatas", "documents"]
        )
        
        if not results or not results.get("ids"):
            # Try fuzzy match: search by name only (last part after last dot)
            simple_name = qualified_name.split(".")[-1]
            results = collection.get(
                where={"name": {"$eq": simple_name}},
                include=["metadatas", "documents"]
            )
            
            if not results or not results.get("ids"):
                logger.debug(f"Chunk not found: {qualified_name}")
                return None
        
        # If multiple results (sub-chunks), prefer FUNCTION or METHOD chunk
        ids = results["ids"]
        metadatas = results["metadatas"]
        documents = results["documents"]
        
        # Find best match
        best_idx = 0
        for i, metadata in enumerate(metadatas):
            chunk_type = metadata.get("chunk_type", "")
            if chunk_type in ["function", "method"]:
                best_idx = i
                break
        
        # Extract data
        chunk_id = ids[best_idx]
        metadata = metadatas[best_idx]
        content = documents[best_idx]
        
        return {
            "chunk_id": chunk_id,
            "content": content,
            "file_path": metadata.get("file_path", ""),
            "language": metadata.get("language", ""),
            "complexity_score": metadata.get("complexity_score", 0),
            "is_entry_point": metadata.get("is_entry_point", False),
            "is_private": metadata.get("is_private", False),
            "calls_serialized": metadata.get("calls_serialized", ""),
            "called_by_serialized": metadata.get("called_by_serialized", ""),
            "start_line": metadata.get("start_line", 0),
            "end_line": metadata.get("end_line", 0),
            "qualified_name": metadata.get("qualified_name", qualified_name)
        }
    
    except Exception as e:
        logger.error(f"Error in chunk_lookup for {qualified_name}: {e}")
        return None


# Test function
if __name__ == "__main__":
    import json
    
    print("Testing chunk_lookup...")
    print("=" * 60)
    
    # Test with itsdangerous repo
    repo_owner = "pallets"
    repo_name = "itsdangerous"
    
    test_functions = [
        "Signer",
        "Signer.sign",
        "TimestampSigner.unsign",
        "URLSafeSerializer",
        "nonexistent_function"
    ]
    
    for qualified_name in test_functions:
        print(f"\nLooking up: {qualified_name}")
        result = chunk_lookup(qualified_name, repo_owner, repo_name)
        
        if result:
            print(f"  ✓ Found: {result['file_path']}:{result['start_line']}-{result['end_line']}")
            print(f"    Language: {result['language']}")
            print(f"    Complexity: {result['complexity_score']}")
            print(f"    Content preview: {result['content'][:100]}...")
        else:
            print(f"  ✗ Not found")
    
    print("\n✓ chunk_lookup tests complete!")
