"""Orion tools - a registry of things Orion can DO.

Shared by two paths:
  * voice_command() -> deterministic voice command parser
  * the AI brain's function calling (ask_ai_with_tools)

execute_tool(name, args) is the single safe entry point for the brain.
"""

import re

import camera
import calculator
import commands
import files
import memory
import screen
import system_control

# ============================================================
# TOOL IMPLEMENTATIONS
# ============================================================

def _open_app(args):
    name = str(args.get("app", "")).strip()
    if not name:
        return "Please tell me which app to open."
    return commands.open_any_app(name)[0] is True or f"Opening {name}"


def _open_website(args):
    site = str(args.get("site", "")).strip()
    if not site:
        return "Which website should I open?"
    for key, aliases in commands.WEBSITE_ALIASES.items():
        if any(alias in site for alias in aliases) or site == key:
            commands.open_website(key)
            return f"Opening {key.title()}"
    if "." in site:
        import webbrowser
        webbrowser.open("https://" + site if not site.startswith("http") else site)
        return f"Opening {site}"
    return "I don't recognize that website."


def _open_folder(args):
    folder = str(args.get("folder", "")).strip().lower()
    targets = {
        "desktop": commands.FOLDERS.get("desktop"),
        "documents": commands.FOLDERS.get("documents"),
        "downloads": commands.FOLDERS.get("downloads"),
        "pictures": commands.FOLDERS.get("pictures"),
        "images": commands.FOLDERS.get("pictures"),
        "music": commands.FOLDERS.get("music"),
        "videos": commands.FOLDERS.get("videos"),
        "video": commands.FOLDERS.get("videos"),
    }
    import os, subprocess
    target = None
    for key, value in targets.items():
        if key in folder:
            target = value
            break
    if target is None:
        return "Which folder? Desktop, Documents, Downloads, Pictures, Music or Videos."
    subprocess.Popen(["explorer.exe", os.path.expandvars(target)])
    return f"Opening {folder} folder"


def _get_time(_args):
    return commands.tell_time()


def _get_date(_args):
    return commands.tell_date()


def _calculate(args):
    expression = str(args.get("expression", "")).strip()
    if not expression:
        return "What should I calculate?"
    plain = expression
    for phrase in ("calculate", "compute", "what is", "what's", "solve",
                   "equals", "is equal to", "math", "please", "the answer to"):
        plain = plain.replace(phrase, "")
    plain = re.sub(r"[?.,;:]", "", plain).strip()
    if re.fullmatch(r"[+\-*/().\d%\s^]+", plain):
        try:
            value = calculator.safe_eval(plain)
            answer = calculator.format_number(value)
            if answer:
                return f"The answer is {answer}."
        except Exception:
            pass
    result = calculator.try_calculate(expression)
    return result or f"I couldn't work that out. The expression was {expression}"


def _screenshot(_args):
    path = screen.capture_screenshot()
    if not path:
        return "I couldn't take a screenshot."
    memory.set("last_screenshot", path)
    return f"Screenshot saved to {path}"


def _read_screen(_args):
    return screen.read_screen_text(describe=True)


def _describe_screen(_args):
    return screen.describe_screen()


def _click_on_screen(args):
    return screen.click_on_screen(str(args.get("target", "")).strip())


def _take_photo(_args):
    filename, error = camera.take_photo()
    if not filename:
        return f"Photo failed. {error or ''}"
    return f"Photo saved to {filename}."


def _open_camera(_args):
    return "Opening the camera." if camera.open_camera() else "I couldn't open the camera."


def _set_volume(args):
    percent = int(float(args.get("percent", 50)))
    if system_control.set_volume(percent):
        return f"Volume set to {percent} percent."
    return system_control.set_volume_updown("up") and f"Volume changed."


def _volume_action(args):
    action = args.get("action", "").lower()
    if action in ("up", "down", "mute"):
        system_control.set_volume_updown(action)
        return f"Volume {action}"
    return "Say volume up, down or mute."


def _get_battery(_args):
    return system_control.get_battery()


def _set_brightness(args):
    percent = int(float(args.get("percent", 50)))
    if system_control.set_brightness(percent):
        return f"Brightness set to {percent} percent."
    return "I couldn't change the brightness."


def _get_brightness(_args):
    value = system_control.get_brightness()
    return f"Brightness is at {value} percent." if value is not None else "Brightness unavailable."


def _get_wifi(_args):
    return system_control.get_wifi_status()


def _get_bluetooth(_args):
    return system_control.get_bluetooth_status()


def _wifi_password(args):
    return system_control.wifi_giveaway(str(args.get("wifi", "")).strip())


def _media(args):
    action = str(args.get("action", "")).strip()
    if system_control.media_control(action):
        return f"Media {action}"
    return "I couldn't control the media."


def _type_text(args):
    text = str(args.get("text", "")).strip()
    if not text:
        return "What should I type?"
    return "Typing." if system_control.type_text(text) else "I couldn't type."


def _press_key(args):
    key = str(args.get("key", "")).strip()
    return "Pressed." if system_control.press_key(key) else "I couldn't press that key."


def _window_action(args):
    action = str(args.get("action", "")).strip().lower()
    app = str(args.get("app", "")).strip()
    if system_control.window_action(action, app):
        return f"{action} {app}"
    return f"I couldn't {action} {app}."


def _set_reminder(args):
    minutes = int(float(args.get("minutes", 1)))
    text = str(args.get("text", "")).strip() or "You asked me to remind you."
    from scheduler import add_minutes_reminder
    return add_minutes_reminder(minutes, text)


def _remind_at(args):
    time_str = str(args.get("time", "")).strip()
    text = str(args.get("text", "")).strip() or "You asked me to remind you."
    match = re.search(r"(\d{1,2}):(\d{2})", time_str)
    if not match:
        match = re.search(r"(\d{1,2})[.\s]+(\d{2})", time_str)
    if not match:
        return "Tell me the time like 6 30."
    from scheduler import add_at_reminder
    hh, mm = int(match.group(1)), int(match.group(2))
    return add_at_reminder(hh, mm, text)


def _list_reminders(_args):
    from scheduler import list_reminders
    return list_reminders()


def _read_file(args):
    name = str(args.get("name", "")).strip()
    if not name:
        return "Which file should I read?"
    return files.read_and_speak(f"read the file {name}")


def _summarize_file(args):
    name = str(args.get("name", "")).strip()
    return files.summarize_file(f"summarize the file {name}")


def _explain_word(args):
    word = str(args.get("word", "")).strip()
    if not word:
        return "Which word should I explain?"
    return files.explain_words(f"what does {word} mean")


def _create_note(args):
    title = str(args.get("title", "")).strip() or "note"
    body = str(args.get("body", "")).strip()
    if not body:
        return "What should the note say?"
    path = files.create_note(title, body)
    return f"Note saved to {path}"


def _weather(args):
    from brain import get_weather
    return get_weather(str(args.get("city", "")).strip())


def _news(args):
    from brain import get_news
    return get_news(str(args.get("topic", "")).strip())


def _translate(args):
    from brain import translate_text
    text = str(args.get("text", "")).strip()
    language = str(args.get("language", "English")).strip()
    if not text:
        return "What should I translate?"
    translated = translate_text(text, language)
    return f"In {language}, that means: {translated}"


def _remember_fact(args):
    fact = str(args.get("fact", "")).strip()
    check = re.search(r"(?:that|how|which|when|would|can|do|is|are|my|i|name)", fact)
    if not fact:
        return "What should I remember?"
    cleaned = re.sub(r"^(remember that|i want you to remember that|you should remember that)\s+",
                     "", fact, flags=re.IGNORECASE).strip()
    if memory.add_fact(cleaned):
        return "Remembered."
    return "I already know that."


def _notify(args):
    title = str(args.get("title", "Orion")).strip() or "Orion"
    message = str(args.get("message", "")).strip()
    if not message:
        return "What should the notification say?"
    try:
        import winotify
        toast = winotify.Notification(app_id="ORION AI", title=title, msg=message)
        toast.show()
        return "Notification sent."
    except Exception as error:
        print("NOTIFY ERROR:", error)
        return "I couldn't send the notification."


def _search(args):
    query = str(args.get("query", "")).strip()
    if not query:
        return "What should I search for?"
    commands.search_google(query)
    return f"Searching Google for {query}"


def _play_media(args):
    query = str(args.get("query", "")).strip()
    if query:
        commands.play_youtube_first_result(query)
        return f"Playing {query} on YouTube"
    return "What should I play?"


def _lock_pc(_args):
    commands.lock_pc()
    return "Locking your PC."


def _enable_autostart(_args):
    if system_control.set_autostart(True):
        return "Orion will start automatically when you log in."
    return "I couldn't enable autostart."


def _disable_autostart(_args):
    if system_control.set_autostart(False):
        return "Orion will no longer start automatically."
    return "I couldn't disable autostart."


def _clear_history(_args):
    memory.clear_history()
    return "I cleared our conversation history."


def _what_remember(_args):
    facts = memory.get_facts()
    if not facts:
        return "I remember nothing personal yet. Tell me something to remember."
    return "You told me: " + "; ".join(facts[-6:])


# ============================================================
# SCHEMA FOR THE AI BRAIN
# ============================================================

def _schema(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def _string(description):
    return {"type": "string", "description": description}


TOOL_SCHEMA = [
    _schema("open_app", "Open any application on the user's PC by its name.", {"app": _string("App name, e.g. chrome, notepad, calculator")}, ["app"]),
    _schema("open_website", "Open a known website in the browser.", {"site": _string("e.g. youtube, google, gmail")}, ["site"]),
    _schema("open_folder", "Open a user folder like Documents, Downloads or Desktop.", {"folder": _string("folder name")}, ["folder"]),
    _schema("get_time", "Tell the current time.", {}, []),
    _schema("get_date", "Tell today's date.", {}, []),
    _schema("calculate", "Evaluate a maths expression the user spoke.", {"expression": _string("pure maths or a spoken phrase like '25 percent of 80'")}, ["expression"]),
    _schema("screenshot", "Capture a screenshot of the whole screen.", {}, []),
    _schema("read_screen", "Read all text currently visible on the screen.", {}, []),
    _schema("describe_screen", "Describe visually what is on the screen.", {}, []),
    _schema("click_on_screen", "Visually find an on-screen object and mouse-click it.", {"target": _string("what to click, e.g. the save button")}, ["target"]),
    _schema("take_photo", "Take a photo with the webcam.", {}, []),
    _schema("open_camera", "Open the Windows Camera app.", {}, []),
    _schema("set_volume", "Set the system volume to a percentage.", {"percent": _string("0 to 100")}, ["percent"]),
    _schema("volume_action", "Turn volume up, down, or mute.", {"action": _string("up, down or mute")}, ["action"]),
    _schema("get_battery", "Report the laptop battery percentage and charging state.", {}, []),
    _schema("set_brightness", "Set the screen brightness percentage.", {"percent": _string("0 to 100")}, ["percent"]),
    _schema("get_brightness", "Report the current screen brightness.", {}, []),
    _schema("get_wifi", "Report the Wi-Fi network the PC is connected to.", {}, []),
    _schema("get_bluetooth", "Report whether Bluetooth is on.", {}, []),
    _schema("wifi_password", "Find the saved password of a Wi-Fi network.", {"wifi": _string("the network name")}, ["wifi"]),
    _schema("media", "Control media playback.", {"action": _string("play, pause, next, previous or stop")}, ["action"]),
    _schema("type_text", "Type text into the focused application.", {"text": _string("text to type")}, ["text"]),
    _schema("press_key", "Press a keyboard key.", {"key": _string("e.g. enter, tab, escape, space")}, ["key"]),
    _schema("window_action", "Minimize, maximize, restore or close an app window.", {"action": _string("minimize, maximize, restore or close"), "app": _string("app name")}, ["action", "app"]),
    _schema("set_reminder", "Set a reminder for a number of minutes from now.", {"minutes": _string("number"), "text": _string("reminder message")}, ["minutes", "text"]),
    _schema("remind_at", "Set a reminder at a specific clock time.", {"time": _string("e.g. 6 30"), "text": _string("reminder message")}, ["time", "text"]),
    _schema("list_reminders", "List pending reminders.", {}, []),
    _schema("read_file", "Find and read a file aloud (text, PDF, Word or Excel).", {"name": _string("file name")}, ["name"]),
    _schema("summarize_file", "Summarize a file the user named, or the last file read.", {"name": _string("file name (optional)")}, []),
    _schema("explain_word", "Explain the meaning of a word or phrase.", {"word": _string("word or phrase")}, ["word"]),
    _schema("create_note", "Create a note file.", {"title": _string("note title"), "body": _string("note content")}, ["title", "body"]),
    _schema("weather", "Get the current weather.", {"city": _string("city name, optional")}, []),
    _schema("news", "Get the latest news.", {"topic": _string("topic, optional")}, []),
    _schema("translate", "Translate text into another language.", {"text": _string("the text"), "language": _string("e.g. Telugu, Hindi, Tamil")}, ["text", "language"]),
    _schema("remember_fact", "Store something about the user that Orion should remember long-term.", {"fact": _string("the fact to remember")}, ["fact"]),
    _schema("what_remember", "List what Orion remembers about the user.", {}, []),
    _schema("notify", "Show a Windows notification bubble.", {"title": _string("title"), "message": _string("message")}, ["message"]),
    _schema("search", "Search Google in the browser.", {"query": _string("search terms")}, ["query"]),
    _schema("play_media", "Play a song or video on YouTube.", {"query": _string("song or video name")}, ["query"]),
    _schema("clear_history", "Clear the conversation history.", {}, []),
    _schema("lock_pc", "Lock the PC.", {}, []),
    _schema("enable_autostart", "Make Orion start automatically at log in.", {}, []),
    _schema("disable_autostart", "Stop Orion from starting automatically.", {}, []),
]

TOOL_FUNCTIONS = {
    "open_app": _open_app,
    "open_website": _open_website,
    "open_folder": _open_folder,
    "get_time": _get_time,
    "get_date": _get_date,
    "calculate": _calculate,
    "screenshot": _screenshot,
    "read_screen": _read_screen,
    "describe_screen": _describe_screen,
    "click_on_screen": _click_on_screen,
    "take_photo": _take_photo,
    "open_camera": _open_camera,
    "set_volume": _set_volume,
    "volume_action": _volume_action,
    "get_battery": _get_battery,
    "set_brightness": _set_brightness,
    "get_brightness": _get_brightness,
    "get_wifi": _get_wifi,
    "get_bluetooth": _get_bluetooth,
    "wifi_password": _wifi_password,
    "media": _media,
    "type_text": _type_text,
    "press_key": _press_key,
    "window_action": _window_action,
    "set_reminder": _set_reminder,
    "remind_at": _remind_at,
    "list_reminders": _list_reminders,
    "read_file": _read_file,
    "summarize_file": _summarize_file,
    "explain_word": _explain_word,
    "create_note": _create_note,
    "weather": _weather,
    "news": _news,
    "translate": _translate,
    "remember_fact": _remember_fact,
    "what_remember": _what_remember,
    "notify": _notify,
    "search": _search,
    "play_media": _play_media,
    "clear_history": _clear_history,
    "lock_pc": _lock_pc,
    "enable_autostart": _enable_autostart,
    "disable_autostart": _disable_autostart,
}


def execute_tool(name, arguments):
    """Safely run a named tool. Always returns a spoken result string."""
    if name not in TOOL_FUNCTIONS:
        return f"I don't have a tool called {name}."
    return TOOL_FUNCTIONS[name](arguments or {})


# ============================================================
# DETERMINISTIC VOICE COMMAND -> TOOL
# ============================================================

def voice_command(command):
    """Match common spoken phrases directly to tools (fast, offline)."""
    command = command.lower().strip()

    if re.search(r"\b(?:what|current)?\s*time\b", command):
        return commands.tell_time()
    if "today's date" in command or "what date" in command or "what's the date" in command:
        return commands.tell_date()
    if "battery" in command or "battery percent" in command:
        return system_control.get_battery()
    if "brightness" in command and re.search(r"set|change|lower|decrease|increase", command):
        value = calculator.words_to_number(re.sub(r"\D", " ", command).strip() or "50")
        return _set_brightness({"percent": value})
    if re.search(r"\bbrightness\b", command):
        return _get_brightness({})
    if "wifi" in command and ("password" in command or "password of" in command):
        return system_control.wifi_giveaway(command)
    if "wifi" in command:
        return system_control.get_wifi_status()
    if "bluetooth" in command:
        return system_control.get_bluetooth_status()
    if "remind me" in command or "reminder" in command:
        return _reminder_command(command)
    if "my reminders" in command or "list reminders" in command:
        return _list_reminders({})
    if "remember that" in command or "remember this" in command:
        return _remember_fact({"fact": command})
    if "what do you remember" in command or "what do you know about me" in command:
        return _what_remember({})
    if "translate" in command or "how do you say" in command:
        return _translate_command(command)
    if "weather" in command or "temperature" in command:
        city = command.replace("weather", "").replace("temperature", "").replace("in", "")
        city = re.sub(r"\b(what|is|the|today|now|check|outside)\b", "", city).strip()
        return _weather({"city": city})
    if "note" in command or "write down" in command or "save a note" in command:
        return _note_command(command)
    if "volume" in command or "mute" in command:
        return _volume_command(command)
    if re.search(r"\b(play|pause|next|previous|skip).*(song|track|music)\b", command) or \
       "next song" in command or "previous song" in command:
        return _media({"action": "next" if "next" in command else
                       ("previous" if "previous" in command else "play")})
    if "click on" in command or "click the" in command:
        target = re.sub(r"\b(click|on|the|please)\b", "", command).strip()
        return _click_on_screen({"target": target})
    if "type " in command and not _looks_like_open(command):
        text = command.split("type ", 1)[1].strip()
        return _type_text({"text": text})
    return None


def _looks_like_open(command):
    return any(word in command for word in ("open", "start", "launch", "run "))


def _volume_command(command):
    if "mute" in command:
        system_control.set_volume_updown("mute")
        return "Muted"
    match = re.search(r"(set|turn|change|make|put)\w*\s+(?:the )?(?:volume )?to\s+(\d+)", command)
    if match:
        return _set_volume({"percent": int(match.group(2))})
    if any(word in command for word in ("increase", "up", "louder", "raise")):
        system_control.set_volume_updown("up")
        return "Volume increased"
    if any(word in command for word in ("decrease", "down", "lower", "quieter", "reduce")):
        system_control.set_volume_updown("down")
        return "Volume decreased"
    current = system_control.get_volume()
    return f"Volume is at {current} percent." if current is not None else "Volume unavailable."


def _reminder_command(command):
    match = re.search(r"(\d+)\s*(?:minutes?|mins?)", command)
    text = re.sub(r"remind me|in \d+ minutes?|to |please|orion", "", command).strip()
    text = text.strip(" ,.!?") or "A reminder you asked for."
    if match:
        return _set_reminder({"minutes": int(match.group(1)), "text": text})
    match = re.search(r"(?:at|by)\s+(\d{1,2})\s*[:\s.]\s*(\d{2})", command)
    if match:
        return _remind_at({"time": f"{match.group(1)}:{match.group(2)}", "text": text})
    match = re.search(r"(\d{1,2})\s+o'?clock", command)
    if match:
        return _remind_at({"time": f"{match.group(1)}:00", "text": text})
    return "Remind me in how many minutes? Tell me like, remind me in 10 minutes to take a break."


def _translate_command(command):
    languages = {
        "telugu": "Telugu", "hindi": "Hindi", "tamil": "Tamil", "kannada": "Kannada",
        "english": "English", "spanish": "Spanish", "french": "French", "german": "German",
    }
    language = None
    for token, name in languages.items():
        if token in command:
            language = name
            break
    if "how do you say" in command:
        match = re.search(r"how do you say\s+(.+?)\s+in\s+(\w+)", command)
        if match:
            return _translate({"text": match.group(1),
                               "language": languages.get(match.group(2).lower(), match.group(2).title())})
    if language:
        match = re.search(r"translate\s+(?:the\s+)?(.+?)\s+(?:(?:in\s+)?to\s+|in\s+)\w+", command)
        text = match.group(1) if match else command
        text = re.sub(r"translate", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s+(?:in\s+)?to\s+\w+\s*$", "", text, flags=re.IGNORECASE).strip()
        text = text.strip(" .,!?")
        return _translate({"text": text, "language": language})
    return None


def _note_command(command):
    text = re.sub(r"note|write down|save a note|please|orion|that\b",
                  "", command, flags=re.IGNORECASE)
    text = (text or "").strip(" ,.!?")
    if text:
        return _create_note({"title": "note", "body": text})
    return "What should the note say?"