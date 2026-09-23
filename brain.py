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
import urllib.parse

from duckduckgo_search import DDGS

OLLAMA_URL = "http://127.0.0.1:11434"
CHAT_URL = f"{OLLAMA_URL}/api/chat"
GENERATE_URL = f"{OLLAMA_URL}/api/generate"
TAGS_URL = f"{OLLAMA_URL}/api/tags"

MODEL = "qwen3:4b-instruct"

# Cooler identities for the assistant voice.
SPOKEN_NAME = "Oh-ree-yon"

MAX_ANSWER_TOKENS = 200


def resolve_model():
    """Pick the configured Ollama model (memory preference or auto-detected)."""
    import memory as mem
    preferred = mem.get_preference("model")
    models = list_local_models()
    if preferred and preferred in models:
        return preferred
    if MODEL in models:
        return MODEL
    if models:
        return models[0]
    return MODEL


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
        "model": resolve_model(),
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
# ADDITIONAL ONLINE TOOLS (weather / news / translate / summarize)
# ------------------------------------------------------------------

def translate_text(text, language="English"):
    """Translate text through free online endpoints (MyMemory, then Google)."""
    lang_codes = {
        "telugu": "te", "hindi": "hi", "tamil": "ta", "kannada": "kn",
        "english": "en", "spanish": "es", "french": "fr", "german": "de",
        "japanese": "ja", "korean": "ko", "chinese": "zh-CN", "russian": "ru",
    }
    code = lang_codes.get(language.lower(), language.lower())
    encoded_query = urllib.parse.quote(text)
    attempt = 0

    while attempt < 3:
        if attempt % 2 == 0:
            url = f"https://api.mymemory.translated.net/get?q={encoded_query}&langpair=en|{code}"
        else:
            url = ("https://translate.googleapis.com/translate_a/single"
                   f"?client=gtx&sl=auto&tl={code}&dt=t&q={encoded_query}")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            if attempt % 2 == 0 and isinstance(data, dict) and data.get("responseData"):
                translated = (data.get("responseData") or {}).get("translatedText", "")
                if translated:
                    return translated.strip()
            elif attempt % 2 == 1:
                translated = "".join(part[0] or "" for part in data[0])
                return translated.strip() or "Translation failed."
        except Exception as error:
            print("TRANSLATE ERROR:", error)
        attempt += 1
        time.sleep(1.2)

    return "I couldn't translate that right now."


def get_weather(city=""):
    """Current weather through wttr.in (no API key needed)."""
    try:
        if city:
            url = f"https://wttr.in/{urllib.parse.quote(city)}?format=3"
        else:
            url = "https://wttr.in/?format=3"
        request = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8").strip()
        if raw and "Unknown location" not in raw:
            return f"Current weather: {raw}"
        return "I couldn't find weather for that place."
    except Exception as error:
        print("WEATHER ERROR:", error)
        return "I couldn't fetch the weather right now."


def get_news(topic=""):
    """Top headlines through DuckDuckGo News."""
    try:
        with DDGS() as ddgs:
            query = topic.strip() or "today"
            results = list(ddgs.news(query, max_results=3))
        headlines = []
        for result in results:
            title = result.get("title", "")
            source = result.get("source", "")
            if title:
                headlines.append(f"{title} from {source}".strip())
        if headlines:
            return "Latest news: " + " ".join(headlines[:3])
        return "I couldn't find news right now."
    except Exception as error:
        print("NEWS ERROR:", error)
        return "I couldn't fetch the news right now."


def summarize_text(text, target_language="English"):
    """Ask the AI brain to summarize a chunk of text."""
    system_prompt = (
        "You are a helpful summarizer. Give a short spoken summary in no more "
        f"that 4 sentences, in plain language, in {target_language}. No markdown."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Summarize this text: {text[:4000]}"},
    ]
    payload = {
        "model": resolve_model(),
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
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
        return clean_answer(result.get("message", {}).get("content", ""))
    except Exception as error:
        print("SUMMARIZE ERROR:", error)
        return ""


# ------------------------------------------------------------------
# TOOL-CALLING (model asks Orion to run actions) 
# ------------------------------------------------------------------

def ask_ai_with_tools(question, target_language="English", history=None, user_name=""):
    """Let the model decide to run Orion tools mid-conversation.

    Falls back to a plain chat answer when the model does not support
    function calling (some small models ignore tools).
    """
    from tools import TOOL_SCHEMA, execute_tool

    today_str = datetime.date.today().strftime("%B %d, %Y")
    facts = memory_context = ""
    try:
        import memory as mem
        memory_context = mem.context_for_ai()
    except Exception:
        pass

    system_prompt = f"""You are Orion {SPOKEN_NAME}, an AI assistant for Windows with real tools.
Today's date is {today_str}.
{('' if not memory_context else 'Memory: ' + memory_context + '.')}
The user prefers you answer in {target_language} (native script if not English).

You have tools available. If the user's request can be fulfilled with a tool,
call the tool instead of answering. If several tools could help, pick the best one.
Never invent tool names. If the tool you need is not available, just answer directly.
Speak short, natural sentences with no markdown when you give a final answer.
Always finish your final answer completely."""

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for entry in list(history)[-8:]:
            role = entry.get("role")
            content = entry.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    for turn in range(4):
        payload = {
            "model": resolve_model(),
            "messages": messages,
            "stream": False,
            "tools": TOOL_SCHEMA,
            "keep_alive": "10m",
            "options": {"temperature": 0.2, "num_predict": MAX_ANSWER_TOKENS + 120},
        }
        try:
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                CHAT_URL, data=body,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            print("TOOL CHAT ERROR:", error)
            return ask_ai(question, target_language=target_language,
                          history=history, user_name=user_name)

        message = result.get("message", {})
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            answer = clean_answer(message.get("content", ""))
            return answer or "I didn't catch that. Can you say it again?"

        messages.append(message)

        for call in tool_calls:
            function = call.get("function", {})
            name = function.get("name", "")
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {}
            tool_result = ""
            try:
                tool_result = str(execute_tool(name, arguments))
            except Exception as error:
                tool_result = f"Tool error: {error}"
            messages.append({"role": "tool", "content": tool_result or "done"})

    return "I did my best, Boss. Ask me again if you need more help."


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


def ask_vision(prompt, image_path, num_predict=220):
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
        "options": {"temperature": 0.3, "num_predict": num_predict},
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