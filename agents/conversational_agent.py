"""
agents/conversational_agent.py

A specialized agent for handling general knowledge base/RAG queries without using codebase tools.
"""

from typing import List

from agents.base_agent import BaseAgent
from agents.tools.base_tool import BaseTool


class ConversationalRAGAgent(BaseAgent):
    """
    Conversational agent dedicated to answering questions directly from RAG context.
    Offers zero tools to structurally prevent tool-loop failures on text documents.
    """

    agent_name = "conversational_agent"
    description = "Conversational assistant for answering general knowledge questions purely from RAG context."

    def _default_system_prompt(self) -> str:
        return (
            "You are a helpful knowledge assistant.\n"
            "Answer strictly from the provided retrieved context. "
            "If the context is insufficient to answer the query, explicitly say so. "
            "Do not invent facts outside of the provided context."
        )

    def default_tools(self) -> List[BaseTool]:
        """Provide zero tools so the model is forced to rely on RAG text."""
        return []
