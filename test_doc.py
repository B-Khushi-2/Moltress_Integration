import sys
import os
import json
from backend.models import ChatRequest
from backend.service import AgentService
from agents.config.agent_config import get_config

def main():
    service = AgentService()
    req = ChatRequest(
        query="Document this Python function:\ndef add(a, b):\n    return a + b",
        agent="documentation_agent",
        request_id="req1"
    )
    status, response = service.chat(req)
    
    print(f"Status: {status}")
    if response and hasattr(response, 'model_dump'):
        from pprint import pprint
        print("Schema passed successfully! Answer generated:")
        print(response.answer)
    else:
        print("FAILED: response is not a valid AgentResponse")

if __name__ == '__main__':
    main()
