import json
import urllib.request


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:4b"


def ask_ai(question):

    data = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Orion, a personal AI assistant. "
                    "Give short, clear and natural answers. "
                    "Do not show your thinking or reasoning. "
                    "Only give the final answer."
                )
            },
            {
                "role": "user",
                "content": question
            }
        ],
        "stream": False,
        "think": False
    }

    data = json.dumps(data).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(request) as response:
        result = json.loads(response.read().decode("utf-8"))

    answer = result["message"]["content"]

    # Remove Qwen thinking if it appears
    if "</think>" in answer:
        answer = answer.split("</think>")[-1]

    return answer.strip()
