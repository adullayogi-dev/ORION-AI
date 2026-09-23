"""Orion scheduler - reminders and one-shot timers in a background thread."""

import datetime
import threading
import time
import uuid

import memory


class Scheduler:
    def __init__(self):
        self._callbacks = []
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._run, name="orion-scheduler", daemon=True)
        self._started = False

    def on_fire(self, callback):
        """Register a callback(text) invoked when a reminder is due."""
        self._callbacks.append(callback)

    def start(self):
        if self._started:
            return
        self._started = True
        self._thread.start()

    def stop(self):
        self._cancel.set()

    def _run(self):
        while not self._cancel.is_set():
            now = time.time()
            due = []
            for item in memory.get_reminders():
                try:
                    when = float(item.get("when", 0))
                    if when <= now and not item.get("fired"):
                        due.append(item)
                except (TypeError, ValueError):
                    continue
            for item in due:
                memory.remove_reminder(item.get("id"))
                item["fired"] = True
                for callback in self._callbacks:
                    try:
                        callback(str(item.get("text", "")))
                    except Exception as error:
                        print("REMINDER CALLBACK ERROR:", error)
            self._cancel.wait(5)


def add_minutes_reminder(minutes, text):
    """Schedule a reminder `minutes` from now. Returns a spoken confirmation."""
    minutes = max(1, int(minutes or 1))
    when = time.time() + minutes * 60
    title = "Orion Reminder"
    reminder = {"id": uuid.uuid4().int, "text": text, "when": when, "title": title,
                "at": datetime.datetime.now().strftime("%I:%M %p")}
    memory.add_reminder(reminder)
    return f"Reminder set for {minutes} minute{'s' if minutes != 1 else ''} from now."


def add_at_reminder(hh, mm, text):
    """Schedule a reminder at a given HH:MM on the clock (24h)."""
    now = datetime.datetime.now()
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    when = time.mktime(target.timetuple())
    title = "Orion Reminder"
    reminder = {"id": uuid.uuid4().int, "text": text, "when": when, "title": title,
                "at": target.strftime("%I:%M %p")}
    memory.add_reminder(reminder)
    return f"Reminder set for {target.strftime('%I:%M %p')}."


def list_reminders():
    items = memory.get_reminders()
    if not items:
        return "You have no reminders set."
    lines = []
    for pos, item in enumerate(items, start=1):
        at = item.get("at", "")
        lines.append(f"{pos}. {item.get('text', '')} at {at}")
    return "Your reminders: " + " ".join(lines)


if __name__ == "__main__":
    scheduler = Scheduler()
    scheduler.on_fire(lambda text: print("FIRE:", text))
    scheduler.start()
    print(add_minutes_reminder(0.02, "test reminder"))