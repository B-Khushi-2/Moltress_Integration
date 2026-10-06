# Moltress Agent Layer Integration

This application answers chats using the Moltress **Agent Layer** (Router → Specialized Agents → Local Ollama / Qwen2.5-Coder).
Setup, configuration, API and troubleshooting can be found in: **[docs/moltress-integration.md](docs/moltress-integration.md)**.

## Team Quick Start (Local Setup)

To quickly spin up the entire application architecture on your local machine, open three separate terminal windows and run the following configuration scripts:

> **Note:** These paths reflect an `E:\Moltress` drive setup. Make sure to update the drive paths in the terminal commands to match your local installation directory if you clone it to a different location (like `C:\`).

**1. Start the FastAPI Backend**
```powershell
cd E:\Moltress\moltress_integrated_application
python -m backend
```

**2. Start the Local Ollama AI Server**
```powershell
$env:OLLAMA_TMPDIR="E:\OllamaTmp"
$env:OLLAMA_MODELS="E:\OllamaModels"
& "E:\Ollama\ollama.exe" serve
```

**3. Start the Electron Frontend UI**
```powershell
$env:npm_config_cache="E:\npm-cache"
$env:TEMP="E:\temp"
$env:ELECTRON_CACHE="E:\electron-cache"
cd E:\Moltress\moltress_integrated_application
npm run dev
```

## Features
- **Local AI Architecture:** Connect to the `Qwen2.5-Coder` model privately without internet API keys.
- **RAG Implementation:** Uses ChromaDB for intelligent document parsing and exact-fact retrieval from local datasets like the Vedanta knowledge base.
- **Persistent Database:** Uses a local SQLite `moltress.db` file to permanently save, recall, and list user chat sessions safely without manual configuration.
- **Agent Orchestrator:** Seamlessly routes complex queries across specialized agents before delivering a cohesive answer to the user.

## Tech Stack
- Frontend: Electron / React / Vite
- Backend: FastAPI (Python)
- Storage: SQLite (chat_sessions, chat_messages)
- Vector DB: ChromaDB
- LLM Provider: Ollama (Qwen2.5-Coder)
