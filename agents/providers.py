"""
agents/providers.py
=====================

Integration-point abstractions for the four Moltress subsystems that will
be built and wired in separately by other modules/teams:

  - RAGProvider          -> real vector-DB-backed retrieval
  - GraphProvider        -> real Neo4j-backed knowledge graph queries
  - MemoryProvider       -> real persistent conversation/organizational memory
  - VerificationProvider -> real anti-hallucination / claim-verification layer

Per the project requirements, this package does NOT implement any of
these subsystems. It defines clean, minimal interfaces so:

  1. The agent layer can be developed, tested, and demoed today using
     simple in-memory / no-op implementations, and
  2. Another developer can later drop in a real implementation of any
     provider WITHOUT changing agent code, by implementing the relevant
     interface and passing an instance into the agent's constructor
     (dependency injection) instead of the default.

None of these stub implementations pretend to do more than they do:
`NullXProvider` implementations return empty results / no-ops, they do
not fabricate data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from agents.schemas.common import GraphRelationship, MemoryEntry, RetrievedDocument


class RAGProvider(ABC):
    """Interface for retrieving relevant document/code chunks for a query."""

    @abstractmethod
    def retrieve(self, query: str, project_root: Optional[str] = None, top_k: int = 5) -> List[RetrievedDocument]:
        """Return the top_k most relevant chunks for `query`."""
        raise NotImplementedError


class NullRAGProvider(RAGProvider):
    """No-op RAG provider used until the real vector-DB-backed system is wired in."""

    def retrieve(self, query: str, project_root: Optional[str] = None, top_k: int = 5) -> List[RetrievedDocument]:
        return []


class GraphProvider(ABC):
    """Interface for querying the project's knowledge graph."""

    @abstractmethod
    def get_relationships(self, entity: str, depth: int = 1) -> List[GraphRelationship]:
        """Return relationships involving `entity`, up to `depth` hops away."""
        raise NotImplementedError


class NullGraphProvider(GraphProvider):
    """No-op Knowledge Graph provider used until Neo4j (or similar) is wired in."""

    def get_relationships(self, entity: str, depth: int = 1) -> List[GraphRelationship]:
        return []


class MemoryProvider(ABC):
    """Interface for retrieving and storing conversation/organizational memory."""

    @abstractmethod
    def get_recent(self, session_id: str, limit: int = 10) -> List[MemoryEntry]:
        raise NotImplementedError

    @abstractmethod
    def append(self, session_id: str, entry: MemoryEntry) -> None:
        raise NotImplementedError


class NullMemoryProvider(MemoryProvider):
    """No-op Memory provider used until the real persistent memory store is wired in."""

    def get_recent(self, session_id: str, limit: int = 10) -> List[MemoryEntry]:
        return []

    def append(self, session_id: str, entry: MemoryEntry) -> None:
        # Intentionally does nothing — memory is not persisted by this stub.
        return None


class VerificationProvider(ABC):
    """
    Interface for the (future) anti-hallucination / claim-verification layer.

    The intended pipeline is:
        Agent -> Draft AgentResponse -> VerificationProvider.verify(...) -> Final response

    Agents in this package do NOT call this themselves by default (per the
    "do not build a complete verification system" requirement); it is
    exposed here so the main Moltress backend can insert it into the
    pipeline around `agent.run(...)`.
    """

    @abstractmethod
    def verify(self, response, context) -> "VerificationResult":
        raise NotImplementedError


class VerificationResult:
    """Minimal result shape a real VerificationProvider would return."""

    def __init__(self, verified: bool, notes: Optional[str] = None):
        self.verified = verified
        self.notes = notes


class NullVerificationProvider(VerificationProvider):
    """No-op verification provider; always returns 'unverified, not checked'."""

    def verify(self, response, context) -> VerificationResult:
        return VerificationResult(verified=False, notes="Verification layer not yet integrated.")
