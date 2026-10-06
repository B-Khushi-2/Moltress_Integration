"""
backend/db_providers.py

Database persistence providers.
"""

from typing import List
from sqlalchemy.orm import Session

from agents.providers import MemoryProvider
from agents.schemas.common import MemoryEntry

from backend.database import SessionLocal
from backend.db_models import ChatSession, ChatMessage


class SQLAlchemyMemoryProvider(MemoryProvider):
    """
    SQLAlchemy-backed persistence memory provider.
    Replaces the InMemoryMemoryProvider to persist chat contexts natively to SQLite.
    """

    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def get_recent(self, session_id: str, limit: int = 10) -> List[MemoryEntry]:
        with self.session_factory() as db:
            messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
                .all()
            )
            # return in chronological order
            return [MemoryEntry(role=m.role, content=m.content) for m in reversed(messages)]

    def append(self, session_id: str, entry: MemoryEntry) -> None:
        with self.session_factory() as db:
            # Ensure session exists
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if not session:
                session = ChatSession(id=session_id)
                db.add(session)
                db.commit()

            message = ChatMessage(
                session_id=session_id,
                role=entry.role,
                content=entry.content
            )
            db.add(message)
            db.commit()
