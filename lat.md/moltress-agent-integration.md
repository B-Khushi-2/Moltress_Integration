How the desktop chat reaches the Moltress Agent Layer (Router → specialised agents → local Ollama model), and why it is wired the way it is.

# Moltress Agent Integration

A chat turn typed in the UI is answered by the Python Agent Layer, not by a Hermes gateway. The renderer is unchanged; only the main-process transport and one transport preference differ.

## Request path

The renderer's IPC `send-message` call is answered by [[src/main/moltress.ts#sendMessageViaMoltress]], which POSTs to the backend, which runs [[backend/service.py#AgentService#chat]].

The service routes with `AgentRouter` (or `AgentOrchestrator` for `/pipeline`), the chosen agent calls the real `OllamaClient`, and the structured answer is flattened to Markdown by [[backend/formatting.py#render_answer]]. The answer reaches the existing chat bubble as a single `onChunk` followed by `onDone` with no session id, so the renderer keeps the streamed text instead of reconciling with a Hermes database.

## Why request/response, not streaming

The Agent Layer validates one complete JSON object per turn (and may loop through tools first), so there are no partial tokens worth streaming; the answer is delivered whole.

## Transport selection

Moltress mode is on unless `MOLTRESS_ENABLED=false`, read by [[src/main/moltress.ts#getMoltressConfig]].

In local mode the renderer would otherwise pick the Hermes dashboard WebSocket transport and never call `send-message`, so the main process reports `moltressEnabled` and the chat screen switches to the legacy IPC transport. The install gate and Hermes gateway start-up are skipped in this mode.

## Failure handling

Every failure is a readable error bubble, never a fake answer: backend unreachable, bad token, Ollama down (503), malformed model output (502), timeout (504), empty answer. Empty or whitespace input is rejected before any request is made.

## Sandbox safety

The agents' read tools are confined to the project root (or the chat's context folder) and refuse credential files such as `.env`.

They also skip `node_modules`, so a model can neither read secrets nor drown in vendored files. Write and terminal tools stay off, and a network caller can never approve actions.
