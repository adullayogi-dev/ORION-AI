"""Orion file & word helper - read text files aloud and explain words."""

import os
import re
from pathlib import Path

import memory
import winfolders

HOME = Path.home().expanduser()
SEARCH_DIRS = [
    Path(winfolders.desktop()),
    Path(winfolders.documents()),
    Path(winfolders.downloads()),
    HOME,
]

TEXT_EXTENSIONS = [
    ".txt", ".md", ".markdown", ".py", ".json", ".csv", ".log",
    ".ini", ".cfg", ".conf", ".yaml", ".yml", ".xml", ".html", ".htm",
    ".cpp", ".c", ".h", ".java", ".js", ".ts", ".tsx", ".jsx",
    ".sh", ".bat", ".ps1", ".ipynb", ".rst", ".rtf", ".srt", ".vtt",
]

MAX_READ_CHARS = 1600  # keep spoken output reasiliently short


def find_file(name):
    """Locate a text file by name (with or without extension)."""
    candidate = Path(name).expanduser()
    if candidate.is_absolute() and candidate.is_file():
        return candidate

    variants = [name]
    if " " in name:
        variants.append(name.replace(" ", "_"))
        variants.append(name.replace(" ", "-"))
    if "_" in name:
        variants.append(name.replace("_", " "))

    for variant in variants:
        base = Path(variant)
        if base.is_file():
            return base
        if not base.suffix:
            for ext in TEXT_EXTENSIONS:
                if (base.with_suffix(ext)).is_file():
                    return base.with_suffix(ext)

    for directory in SEARCH_DIRS:
        if not directory.is_dir():
            continue

        for variant in variants:
            for ext in TEXT_EXTENSIONS:
                exact = directory / f"{variant}{ext}"
                if exact.is_file():
                    return exact
            for match in directory.glob(f"{variant}.*"):
                if match.is_file():
                    return match

    # Fuzzy match: compare cleaned file stems to the spoken name.
    target_norm = _normalize(name)
    if len(target_norm) >= 3:
        for directory in SEARCH_DIRS:
            if not directory.is_dir():
                continue
            try:
                for match in directory.iterdir():
                    if not match.is_file():
                        continue
                    stem_norm = _normalize(match.stem)
                    if not stem_norm:
                        continue
                    if stem_norm == target_norm or target_norm in stem_norm:
                        return match
            except OSError:
                continue

    return None


def _normalize(text):
    return "".join(ch for ch in text.lower() if ch.isalnum())


def read_text_file(path):
    """Read a text file safely, trying several common encodings."""
    content = None
    for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            content = Path(path).read_text(encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError, OSError):
            continue

    if content is None:
        return None
    content = content.lstrip("\ufeff")
    return _strip_markup(content)


def _strip_markup(content):
    content = re.sub(r"```[a-zA-Z]*", "", content)
    content = re.sub(r"[*_>`#~\[\]]", " ", content)
    content = re.sub(r"\s+", " ", content).strip()
    return content


def read_and_speak(command, spoken_name="Orion"):
    """Handle 'read <file>' requests. Returns text for Orion to speak."""
    match = re.search(
        r"\bread\s*(?:the|out\s*loud)?\s*(?:text\s*)?(?:file\s*)?"
        r"\s*(?:from\s*(?:the\s*)?(?:my\s*)?(?:desktop|documents|downloads|folder|computer)?\s*:?\s*)?(.+)",
        command
    )
    if not match:
        return None

    requested = match.group(1).strip().strip(".,;:'\"").strip()
    requested = re.sub(
        r"\s+(?:on|in|from|of|at)\s+(?:my|the)?\s*(?:desktop|documents|downloads|computer|folder|home)\s*$",
        "",
        requested,
    ).strip()
    if not requested or _is_not_a_file_phrase(requested):
        return None

    path = find_file(requested)
    if path is None:
        return f"I couldn't find a file called {requested}. Try the full file name."

    content = read_text_file(path)
    if content is None:
        return f"I found {path.name} but could not read it as text."

    memory.set("last_file", str(path))

    if len(content) <= MAX_READ_CHARS:
        return f"I read {path.name}. Here is what it says. {content}"
    return (f"I read {path.name}, which is {len(content):,} characters long. "
            f"Here is the beginning. {content[:MAX_READ_CHARS]}")


def _is_not_a_file_phrase(text):
    lowered = text.lower()
    non_files = (
        "aloud", "that file", "out loud", "your mind", "my mind",
        "through this", "again", "the words", "more",
    )
    return any(part == lowered for part in non_files)


def explain_words(command):
    """Answer 'what does X mean' / 'explain X' using the AI brain."""
    match = re.search(
        r"\b(?:what\s*does|what\s*do|what\s*is\s*the\s*meaning\s*of|explain\s*the\s*meaning\s*of|meaning\s*of|define|explain)\s+(.+?)(?:\s*please\s*|\s*to\s*me\s*)?$",
        command
    )
    if not match:
        return None

    topic = match.group(1).strip().strip("?.,;:'\"")
    if not topic or len(topic) < 2 or len(topic) > 120:
        return None

    # Only attach file context when the word actually appears in that file.
    context = ""
    last_file = memory.get("last_file", "")
    if last_file and os.path.exists(last_file):
        content = read_text_file(last_file)
        if content and topic.lower() in content.lower():
            excerpt = content[:600]
            context = (
                f"\nThe user recently read this file ({os.path.basename(last_file)}). "
                f"'{topic}' appears in it, so explain it in that context. File content: {excerpt}"
            )

    try:
        from brain import ask_ai
        prompt = (f"Explain the meaning of '{topic}' in a clear, friendly way for a general "
                  f"person. Use 2 or 3 short sentences. Do not use markdown.{context}")
        explanation = ask_ai(prompt)
        return explanation
    except Exception as error:
        print("EXPLAIN ERROR:", error)
        return f"I couldn't look up '{topic}' right now."


if __name__ == "__main__":
    sample = input("Command: ").strip()
    print("READ:", read_and_speak(sample))
    print("EXPLAIN:", explain_words(sample))