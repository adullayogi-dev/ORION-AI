"""Small persistent memory for Orion (user name, preferences)."""

import json
import os

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orion_memory.json")

_memory = None


def _defaults():
    return {
        "user_name": "",
        "preferences": {},
        "last_file": "",
        "last_screenshot": "",
    }


def load():
    global _memory
    if _memory is not None:
        return _memory

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            _memory = {**_defaults(), **data}
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


def set_user_name(name):
    memory = load()
    memory["user_name"] = name.strip().title()
    save()
    return memory["user_name"]


def get_user_name():
    return load()["user_name"] or ""


def set(key, value):
    memory = load()
    memory[key] = value
    save()


def get(key, default=""):
    return load().get(key, default)