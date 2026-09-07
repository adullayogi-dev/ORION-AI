"""Animated wake-only visual for Orion (no external image assets required)."""

from __future__ import annotations

import math
import queue
import threading
import tkinter as tk


class OrionIsland:
    """A small Siri-inspired face that exists only while Orion is awake."""

    def __init__(self) -> None:
        self._events: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="orion-island", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(timeout=2)

    def show(self, title: str = "ORION", subtitle: str = "I am listening") -> None:
        self._events.put(("show", f"{title}\n{subtitle}"))

    def hide(self) -> None:
        # Keep the listener alive, but remove every visual from the screen.
        self._events.put(("hide", ""))

    def close(self) -> None:
        self._events.put(("close", ""))

    def _run(self) -> None:
        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.97)
        root.configure(bg="#070a18")

        # Compact by design: a small status jewel, not a large dialog.
        width, height = 224, 112
        x = (root.winfo_screenwidth() - width) // 2
        root.geometry(f"{width}x{height}+{x}+24")

        canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0, bg="#070a18")
        canvas.pack(fill="both", expand=True)
        canvas.create_oval(14, 9, 106, 101, fill="#101b48", outline="#355bff", width=2, tags="orb")
        canvas.create_oval(20, 15, 100, 95, fill="#172766", outline="", tags="face")
        left_eye = canvas.create_oval(38, 43, 50, 55, fill="#8cf8ff", outline="", tags="feature")
        right_eye = canvas.create_oval(70, 43, 82, 55, fill="#8cf8ff", outline="", tags="feature")
        mouth = canvas.create_arc(44, 57, 76, 79, start=200, extent=140, style="arc", outline="#f7a7ff", width=3, tags="feature")
        title = canvas.create_text(159, 43, text="ORION", fill="#f5f7ff", font=("Segoe UI", 12, "bold"))
        status = canvas.create_text(159, 65, text="Listening", fill="#b9ccff", font=("Segoe UI", 9))

        visible = False
        phase = 0.0
        self._ready.set()

        def animate() -> None:
            nonlocal phase
            if visible:
                phase += 0.18
                breathe = math.sin(phase) * 5
                blink = 4 + abs(math.sin(phase * 0.55)) * 20
                canvas.coords(left_eye, 38, 49 - blink / 4, 50, 49 + blink / 4)
                canvas.coords(right_eye, 70, 49 - blink / 4, 82, 49 + blink / 4)
                canvas.coords(mouth, 44, 57 + breathe / 2, 76, 79 + breathe / 2)
                glow = "#%02x%02x%02x" % (50, int(90 + 45 * (math.sin(phase) + 1) / 2), 255)
                canvas.itemconfig("orb", outline=glow)
            root.after(45, animate)

        def process_events() -> None:
            nonlocal visible
            while True:
                try:
                    action, value = self._events.get_nowait()
                except queue.Empty:
                    break

                if action == "show":
                    heading, detail = value.split("\n", 1)
                    canvas.itemconfig(title, text=heading)
                    canvas.itemconfig(status, text=detail)
                    visible = True
                    root.deiconify()
                    root.lift()
                elif action == "hide":
                    visible = False
                    root.withdraw()
                elif action == "close":
                    root.destroy()
                    return
            root.after(30, process_events)

        root.after(30, process_events)
        root.after(45, animate)
        root.mainloop()
