"""
agents/providers_impl.py
==========================

Concrete, working implementations of the four Moltress subsystem providers:

  - `LocalCodeRAGProvider`         -> Scans & indexes project files to retrieve code chunks.
  - `ASTGraphProvider`             -> Uses Python AST parsing to retrieve code relationship edges.
  - `InMemoryMemoryProvider`       -> Persistent, in-memory session history store.
  - `CodeFactVerificationProvider` -> Re-exported from agents.verification for convenience.
"""

from __future__ import annotations

import ast
import os
import re
from typing import Dict, List, Optional

from agents.providers import (
    GraphProvider,
    MemoryProvider,
    RAGProvider,
)
from agents.schemas.common import (
    GraphRelationship,
    MemoryEntry,
    RetrievedDocument,
)
from agents.tools.file_tools import IGNORED_DIR_NAMES, is_sensitive_file
from agents.verification import CodeFactVerificationProvider


class LocalCodeRAGProvider(RAGProvider):
    """
    RAG Provider that indexes files under project_root and retrieves relevant code chunks.
    """

    def retrieve(self, query: str, project_root: Optional[str] = None, top_k: int = 5) -> List[RetrievedDocument]:
        if not project_root or not os.path.exists(project_root):
            return []

        query_terms = set(re.findall(r"\w+", query.lower()))
        if not query_terms:
            return []

        results: List[RetrievedDocument] = []

        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES]
            for fname in files:
                if is_sensitive_file(fname):
                    continue
                if fname.endswith((".py", ".md", ".json", ".txt")):
                    full_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(full_path, project_root)
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                    except Exception:
                        continue

                    # Split by double newline / paragraph / functions
                    chunks = [c.strip() for c in content.split("\n\n") if c.strip()]
                    for i, chunk in enumerate(chunks):
                        chunk_terms = set(re.findall(r"\w+", chunk.lower()))
                        overlap = len(query_terms.intersection(chunk_terms))
                        if overlap > 0:
                            score = round(overlap / (len(query_terms) + 1), 2)
                            results.append(
                                RetrievedDocument(
                                    source=f"{rel_path}#chunk-{i+1}",
                                    content=chunk[:1000],
                                    score=score,
                                    metadata={"file": rel_path, "chunk_index": i},
                                )
                            )

        results.sort(key=lambda d: d.score or 0.0, reverse=True)
        return results[:top_k]


class ASTGraphProvider(GraphProvider):
    """
    Knowledge Graph Provider that parses Python files in project_root to discover
    relationships ('imports', 'defines_function', 'defines_class', 'calls').
    """

    def get_relationships(self, entity: str, depth: int = 1, project_root: Optional[str] = None) -> List[GraphRelationship]:
        relationships: List[GraphRelationship] = []
        entity_lower = entity.lower()

        if not project_root or not os.path.exists(project_root):
            return relationships

        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES]
            for fname in files:
                if is_sensitive_file(fname):
                    continue
                if fname.endswith(".py"):
                    full_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(full_path, project_root)
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            code = f.read()
                        tree = ast.parse(code)
                    except Exception:
                        continue

                    module_name = os.path.splitext(fname)[0]

                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            if entity_lower in module_name.lower() or entity_lower in node.name.lower():
                                relationships.append(
                                    GraphRelationship(
                                        subject=module_name,
                                        relation="defines_function",
                                        target=node.name,
                                        metadata={"file": rel_path, "line": node.lineno},
                                    )
                                )
                        elif isinstance(node, ast.ClassDef):
                            if entity_lower in module_name.lower() or entity_lower in node.name.lower():
                                relationships.append(
                                    GraphRelationship(
                                        subject=module_name,
                                        relation="defines_class",
                                        target=node.name,
                                        metadata={"file": rel_path, "line": node.lineno},
                                    )
                                )
                        elif isinstance(node, ast.Import):
                            for alias in node.names:
                                if entity_lower in alias.name.lower() or entity_lower in module_name.lower():
                                    relationships.append(
                                        GraphRelationship(
                                            subject=module_name,
                                            relation="imports",
                                            target=alias.name,
                                            metadata={"file": rel_path},
                                        )
                                    )
                        elif isinstance(node, ast.ImportFrom):
                            mod = node.module or ""
                            if entity_lower in mod.lower() or entity_lower in module_name.lower():
                                relationships.append(
                                    GraphRelationship(
                                        subject=module_name,
                                        relation="imports_from",
                                        target=mod,
                                        metadata={"file": rel_path},
                                    )
                                )

        return relationships[:15]


class InMemoryMemoryProvider(MemoryProvider):
    """
    In-memory persistent memory provider for session history.
    """

    def __init__(self):
        self._store: Dict[str, List[MemoryEntry]] = {}

    def get_recent(self, session_id: str, limit: int = 10) -> List[MemoryEntry]:
        entries = self._store.get(session_id, [])
        return entries[-limit:]

    def append(self, session_id: str, entry: MemoryEntry) -> None:
        if session_id not in self._store:
            self._store[session_id] = []
        self._store[session_id].append(entry)


__all__ = [
    "LocalCodeRAGProvider",
    "ASTGraphProvider",
    "InMemoryMemoryProvider",
    "CodeFactVerificationProvider",
]
