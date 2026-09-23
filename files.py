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

DOC_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".pptx"]

ALL_EXTENSIONS = TEXT_EXTENSIONS + DOC_EXTENSIONS

MAX_READ_CHARS = 1600  # keep spoken output reasiliently short
NOTES_DIR = os.path.join(winfolders.documents(), "OrionNotes")


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
            for ext in ALL_EXTENSIONS:
                if (base.with_suffix(ext)).is_file():
                    return base.with_suffix(ext)

    for directory in SEARCH_DIRS:
        if not directory.is_dir():
            continue

        for variant in variants:
            for ext in ALL_EXTENSIONS:
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


def read_document(path):
    """Read any supported document (text, PDF, Word, Excel) into plain text."""
    suffix = Path(path).suffix.lower()
    try:
        if suffix == ".pdf":
            return _read_pdf(path)
        if suffix == ".docx":
            return _read_docx(path)
        if suffix == ".xlsx":
            return _read_xlsx(path)
        if suffix == ".pptx":
            return _read_pptx(path)
        return read_text_file(path)
    except Exception as error:
        print("DOCUMENT READ ERROR:", error)
        return None


def _read_pdf(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages[:12]:
        text = page.extract_text() or ""
        pages.append(text)
    return _strip_markup("\n".join(pages))


def _read_docx(path):
    from docx import Document
    document = Document(str(path))
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    paragraphs.append(cell.text.strip())
    return _strip_markup("\n".join(paragraphs))


def _read_xlsx(path):
    from openpyxl import load_workbook
    workbook = load_workbook(str(path), read_only=True, data_only=True)
    rows = []
    for sheet in workbook.worksheets[:3]:
        rows.append(f"Sheet: {sheet.title}")
        for index, row in enumerate(sheet.iter_rows(values_only=True)):
            if index >= 30:
                break
            values = [str(cell) for cell in row if cell is not None]
            if values:
                rows.append(" | ".join(values))
    workbook.close()
    return _strip_markup("\n".join(rows))


def _read_pptx(path):
    from pptx import Presentation
    presentation = Presentation(str(path))
    slides = []
    for index, slide in enumerate(presentation.slides[:15]):
        texts = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                texts.append(shape.text)
        if texts:
            slides.append(f"Slide {index + 1}: {' '.join(texts)}")
    return _strip_markup("\n".join(slides))


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

    content = read_document(path)
    if content is None:
        extension = path.suffix.lower()
        if extension in (".docx", ".xlsx", ".pptx"):
            return f"I found {path.name}, but the {extension.replace('.', '').upper()} reading library isn't ready."
        return f"I found {path.name} but could not read it as text."

    memory.set("last_file", str(path))

    if len(content) <= MAX_READ_CHARS:
        return f"I read {path.name}. Here is what it says. {content}"
    return (f"I read {path.name}, which is {len(content):,} characters long. "
            f"Here is the beginning. {content[:MAX_READ_CHARS]}")


def summarize_file(command):
    """Read a file and ask the AI for a short summary of it."""
    requested = command.replace("summarize", "").replace("summarise", "")
    requested = requested.replace("the file", "").replace("this file", "").replace("that file", "").strip()
    path = find_file(requested) if requested else None
    if path is None:
        saved = memory.get("last_file", "")
        if saved and os.path.exists(saved):
            path = saved
    if path is None:
        return "Which file should I summarize? Name the file you read earlier, or say summarize then the file name."
    content = read_document(path)
    if not content:
        return f"I could not read {os.path.basename(path)}."
    try:
        from brain import summarize_text
        summary = summarize_text(content[:4000])
        return f"Here's a summary of {os.path.basename(path)}: {summary}"
    except Exception as error:
        print("SUMMARIZE ERROR:", error)
        return f"I could not summarize {os.path.basename(path)}."


def create_note(title, body):
    """Save a note as a text file under Documents/OrionNotes."""
    os.makedirs(NOTES_DIR, exist_ok=True)
    safe_title = "".join(ch for ch in title if ch.isalnum() or ch in " _-").strip() or "note"
    filename = os.path.join(NOTES_DIR, f"{safe_title}.txt")
    with open(filename, "w", encoding="utf-8") as handle:
        handle.write(str(body) + "\n")
    return filename


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