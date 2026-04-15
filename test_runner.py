import os
import sys

# 添加工程根目录到环境变量
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    print("--- Testing Python Imports ---")
    try:
        import PySide6
        print("[OK] PySide6")
    except Exception as e:
        print(f"[FAIL] PySide6: {e}")
        
    try:
        import chromadb
        print("[OK] chromadb")
    except Exception as e:
        print(f"[FAIL] chromadb: {e}")
        
    try:
        import google.genai
        print("[OK] google.genai")
    except Exception as e:
        print(f"[FAIL] google.genai: {e}")
        
    try:
        import pydantic
        print("[OK] pydantic")
    except Exception as e:
        print(f"[FAIL] pydantic: {e}")

def test_rag_controller():
    print("\n--- Testing RAG Controller (ChromaDB) ---")
    try:
        from services.rag_controller import rag_controller
        rag_controller._ensure_initialized()
        if rag_controller._client is not None:
            print("[OK] RAG Controller Initialized")
        else:
            print("[FAIL] RAG Controller Client is None")
    except Exception as e:
        print(f"[FAIL] RAG Controller: {e}")

def test_ai_service():
    print("\n--- Testing AI Service ---")
    try:
        from services.ai_service import ai_service
        # 此处不产生真实的计费和拦截请求，只需鉴权或初始化
        ai_service.initialize()
        print("[OK] AI Service Initialization (creds loaded, proxy set)")
    except Exception as e:
        print(f"[FAIL] AI Service Initialization: {e}")

if __name__ == "__main__":
    test_imports()
    test_rag_controller()
    test_ai_service()
    print("\nTests finished.")
