"""Orion wake visual - a live transcript window with an animated orb.

Pure tkinter, no image assets. Sleep/Stop buttons send events back to
the main assistant loop through `take_control()`.
"""

from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext


class OrionIsland:
    """A small always-on-top window with the transcript and Orb."""

    COLOR_BG = "#0b1023"
    COLOR_PANEL = "#131a36"
    COLOR_ACCENT = "#355bff"
    COLOR_TEXT = "#f2f5ff"
    COLOR_MUTED = "#9fb2d8"
    COLOR_USER = "#ffd77a"
    COLOR_AI = "#a8f0c8"

    def __init__(self) -> None:
        self._events: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()
        self._control_events: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="orion-window", daemon=True)

    # ---------------- public API (called from the assistant thread) ----------

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(timeout=3)

    def show(self, title: str = "ORION", subtitle: str = "Listening") -> None:
        self._events.put(("show", f"{title}|{subtitle}"))

    def hide(self) -> None:
        self._events.put(("hide", ""))

    def close(self) -> None:
        self._events.put(("close", ""))

    def set_status(self, text: str) -> None:
        self._events.put(("status", text))

    def log(self, role: str, text: str) -> None:
        label = "YOU" if role == "user" else "ORION"
        self._events.put(("log", f"{label}|{text}"))

    def take_control(self) -> str | None:
        """Return 'sleep', 'stop' or None (called by the assistant loop)."""
        try:
            return self._control_events.get_nowait()
        except queue.Empty:
            return None

    # ---------------- tkinter runner ----------------

    def _run(self) -> None:
        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.98)
        root.configure(bg=self.COLOR_BG)

        width, height = 460, 320
        x = (root.winfo_screenwidth() - width) // 2
        y = root.winfo_screenheight() - height - 60
        root.geometry(f"{width}x{height}+{x}+{y}")

        header = tk.Frame(root, bg=self.COLOR_BG)
        header.pack(fill="x", padx=12, pady=(10, 4))

        canvas = tk.Canvas(header, width=72, height=72, highlightthickness=0, bg=self.COLOR_BG)
        canvas.pack(side="left")
        canvas.create_oval(8, 8, 64, 64, fill="#101b48", outline=self.COLOR_ACCENT, width=2, tags="orb")
        canvas.create_oval(14, 14, 58, 58, fill="#172766", outline="", tags="face")
        left_eye = canvas.create_oval(26, 30, 34, 38, fill="#8cf8ff", outline="", tags="eye")
        right_eye = canvas.create_oval(38, 30, 46, 38, fill="#8cf8ff", outline="", tags="eye")
        mouth = canvas.create_arc(28, 38, 44, 52, start=200, extent=140,
                                  style="arc", outline="#f7a7ff", width=3, tags="mouth")

        titles = tk.Frame(header, bg=self.COLOR_BG)
        titles.pack(side="left", padx=12)
        title = tk.Label(titles, text="ORION", bg=self.COLOR_BG, fg=self.COLOR_TEXT,
                         font=("Segoe UI", 15, "bold"))
        title.pack(anchor="w")
        status = tk.Label(titles, text="Listening...", bg=self.COLOR_BG, fg=self.COLOR_MUTED,
                          font=("Segoe UI", 9))
        status.pack(anchor="w")

        transcript = scrolledtext.ScrolledText(
            root, bg=self.COLOR_PANEL, fg=self.COLOR_TEXT, insertbackground=self.COLOR_TEXT,
            wrap="word", font=("Segoe UI", 10), relief="flat", height=8, state="disabled",
        )
        transcript.pack(fill="both", expand=True, padx=12, pady=(4, 6))

        buttons = tk.Frame(root, bg=self.COLOR_BG)
        buttons.pack(fill="x", padx=12, pady=(0, 10))

        def sleep_clicked():
            self._control_events.put("sleep")

        def stop_clicked():
            self._control_events.put("stop")

        sleep_button = tk.Button(buttons, text="Sleep", command=sleep_clicked,
                                 bg="#1d2a4d", fg=self.COLOR_TEXT, activebackground="#2a3c6b",
                                 activeforeground=self.COLOR_TEXT, relief="flat",
                                 font=("Segoe UI", 10, "bold"), padx=14)
        sleep_button.pack(side="left")
        stop_button = tk.Button(buttons, text="Stop", command=stop_clicked,
                                bg="#4d1d2a", fg=self.COLOR_TEXT, activebackground="#6b2a3c",
                                activeforeground=self.COLOR_TEXT, relief="flat",
                                font=("Segoe UI", 10, "bold"), padx=14)
        stop_button.pack(side="right")

        # ---- dragging ----
        def start_drag(event):
            root._drag_x, root._drag_y = event.x_root - root.winfo_x(), event.y_root - root.winfo_y()

        def do_drag(event):
            root.geometry(f"+{event.x_root - root._drag_x}+{event.y_root - root._drag_y}")

        header.bind("<Button-1>", start_drag)
        header.bind("<B1-Motion>", do_drag)
        titles.bind("<Button-1>", start_drag)
        titles.bind("<B1-Motion>", do_drag)

        visible = False
        phase = 0.0

        def log_line(payload: str) -> None:
            label, message = payload.split("|", 1)
            tag = "user" if label == "YOU" else "ai"
            transcript.configure(state="normal")
            transcript.insert("end", f"{label}: ", (tag,))
            transcript.insert("end", message + "\n", (tag,))
            transcript.see("end")
            transcript.configure(state="disabled")

        def animate() -> None:
            nonlocal phase
            if visible:
                phase += 0.18
                breathe = math.sin(phase) * 3
                blink = 5 + abs(math.sin(phase * 0.55)) * 18
                canvas.coords(left_eye, 26, 34 - blink / 4, 34, 34 + blink / 4)
                canvas.coords(right_eye, 38, 34 - blink / 4, 46, 34 + blink / 4)
                canvas.coords(mouth, 28, 38 + breathe / 2, 44, 52 + breathe / 2)
                glow = "#%02x%02x%02x" % (50, int(90 + 45 * (math.sin(phase) + 1) / 2), 255)
                canvas.itemconfig("orb", outline=glow)
            root.after(45, animate)

        def process_events() -> None:
            nonlocal visible
            while True:
                try:
                    event, value = self._events.get_nowait()
                except queue.Empty:
                    break

                if event == "show":
                    heading, detail = value.split("|", 1)
                    title.configure(text=heading or "ORION")
                    status.configure(text=detail or "Listening")
                    visible = True
                    root.deiconify()
                    root.lift()
                    root.attributes("-topmost", True)
                elif event == "hide":
                    visible = False
                    root.withdraw()
                elif event == "status":
                    status.configure(text=value)
                elif event == "log":
                    log_line(value)
                elif event == "close":
                    root.destroy()
                    return
            root.after(30, process_events)

        root.after(0, lambda: root.attributes("-topmost", True))
        root.after(30, process_events)
        root.after(45, animate)
        self._ready.set()
        root.mainloop()