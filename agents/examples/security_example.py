"""
examples/security_example.py

Run with:  python -m examples.security_example
"""

from agents.security_agent import SecurityAgent
from agents.schemas.common import AgentRequest

INSECURE_CODE = """
import subprocess

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"

def run_user_command(cmd):
    subprocess.run(cmd, shell=True)
"""


def main():
    agent = SecurityAgent()
    request = AgentRequest(
        query="Check this code for security vulnerabilities.",
        code=INSECURE_CODE,
    )
    response = agent.run(request)
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
