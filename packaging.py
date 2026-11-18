"""Orion packaging - logging, tray icon and autostart helpers."""

import logging
import os
import threading

import system_control

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orion.log")
STOP_FLAG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orion.stop")

_configured = False


def setup_logging():
    global _configured
    if _configured:
        return
    _configured = True
    try:
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger = logging.getLogger("orion")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
    except Exception as error:
        print("LOGGING ERROR:", error)


def log(message):
    try:
        logging.getLogger("orion").info(message)
    except Exception:
        pass


def is_autostart_enabled():
    return system_control.get_autostart()


def mark_explicit_stop():
    """Tell the background watchdog that this shutdown was intentional."""
    try:
        with open(STOP_FLAG, "w", encoding="utf-8") as handle:
            handle.write("stop")
    except Exception:
        pass


def clear_explicit_stop():
    try:
        if os.path.exists(STOP_FLAG):
            os.remove(STOP_FLAG)
    except Exception:
        pass


def was_explicit_stop():
    return os.path.exists(STOP_FLAG)


class TrayRuntimeError(RuntimeError):
    pass


try:
    import pystray
    from PIL import Image, ImageDraw
    PYSTRAY_AVAILABLE = True
except Exception:
    PYSTRAY_AVAILABLE = False


def tray_icon(on_sleep, on_stop):
    """Start a system-tray icon in a daemon thread.

    Returns a callable to stop it, or None when the tray isn't available.
    """
    if not PYSTRAY_AVAILABLE:
        return None

    import pystray

    def build_image():
        image = Image.new("RGB", (64, 64), "#0b1023")
        draw = ImageDraw.Draw(image)
        draw.ellipse((6, 6, 58, 58), fill="#101b48", outline="#355bff", width=3)
        draw.ellipse((18, 22, 27, 31), fill="#8cf8ff")
        draw.ellipse((37, 22, 46, 31), fill="#8cf8ff")
        draw.arc((24, 34, 40, 50), start=200, end=340, fill="#f7a7ff", width=4)
        return image

    # pystray calls actions with (icon, item); wrap the zero-arg callbacks.
    def sleep_action(icon=None, item=None):
        try:
            on_sleep()
        except Exception as error:
            print("TRAY SLEEP ERROR:", error)

    def stop_action(icon=None, item=None):
        try:
            on_stop()
        except Exception as error:
            print("TRAY STOP ERROR:", error)

    menu = None
    try:
        menu = pystray.Menu(
            pystray.MenuItem("Sleep", sleep_action, default=True),
            pystray.MenuItem("Quit", stop_action),
        )
        icon = pystray.Icon("ORION", build_image(), "ORION AI", menu)
        thread = threading.Thread(target=icon.run, name="orion-tray", daemon=True)
        thread.start()
        return icon
    except Exception as error:
        print("TRAY ERROR:", error)
        return None


if __name__ == "__main__":
    print("autostart:", is_autostart_enabled())