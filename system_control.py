"""Orion system control - volume, screen, power, network, media, windows, GUI."""

import ctypes
import os
import re
import subprocess
import winreg

import pyautogui
import pygetwindow as gw

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.04

# ------------------------------------------------------------------
# VOLUME (real system volume through pycaw)
# ------------------------------------------------------------------

def _core_audio():
    """Return the IAudioEndpointVolume COM pointer, or None."""
    try:
        from pycaw.pycaw import AudioUtilities
        device = AudioUtilities.GetSpeakers()
        if device is None:
            return None
        return getattr(device, "EndpointVolume", None)
    except Exception as error:
        print("VOLUME AUDIO ERROR:", error)
        return None


def get_volume():
    endpoint = _core_audio()
    if not endpoint:
        return None
    try:
        return int(round(endpoint.GetMasterVolumeLevelScalar() * 100))
    except Exception:
        return None


def set_volume(percent):
    endpoint = _core_audio()
    if not endpoint:
        return False
    try:
        percent = max(0, min(100, int(percent)))
        endpoint.SetMasterVolumeLevelScalar(percent / 100.0, None)
        return True
    except Exception as error:
        print("VOLUME SET ERROR:", error)
        return False


def set_volume_updown(level):
    if level == "up":
        set_volume((get_volume() or 0) + 10)
        return True
    if level == "down":
        set_volume((get_volume() or 0) - 10)
        return True
    if level == "mute":
        endpoint = _core_audio()
        if endpoint:
            try:
                endpoint.SetMute(1, None)
                return True
            except Exception:
                pass
    return False


# ------------------------------------------------------------------
# DISPLAY / POWER
# ------------------------------------------------------------------

def get_battery():
    """Return a status string like '87% plugged in'."""
    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_ubyte),
            ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte),
            ("SystemStatusFlag", ctypes.c_ubyte),
            ("BatteryLifeTime", ctypes.c_ulong),
            ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    status = SYSTEM_POWER_STATUS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return "Battery status unavailable."

    percent = status.BatteryLifePercent
    if percent == 255:
        percent = get_battery_wmi()
    charging = "plugged in" if status.ACLineStatus == 1 else "on battery"
    level = "battery high" if percent >= 50 else "battery low"
    return f"Battery at {percent} percent, {charging}, {level}."


def get_battery_wmi():
    try:
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Battery).EstimatedChargeRemaining"],
            capture_output=True, text=True, timeout=10)
        return int(output.stdout.strip().splitlines()[-1])
    except Exception:
        return 0


def set_brightness(percent):
    try:
        percent = max(5, min(100, int(percent)))
        script = (
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            ".WmiSetBrightness(1, {p})".format(p=percent)
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15)
        return result.returncode == 0
    except Exception as error:
        print("BRIGHTNESS ERROR:", error)
        return False


def get_brightness():
    try:
        script = "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15).stdout
        value = output.strip().splitlines()
        return int(value[0]) if value else None
    except Exception:
        return None


# ------------------------------------------------------------------
# NETWORK
# ------------------------------------------------------------------

def _netsh(args):
    try:
        result = subprocess.run(["netsh"] + args, capture_output=True, text=True, timeout=20)
        return result.stdout.strip() or result.stderr.strip()
    except Exception as error:
        print("NETSH ERROR:", error)
        return ""


def wifi_giveaway(wifi):
    try:
        output = subprocess.run(["netsh", "wlan", "show", "profiles"],
                                capture_output=True, text=True, timeout=20).stdout or ""
        profiles = re.findall(r"All User Profile\s*:\s*(.+)", output)
        for profile in profiles:
            profile = profile.strip()
            if profile.lower() in wifi.lower() or wifi.lower() in profile.lower():
                detail = subprocess.run(["netsh", "wlan", "show", "profile", profile, "key=clear"],
                                        capture_output=True, text=True, timeout=20).stdout or ""
                match = re.search(r"Key Content\s*:\s*(.+)", detail)
                if match:
                    return f"The password for {profile} is {match.group(1).strip()}."
        return "I couldn't find that saved Wi-Fi network."
    except Exception as error:
        return f"Wi-Fi password lookup failed. {error}"


def get_wifi_status():
    output = _netsh(["wlan", "show", "interfaces"])
    match = re.search(r"SSID\s*:\s*(.+)", output)
    if not match:
        return "You are not connected to Wi-Fi."
    return f"You are connected to Wi-Fi network {match.group(1).strip()}."


def get_bluetooth_status():
    try:
        script = (
            "Get-PnpDevice -Class Bluetooth -Status OK -ErrorAction SilentlyContinue "
            "| Select-Object -First 1 | ForEach-Object { $_.FriendlyName }"
        )
        output = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                capture_output=True, text=True, timeout=20).stdout.strip()
        return f"Bluetooth is on ({output.strip()})." if output else "Bluetooth is off or has no devices."
    except Exception:
        return "Bluetooth status unavailable."


# ------------------------------------------------------------------
# MEDIA KEYS / KEYBOARD / MOUSE  (pyautogui)
# ------------------------------------------------------------------

MEDIA_KEYS = {
    "play": "playpause", "pause": "playpause", "play pause": "playpause",
    "next": "nexttrack", "next track": "nexttrack", "previous": "prevtrack",
    "previous track": "prevtrack", "stop": "stop", "skip": "nexttrack",
}


def media_control(action):
    action = action.lower().strip()
    key = MEDIA_KEYS.get(action) or MEDIA_KEYS.get(action.replace(" ", " "))
    if not key:
        for token, mapped in MEDIA_KEYS.items():
            if token in action:
                key = mapped
                break
    if not key:
        return False
    try:
        pyautogui.press(key)
        return True
    except Exception:
        return False


def media_next():
    pyautogui.press("nexttrack")


def media_prev():
    pyautogui.press("prevtrack")


def media_play_pause():
    pyautogui.press("playpause")


def press_key(key):
    try:
        pyautogui.press(key)
        return True
    except Exception:
        return False


def hotkey(*keys):
    try:
        pyautogui.hotkey(*keys)
        return True
    except Exception:
        return False


def type_text(text):
    try:
        pyautogui.typewrite(text.replace("\\n", "\n"), interval=0.01)
        return True
    except Exception:
        return False


def scroll(direction, clicks=3):
    try:
        pyautogui.scroll(clicks if direction == "down" else -clicks)
        return True
    except Exception:
        return False


def click_position(x, y, double=False):
    try:
        pyautogui.click(int(x), int(y), clicks=2 if double else 1)
        return True
    except Exception as error:
        print("CLICK ERROR:", error)
        return False


# ------------------------------------------------------------------
# WINDOWS (activate / minimize / maximize / close)
# ------------------------------------------------------------------

def _window_for_app(app_name):
    try:
        windows = gw.getWindowsWithTitle(app_name)
        if windows:
            return windows[0]
        for window in gw.getAllWindows():
            if not window.title:
                continue
            if app_name.lower() in window.title.lower():
                return window
    except Exception:
        pass
    return None


def window_action(action, app_name):
    window = _window_for_app(app_name)
    if not window:
        return False
    try:
        if action in ("minimize", "minimise"):
            window.minimize()
        elif action in ("maximize", "maximise"):
            window.maximize()
        elif action in ("restore",):
            window.restore()
        elif action in ("close", "close window"):
            window.close()
        else:  # activate / open / focus
            if window.isMinimized:
                window.restore()
            window.activate()
        return True
    except Exception:
        try:
            if action == "close":
                window.close()
            else:
                window.activate()
            return True
        except Exception:
            return False


# ------------------------------------------------------------------
# AUTOSTART
# ------------------------------------------------------------------

def set_autostart(enabled):
    name = "ORION"
    exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "start_orion_silently.vbs")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, f'wscript.exe "{exe}"')
            else:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
        return True
    except OSError as error:
        print("AUTOSTART ERROR:", error)
        return False


def get_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, "ORION")
            return True
    except OSError:
        return False


# ------------------------------------------------------------------
# CLIPBOARD
# ------------------------------------------------------------------

def clip_get():
    try:
        import pyperclip
        return pyperclip.paste().strip()
    except Exception:
        return ""


def clip_set(text):
    try:
        import pyperclip
        pyperclip.copy(str(text))
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print("VOLUME:", get_volume())
    print("BATTERY:", get_battery())
    print("BRIGHTNESS:", get_brightness())
    print("WIFI:", get_wifi_status())
    print("BLUETOOTH:", get_bluetooth_status())