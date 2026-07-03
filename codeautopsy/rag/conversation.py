"""
rag/conversation.py — Multi-turn Conversation Management

Manages conversation sessions:
- Creates and tracks sessions
- Saves/loads from disk
- Maintains conversation history
- Provides recent context for LLM
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MAX_CONVERSATION_TURNS, DATA_DIR

from rag import ConversationSession, ConversationTurn, RAGResponse, Citation

logger = logging.getLogger(__name__)


class SessionNotFoundError(Exception):
    """Raised when session not found."""
    pass


class ConversationManager:
    """
    Manages multi-turn conversation sessions.
    
    Usage:
        manager = ConversationManager("owner", "repo", data_dir)
        session_id = manager.create_session()
        manager.add_turn(session_id, response, chunk_ids)
    """
    
    def __init__(self, repo_owner: str, repo_name: str, data_dir: Path):
        """
        Initialize conversation manager.
        
        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            data_dir: Data directory path
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.sessions: dict[str, ConversationSession] = {}
        
        # Create conversations directory
        self.conversations_dir = (
            data_dir / f"{repo_owner}__{repo_name}" / "conversations"
        )
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Conversation manager initialized for {repo_owner}/{repo_name}")
    
    def create_session(self) -> str:
        """
        Create a new conversation session.
        
        Returns:
            Session ID (8-character UUID)
        """
        session_id = str(uuid.uuid4())[:8]  # Short readable ID
        
        session = ConversationSession(
            session_id=session_id,
            repo_owner=self.repo_owner,
            repo_name=self.repo_name,
            created_at=datetime.now().isoformat(),
            last_active=datetime.now().isoformat(),
            turns=[],
            total_questions=0
        )
        
        self.sessions[session_id] = session
        self._save_session(session_id)
        
        logger.info(f"Created session: {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> ConversationSession:
        """
        Get a conversation session.
        
        Args:
            session_id: Session ID
        
        Returns:
            ConversationSession
        
        Raises:
            SessionNotFoundError: If session not found
        """
        # Check in-memory cache
        if session_id in self.sessions:
            return self.sessions[session_id]
        
        # Try to load from disk
        try:
            session = self._load_session(session_id)
            self.sessions[session_id] = session
            return session
        except FileNotFoundError:
            raise SessionNotFoundError(
                f"Session {session_id} not found. "
                f"Create a new session or check the session ID."
            )
    
    def add_turn(
        self,
        session_id: str,
        response: RAGResponse,
        retrieved_chunk_ids: list[str]
    ) -> None:
        """
        Add a turn to the conversation.
        
        Args:
            session_id: Session ID
            response: RAG response
            retrieved_chunk_ids: IDs of retrieved chunks
        """
        session = self.get_session(session_id)
        
        # Create turn
        turn = ConversationTurn(
            turn_number=response.turn_number,
            question=response.question,
            answer=response.answer,
            citations=response.citations,
            retrieved_chunk_ids=retrieved_chunk_ids,
            timestamp=datetime.now().isoformat()
        )
        
        # Add to session
        session.turns.append(turn)
        session.total_questions += 1
        session.last_active = datetime.now().isoformat()
        
        # Trim old turns if exceeding limit
        if len(session.turns) > MAX_CONVERSATION_TURNS:
            removed = session.turns.pop(0)
            logger.debug(f"Removed old turn {removed.turn_number} from session {session_id}")
        
        # Save to disk
        self._save_session(session_id)
        
        logger.debug(f"Added turn {turn.turn_number} to session {session_id}")
    
    def get_recent_context(
        self,
        session: ConversationSession,
        max_turns: int = 3
    ) -> str:
        """
        Get formatted recent conversation context.
        
        Args:
            session: Conversation session
            max_turns: Maximum turns to include
        
        Returns:
            Formatted context string
        """
        if not session.turns:
            return ""
        
        # Take last N turns
        recent_turns = session.turns[-max_turns:]
        
        context_parts = []
        for turn in recent_turns:
            # Truncate answer to 300 chars
            answer = turn.answer
            if len(answer) > 300:
                answer = answer[:297] + "..."
            
            context_parts.append(
                f"Previous Q: {turn.question}\n"
                f"Previous A: {answer}"
            )
        
        return "\n\n".join(context_parts)
    
    def list_sessions(self) -> list[dict]:
        """
        List all sessions for this repository.
        
        Returns:
            List of session summaries
        """
        summaries = []
        
        # List all session files
        if self.conversations_dir.exists():
            for session_file in self.conversations_dir.glob("*.json"):
                try:
                    with open(session_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    summaries.append({
                        'session_id': data['session_id'],
                        'created_at': data['created_at'],
                        'last_active': data['last_active'],
                        'total_questions': data['total_questions']
                    })
                except Exception as e:
                    logger.warning(f"Failed to load session {session_file}: {e}")
        
        # Sort by last_active (most recent first)
        summaries.sort(key=lambda s: s['last_active'], reverse=True)
        
        return summaries
    
    def _save_session(self, session_id: str) -> None:
        """Save session to disk."""
        session = self.sessions[session_id]
        session_file = self.conversations_dir / f"{session_id}.json"
        
        # Convert to dict
        data = self._session_to_dict(session)
        
        # Save
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Saved session {session_id} to {session_file}")
    
    def _load_session(self, session_id: str) -> ConversationSession:
        """Load session from disk."""
        session_file = self.conversations_dir / f"{session_id}.json"
        
        if not session_file.exists():
            raise FileNotFoundError(f"Session file not found: {session_file}")
        
        with open(session_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Convert to ConversationSession
        session = self._dict_to_session(data)
        
        logger.debug(f"Loaded session {session_id} from {session_file}")
        return session
    
    def _session_to_dict(self, session: ConversationSession) -> dict:
        """Convert ConversationSession to dict."""
        return {
            'session_id': session.session_id,
            'repo_owner': session.repo_owner,
            'repo_name': session.repo_name,
            'created_at': session.created_at,
            'last_active': session.last_active,
            'total_questions': session.total_questions,
            'turns': [self._turn_to_dict(turn) for turn in session.turns]
        }
    
    def _turn_to_dict(self, turn: ConversationTurn) -> dict:
        """Convert ConversationTurn to dict."""
        return {
            'turn_number': turn.turn_number,
            'question': turn.question,
            'answer': turn.answer,
            'citations': [self._citation_to_dict(c) for c in turn.citations],
            'retrieved_chunk_ids': turn.retrieved_chunk_ids,
            'timestamp': turn.timestamp
        }
    
    def _citation_to_dict(self, citation: Citation) -> dict:
        """Convert Citation to dict."""
        return {
            'file_path': citation.file_path,
            'function_name': citation.function_name,
            'class_name': citation.class_name,
            'start_line': citation.start_line,
            'end_line': citation.end_line,
            'chunk_id': citation.chunk_id,
            'relevance': citation.relevance
        }
    
    def _dict_to_session(self, data: dict) -> ConversationSession:
        """Convert dict to ConversationSession."""
        return ConversationSession(
            session_id=data['session_id'],
            repo_owner=data['repo_owner'],
            repo_name=data['repo_name'],
            created_at=data['created_at'],
            last_active=data['last_active'],
            turns=[self._dict_to_turn(t) for t in data.get('turns', [])],
            total_questions=data['total_questions']
        )
    
    def _dict_to_turn(self, data: dict) -> ConversationTurn:
        """Convert dict to ConversationTurn."""
        return ConversationTurn(
            turn_number=data['turn_number'],
            question=data['question'],
            answer=data['answer'],
            citations=[self._dict_to_citation(c) for c in data.get('citations', [])],
            retrieved_chunk_ids=data.get('retrieved_chunk_ids', []),
            timestamp=data['timestamp']
        )
    
    def _dict_to_citation(self, data: dict) -> Citation:
        """Convert dict to Citation."""
        return Citation(
            file_path=data['file_path'],
            function_name=data.get('function_name'),
            class_name=data.get('class_name'),
            start_line=data['start_line'],
            end_line=data['end_line'],
            chunk_id=data['chunk_id'],
            relevance=data['relevance']
        )


# Test function
def test_conversation_manager():
    """Test the conversation manager."""
    print("Testing Conversation Manager...")
    print("=" * 60)
    
    try:
        from rag import RAGResponse, QueryType, Citation
        
        # Create manager
        test_dir = Path("/tmp/codeautopsy_test")
        manager = ConversationManager("test", "repo", test_dir)
        print("✓ Conversation manager initialized")
        print()
        
        # Create session
        session_id = manager.create_session()
        print(f"✓ Created session: {session_id}")
        print()
        
        # Create mock response
        mock_response = RAGResponse(
            question="What is the main function?",
            answer="The main function is the entry point...",
            citations=[
                Citation(
                    file_path="main.py",
                    function_name="main",
                    class_name=None,
                    start_line=10,
                    end_line=20,
                    chunk_id="chunk1",
                    relevance="Entry point"
                )
            ],
            confidence="high",
            confidence_reason="Direct match",
            query_type=QueryType.WHAT_IS,
            chunks_retrieved=5,
            chunks_used_in_context=3,
            model_used="gemini",
            response_time_seconds=1.5,
            session_id=session_id,
            turn_number=1
        )
        
        # Add turn
        manager.add_turn(session_id, mock_response, ["chunk1", "chunk2"])
        print("✓ Added turn to session")
        print()
        
        # Get session
        session = manager.get_session(session_id)
        print(f"Session has {len(session.turns)} turn(s)")
        print()
        
        # Get recent context
        context = manager.get_recent_context(session)
        print("Recent context:")
        print("-" * 60)
        print(context)
        print()
        
        # List sessions
        sessions = manager.list_sessions()
        print(f"✓ Found {len(sessions)} session(s)")
        print()
        
        print("✓ Conversation manager test passed!")
        return True
    
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_conversation_manager()
