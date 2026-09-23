"""Orion screen access - screenshots, on-screen text OCR and screen vision."""

import os
import subprocess
import time

import memory
import winfolders

SCREENSHOT_DIR = os.path.join(winfolders.pictures(), "OrionScreenshots")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def capture_screenshot(remember=True):
    """Capture the full desktop (every monitor) and return the PNG path."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    filename = os.path.join(SCREENSHOT_DIR, f"screen_{int(time.time())}.png")
    script = os.path.join(SCRIPT_DIR, "screenshot.ps1")

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", script, "-Path", filename],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and os.path.exists(filename):
            if remember:
                memory.set("last_screenshot", filename)
            return filename
        print("SCREENSHOT ERROR:", result.stdout.strip() or result.stderr.strip())
    except Exception as error:
        print("SCREENSHOT ERROR:", error)
    return None


def ocr_image(image_path):
    """Use the built-in Windows OCR engine to extract text from an image."""
    script = os.path.join(SCRIPT_DIR, "ocr.ps1")
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", script, "-ImagePath", image_path],
            capture_output=True, text=True, timeout=60
        )
    except Exception as error:
        print("OCR ERROR:", error)
        return None

    lines = [line.strip() for line in result.stdout.splitlines()
             if line.strip() and "OCR_" not in line]
    if not lines:
        return None
    text = "\n".join(lines)
    return text


def read_screen_text(describe=False):
    """Take a screenshot, OCR it and return a spoken summary."""
    filename = capture_screenshot()
    if not filename:
        return "I couldn't capture the screen."

    text = ocr_image(filename)
    if not text:
        return "I captured the screen, but I couldn't read any text on it."

    line_count = text.count("\n") + 1
    if describe:
        return text
    short = text if len(text) <= 600 else text[:600] + "..."
    return f"I saw {line_count} lines of text on your screen. Here is what it says. {short}"


def has_keywords(text, words):
    lowered = text.lower()
    return any(word in lowered for word in words)


def describe_screen():
    """OCR the screen, then ask the vision-aware AI to understand it."""
    filename = capture_screenshot()
    if not filename:
        return "I couldn't capture the screen."

    screen_text = ocr_image(filename)

    try:
        from brain import ask_vision
        description = ask_vision("Look at this screenshot and describe what is happening on the screen in two short sentences.", filename)
        if description:
            if screen_text:
                return f"{description} I can also read this text from your screen: {screen_text[:300]}"
            return description
    except Exception as error:
        print("SCREEN VISION ERROR:", error)

    if screen_text:
        return f"I couldn't use visual understanding right now, but I can read the text on your screen. {screen_text[:500]}"
    return "I couldn't understand the screen right now. Let me know if you want me to read text instead."


def last_screenshot():
    saved = memory.get("last_screenshot", "")
    if saved and os.path.exists(saved):
        return saved
    return capture_screenshot()


if __name__ == "__main__":
    path = capture_screenshot()
    print("SHOT:", path)
    print("OCR:", ocr_image(path))