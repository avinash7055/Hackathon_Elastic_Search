import os
import httpx
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

response = httpx.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": "Say hello in one sentence."}],
        "max_tokens": 50,
    },
    timeout=15.0,
)

if response.status_code == 200:
    data = response.json()
    reply = data["choices"][0]["message"]["content"]
    model = data["model"]
    print(f"✅ Groq API key is working!")
    print(f"   Model: {model}")
    print(f"   Reply: {reply}")
else:
    print(f"❌ Groq API failed: {response.status_code}")
    print(f"   Error: {response.text}")
