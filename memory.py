"""Persistent memory for Orion - name, preferences, long-term facts and history."""

import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "orion_memory.json")
HISTORY_FILE = os.path.join(BASE_DIR, "orion_history.json")

_memory = None
_history = None
_lock = threading.Lock()


def _defaults():
    return {
        "user_name": "",
        "preferences": {
            "language": "English",
            "model": "auto",
            "voice_speed": "+10%",
            "wake_word": "enabled",
        },
        "facts": [],
        "last_file": "",
        "last_screenshot": "",
        "reminders": [],
    }


def load():
    global _memory
    with _lock:
        if _memory is not None:
            return _memory
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                _memory = {**_defaults(), **data}
                _memory.setdefault("facts", [])
                _memory.setdefault("preferences", {})
                _memory.setdefault("reminders", [])
                return _memory
        except (OSError, ValueError):
            pass
        _memory = _defaults()
        return _memory


def save():
    if _memory is None:
        load()
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as handle:
            json.dump(_memory, handle, indent=2, ensure_ascii=False)
    except OSError as error:
        print("MEMORY SAVE ERROR:", error)


def _load_history():
    global _history
    if _history is not None:
        return _history
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            _history = data
            return _history
    except (OSError, ValueError):
        pass
    _history = []
    return _history


def _save_history():
    if _history is None:
        _load_history()
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as handle:
            json.dump(_history[-50:], handle, indent=2, ensure_ascii=False)
    except OSError:
        pass


# ------------------------------------------------------------------
# NAME
# ------------------------------------------------------------------

def set_user_name(name):
    memory = load()
    memory["user_name"] = name.strip().title()
    save()
    return memory["user_name"]


def get_user_name():
    return load()["user_name"] or ""


# ------------------------------------------------------------------
# GENERIC KEY/VALUE
# ------------------------------------------------------------------

def set(key, value):
    memory = load()
    memory[key] = value
    save()


def get(key, default=""):
    return load().get(key, default)


# ------------------------------------------------------------------
# PREFERENCES
# ------------------------------------------------------------------

def set_preference(key, value):
    memory = load()
    memory.setdefault("preferences", {})[key] = value
    save()


def get_preference(key, default=""):
    return load().get("preferences", {}).get(key, default)


# ------------------------------------------------------------------
# LONG-TERM FACTS
# ------------------------------------------------------------------

def add_fact(fact):
    memory = load()
    facts = memory.setdefault("facts", [])
    fact = str(fact).strip()
    lowered = fact.lower()
    if not fact or any(lowered == existing.lower() for existing in facts[:50]):
        return False
    facts.append(fact[:300])
    if len(facts) > 60:
        del facts[:-60]
    save()
    return True


def get_facts():
    return list(load().get("facts", []))


def clear_facts():
    memory = load()
    memory["facts"] = []
    save()


def context_for_ai():
    """Short text injected into the AI prompt so Orion remembers things."""
    memory = load()
    parts = []
    name = memory.get("user_name")
    if name:
        parts.append(f"the user's name is {name}")
    facts = memory.get("facts", [])
    if facts:
        parts.append("you remember: " + "; ".join(facts[-8:]))
    return ". ".join(parts)


# ------------------------------------------------------------------
# CONVERSATION HISTORY (persisted across restarts)
# ------------------------------------------------------------------

def remember_turn(role, text):
    history = _load_history()
    from brain import clean_answer
    text = clean_answer(text)
    if not text:
        return
    history.append({"role": role, "content": text[:300]})
    if len(history) > 60:
        del history[:-60]
    _save_history()
    return history


def recent_history(max_entries=8):
    return list(_load_history()[-max_entries:])


def clear_history():
    global _history
    _history = []
    _save_history()


# ------------------------------------------------------------------
# REMINDERS (shared with scheduler.py)
# ------------------------------------------------------------------

def get_reminders():
    return list(load().get("reminders", []))


def add_reminder(reminder):
    memory = load()
    reminder["id"] = reminder.get("id") or str(int(__import__("time").time()))
    memory.setdefault("reminders", [])
    memory["reminders"].insert(0, reminder)
    save()
    return reminder


def remove_reminder(reminder_id):
    memory = load()
    before = len(memory.get("reminders", []))
    memory["reminders"] = [
        item for item in memory.get("reminders", [])
        if str(item.get("id", "")) != str(reminder_id)
    ]
    save()
    return len(memory["reminders"]) != before