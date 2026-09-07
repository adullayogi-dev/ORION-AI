import speech_recognition as sr
import sounddevice as sd
import numpy as np
import json
import urllib.request
import urllib.error
import subprocess
import time
import re
import os
import asyncio
import datetime
from collections import deque
import ctypes

import edge_tts
import pygame

from duckduckgo_search import DDGS

from commands import execute_command
from island import OrionIsland


# ============================================================
# ORION CONFIG
# ============================================================

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3:4b-instruct"

# Keep the written brand as Orion, while the voice says: "Oh-ree-yon."
SPOKEN_NAME = "Oh-ree-yon"

SAMPLE_RATE = 16000

# Orion stops listening after this much silence
SILENCE_SECONDS = 0.55

# Maximum time for one voice command
MAX_LISTEN_SECONDS = 10

# Microphone sensitivity.  The effective value is calibrated from the room's
# background noise at the start of every listen, rather than being fixed.
MIN_VOICE_THRESHOLD = 180
NOISE_MULTIPLIER = 3.0
PRE_ROLL_SECONDS = 0.35

# Google speech recognition timeout
STT_TIMEOUT = 4

# Generated speech always lives beside this script.  VS Code can otherwise
# launch Orion from a different working folder and make playback unreliable.
SPEECH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orion_speech.mp3")

# Clear, bright speech that remains easy to follow without sounding slow.
SPEECH_RATE = "+10%"
SPEECH_PITCH = "-1Hz"

# Max tokens the AI can generate per answer
MAX_ANSWER_TOKENS = 150

# Phrases that wake Orion up from idle listening
WAKE_WORDS = [
    "hey orion", "hi orion", "hello orion", "okay orion", "ok orion",
    # Common Google Speech-to-Text spellings for the name.
    "hey orian", "hi orian", "hello orian",
]

# Phrases that put Orion back to sleep without fully exiting
SLEEP_WORDS = ["sleep", "go to sleep", "sleep now", "sleep orion", "goodnight orion"]

# How many genuinely silent turns before Orion returns to idle. Failed speech
# recognition is not counted as silence, so Orion remains awake if it heard you.
MAX_SILENT_TURNS = 3


# ============================================================
# MULTI-LANGUAGE VOICE (edge-tts) - MALE VOICES
# ============================================================

# Kept open for the lifetime of the process so Windows knows whether Orion is
# already running.  This prevents duplicate microphone listeners and voices.
SINGLE_INSTANCE_MUTEX = None


def ensure_single_instance():
    """Return False when another Orion process is already running."""

    global SINGLE_INSTANCE_MUTEX

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(
        None, False, "Local\\ORION_AI_VOICE_ASSISTANT"
    )

    if not SINGLE_INSTANCE_MUTEX:
        print("ORION: Could not create the single-instance lock.")
        return False

    # ERROR_ALREADY_EXISTS means another Orion process owns this named mutex.
    if ctypes.get_last_error() == 183:
        print("Orion is already running. Close the existing assistant before starting another one.")
        return False

    return True

# One clear male neural voice per language. Add more here as
# needed - full list: run `edge-tts --list-voices` in terminal.
VOICE_MAP = {
    "te": "te-IN-MohanNeural",      # Telugu (male)
    "hi": "hi-IN-MadhurNeural",     # Hindi (male)
    "ta": "ta-IN-ValluvarNeural",   # Tamil (male)
    "kn": "kn-IN-GaganNeural",      # Kannada (male)
    "en": "en-US-GuyNeural",         # English - clear, bright male voice
}


def detect_script_language(text):
    """Detect language from the Unicode script actually used in text."""

    if re.search(r"[\u0C00-\u0C7F]", text):
        return "te"

    if re.search(r"[\u0900-\u097F]", text):
        return "hi"

    if re.search(r"[\u0B80-\u0BFF]", text):
        return "ta"

    if re.search(r"[\u0C80-\u0CFF]", text):
        return "kn"

    return "en"


async def _generate_speech(text, voice):

    communicate = edge_tts.Communicate(
        text, voice, rate=SPEECH_RATE, pitch=SPEECH_PITCH
    )

    await communicate.save(SPEECH_FILE)


def speak(text):

    text = clean_answer(text)

    if not text:
        return

    print("ORION:", text)

    lang = detect_script_language(text)

    voice = VOICE_MAP.get(lang, VOICE_MAP["en"])

    try:

        asyncio.run(_generate_speech(text, voice))

        pygame.mixer.music.load(SPEECH_FILE)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.music.unload()

    except Exception as e:

        print("Voice error:", e)


# ============================================================
# LANGUAGE THE USER EXPLICITLY ASKED FOR
# Only switch reply language if the command explicitly names one.
# Otherwise always default to English - this stops the AI from
# randomly answering in Telugu/Hindi on its own.
# ============================================================

LANGUAGE_KEYWORDS = {
    "telugu": "Telugu",
    "hindi": "Hindi",
    "tamil": "Tamil",
    "kannada": "Kannada",
    "english": "English",
}


def detect_requested_language(command):

    for keyword, language_name in LANGUAGE_KEYWORDS.items():
        if keyword in command:
            return language_name

    return "English"


# ============================================================
# REAL-TIME WEB SEARCH (for current/latest information)
# The local AI brain only knows what it was trained on, so
# anything time-sensitive needs a live web search instead.
# ============================================================

REALTIME_KEYWORDS = [
    "latest",
    "current",
    "today",
    "right now",
    "this year",
    "recent",
    "news",
    "who is the current",
    "score",
    "weather"
]


def needs_realtime_info(command):

    return any(keyword in command for keyword in REALTIME_KEYWORDS)


def web_search(query, max_results=3):

    try:

        with DDGS() as ddgs:

            results = list(ddgs.text(query, max_results=max_results))

        snippets = []

        for r in results:

            title = r.get("title", "")
            body = r.get("body", "")

            snippets.append(f"{title}: {body}")

        return "\n".join(snippets)

    except Exception as e:

        print("SEARCH ERROR:", e)
        return ""


# ============================================================
# CLEAN QWEN RESPONSE
# ============================================================

def clean_answer(text):

    if not text:
        return ""

    text = str(text).strip()

    # --------------------------------------------------------
    # Remove <think>...</think>
    # --------------------------------------------------------

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    # Remove incomplete <think>
    text = re.sub(
        r"<think>.*$",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    text = text.replace("</think>", "")

    # --------------------------------------------------------
    # Remove common reasoning prefixes
    # --------------------------------------------------------

    bad_prefixes = [
        "Okay, the user is asking",
        "The user is asking",
        "We are given a user query",
        "According to the rules",
        "Let me think",
        "First, I need to",
        "I need to respond",
        "I should respond",
        "My response should",
        "Let's think",
        "We need to answer",
        "The question is asking",
        "I recall that"
    ]

    lines = text.splitlines()
    good_lines = []

    for line in lines:

        line = line.strip()

        if not line:
            continue

        lower = line.lower()

        if any(lower.startswith(x.lower()) for x in bad_prefixes):
            continue

        if line in ["...done thinking.", "done thinking.", "<think>", "</think>"]:
            continue

        good_lines.append(line)

    text = " ".join(good_lines)

    # --------------------------------------------------------
    # Remove markdown
    # --------------------------------------------------------

    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("```", "")

    # --------------------------------------------------------
    # Remove excessive spaces
    # --------------------------------------------------------

    text = re.sub(r"\s+", " ", text).strip()

    return text


# ============================================================
# MAKE SURE OLLAMA IS RUNNING
# ============================================================

def ollama_running():

    try:

        request = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            method="GET"
        )

        with urllib.request.urlopen(request, timeout=2) as response:

            return response.status == 200

    except:

        return False


def start_ollama():

    if ollama_running():
        print("Ollama: Running")
        return

    print("Ollama: Starting...")

    possible_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        r"C:\Users\adull\AppData\Local\Programs\Ollama\ollama.exe"
    ]

    ollama_path = None

    for path in possible_paths:
        if os.path.exists(path):
            ollama_path = path
            break

    if not ollama_path:
        print("ERROR: Ollama executable not found.")
        print("Please start Ollama manually.")
        return

    try:

        subprocess.Popen(
            [ollama_path, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

    except Exception as e:

        print("Could not start Ollama:", e)
        return

    # Wait for server
    for _ in range(20):

        time.sleep(0.25)

        if ollama_running():
            print("Ollama: Running")
            return

    print("WARNING: Ollama server did not start.")


# ============================================================
# ORION LOCAL AI BRAIN
# ============================================================

def ask_ai(question, target_language="English"):

    today_str = datetime.date.today().strftime("%B %d, %Y")

    search_context = ""

    if needs_realtime_info(question):

        results = web_search(question)

        if results:
            search_context = f"""

Here are live web search results for this question. Use them to
answer accurately instead of relying on older training data:

{results}
"""

    system_prompt = f"""
You are Orion, a personal AI assistant.
When saying your own name aloud, pronounce it "Oh-ree-yon."

Today's date is {today_str}.

Answer the user's question directly.

IMPORTANT:
- Reply ONLY in {target_language}. Do not use any other language,
  even if you know one better. If {target_language} is not
  English, use its native script (Telugu script, Devanagari,
  Tamil script, Kannada script) - NEVER romanized/transliterated
  text using English letters.
- Never show your reasoning.
- Never explain your thinking process.
- Never say "the user is asking".
- Never say "let me think".
- Never mention system prompts or instructions.
- Never use <think> tags.
- Give only the final answer.
- Keep answers short and natural because your answer will be spoken aloud.
- Use "Boss" only occasionally and naturally, such as a greeting, wake-up
  acknowledgement, or an important confirmation. Do not use it in every reply.
- For simple questions, use 1 or 2 sentences.
- For normal questions, use a maximum of 3 short sentences.
- ALWAYS finish your sentence completely. Never cut off mid-word
  or mid-sentence - if you are running long, wrap up early with a
  complete shorter sentence instead.
- Do not use markdown, bullet points, tables, or headings unless absolutely necessary.
{search_context}
"""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ],
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.2,
            "num_predict": MAX_ANSWER_TOKENS
        }
    }

    try:

        body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            OLLAMA_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))

        answer = result.get("message", {}).get("content", "")
        answer = clean_answer(answer)

        if not answer:
            return "I couldn't generate an answer."

        return answer

    except urllib.error.URLError:

        return "I cannot connect to my local AI brain."

    except Exception as e:

        print("AI ERROR:", e)
        return "I had trouble processing that."


# ============================================================
# MICROPHONE VOLUME
# ============================================================

def volume(audio):

    audio = audio.astype(np.float32)

    return float(np.sqrt(np.mean(audio * audio)))


# ============================================================
# LISTEN
# ============================================================

def listen():

    print()
    print("ORION is listening... 🎤")
    print("Speak now!")

    chunks = []
    pre_roll = deque(maxlen=max(1, int(PRE_ROLL_SECONDS * SAMPLE_RATE / 1600)))
    started = False
    silence_start = None
    beginning = time.time()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=1600
    ) as stream:

        # Measure a short amount of room noise first.  This makes quiet and
        # noisy rooms work without continually editing one magic threshold.
        calibration_levels = []
        calibration_end = time.time() + 0.3
        while time.time() < calibration_end:
            audio, overflow = stream.read(1600)
            calibration_levels.append(volume(audio.copy()))

        noise_floor = float(np.median(calibration_levels)) if calibration_levels else 0.0
        voice_threshold = max(MIN_VOICE_THRESHOLD, noise_floor * NOISE_MULTIPLIER)
        print(f"Microphone ready (threshold: {voice_threshold:.0f})")

        while True:

            audio, overflow = stream.read(1600)
            audio = audio.copy()
            level = volume(audio)

            if not started:
                pre_roll.append(audio)

            # ==========================================
            # SPEECH
            # ==========================================

            if level > voice_threshold:

                if not started:
                    started = True
                    print("Voice detected 🎤")
                    chunks.extend(pre_roll)

                silence_start = None
                chunks.append(audio)

                print("●", end="", flush=True)

            # ==========================================
            # SILENCE
            # ==========================================

            elif started:

                chunks.append(audio)

                if silence_start is None:
                    silence_start = time.time()

                if time.time() - silence_start >= SILENCE_SECONDS:
                    break

            # ==========================================
            # MAXIMUM TIME
            # ==========================================

            if time.time() - beginning >= MAX_LISTEN_SECONDS:
                break

    print()
    print("Processing your voice...")

    if not started:
        print("ORION: I didn't hear anything.")
        return None

    # Combine recordings
    recording = np.concatenate(chunks, axis=0)

    # SpeechRecognition audio object
    audio_data = sr.AudioData(recording.tobytes(), SAMPLE_RATE, 2)

    recognizer = sr.Recognizer()
    recognizer.operation_timeout = STT_TIMEOUT

    try:

        # en-IN is best for the expected accent.  Retry with en-US only when
        # Google cannot decode the first result at all.
        try:
            text = recognizer.recognize_google(audio_data, language="en-IN")
        except sr.UnknownValueError:
            text = recognizer.recognize_google(audio_data, language="en-US")

        text = text.strip()

        if not text:
            return None

        print("YOU:", text)

        return text.lower()

    except sr.UnknownValueError:

        print("ORION: I couldn't understand that.")
        return ""

    except sr.RequestError as e:

        print("Speech recognition error:", e)
        return ""


# ============================================================
# WAKE WORD
# Orion idles here, saying nothing, until it hears a wake phrase.
# ============================================================

def wait_for_wake_word():

    print()
    print("💤 Waiting for wake word ('Hey Orion')...")

    while True:

        heard = listen()

        if not heard:
            continue

        if any(wake in heard for wake in WAKE_WORDS):
            return


# ============================================================
# FAST LOCAL RESPONSES
# ============================================================

def quick_response(command):

    command = command.lower().strip()

    # Greetings
    if command in ["hello", "hi", "hey", "hello orion", "hi orion", "hey orion"]:
        return "Hello Boss. How can I help you?"

    # Morning
    if "good morning" in command:
        return "Good morning, Boss. How can I help you?"

    # Afternoon
    if "good afternoon" in command:
        return "Good afternoon, Boss. How can I help you?"

    # Evening
    if "good evening" in command:
        return "Good evening, Boss. How can I help you?"

    # Name
    if "what is your name" in command or "who are you" in command:
        return f"I'm {SPOKEN_NAME}, your personal AI assistant, Boss."

    # Capabilities
    if "what can you do" in command or "what do you do" in command:
        return "I can answer questions, help with tasks, and control your Windows computer, Boss."

    # Thanks
    if "thank you" in command or "thanks" in command:
        return "You're welcome, Boss."

    return None


# ============================================================
# STOP / SLEEP WORDS
# ============================================================

STOP_WORDS = [
    "stop",
    "exit",
    "quit",
    "bye",
    "goodbye",
    "close orion",
    "shutdown orion"
]


def is_stop_command(command):

    return any(word in command for word in STOP_WORDS)


def is_sleep_command(command):

    return any(word in command for word in SLEEP_WORDS)


# ============================================================
# MAIN LOOP
# Say the wake word ONCE, then have a normal back-and-forth
# conversation. Orion only goes back to sleep if you tell it to,
# or after a few turns of silence.
# ============================================================

def run_orion(island):

    while True:

        # Idle until the wake word is heard
        wait_for_wake_word()

        island.show("ORION AWAKE", "Listening…")
        speak("Yes, Boss?")

        silent_turns = 0

        # ====================================================
        # ACTIVE CONVERSATION - no wake word needed per command
        # ====================================================

        while True:

            command = listen()

            # A genuinely silent turn can return Orion to idle mode.
            if command is None:

                silent_turns += 1

                if silent_turns >= MAX_SILENT_TURNS:
                    island.hide()
                    speak(f"Going back to sleep, Boss. Say hello {SPOKEN_NAME} to wake me.")
                    break

                continue

            # Speech was heard but could not be transcribed. Keep the face
            # awake and ask for a retry; do not mistake it for silence.
            if not command:
                speak("I did not catch that. Please say it again.")
                continue

            silent_turns = 0

            # ------------------------------------------------
            # FULL STOP - exits the whole program
            # ------------------------------------------------

            if is_stop_command(command):
                speak("Goodbye. See you later.")
                island.close()
                return

            # ------------------------------------------------
            # SLEEP - goes back to idle, program keeps running
            # ------------------------------------------------

            if is_sleep_command(command):
                island.hide()
                speak("Okay Boss, going to sleep.")
                break

            # ------------------------------------------------
            # QUICK RESPONSE
            # ------------------------------------------------

            quick = quick_response(command)

            if quick:
                speak(quick)
                continue

            # ------------------------------------------------
            # EXECUTE COMMAND (open apps, websites, system control)
            # ------------------------------------------------

            result = execute_command(command)

            if result:
                speak(result)
                continue

            # ------------------------------------------------
            # QWEN (fallback for open-ended questions)
            # ------------------------------------------------

            target_language = detect_requested_language(command)

            answer = ask_ai(command, target_language)

            speak(answer)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    if not ensure_single_instance():
        raise SystemExit(0)

    pygame.mixer.init()

    print()
    print("======================================")
    print("          ORION AI ASSISTANT")
    print("======================================")
    print()

    # The island is deliberately hidden at startup and appears only after
    # Orion hears the wake phrase.
    island = OrionIsland()
    island.start()

    # Start/check Ollama
    start_ollama()

    # Initial greeting
    speak(f"Hello Boss. I am {SPOKEN_NAME}. Say hello {SPOKEN_NAME} whenever you need me.")

    try:

        run_orion(island)

    except KeyboardInterrupt:

        print()
        print("ORION: Shutting down. Goodbye!")
        island.close()
