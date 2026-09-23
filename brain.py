"""Orion AI brain - local Ollama intelligence with web search + screen vision."""

import base64
import datetime
import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.error

from duckduckgo_search import DDGS

OLLAMA_URL = "http://127.0.0.1:11434"
CHAT_URL = f"{OLLAMA_URL}/api/chat"
GENERATE_URL = f"{OLLAMA_URL}/api/generate"
TAGS_URL = f"{OLLAMA_URL}/api/tags"

MODEL = "qwen3:4b-instruct"

# Cooler identities for the assistant voice.
SPOKEN_NAME = "Oh-ree-yon"

MAX_ANSWER_TOKENS = 200

# ------------------------------------------------------------------
# OLLAMA LIFE-CYCLE
# ------------------------------------------------------------------

def ollama_running():
    try:
        request = urllib.request.Request(TAGS_URL, method="GET")
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def start_ollama(silent=False):
    if ollama_running():
        if not silent:
            print("Ollama: Running")
        return True

    if not silent:
        print("Ollama: Starting...")

    possible_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        r"C:\Users\adull\AppData\Local\Programs\Ollama\ollama.exe",
    ]

    ollama_path = next((path for path in possible_paths if os.path.exists(path)), None)
    if not ollama_path:
        if not silent:
            print("ERROR: Ollama executable not found. Start it manually.")
        return False

    try:
        subprocess.Popen(
            [ollama_path, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as error:
        print("Could not start Ollama:", error)
        return False

    for _ in range(24):
        time.sleep(0.25)
        if ollama_running():
            if not silent:
                print("Ollama: Running")
            return True

    if not silent:
        print("WARNING: Ollama server did not start.")
    return False


# ------------------------------------------------------------------
# REALTIME WEB SEARCH
# ------------------------------------------------------------------

REALTIME_KEYWORDS = [
    "latest", "current", "today", "right now", "this year", "recent",
    "news", "who is the current", "score", "weather", "live",
]


def needs_realtime_info(command):
    return any(keyword in command for keyword in REALTIME_KEYWORDS)


def web_search(query, max_results=3):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        snippets = [
            f"{result.get('title', '')}: {result.get('body', '')}"
            for result in results
        ]
        return "\n".join(snippets)
    except Exception as error:
        print("SEARCH ERROR:", error)
        return ""


# ------------------------------------------------------------------
# TARGET LANGUAGE (only switch when the user asks)
# ------------------------------------------------------------------

LANGUAGE_KEYWORDS = {
    "telugu": "Telugu",
    "hindi": "Hindi",
    "tamil": "Tamil",
    "kannada": "Kannada",
    "english": "English",
}


def detect_requested_language(command):
    for keyword, name in LANGUAGE_KEYWORDS.items():
        if keyword in command:
            return name
    return "English"


# ------------------------------------------------------------------
# CLEAN OLLAMA OUTPUT
# ------------------------------------------------------------------

def clean_answer(text):
    if not text:
        return ""

    text = str(text).strip()

    text = re.sub(r"think.*?response", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"think.*$", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = text.replace("response", "")

    bad_prefixes = [
        "okay, the user is asking", "the user is asking",
        "we are given a user query", "according to the rules",
        "let me think", "first, i need to", "i need to respond",
        "i should respond", "my response should", "let's think",
        "we need to answer", "the question is asking", "i recall that",
    ]

    good_lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(line.lower().startswith(prefix) for prefix in bad_prefixes):
            continue
        good_lines.append(line)

    text = " ".join(good_lines)
    text = text.replace("**", "").replace("__", "").replace("```", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ------------------------------------------------------------------
# MAIN CHAT
# ------------------------------------------------------------------

def ask_ai(question, target_language="English", history=None, user_name=""):
    today_str = datetime.date.today().strftime("%B %d, %Y")

    search_context = ""
    if needs_realtime_info(question):
        results = web_search(question)
        if results:
            search_context = f"""
Live web search results for this question. Use them to answer accurately:
{results}
"""

    name_hint = f"\nThe user's name is {user_name}. Address them as 'Boss' occasionally." if user_name else ""

    system_prompt = f"""You are Orion {SPOKEN_NAME}, a powerful personal AI assistant for Windows, helping a human.
Today's date is {today_str}.{name_hint}

Answer the user's question directly.
IMPORTANT:
- Reply ONLY in {target_language}. If it is not English, use its native script
  (Telugu, Devanagari, Tamil, Kannada) - never romanized text.
- Never show reasoning, never say "the user is asking", never use thinking tags.
- Keep answers short and natural because they will be spoken aloud.
- ALWAYS finish your sentence completely; wrap up early if running long.
- No markdown, bullets, tables or headings.
{search_context}"""

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        for entry in history[-8:]:
            role = entry.get("role")
            content = entry.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": question})

    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": 0.2, "num_predict": MAX_ANSWER_TOKENS},
    }

    try:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            CHAT_URL, data=body,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))

        answer = clean_answer(result.get("message", {}).get("content", ""))
        return answer or "I couldn't generate an answer."

    except urllib.error.URLError:
        return "I cannot connect to my local AI brain."
    except Exception as error:
        print("AI ERROR:", error)
        return "I had trouble processing that."


# ------------------------------------------------------------------
# SCREEN VISION (describe what is on screen)
# ------------------------------------------------------------------

VISION_MODEL_HINTS = ("vl", "llava", "vision", "moondream", "minicpm", "gemma3", "bakllava")


def list_local_models():
    try:
        request = urllib.request.Request(TAGS_URL, method="GET")
        with urllib.request.urlopen(request, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
        return [model.get("name", "") for model in data.get("models", [])]
    except Exception:
        return []


def is_vision_available():
    return bool(visual_model())


def visual_model():
    """Return the first installed model that can understand images."""
    for model in list_local_models():
        lowered = model.lower()
        if any(hint in lowered for hint in VISION_MODEL_HINTS):
            return model
    return None


def ask_vision(prompt, image_path):
    """Send an image to a local vision model and return its description."""
    model = visual_model()
    if not model:
        return None
    if not os.path.exists(image_path):
        return None

    try:
        with open(image_path, "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("utf-8")
    except OSError as error:
        print("VISION IMAGE ERROR:", error)
        return None

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [encoded],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 220},
    }

    try:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            GENERATE_URL, data=body,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
        return clean_answer(result.get("response", "")) or None
    except Exception as error:
        print("VISION ERROR:", error)
        return None


if __name__ == "__main__":
    question = input("YOU: ")
    print("ORION:", ask_ai(question))