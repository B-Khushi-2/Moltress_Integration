import requests
import time

print("1. Ingesting Vedanta TXT file to RAG workspace")
resp = requests.post("http://127.0.0.1:8765/api/rag/ingest", json={
    "path": "E:/Moltress/moltress_integrated_application/Vedanta",
    "workspace": "Vedanta"
})
print("Ingest Status:", resp.status_code)
print("Ingest Response:", resp.json())

print("\n2. Querying RAG Backend via /api/agent/chat")
req = {
    "query": "What is the RAG test number?",
    "agent": "documentation_agent",
    "request_id": "req-rag-2",
    "context_folder": "E:/Moltress/moltress_integrated_application/Vedanta",
    "context": {"source_files": []}
}
resp2 = requests.post("http://127.0.0.1:8765/api/agent/chat", json=req)
print("Chat Status:", resp2.status_code)

try:
    ans = resp2.json()
    print("Agent Answer:")
    print(ans.get("error") if not ans.get("ok") else ans.get("result", ans).get("answer", ans))
except:
    print(resp2.text)
