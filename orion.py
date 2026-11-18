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

MIN_VOICE_THRESHOLD = 180
NOISE_MULTIPLIER = 3.0
PRE_ROLL_SECONDS = 0.35

SPEECH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orion_speech.mp3")
SPEECH_RATE = "+10%"
SPEECH_PITCH = "-1Hz"

WAKE_WORDS = [
    "hey orion", "hi orion", "hello orion", "okay orion", "ok orion",
    "hey orian", "hi orian", "hello orian",
]

SLEEP_WORDS = ["sleep", "go to sleep", "sleep now", "sleep orion", "goodnight orion"]
STOP_WORDS = ["stop", "exit", "quit", "bye", "goodbye"]

MAX_SILENT_TURNS = 3

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
    except Exception as error:
        print("Voice error:", error)


# ============================================================
# MICROPHONE + OFFLINE STT
# ============================================================

def volume(audio):
    audio = audio.astype(np.float32)
    return float(np.sqrt(np.mean(audio * audio)))


def record_command():
    """Record until the user stops talking. Returns AudioData or None."""
    print()
    print("ORION is listening...")
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
        blocksize=1600,
    ) as stream:

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

            if level > voice_threshold:
                if not started:
                    started = True
                    print("Voice detected")
                    chunks.extend(pre_roll)
                silence_start = None
                chunks.append(audio)
            elif started:
                chunks.append(audio)
                if silence_start is None:
                    silence_start = time.time()
                if time.time() - silence_start >= SILENCE_SECONDS:
                    break

            if time.time() - beginning >= MAX_LISTEN_SECONDS:
                break

    print()
    print("Processing your voice...")

    if not started:
        print("ORION: I didn't hear anything.")
        return None

    recording = np.concatenate(chunks, axis=0)
    return sr.AudioData(recording.tobytes(), SAMPLE_RATE, 2)


def listen():
    """Record and transcribe offline (Whisper), Google as fallback.

    Never let a microphone/driver hiccup kill the background assistant.
    """
    try:
        audio_data = record_command()
        if audio_data is None:
            return None

        text, engine = stt.recognize(audio_data, language="en-IN")
        text = text.strip()
        if not text:
            print("ORION: I couldn't understand that.")
            return ""
        print(f"YOU:{engine}", text)
        return text.lower()
    except Exception as error:
        detail = f"LISTEN ERROR: {type(error).__name__}: {error}"
        print(detail)
        packaging.log(detail)
        time.sleep(1.0)
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

        heard = listen()
        if not heard:
            continue
        if any(wake in heard for wake in WAKE_WORDS):
            return


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
    history = deque()

    while True:
        island.hide()
        packaging.log(f"STATE: sleeping (pid {os.getpid()})")
        speak(f"Going to sleep, Boss. Say hello {SPOKEN_NAME} to wake me.")
        wait_for_wake_word(island)
        packaging.log("STATE: wake word detected")

        island.show("ORION AWAKE", "Listening...")
        packaging.log("STATE: awake")
        speak("Yes, Boss?")
        silent_turns = 0

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

            command = listen()

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
    global ISLAND

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

    if "--autostart" in sys.argv:
        system_control.set_autostart(True)
        print("Autostart enabled.")
    if "--no-autostart" in sys.argv:
        system_control.set_autostart(False)
        print("Autostart disabled.")
    print("Autostart:", "ON" if packaging.is_autostart_enabled() else "OFF")

    ISLAND = OrionIsland()
    ISLAND.start()

    scheduler_manager = Scheduler()
    scheduler_manager.on_fire(reminder_fired())
    scheduler_manager.start()

    set_confirm_callback(ask_confirmation)

    packaging.tray_icon(on_sleep=lambda: ISLAND.request_sleep() if ISLAND else None,
                        on_stop=lambda: ISLAND.request_stop() if ISLAND else None)

    start_ollama()

    speak(f"Hello Boss. I am {SPOKEN_NAME}. Say hello {SPOKEN_NAME} whenever you need me.")

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