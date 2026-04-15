import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_api():
    print("--- Testing API Call ---")
    try:
        from services.ai_service import ai_service
        # 发送简单的 prompt
        resp = ai_service.generate("Reply with completely plain text exactly saying 'TEST_PASSED'", system_prompt="You are a helpful assistant.", max_tokens=10)
        print(f"[API RESPONSE] {resp}")
        if "TEST_PASSED" in resp:
            print("[OK] Vertex AI API Call Success")
        else:
            print("[FAIL] Vertex AI API Response unexpected")
    except Exception as e:
        print(f"[FAIL] Vertex AI API Call: {e}")

if __name__ == "__main__":
    test_api()
    print("\nAPI Test finished.")
