"""Resolve real Windows user folders (handles OneDrive redirection)."""

import os
import subprocess


def _powershell_folder(kind):
    try:
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            f"[System.Environment]::GetFolderPath('{kind}')"
        )
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
        return output if output and os.path.isdir(output) else None
    except Exception:
        return None


def _fallback(*parts):
    candidate = os.path.join(os.path.expanduser("~"), *parts)
    return candidate if os.path.isdir(candidate) else None


def _known(kind):
    value = _powershell_folder(kind)
    return value or None


def desktop():
    return _known("Desktop") or _fallback("Desktop") or os.path.expanduser("~")


def documents():
    return _known("MyDocuments") or _fallback("Documents")


def pictures():
    return _known("MyPictures") or _fallback("Pictures")


def downloads():
    value = _known("UserProfile")
    if value:
        candidate = os.path.join(value, "Downloads")
        return candidate if os.path.isdir(candidate) else None
    return _fallback("Downloads")


def user_home():
    return os.path.expanduser("~")