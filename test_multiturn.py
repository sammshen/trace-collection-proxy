"""Simple multi-turn conversation through the proxy to verify trace capture."""

import requests

URL = "http://localhost:8201/v1/chat/completions"
MODEL = "MiniMaxAI/MiniMax-M2.5"

messages = [
    {"role": "system", "content": "You are a helpful assistant. Keep responses short (1-2 sentences)."}
]

questions = [
    "What is the capital of France?",
    "What language do they speak there?",
    "What's a famous landmark in that city?",
    "How tall is it?",
]

for q in questions:
    messages.append({"role": "user", "content": q})
    print(f"\n--- Turn {len(messages)//2} ---")
    print(f"User: {q}")
    print(f"Messages in request: {len(messages)}")

    resp = requests.post(URL, json={
        "model": MODEL,
        "messages": messages,
        "stream": False,
    })
    data = resp.json()
    reply = data["choices"][0]["message"]["content"]
    messages.append({"role": "assistant", "content": reply})
    print(f"Assistant: {reply}")

print(f"\nDone. Final message count: {len(messages)}")
