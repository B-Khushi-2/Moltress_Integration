"""
Moltress backend
================

A thin HTTP service that exposes the Moltress Agent Layer (``agents/``) to
the desktop UI. It owns no AI logic of its own: it validates requests,
builds ``AgentRequest`` objects, delegates to ``AgentRouter`` /
``AgentOrchestrator``, and converts the structured ``AgentResponse`` into a
stable JSON contract the UI can render.

    UI (Electron main) --HTTP--> backend --> agents --> Ollama
"""

__version__ = "1.0.0"
