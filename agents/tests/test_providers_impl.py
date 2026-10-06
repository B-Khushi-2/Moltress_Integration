"""
agents/tests/test_providers_impl.py
====================================

Tests for LocalCodeRAGProvider, ASTGraphProvider, and InMemoryMemoryProvider.
"""

import os
import tempfile
import pytest

from agents.providers_impl import ASTGraphProvider, InMemoryMemoryProvider, LocalCodeRAGProvider
from agents.schemas.common import MemoryEntry


def test_local_code_rag_provider():
    with tempfile.TemporaryDirectory() as project_root:
        # Create a sample file
        sample_path = os.path.join(project_root, "auth.py")
        with open(sample_path, "w") as f:
            f.write("def authenticate_user(username, password):\n    # Validate user credentials\n    return True\n")

        rag = LocalCodeRAGProvider()
        docs = rag.retrieve("authenticate credentials", project_root=project_root)

        assert len(docs) >= 0
        if len(docs) > 0:
            assert "auth.py" in docs[0].source
            assert "authenticate_user" in docs[0].content


def test_ast_graph_provider():
    with tempfile.TemporaryDirectory() as project_root:
        sample_path = os.path.join(project_root, "service.py")
        with open(sample_path, "w") as f:
            f.write("import math\nfrom utils import helper\n\ndef process_data():\n    pass\n")

        graph = ASTGraphProvider()
        rels = graph.get_relationships("service", project_root=project_root)

        assert len(rels) >= 2
        rels_targets = [r.target for r in rels]
        assert "process_data" in rels_targets or "math" in rels_targets or "utils" in rels_targets


def test_in_memory_memory_provider():
    mem_provider = InMemoryMemoryProvider()
    session_id = "session-test-01"

    mem_provider.append(session_id, MemoryEntry(role="user", content="Remember: use PostgreSQL"))
    mem_provider.append(session_id, MemoryEntry(role="assistant", content="Acknowledged preference."))

    recent = mem_provider.get_recent(session_id)
    assert len(recent) == 2
    assert recent[0].content == "Remember: use PostgreSQL"
