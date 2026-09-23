"""Orion commands - opens anything, reads files, sees the screen, does maths.

execute_command() returns a spoken line when Orion handled the command,
or None so the AI brain gets a chance to answer.
"""

import os
import re
import subprocess
import time
import webbrowser
import datetime
import ctypes
import winreg
from pathlib import Path

import camera
import calculator
import files
import memory
import screen
import winfolders

# ============================================================
# KNOWN APPLICATIONS (reliable paths only - everything else is
# found through the registry, PATH and Windows Start Apps).
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
    "camera": None,  # handled specially through camera.open_camera()
    "settings": "start ms-settings:",
    "control panel": "shell:ControlPanelFolder",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"),
    "photos": "start ms-photos:",
    "sticky notes": "start ms-sticky-notes:",
}

APP_ALIASES = {
    "chrome": ["chrome", "google chrome"],
    "edge": ["edge", "microsoft edge"],
    "notepad": ["notepad"],
    "calculator": ["calculator", "calc"],
    "paint": ["paint", "ms paint", "microsoft paint"],
    "file explorer": ["file explorer", "explorer"],
    "task manager": ["task manager", "taskmgr"],
    "vs code": ["vs code", "vscode", "visual studio code", "v s code"],
    "camera": ["camera", "webcam", "web camera"],
    "settings": ["settings", "windows settings"],
    "control panel": ["control panel"],
    "cmd": ["cmd", "command prompt", "command line", "console"],
    "powershell": ["powershell"],
    "terminal": ["terminal", "windows terminal", "new terminal"],
    "photos": ["photos", "photo viewer", "microsoft photos", "image viewer"],
    "sticky notes": ["sticky notes", "stickies"],
}

FOLDERS = {
    "pictures": os.path.join(winfolders.pictures(), ""),
    "documents": os.path.join(winfolders.documents(), ""),
    "downloads": os.path.join(winfolders.downloads(), ""),
    "desktop": os.path.join(winfolders.desktop(), ""),
    "music": winfolders._known("MyMusic") or os.path.join(os.path.expanduser("~"), "Music"),
    "videos": winfolders._known("MyVideos") or os.path.join(os.path.expanduser("~"), "Videos"),
    "this pc": "shell:ThisPCFolder",
    "recycle bin": "shell:RecycleBinFolder",
}

WEBSITES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "github": "https://github.com",
    "chatgpt": "https://chat.openai.com",
    "gemini": "https://gemini.google.com",
    "netflix": "https://netflix.com",
    "instagram": "https://instagram.com",
    "facebook": "https://facebook.com",
    "x": "https://x.com",
    "twitter": "https://x.com",
    "linkedin": "https://linkedin.com",
    "reddit": "https://reddit.com",
    "spotify": "https://open.spotify.com",
    "stack overflow": "https://stackoverflow.com",
    "wikipedia": "https://wikipedia.org",
    "amazon": "https://amazon.in",
    "flipkart": "https://flipkart.com",
    "maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "classroom": "https://classroom.google.com",
}

WEBSITE_ALIASES = {
    "youtube": ["youtube", "you tube"],
    "google": ["google"],
    "gmail": ["gmail", "g mail"],
    "whatsapp": ["whatsapp", "what's app", "whats app"],
    "github": ["github", "git hub"],
    "chatgpt": ["chatgpt", "chat gpt", "chat g p t", "charge gpt"],
    "gemini": ["gemini", "google gemini"],
    "netflix": ["netflix"],
    "instagram": ["instagram", "insta"],
    "facebook": ["facebook", "fb"],
    "x": ["x", "twitter"],
    "twitter": ["twitter"],
    "linkedin": ["linkedin", "linked in"],
    "reddit": ["reddit"],
    "spotify": ["spotify"],
    "stack overflow": ["stack overflow", "stackoverflow"],
    "wikipedia": ["wikipedia", "wiki"],
    "amazon": ["amazon", "amazon shopping"],
    "flipkart": ["flipkart"],
    "maps": ["google maps", "maps"],
    "drive": ["google drive", "drive"],
    "classroom": ["google classroom", "classroom"],
}

PROCESS_NAMES = {
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "notepad": "notepad.exe",
    "calculator": "CalculatorApp.exe",
    "paint": "mspaint.exe",
    "file explorer": "explorer.exe",
    "task manager": "Taskmgr.exe",
    "vs code": "Code.exe",
    "camera": "WindowsCamera.exe",
    "photos": "Microsoft.Photos.exe",
    "spotify": "spotify.exe",
    "discord": "Discord.exe",
    "zoom": "Zoom.exe",
    "terminal": "WindowsTerminal.exe",
    "youtube": "msedge.exe",
    "google": "msedge.exe",
    "gmail": "msedge.exe",
    "whatsapp": "msedge.exe",
    "github": "msedge.exe",
    "chatgpt": "msedge.exe",
    "netflix": "msedge.exe",
    "instagram": "msedge.exe",
    "facebook": "msedge.exe",
}

LANA_DEL_REY_SONGS = (
    "Video Games", "Summertime Sadness", "Young and Beautiful",
    "Born to Die", "West Coast", "Doin' Time",
)

# Cache for Windows Start Apps lookups
_START_APPS = {}
_START_APPS_TS = 0


# ============================================================
# HELPERS
# ============================================================

def normalize_app_name(name):
    return "".join(ch for ch in name.lower() if ch.isalnum())


def resolve_app(raw_name):
    """Map any spoken name to an APPS key."""
    n = normalize_app_name(raw_name)
    if n in APPS:
        return n
    for app, aliases in APP_ALIASES.items():
        for alias in aliases:
            a = normalize_app_name(alias)
            if a == n or a in n or n in a:
                return app
    return None


def _registry_app_path(exe_name):
    """Find a program through the Windows App Paths registry."""
    if not exe_name.lower().endswith(".exe"):
        exe_name += ".exe"
    subkeys = (
        rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}",
        rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}",
    )
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for subkey in subkeys:
            try:
                with winreg.OpenKey(root, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, "")
                    if value and os.path.exists(value):
                        return value
            except OSError:
                continue
    return None


def _where(exe_name):
    """Search the system PATH for an executable."""
    if not exe_name.lower().endswith(".exe"):
        exe_name += ".exe"
    try:
        result = subprocess.run(
            ["where", exe_name], capture_output=True, text=True, timeout=8
        )
        for line in result.stdout.splitlines():
            candidate = line.strip()
            if os.path.isfile(candidate):
                return candidate
    except Exception:
        pass
    return None


def start_apps(fresh=False):
    """Cache the Windows Start Apps list ({name: appid})."""
    global _START_APPS, _START_APPS_TS
    if not fresh and _START_APPS and time.time() - _START_APPS_TS < 300:
        return _START_APPS

    apps = {}
    script = r'Get-StartApps | ForEach-Object { "{0}`t{1}" -f $_.Name, $_.AppID }'
    try:
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=25,
        ).stdout
        for line in output.splitlines():
            if "\t" not in line:
                continue
            name, appid = line.split("\t", 1)
            apps[normalize_app_name(name)] = appid.strip()
    except Exception as error:
        print("GET-STARTAPPS ERROR:", error)

    _START_APPS, _START_APPS_TS = apps, time.time()
    return apps


def _launch_uwp(appid):
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appid}"])


def discover_start_menu_apps():
    """Map spoken display names to Start Menu shortcuts."""
    folders = (
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    )
    apps = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        for shortcut in folder.rglob("*.lnk"):
            display_name = normalize_app_name(shortcut.stem)
            if display_name:
                apps.setdefault(display_name, shortcut)
    return apps


# ============================================================
# OPEN ANYTHING
# ============================================================

def open_app(app_key):
    """Launch a known app by APPS key."""
    if app_key == "camera":
        return camera.open_camera()

    path = APPS.get(app_key)
    if not path:
        return False

    if path.startswith("start "):
        os.system(path)
        return True

    if path.startswith("shell:"):
        subprocess.Popen(["explorer.exe", path])
        return True

    try:
        subprocess.Popen(path, shell=False)
        return True
    except Exception as error:
        print("APP OPEN ERROR:", error)
        return False


def open_any_app(requested):
    """Open any application by name. Returns (opened, nice_name)."""
    requested = requested.strip().strip(".,;:'\"")
    if not requested:
        return False, ""

    # 1) Folders like "my documents" / "this pc"
    requested_n = normalize_app_name(requested)
    for folder, target in FOLDERS.items():
        if requested_n == normalize_app_name(folder):
            subprocess.Popen(["explorer.exe", os.path.expandvars(target)])
            return True, folder

    # 2) Known apps
    app_key = resolve_app(requested)
    if app_key and open_app(app_key):
        return True, app_key

    # 3) Registry App Paths
    for candidate in (requested, requested + ".exe"):
        app_path = _registry_app_path(candidate)
        if app_path:
            try:
                subprocess.Popen([app_path])
                return True, requested
            except Exception as error:
                print("APP OPEN ERROR:", error)

    # 4) PATH executables
    app_path = _where(requested)
    if app_path:
        try:
            subprocess.Popen([app_path])
            return True, requested
        except Exception as error:
            print("APP OPEN ERROR:", error)

    # 5) Windows Start Apps (covers all modern/UWP apps)
    apps = start_apps() or start_apps(fresh=True)
    n = requested_n
    if n in apps:
        _launch_uwp(apps[n])
        return True, requested
    for name, appid in apps.items():
        if n in name or name in n:
            _launch_uwp(appid)
            return True, requested

    # 6) Start Menu shortcuts
    for display, shortcut in discover_start_menu_apps().items():
        if display == n or n in display or display in n:
            try:
                os.startfile(str(shortcut))
                return True, requested
            except OSError as error:
                print("START MENU APP ERROR:", error)

    return False, requested


def close_app(name):
    """Close an app by process name."""
    process = PROCESS_NAMES.get(name) or f"{name}.exe"
    try:
        result = subprocess.run(
            ["taskkill", "/IM", process, "/F"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return True
        # App not running is still success for a spoken reply.
        return True
    except Exception as error:
        print("APP CLOSE ERROR:", error)
        return False


# ============================================================
# WEBSITES / SEARCH / YOUTUBE
# ============================================================

def open_website(site):
    url = WEBSITES.get(site)
    if not url:
        return False
    webbrowser.open(url)
    return True


def search_youtube(query):
    webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")


def search_google(query):
    webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")


def play_youtube_first_result(query):
    search_youtube(query)


def play_lana_del_rey_song(command):
    normalized_command = normalize_app_name(command)
    for song in LANA_DEL_REY_SONGS:
        if normalize_app_name(song) in normalized_command:
            search_youtube(f"Lana Del Rey {song} official audio")
            return f"Opening {song} by Lana Del Rey on YouTube"
    search_youtube("Lana Del Rey official music playlist")
    return "Opening Lana Del Rey's official music playlist on YouTube"


# ============================================================
# SYSTEM / TIME
# ============================================================

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
    except ImportError:
        return False
    except Exception as error:
        print("VOLUME ERROR:", error)
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
# SCREEN / PHOTO / FILE PATTERNS
# ============================================================

MATH_OPERATOR_WORDS = (
    "plus", "minus", "times", "multiply", "multiplied", "divide", "divided",
    "add", "subtract", "subtracted", "percent", "percentage", "squared",
    "square root", "sqrt", "power", "sum of", "total of", "calculate",
    "compute", "math",
)


def _looks_like_math(command):
    return bool(re.search(r"\d", command)) or any(
        op in command for op in MATH_OPERATOR_WORDS
    )


def _explain_math_command(command):
    """Only explain maths when the command is arithmetical, not 'open calculator'."""
    if "calculator" in command and not _looks_like_math(command):
        return None
    if not _looks_like_math(command):
        return None
    if any(word in command for word in ("youtube", "whatsapp", "facebook", "google", "gmail", "github")):
        return None
    return calculator.try_calculate(command)


# ------------------------------------------------------------------
# CONFIRMATION SAFETY (set by orion.py so destructive actions ask first)
# ------------------------------------------------------------------

_confirm_callback = None


def set_confirm_callback(callback):
    """Accept a callable(prompt) -> bool used before destructive actions."""
    global _confirm_callback
    _confirm_callback = callback


def confirm(prompt):
    if _confirm_callback is None:
        return True
    try:
        return bool(_confirm_callback(prompt))
    except Exception as error:
        print("CONFIRM ERROR:", error)
        return False


# ============================================================
# MAIN DISPATCHER
# ============================================================

def execute_command(command):

    command = command.lower().strip()

    # ---------------- Name memory ----------------
    name_match = re.search(r"(?:my name is|you can call me|call me|remember my name is|i am called|the name is)\s+(.+)", command)
    if name_match and not any(word in command for word in ("what", "do you know")):
        spoken_name = name_match.group(1).strip().strip(".,!?")
        if spoken_name and not _contains_name_noise(spoken_name):
            saved = memory.set_user_name(spoken_name)
            return f"Nice to meet you, {saved}. I will remember your name."

    if "what is my name" in command or "do you know my name" in command:
        name = memory.get_user_name()
        return f"Your name is {name}." if name else "I haven't been told your name yet. Say, my name is, and tell me."

    if "forget my name" in command:
        memory.set("user_name", "")
        return "Okay, I forgot your name."

    # ---------------- Screen access ----------------
    if any(word in command for word in ("look at my screen", "look at the screen", "describe my screen", "describe the screen",
                                        "what is on my screen", "what's on my screen", "what is on the screen", "what's on the screen",
                                        "understand my screen", "see my screen", "check my screen")):
        return screen.describe_screen()

    if any(word in command for word in ("read my screen", "read the screen", "read your screen", "read this screen",
                                        "scan my screen", "scan the screen", "what is written on screen",
                                        "read the text on", "read what is on the screen")):
        return screen.read_screen_text()

    # ---------------- Camera / photo ----------------
    if any(word in command for word in ("open camera", "open the camera", "launch camera", "start camera")):
        if camera.open_camera():
            return "Opening the camera."
        return "I couldn't open the camera."

    if any(word in command for word in ("take a photo", "take a picture", "take photo", "take picture",
                                        "click a photo", "click a picture", "capture a photo", "capture a picture",
                                        "take a selfie", "take selfie")):
        filename, error = camera.take_photo()
        if filename:
            return f"Photo captured and saved to {filename}."
        if error == "webcam library missing":
            return "I opened the camera app for you, since my photo library isn't installed yet."
        return f"I couldn't take a photo. {error or 'Please try again.'}"

    # ---------------- Read text files ----------------
    if re.search(r"\bread\b", command) or "read the file" in command or "read that file" in command:
        response = files.read_and_speak(command)
        if response:
            return response

    # ---------------- Explain words ----------------
    if re.search(r"\b(?:what does|what do|meaning of|explain|define)\b", command):
        explanation = files.explain_words(command)
        if explanation:
            return explanation

    # ---------------- Close / kill apps ----------------
    close_match = re.search(r"(?:close|closed|kill) (?:the )?(.+)", command)
    if close_match:
        target = close_match.group(1).strip()
        app_key = resolve_app(target)
        if app_key:
            if close_app(app_key):
                return f"Closing {app_key.title()}"
            return f"I couldn't close {app_key.title()}"
        site_key = _resolve_site(target)
        if site_key:
            if close_app(site_key):
                return f"Closing {site_key.title()}"
            return f"I couldn't close {site_key.title()}"
        if close_app(target):
            return f"Closing {target.title()}"

    # ---------------- Maths / calculator ----------------
    if "calculator" in command or _looks_like_math(command):
        if "open calculator" in command:
            open_app("calculator")
            result = _explain_math_command(command)
            if result:
                return f"Opened the calculator. {result}"
            return "Opening the calculator."
        result = _explain_math_command(command)
        if result:
            return result

    # ---------------- Open websites ----------------
    for site, aliases in WEBSITE_ALIASES.items():
        if any(f"open {alias}" in command for alias in aliases):
            open_website(site)
            return f"Opening {site.title()}"

    # ---------------- YouTube ----------------
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

    # ---------------- Open apps (anything, not just a whitelist) ----------------
    open_match = re.search(r"(?:open|launch|start|run) (?:the )?(.+)", command)
    if open_match:
        requested = open_match.group(1).strip()
        if requested:
            opened, nice = open_any_app(requested)
            if opened:
                return f"Opening {nice.title()}."
            return f"I couldn't find {requested.title()} on this PC. Try saying the app name again."

    # ---------------- Google search ----------------
    match = re.search(r"search (?:for )?(.+?) on google", command)
    if match:
        search_google(match.group(1))
        return f"Searching Google for {match.group(1)}"

    # ---------------- Screenshots ----------------
    if "screenshot" in command or "capture the screen" in command or "capture screen" in command:
        filename = screen.capture_screenshot()
        return f"Screenshot saved to {filename}." if filename else "I couldn't take a screenshot"

    # ---------------- Volume ----------------
    if "volume up" in command or "increase volume" in command or "turn up the volume" in command:
        set_volume("up")
        return "Volume increased"

    if "volume down" in command or "decrease volume" in command or "turn down the volume" in command:
        set_volume("down")
        return "Volume decreased"

    if "mute" in command or "mute the volume" in command:
        set_volume("mute")
        return "Muted"

    # ---------------- System power (with confirmation) ----------------
    if "lock" in command and "pc" in command:
        lock_pc()
        return "Locking your PC"

    if "shutdown" in command and "pc" in command:
        if confirm("Shutting down your PC. Are you sure? Say yes to confirm."):
            shutdown_pc()
            return "Shutting down in 5 seconds"
        return "Okay, I won't shut down."

    if "restart" in command and "pc" in command:
        if confirm("Restarting your PC. Are you sure? Say yes to confirm."):
            restart_pc()
            return "Restarting in 5 seconds"
        return "Okay, I won't restart."

    if "sleep" in command and "pc" in command:
        if confirm("Putting your PC to sleep. Are you sure? Say yes to confirm."):
            sleep_pc()
            return "Putting your PC to sleep"
        return "Okay, I won't put the PC to sleep."

    # ---------------- Time / date ----------------
    if "what time" in command or "current time" in command or "the time" in command:
        return tell_time()

    if "what date" in command or "today's date" in command:
        return tell_date()

    # ---------------- New-generation tool phrases ----------------
    try:
        from tools import voice_command
        handled = voice_command(command)
        if handled:
            return handled
    except Exception as error:
        print("VOICE TOOL ERROR:", error)

    return None


# ============================================================
# Internal helpers
# ============================================================

def _contains_name_noise(text):
    """Names like 'happy' or 'what can you do' aren't names."""
    noise = ("fine", "thanks", "happy", "hungry", "sad", "tired", "bored",
             "your name", "orion", "boss")
    lowered = text.lower()
    return any(word == lowered for word in noise)


def _resolve_site(target):
    for site, aliases in WEBSITE_ALIASES.items():
        if any(alias in target for alias in aliases):
            return site
    return None