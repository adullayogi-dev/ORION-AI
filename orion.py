# ORION AI ASSISTANT
# Upgrade complete: tool-calling brain, offline STT, live transcript window,
# system control, reminders, scheduler, tray icon, packaging and autostart.

import asyncio
import ctypes
import os
import re
import sys
import time
import traceback
from collections import deque

import numpy as np
import pygame
import sounddevice as sd
import speech_recognition as sr
import edge_tts

import memory
import packaging
import stt
import system_control
from brain import SPOKEN_NAME, ask_ai_with_tools, clean_answer, detect_requested_language, start_ollama
from commands import execute_command, set_confirm_callback
from island import OrionIsland
from scheduler import Scheduler

# ============================================================
# ORION CONFIG
# ============================================================

SAMPLE_RATE = 16000
SILENCE_SECONDS = 0.55
MAX_LISTEN_SECONDS = 10

MIN_VOICE_THRESHOLD = 160
NOISE_MULTIPLIER = 2.4
PRE_ROLL_SECONDS = 0.35

BLOCK_SAMPLES = 1600                     # 100 ms at 16 kHz
CALIBRATION_SECONDS = 0.8
SPEECH_REQUIRED_BLOCKS = 3               # ~300 ms of real speech before recording
MIN_UTTERANCE_SECONDS = 0.45             # discard short noise bursts
NOISE_ADAPT_RATE = 0.03
# Wake mode is deliberately stricter: TV/radio speech must not wake Orion.
WAKE_NOISE_MULTIPLIER = 4.0
WAKE_MIN_THRESHOLD = 500
WAKE_MAX_SECONDS = 3.0
MIC_BLOCKED_UNTIL = 0.0                  # prevents hearing Orion's own answers

SPEECH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orion_speech.mp3")
SPEECH_RATE = "+10%"
SPEECH_PITCH = "-1Hz"

WAKE_WORDS = [
    "hey orion", "hi orion", "hello orion", "okay orion", "ok orion",
    "hey orian", "hi orian", "hello orian", "okay orian", "ok orian",
    "hey ryan", "hi ryan", "hello ryan", "okay ryan", "ok ryan",
    "hey arion", "hi arion", "hello arion",
]


GREETING_WORDS = {"hello", "hey", "hi", "okay", "ok", "yo", "good"}
NAME_WORDS = {"orion", "orian", "ryan", "arion", "oreon", "orryan", "ohrion", "orien"}


def wake_match(text):
    """Return (is_wake, remaining_command) for a spoken wake phrase.

    Tolerates punctuation, missing spaces and common Whisper mishearings
    ("Hello, Ryan open Chrome", "helloryan open chrome", "hey orien ...").
    """
    normalized = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()

    for phrase in WAKE_WORDS:
        pattern = r"\b" + r"\s*".join(re.escape(word) for word in phrase.split()) + r"\b"
        match = re.search(pattern, normalized)
        if match:
            return True, normalized[match.end():].strip()

    # Fuzzy fallback: a name-like word with a greeting just before it, or the
    # name on its own. This catches spellings Whisper invents.
    tokens = re.findall(r"[a-z]+", normalized)
    for index, token in enumerate(tokens):
        if token not in NAME_WORDS:
            continue
        previous = tokens[max(0, index - 2):index]
        if any(word in GREETING_WORDS for word in previous) or len(tokens) == 1:
            return True, " ".join(tokens[index + 1:])
    return False, ""

SLEEP_WORDS = ["sleep", "go to sleep", "sleep now", "sleep orion", "goodnight orion"]
STOP_WORDS = ["stop", "exit", "quit", "bye", "goodbye"]

MAX_SILENT_TURNS = 3
LAST_AUDIO_ERROR_LOG = 0.0
OLLAMA_READY = False
SILENT_MODE = False

SINGLE_INSTANCE_MUTEX = None
ISLAND: OrionIsland | None = None


class StopRequested(Exception):
    """Raised when the user asks Orion to quit (tray / orb / voice)."""


def ensure_single_instance():
    global SINGLE_INSTANCE_MUTEX
    kernel32 = ctypes.windll.kernel32
    # Clear any stale error first, then read GetLastError immediately after
    # CreateMutexW. ERROR_ALREADY_EXISTS (183) means another Orion owns it.
    kernel32.SetLastError(0)
    SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(
        None, False, "Local\\ORION_AI_VOICE_ASSISTANT"
    )

    if not SINGLE_INSTANCE_MUTEX:
        print("ORION: Could not create the single-instance lock.")
        return False

    if kernel32.GetLastError() == 183:
        print("Orion is already running. Close the existing assistant before starting another one.")
        return False

    return True


# ============================================================
# MULTI-LANGUAGE VOICE
# ============================================================

VOICE_MAP = {
    "te": "te-IN-MohanNeural",
    "hi": "hi-IN-MadhurNeural",
    "ta": "ta-IN-ValluvarNeural",
    "kn": "kn-IN-GaganNeural",
    "en": "en-US-GuyNeural",
}


def detect_script_language(text):
    if re.search(r"[\u0C00-\u0C7F]", text):
        return "te"
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    if re.search(r"[\u0B80-\u0BFF]", text):
        return "ta"
    if re.search(r"[\u0C80-\u0CFF]", text):
        return "kn"
    return "en"


def set_speech_rate(rate):
    global SPEECH_RATE
    SPEECH_RATE = rate


async def _generate_speech(text, voice):
    communicate = edge_tts.Communicate(text, voice, rate=SPEECH_RATE, pitch=SPEECH_PITCH)
    await communicate.save(SPEECH_FILE)


def speak(text):
    global MIC_BLOCKED_UNTIL
    text = clean_answer(text)
    if not text:
        return

    try:
        print("ORION:", text)
        packaging.log("ORION: " + text)
    except UnicodeEncodeError:
        pass

    if ISLAND is not None:
        ISLAND.log("assistant", text)

    lang = detect_script_language(text)
    voice = VOICE_MAP.get(lang, VOICE_MAP["en"])

    try:
        asyncio.run(_generate_speech(text, voice))
        pygame.mixer.music.load(SPEECH_FILE)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        pygame.mixer.music.unload()
        # Ignore the tail of our own voice echo before listening again.
        MIC_BLOCKED_UNTIL = time.time() + 0.5
    except Exception as error:
        print("Voice error:", error)


# ============================================================
# MICROPHONE + OFFLINE STT
# ============================================================

def safe_print(*parts):
    """Print without dying on non-ASCII text in pythonw's cp1252 stream."""
    try:
        print(*parts)
    except (UnicodeEncodeError, ValueError):
        try:
            print(" ".join(str(p).encode("ascii", "replace").decode() for p in parts))
        except Exception:
            pass


def volume(audio):
    audio = audio.astype(np.float32)
    return float(np.sqrt(np.mean(audio * audio)))


def speech_features(audio):
    """Return (rms, spectral_flatness, low_frequency_ratio) for one block.

    Speech is tonal and low-frequency. Fans, hiss and keyboard noise are
    broadband/flat. This lets us reject background noise that is louder than
    the simple RMS threshold would allow.
    """
    # sounddevice returns (block, channels); flatten to a 1-D mono array.
    signal = np.asarray(audio, dtype=np.float32).reshape(-1) / 32768.0
    rms = float(np.sqrt(np.mean(signal * signal))) * 32768.0

    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal)))) + 1e-8
    spectrum[0] = 0.0
    frequencies = np.fft.rfftfreq(len(signal), 1.0 / SAMPLE_RATE)
    low_ratio = float(spectrum[frequencies < 1200].sum() / (spectrum.sum() + 1e-8))

    usable = spectrum[spectrum > 1e-6]
    flatness = (
        float(np.exp(np.mean(np.log(usable))) / (np.mean(usable) + 1e-8))
        if usable.size else 1.0
    )
    return rms, flatness, low_ratio


def looks_like_speech(features, threshold):
    rms, flatness, low_ratio = features
    if rms < threshold:
        return False
    return flatness < 0.42 or low_ratio > 0.62


def record_command(strict=False):
    """Record a real utterance, ignoring steady background noise.

    strict=True is used for wake-word detection: a louder threshold and a
    short window keep TV/radio chatter in the room from waking Orion.
    Returns AudioData, or None if no convincing speech was heard.
    """
    global MIC_BLOCKED_UNTIL

    min_threshold = WAKE_MIN_THRESHOLD if strict else MIN_VOICE_THRESHOLD
    multiplier = WAKE_NOISE_MULTIPLIER if strict else NOISE_MULTIPLIER
    max_seconds = WAKE_MAX_SECONDS if strict else MAX_LISTEN_SECONDS

    # Never listen to Orion's own answer playing through the speakers.
    remaining = MIC_BLOCKED_UNTIL - time.time()
    if remaining > 0:
        time.sleep(min(remaining, 1.0))

    print()
    print("ORION is listening...")
    print("Speak now!")

    chunks = []
    pre_roll = deque(maxlen=max(1, int(PRE_ROLL_SECONDS * SAMPLE_RATE / BLOCK_SAMPLES)))
    started = False
    voice_blocks = 0
    silent_blocks = 0
    beginning = time.time()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=BLOCK_SAMPLES,
    ) as stream:
        # Calibrate the current room noise. 75th percentile avoids a single
        # cough making the threshold too low for everything afterwards.
        calibration = []
        blocks = max(3, int(CALIBRATION_SECONDS * SAMPLE_RATE / BLOCK_SAMPLES))
        for _ in range(blocks):
            audio, overflow = stream.read(BLOCK_SAMPLES)
            if not overflow:
                calibration.append(speech_features(audio.copy()))

        if calibration:
            noise_rms = float(np.percentile([f[0] for f in calibration], 75))
        else:
            noise_rms = float(MIN_VOICE_THRESHOLD)
        threshold = max(min_threshold, noise_rms * multiplier)
        print(f"Microphone ready (threshold: {threshold:.0f})")

        while True:
            audio, overflow = stream.read(BLOCK_SAMPLES)
            if overflow:
                continue
            audio = audio.copy().reshape(-1)
            features = speech_features(audio)
            speech = looks_like_speech(features, threshold)

            if not started:
                pre_roll.append(audio)
                if speech:
                    voice_blocks += 1
                    if voice_blocks >= SPEECH_REQUIRED_BLOCKS:
                        started = True
                        chunks.extend(pre_roll)
                        chunks.append(audio)
                        silent_blocks = 0
                        print("Voice detected")
                else:
                    voice_blocks = 0
                    noise_rms += (features[0] - noise_rms) * NOISE_ADAPT_RATE
                    threshold = max(min_threshold, noise_rms * multiplier)
            else:
                chunks.append(audio)
                if speech:
                    silent_blocks = 0
                else:
                    silent_blocks += 1
                    if silent_blocks * BLOCK_SAMPLES / SAMPLE_RATE >= SILENCE_SECONDS:
                        break

            if time.time() - beginning >= max_seconds:
                break

    print()
    print("Processing your voice...")

    if not started:
        return None

    duration = len(chunks) * BLOCK_SAMPLES / SAMPLE_RATE
    if duration < MIN_UTTERANCE_SECONDS:
        return None

    recording = np.concatenate(chunks, axis=0)
    return sr.AudioData(recording.tobytes(), SAMPLE_RATE, 2)


def listen(mode="command"):
    """Record and transcribe offline (Whisper), Google as fallback.

    mode='wake' uses a stricter, shorter recording so room noise is ignored.
    Never let a microphone/driver hiccup kill the assistant.
    """
    global LAST_AUDIO_ERROR_LOG
    try:
        audio_data = record_command(strict=(mode == "wake"))
        if audio_data is None:
            return None

        text, engine = stt.recognize(audio_data, language="en-IN")
        text = text.strip()
        if not text:
            print("ORION: I couldn't understand that.")
            return ""
        safe_print(f"YOU:{engine}", text)
        return text.lower()
    except Exception as error:
        detail = f"LISTEN ERROR: {type(error).__name__}: {error}"
        safe_print(detail)
        # Log audio-device hiccups sparingly; they can repeat every second.
        now = time.time()
        if now - LAST_AUDIO_ERROR_LOG >= 60:
            packaging.log(detail)
            LAST_AUDIO_ERROR_LOG = now
        time.sleep(1.5)
        return None


# ============================================================
# WAKE WORD / QUICK RESPONSES
# ============================================================

def wait_for_wake_word(island=None):
    print()
    print("Waiting for wake word ('Hey Orion')...")

    while True:
        # Tray/Quit must work even while Orion is sleeping.
        if island is not None:
            control = island.take_control()
            if control == "stop":
                raise StopRequested()
            # "sleep" is a no-op here - we are already asleep.

        heard = listen(mode="wake")
        if not heard:
            continue
        is_wake, remainder = wake_match(heard)
        if is_wake:
            # "hello Orion, open Chrome" -> also execute "open Chrome".
            return remainder


def quick_response(command):
    command = command.lower().strip()

    if command in ["hello", "hi", "hey", "hello orion", "hi orion", "hey orion"]:
        return "Hello Boss. How can I help you?"
    if "good morning" in command:
        return "Good morning, Boss. How can I help you?"
    if "good afternoon" in command:
        return "Good afternoon, Boss. How can I help you?"
    if "good evening" in command:
        return "Good evening, Boss. How can I help you?"
    if "what is your name" in command or "who are you" in command:
        return f"I'm {SPOKEN_NAME}, your personal AI assistant, Boss."
    if "what can you do" in command or "what do you do" in command:
        return ("I can open any app, take photos and screenshots, watch your screen, "
                "read and summarize files, set reminders, control volume and brightness, "
                "check battery and Wi-Fi, translate, tell weather and news, type and click, "
                "and answer your questions, Boss.")
    if "thank you" in command or "thanks" in command:
        return "You're welcome, Boss."
    if "how are you" in command:
        return "I'm doing great, Boss. Ready to help."
    return None


# ============================================================
# COMMAND HANDLING
# ============================================================

def is_stop_command(command):
    command = command.strip()
    if command in STOP_WORDS:
        return True
    if "close orion" in command or "shutdown orion" in command:
        return True
    return False


def is_sleep_command(command):
    return any(word in command for word in SLEEP_WORDS)


def ask_confirmation(prompt):
    """Confirm destructive actions by voice. Returns True/False."""
    speak(prompt)
    reply = listen()
    if not reply:
        return False
    return any(word in reply for word in
               ("yes", "yeah", "yep", "sure", "do it", "go ahead", "confirm", "okay", "ok "))


def remember(history, role, text):
    text = clean_answer(text)
    if not text:
        return
    if len(text) > 400:
        text = text[:400] + "..."
    history.append({"role": role, "content": text})
    while len(history) > 12:
        history.popleft()
    memory.remember_turn(role, text)


# ============================================================
# MAIN LOOP
# ============================================================

def run_orion(island):
    global OLLAMA_READY, SILENT_MODE
    history = deque()

    while True:
        if SILENT_MODE:
            island.hide()
        else:
            # Keep the blue orb visible while idle when run interactively.
            island.show("ORION SLEEPING", "Say hello Orion")
        # Silent by design: sleeping is logged, never spoken.
        packaging.log(f"STATE: sleeping (pid {os.getpid()})")
        spoken_with_wake = wait_for_wake_word(island)
        packaging.log("STATE: wake word detected")

        island.show("ORION AWAKE", "Listening...")
        packaging.log("STATE: awake")
        speak("Yes, Boss?")
        silent_turns = 0
        # Support "hello Orion, open Chrome" as one utterance.
        pending_command = spoken_with_wake.strip()

        while True:
            control = island.take_control()
            if control:
                packaging.log(f"CONTROL: {control}")
            if control == "sleep":
                break
            if control == "stop":
                island.close()
                speak("Goodbye. See you later.")
                return

            command = pending_command if pending_command else listen()
            pending_command = ""

            if command is None:
                silent_turns += 1
                if silent_turns >= MAX_SILENT_TURNS:
                    packaging.log("STATE: auto-sleep (no audio)")
                    break
                continue

            if not command:
                speak("I did not catch that. Please say it again.")
                continue

            silent_turns = 0
            remember(history, "user", command)

            if is_stop_command(command):
                packaging.log("STATE: voice stop")
                island.close()
                speak("Goodbye. See you later.")
                return

            if is_sleep_command(command):
                packaging.log("STATE: voice sleep")
                break

            try:
                quick = quick_response(command)
                if quick:
                    remember(history, "assistant", quick)
                    speak(quick)
                    continue

                result = execute_command(command)
                if result:
                    remember(history, "assistant", result)
                    speak(result)
                    continue

                target_language = detect_requested_language(command)
                if not OLLAMA_READY:
                    # Start the local model only when an AI answer is actually
                    # needed - keeps startup fast and memory low.
                    start_ollama(silent=True)
                    OLLAMA_READY = True
                answer = ask_ai_with_tools(
                    command,
                    target_language=target_language,
                    history=list(history),
                    user_name=memory.get_user_name(),
                )
                remember(history, "assistant", answer)
                speak(answer)
            except Exception as error:
                detail = f"COMMAND ERROR: {type(error).__name__}: {error}"
                print(detail)
                packaging.log(detail)
                speak("Sorry Boss, something went wrong. Please try again.")


def reminder_fired():
    """Notification + spoken reminder when a scheduled reminder is due."""

    def fire(text):
        if ISLAND is not None:
            ISLAND.show("ORION REMINDER", "Speaking")
        try:
            speak(f"Reminder. {text}")
        except Exception:
            pass
        try:
            import winotify
            toast = winotify.Notification(app_id="ORION AI", title="Orion Reminder", msg=text)
            toast.show()
        except Exception as error:
            print("TOAST ERROR:", error)

    return fire


# ============================================================
# START
# ============================================================

def main():
    global ISLAND, SILENT_MODE

    # VS Code / normal run: the blue orb is visible. --silent is only used by
    # the optional background launcher and keeps everything hidden.
    SILENT_MODE = "--silent" in sys.argv

    if not ensure_single_instance():
        raise SystemExit(0)

    packaging.setup_logging()
    packaging.clear_explicit_stop()
    packaging.log(f"LAUNCH: pid={os.getpid()} exe={sys.executable} args={sys.argv[1:]}")
    packaging.log("ORION starting.")

    pygame.mixer.init()

    print()
    print("======================================")
    print("          ORION AI ASSISTANT")
    print("======================================")
    print()

    # Orion does not start at login by default; you launch it from VS Code.
    if "--no-autostart" in sys.argv:
        system_control.set_autostart(False)
    print("Autostart:", "ON" if packaging.is_autostart_enabled() else "OFF")

    ISLAND = OrionIsland()
    ISLAND.start()
    if not SILENT_MODE:
        ISLAND.show("ORION", "Ready - say hello Orion")

    scheduler_manager = Scheduler()
    scheduler_manager.on_fire(reminder_fired())
    scheduler_manager.start()

    set_confirm_callback(ask_confirmation)

    packaging.tray_icon(on_sleep=lambda: ISLAND.request_sleep() if ISLAND else None,
                        on_stop=lambda: ISLAND.request_stop() if ISLAND else None)

    # No spoken greeting and no Ollama launch here: login must be silent and
    # fast. The model starts on the first real question instead.
    packaging.log(f"READY: say hello {SPOKEN_NAME}")

    try:
        run_orion(ISLAND)
    except KeyboardInterrupt:
        print()
        print("ORION: Shutting down. Goodbye!")
    except StopRequested:
        packaging.log("STATE: stop requested")
    except Exception:
        detail = "FATAL ERROR:\n" + traceback.format_exc()
        print(detail)
        packaging.log(detail)
    finally:
        packaging.log("STATE: shutting down")
        scheduler_manager.stop()
        if ISLAND is not None:
            if ISLAND.explicit_stop:
                packaging.mark_explicit_stop()
            # Waits until the Tk thread has destroyed its own root.
            ISLAND.close()
        packaging.log("ORION stopped.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        detail = "STARTUP FATAL ERROR:\n" + traceback.format_exc()
        print(detail)
        try:
            with open(packaging.LOG_FILE, "a", encoding="utf-8") as handle:
                handle.write(detail + "\n")
        except Exception:
            pass