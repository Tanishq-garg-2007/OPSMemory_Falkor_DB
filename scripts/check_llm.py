import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
from app.config import get_settings
from app.llm import get_llm_client
from app.llm.mock import MockLLMClient
from app.llm.google_genai import GoogleGenAIClient


async def check():
    settings = get_settings()
    print(f"Checking LLM configuration:")
    print(f"  REAL_LLM: {settings.REAL_LLM}")
    print(f"  LLM_PROVIDER: {settings.LLM_PROVIDER}")
    print(f"  LLM_MODEL_ID: {settings.LLM_MODEL_ID}")

    if settings.REAL_LLM == 1:
        if not settings.effective_google_api_key:
            print("ERROR: REAL_LLM=1 requested but no GOOGLE_API_KEY or GEMINI_API_KEY found.")
            return 2

        print("Testing live Google GenAI model request...")
        client = GoogleGenAIClient(settings)
        try:
            res = await client.generate_text("Reply with 'READY'", system_prompt="You are a health checker.")
            print(f"SUCCESS: Real model responded: {res.strip()[:60]}")
            return 0
        except Exception as e:
            print(f"ERROR: Live model call failed: {e}")
            return 3
    else:
        print("Testing mock LLM provider...")
        client = MockLLMClient()
        try:
            res = await client.generate_json("payments-api incident outage")
            if "entities" in res or "answer" in res:
                print("SUCCESS: Mock LLM provider responded deterministically.")
                return 0
            else:
                print("ERROR: Mock LLM returned unexpected structure.")
                return 3
        except Exception as e:
            print(f"ERROR: Mock LLM failed: {e}")
            return 3


if __name__ == "__main__":
    code = asyncio.run(check())
    sys.exit(code)
