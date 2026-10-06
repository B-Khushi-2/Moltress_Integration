import requests
import time

print("Querying RAG Backend via /api/agent/chat for Q2 (Bauxite) WITH history")
req = {
    "query": "What is bauxite used for?",
    "agent": "documentation_agent",
    "request_id": "req-bauxite",
    "history": [
        {"role": "user", "content": "What is the RAG test number mentioned in the Vedanta document?"},
        {"role": "assistant", "content": "The RAG test number is 78421."}
    ],
    "context_folder": "E:/Moltress/moltress_integrated_application/Vedanta",
    "context": {"source_files": []}
}
resp = requests.post("http://127.0.0.1:8765/api/agent/chat", json=req)
print("Chat Status:", resp.status_code)
try:
    ans = resp.json()
    print("Agent Answer:")
    print(ans.get("error") if not ans.get("ok") else ans.get("result", ans).get("answer", ans))
except:
    print(resp.text)
