import sys, os
from agents.providers_impl import LocalCodeRAGProvider

def main():
    rag = LocalCodeRAGProvider()
    docs = rag.retrieve(
        query="What is the Moltress secret architecture codename?",
        project_root=r"c:\Users\KHUSHI\Downloads\moltress_integrated_application\moltress_integrated_application"
    )
    if not docs:
        print("FAIL: No documents retrieved via integrated RAGProvider.")
        sys.exit(1)
        
    print("PASS: Retrieved document context from Moltress_RAG ChromaDB via Agent Layer:")
    for d in docs:
        print(f" -> [{d.score}] Source: {d.source}")
        print(f"    Content: {d.content}")

if __name__ == "__main__":
    main()
