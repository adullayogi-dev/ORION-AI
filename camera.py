"""Orion camera control - open the Windows Camera app and take photos."""

import os
import subprocess
import time

import winfolders

PHOTO_DIR = os.path.join(winfolders.pictures(), "OrionPhotos")
CAMERA_APP_ID = "Microsoft.WindowsCamera_8wekyb3d8bbwe!App"


def _start_apps():
    """Return a {normalized_name: appid} map from Windows Get-StartApps."""
    script = r'Get-StartApps | ForEach-Object { "{0}`t{1}" -f $_.Name, $_.AppID }'
    try:
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=20
        ).stdout
    except Exception as error:
        print("GET-STARTAPPS ERROR:", error)
        return {}

    apps = {}
    for line in output.splitlines():
        if "\t" not in line:
            continue
        name, appid = line.split("\t", 1)
        normalized = "".join(ch for ch in name.lower() if ch.isalnum())
        if normalized:
            apps[normalized] = appid.strip()
    return apps


def open_camera():
    """Launch the Windows Camera app."""
    # 1) Find the real Camera AppID through Start Apps.
    try:
        apps = _start_apps()
        for name, appid in apps.items():
            if "camera" in name:
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appid}"])
                return True
    except Exception as error:
        print("CAMERA OPEN ERROR:", error)

    # 2) Fallback to the well-known AppID.
    try:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{CAMERA_APP_ID}"])
        return True
    except Exception as error:
        print("CAMERA OPEN ERROR:", error)
        return False


def take_photo():
    """Capture a photo from the webcam and save it to Pictures/OrionPhotos."""
    os.makedirs(PHOTO_DIR, exist_ok=True)
    filename = os.path.join(PHOTO_DIR, f"photo_{int(time.time())}.png")

    try:
        import cv2
    except ImportError:
        # No camera library installed - open the Camera app instead.
        open_camera()
        return None, "webcam library missing"

    capture = None
    try:
        capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not capture.isOpened():
            capture = cv2.VideoCapture(0)
        if not capture.isOpened():
            open_camera()
            return None, "no webcam found"

        # Warm up - the first frames are often dark or black.
        for _ in range(12):
            capture.read()

        ok, frame = capture.read()
        if not ok:
            return None, "camera read failed"

        # Store upright, portrait-friendly images.
        if hasattr(cv2, "imwrite"):
            saved = cv2.imwrite(filename, frame)
            if saved and os.path.exists(filename):
                return filename, None
        return None, "save failed"

    except Exception as error:
        print("PHOTO ERROR:", error)
        return None, str(error)

    finally:
        if capture is not None:
            capture.release()


if __name__ == "__main__":
    result, error = take_photo()
    print("PHOTO:", result or error)