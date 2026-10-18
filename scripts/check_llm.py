import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
from app.config import get_settings
from app.llm import get_llm_client


async def check():
    s = get_settings()
    print(f"REAL_LLM={s.REAL_LLM} LLM_PROVIDER={s.LLM_PROVIDER} groq_key={bool(s.effective_groq_api_key)} google_key={bool(s.effective_google_api_key)}")
    client = get_llm_client()
    print(f"Client in use: {type(client).__name__}")
    if s.REAL_LLM == 1 and type(client).__name__ == "MockLLMClient":
        print("ERROR: REAL_LLM=1 but the Mock client was selected (missing key/provider).")
        return 2
    try:
        res = await client.generate_json("Return {\"ok\": true}", "Reply with JSON only.")
        print(f"SUCCESS: {str(res)[:80]}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(asyncio.run(check()))
