import requests
import json
import time

print("1. Testing new UI Ingestion API Endpoint (/api/rag/ingest)")
resp = requests.post("http://127.0.0.1:8765/api/rag/ingest", json={
    "path": "E:/Moltress/moltress_integrated_application/RAG_Test_Project",
    "workspace": "default"
})
print("Status:", resp.status_code)
print("Response:", resp.json())

print("\n2. Querying RAG Backend End-to-End via /api/agent/chat")
req = {
    "query": "According to the project knowledge, what is the special number in RAG_Test_Project?",
    "agent": "documentation_agent",
    "request_id": "req-rag-1",
    "context": {"source_files": []}
}
resp2 = requests.post("http://127.0.0.1:8765/api/agent/chat", json=req)
print("Status:", resp2.status_code)

try:
    ans = resp2.json()
    print("Agent Answer:")
    print(ans.get("error") if not ans.get("ok") else ans.get("result", ans).get("answer", ans))
except:
    print(resp2.text)
