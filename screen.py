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


def capture_window(app_name):
    """Capture just one app's window into a PNG and return its path."""
    try:
        import pygetwindow as gw
        window = None
        candidates = gw.getWindowsWithTitle(app_name)
        if candidates:
            window = candidates[0]
        else:
            for candidate in gw.getAllWindows():
                if not candidate.title:
                    continue
                if app_name.lower() in candidate.title.lower():
                    window = candidate
                    break
        if not window or window.width <= 0 or window.height <= 0:
            return None

        filename = capture_screenshot(remember=False)
        if not filename:
            return None

        from PIL import Image
        image = Image.open(filename)
        left = max(0, int(window.left))
        top = max(0, int(window.top))
        right = min(image.width, left + int(window.width))
        bottom = min(image.height, top + int(window.height))
        if right <= left or bottom <= top:
            return filename
        cropped = image.crop((left, top, right, bottom))

        window_path = os.path.join(SCREENSHOT_DIR, f"window_{int(time.time())}.png")
        cropped.save(window_path)
        return window_path
    except Exception as error:
        print("WINDOW CAPTURE ERROR:", error)
        return None


def ocr_lines_with_boxes(image_path):
    """OCR a screenshot and return [(text, x, y, w, h)] using Windows OCR."""
    script = os.path.join(SCRIPT_DIR, "ocrboxes.ps1")
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", script, "-ImagePath", image_path],
            capture_output=True, text=True, timeout=60
        )
    except Exception as error:
        print("OCR BOXES ERROR:", error)
        return []
    lines = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "OCR_" in line:
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        try:
            text, left, top, width, height = parts
            lines.append((text.strip(), int(left), int(top), int(width), int(height)))
        except ValueError:
            continue
    return lines


def find_text_on_screen(target):
    """Locate a visible text label and return the pixel center (x, y), or None."""
    shot = capture_screenshot(remember=False)
    if not shot:
        return None
    target_normalized = "".join(ch.lower() for ch in target if ch.isalnum())
    for text, left, top, width, height in ocr_lines_with_boxes(shot):
        normalized = "".join(ch.lower() for ch in text if ch.isalnum())
        if not target_normalized or not normalized:
            continue
        if target_normalized in normalized or normalized in target_normalized:
            return int(left + width / 2), int(top + height / 2)
    return None


def click_on_screen(target):
    """Click an on-screen thing: find visible text first, then vision fallback.

    Returns a spoken result string.
    """
    from system_control import click_position

    unknown = f"I couldn't find {target} on the screen."

    # Preferred: the thing might be a visible text label or button.
    point = find_text_on_screen(target)
    if point:
        if click_position(*point):
            return f"Clicked on {target}."
        return unknown

    # Fallback: moondream vision coordinates (best effort).
    shot = capture_screenshot(remember=False)
    if not shot:
        return "I couldn't capture the screen to find that."
    point = vision_point(shot, target)
    if not point:
        return unknown
    x, y = point
    if click_position(x, y):
        return f"Clicked on {target}."
    return unknown


def vision_point(image_path, target):
    """Ask the vision model where `target` is. Returns (x, y) pixels or None."""
    from brain import ask_vision
    prompt = (
        f"Where in this image is the {target}? Answer with ONLY the x and y "
        f"coordinates as two numbers between 0 and 1 separated by a comma, like 0.50,0.25."
    )
    answer = ask_vision(prompt, image_path, num_predict=30)
    if not answer:
        return None

    import re
    numbers = re.findall(r"[0-9]*\.?[0-9]+", answer.replace(":", " ").replace("(", " ").replace(")", " "))
    if numbers:
        try:
            values = [float(value) for value in numbers[:2]]
            if len(values) == 2:
                from PIL import Image
                with Image.open(image_path) as image:
                    width, height = image.size
                return int(values[0] * width), int(values[1] * height)
        except (ValueError, IndexError, OSError):
            pass
    return None


def last_screenshot():
    saved = memory.get("last_screenshot", "")
    if saved and os.path.exists(saved):
        return saved
    return capture_screenshot()


if __name__ == "__main__":
    path = capture_screenshot()
    print("SHOT:", path)
    print("OCR:", ocr_image(path))