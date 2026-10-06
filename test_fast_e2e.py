import sys
import os
import json
from backend.models import ChatRequest
from backend.service import AgentService
from agents.config.agent_config import get_config

def main():
    service = AgentService()
    
    # Query 1
    req1 = ChatRequest(query="According to the project knowledge, what is the special number in RAG_Test_Project?", agent="debugging", request_id="req1")
    status1, response1 = service.chat(req1)
    
    print("\n--- TEST 1 ---")
    print(f"Status: {status1}")
    print(f"Answer: {response1.answer}")
    
    if "8472" not in response1.answer:
        print("FAIL: Did not retrieve 8472")

    # Query 2
    req2 = ChatRequest(query="According to the project knowledge, who is the creator of RAG_Test_Project?", agent="debugging", request_id="req2")
    status2, response2 = service.chat(req2)
    
    print("\n--- TEST 2 ---")
    print(f"Status: {status2}")
    print(f"Answer: {response2.answer}")

    if "Khushi" not in response2.answer:
        print("FAIL: Did not retrieve Khushi")
        
    print("\nALL BACKEND API TESTS SUCCESSFUL!")

if __name__ == "__main__":
    main()
