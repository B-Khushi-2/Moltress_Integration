import sys
import os
import json
from backend.models import ChatRequest
from backend.service import AgentService
from agents.config.agent_config import get_config

def main():
    service = AgentService()
    req = ChatRequest(query='According to the project knowledge, what is the special number in RAG_Test_Project?', agent='developer_agent', request_id='req1')
    status, response = service.chat(req)
    print(f'RAG ENABLED FLAG: {get_config().rag_enabled}')
    print(f'Answer: {response.answer}')
    if '8472' in response.answer:
        print('SUCCESS')
    else:
        print('FAIL')

if __name__ == '__main__':
    main()
