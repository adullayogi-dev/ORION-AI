import webbrowser
import subprocess
import os
import time
import datetime
import re
import ctypes
from pathlib import Path


# ============================================================
# APP PATHS (edit these to match your PC)
# ============================================================

APPS = {
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "file explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "vs code": os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
    "settings": "start ms-settings:",
}

# Alternate ways each app might be heard/spoken.
APP_ALIASES = {
    "chrome": ["chrome"],
    "edge": ["edge", "microsoft edge"],
    "notepad": ["notepad"],
    "calculator": ["calculator"],
    "paint": ["paint"],
    "file explorer": ["file explorer", "explorer"],
    "task manager": ["task manager"],
    "vs code": ["vs code", "visual studio code", "v s code"],
    "settings": ["settings"],
}

WEBSITES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "github": "https://github.com",
    "chatgpt": "https://chat.openai.com",
}

# Alternate ways each site might be heard/spoken (includes common
# speech-recognition mishears - add more here as you notice them).
WEBSITE_ALIASES = {
    "youtube": ["youtube"],
    "google": ["google"],
    "gmail": ["gmail", "g mail"],
    "whatsapp": ["whatsapp", "what's app", "whats app"],
    "github": ["github", "git hub"],
    "chatgpt": ["chatgpt", "chat gpt", "chat g p t", "charge gpt", "charge g p t"],
}

# Commands can also find ordinary applications from Windows Start-menu
# shortcuts. Security-sensitive tools remain deliberately unavailable.
START_MENU_FOLDERS = (
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
)
BLOCKED_APP_TERMS = (
    "windows security", "defender", "antivirus", "credential", "password",
    "registry", "powershell", "command prompt", "terminal",
)
DISCOVERED_APPS = None

# Orion opens official search results for these songs. It does not generate
# lyrics or imitate the artist's voice.
LANA_DEL_REY_SONGS = (
    "Video Games", "Summertime Sadness", "Young and Beautiful",
    "Born to Die", "West Coast", "Doin' Time",
)

# ============================================================
# PROCESS NAMES (for closing apps)
# The actual .exe process name as seen in Task Manager.
# ============================================================

PROCESS_NAMES = {
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "notepad": "notepad.exe",
    "calculator": "CalculatorApp.exe",
    "paint": "mspaint.exe",
    "file explorer": "explorer.exe",
    "task manager": "Taskmgr.exe",
    "vs code": "Code.exe",
    "youtube": "msedge.exe",
    "google": "msedge.exe",
    "gmail": "msedge.exe",
    "whatsapp": "msedge.exe",
    "github": "msedge.exe",
    "chatgpt": "msedge.exe",
}


# ============================================================
# HELPERS
# ============================================================

def open_app(name):
    path = APPS.get(name)
    if not path:
        return False


def normalize_app_name(name):
    """Make spoken and Start-menu app names comparable."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def discover_start_menu_apps():
    """Return ordinary Start-menu apps by their spoken display name."""
    global DISCOVERED_APPS
    if DISCOVERED_APPS is not None:
        return DISCOVERED_APPS

    apps = {}
    for folder in START_MENU_FOLDERS:
        if not folder.is_dir():
            continue
        for shortcut in folder.rglob("*.lnk"):
            display_name = normalize_app_name(shortcut.stem)
            if not display_name or any(term in shortcut.stem.lower() for term in BLOCKED_APP_TERMS):
                continue
            apps.setdefault(display_name, shortcut)

    DISCOVERED_APPS = apps
    return apps


def open_discovered_app(spoken_name):
    """Launch a non-sensitive Start-menu shortcut named by the user."""
    target = normalize_app_name(spoken_name)
    if not target or any(term in spoken_name.lower() for term in BLOCKED_APP_TERMS):
        return False, True

    apps = discover_start_menu_apps()
    shortcut = apps.get(target)
    if shortcut is None:
        matches = [path for name, path in apps.items() if target in name or name in target]
        if len(matches) == 1:
            shortcut = matches[0]

    if shortcut is None:
        return False, False

    try:
        os.startfile(str(shortcut))
        return True, False
    except OSError as error:
        print("START MENU APP ERROR:", error)
        return False, False
    try:
        if path.startswith("start "):
            os.system(path)
        else:
            subprocess.Popen(path)
        return True
    except Exception as e:
        print("APP OPEN ERROR:", e)
        return False


def open_website(name):
    url = WEBSITES.get(name)
    if not url:
        return False
    webbrowser.open(url)
    return True


def close_app(name):
    process_name = PROCESS_NAMES.get(name)
    if not process_name:
        return False
    try:
        result = subprocess.run(
            ["taskkill", "/IM", process_name, "/F"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        print("APP CLOSE ERROR:", e)
        return False


def search_youtube(query):
    query = query.strip().replace(" ", "+")
    webbrowser.open(f"https://www.youtube.com/results?search_query={query}")


def play_youtube_first_result(query):
    # Opens the search page - user picks. For true auto-play of the
    # first result you'd need the YouTube Data API (needs an API key).
    search_youtube(query)


def play_lana_del_rey_song(command):
    """Open an official music search without generating copyrighted lyrics."""
    normalized_command = normalize_app_name(command)
    for song in LANA_DEL_REY_SONGS:
        if normalize_app_name(song) in normalized_command:
            search_youtube(f"Lana Del Rey {song} official audio")
            return f"Opening {song} by Lana Del Rey on YouTube"

    search_youtube("Lana Del Rey official music playlist")
    return "Opening Lana Del Rey's official music playlist on YouTube"


def search_google(query):
    query = query.strip().replace(" ", "+")
    webbrowser.open(f"https://www.google.com/search?q={query}")


def take_screenshot():
    try:
        import pyautogui
        folder = os.path.join(os.path.expanduser("~"), "Pictures", "OrionScreenshots")
        os.makedirs(folder, exist_ok=True)
        filename = os.path.join(folder, f"screenshot_{int(time.time())}.png")
        pyautogui.screenshot().save(filename)
        return filename
    except Exception as e:
        print("SCREENSHOT ERROR:", e)
        return None


def set_volume(level):
    try:
        import pyautogui
        if level == "up":
            for _ in range(5):
                pyautogui.press("volumeup")
        elif level == "down":
            for _ in range(5):
                pyautogui.press("volumedown")
        elif level == "mute":
            pyautogui.press("volumemute")
        return True
    except Exception as e:
        print("VOLUME ERROR:", e)
        return False


def lock_pc():
    ctypes.windll.user32.LockWorkStation()


def shutdown_pc():
    os.system("shutdown /s /t 5")


def restart_pc():
    os.system("shutdown /r /t 5")


def sleep_pc():
    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")


def tell_time():
    return datetime.datetime.now().strftime("It's %I:%M %p")


def tell_date():
    return datetime.datetime.now().strftime("Today is %A, %B %d")


# ============================================================
# MAIN DISPATCHER
# Returns a spoken response string if handled, or None if Orion
# should fall through to the AI brain.
# ============================================================

def execute_command(command):

    command = command.lower().strip()

    # ---------------- YouTube (play music / search) ----------------
    if command.startswith("play ") and "lana del rey" in command:
        return play_lana_del_rey_song(command)

    match = re.search(r"play (.+?) on youtube", command)
    if match:
        play_youtube_first_result(match.group(1))
        return f"Playing {match.group(1)} on YouTube"

    if "play music" in command or command == "play":
        search_youtube("music")
        return "Playing music"

    match = re.search(r"search (.+?) on youtube", command)
    if match:
        search_youtube(match.group(1))
        return f"Searching YouTube for {match.group(1)}"

    # ---------------- Close / kill apps or sites ----------------
    # Checked BEFORE open, so "close chrome" doesn't get caught
    # by anything else first. Matches close/closed/quit/kill/exit
    # so both present and past tense work.
    close_match = re.search(r"(?:close|closed|quit|kill|exit) (?:the )?(.+)", command)
    if close_match:
        target = close_match.group(1).strip()

        for app, aliases in APP_ALIASES.items():
            if any(alias in target for alias in aliases):
                if close_app(app):
                    return f"Closing {app.title()}"
                return f"I couldn't close {app.title()}"

        for site, aliases in WEBSITE_ALIASES.items():
            if any(alias in target for alias in aliases):
                if close_app(site):
                    return f"Closing {site.title()}"
                return f"I couldn't close {site.title()}"

    # ---------------- Open websites ----------------
    for site, aliases in WEBSITE_ALIASES.items():
        if any(f"open {alias}" in command for alias in aliases):
            open_website(site)
            return f"Opening {site.title()}"

    # ---------------- Open apps ----------------
    for app, aliases in APP_ALIASES.items():
        if any(f"open {alias}" in command for alias in aliases):
            if open_app(app):
                return f"Opening {app.title()}"
            return f"I couldn't find {app.title()} on this PC"

    # ---------------- Other ordinary Start-menu apps ----------------
    open_match = re.fullmatch(r"(?:open|launch|start) (?:the )?(.+)", command)
    if open_match:
        requested_app = open_match.group(1).strip()
        opened, blocked = open_discovered_app(requested_app)
        if blocked:
            return "I can't open security-sensitive system tools"
        if opened:
            return f"Opening {requested_app.title()}"
        return f"I couldn't find {requested_app.title()} in the Start menu"

    # ---------------- Google search ----------------
    match = re.search(r"search (?:for )?(.+?) on google", command)
    if match:
        search_google(match.group(1))
        return f"Searching Google for {match.group(1)}"

    # ---------------- Screenshot ----------------
    if "take a screenshot" in command or "screenshot" in command:
        path = take_screenshot()
        return "Screenshot taken" if path else "I couldn't take a screenshot"

    # ---------------- Volume ----------------
    if "volume up" in command or "increase volume" in command:
        set_volume("up")
        return "Volume increased"

    if "volume down" in command or "decrease volume" in command:
        set_volume("down")
        return "Volume decreased"

    if "mute" in command:
        set_volume("mute")
        return "Muted"

    # ---------------- System power ----------------
    if "lock" in command and "pc" in command:
        lock_pc()
        return "Locking your PC"

    if "shutdown" in command and "pc" in command:
        shutdown_pc()
        return "Shutting down in 5 seconds"

    if "restart" in command and "pc" in command:
        restart_pc()
        return "Restarting in 5 seconds"

    if "sleep" in command and "pc" in command:
        sleep_pc()
        return "Putting your PC to sleep"

    # ---------------- Time / date ----------------
    if "what time" in command or "current time" in command:
        return tell_time()

    if "what date" in command or "today's date" in command:
        return tell_date()

    return None
