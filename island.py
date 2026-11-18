"""Orion wake visual - a live transcript window with an animated orb.

Pure tkinter, no image assets. Sleep/Stop buttons send events back to
the main assistant loop through `take_control()`.

THREAD-SAFETY NOTE (this used to crash Orion):
    Tcl/Tk must be created AND destroyed on the same thread. The entire
    window therefore lives in one dedicated thread. `close()` only signals
    that thread and then waits for it to finish tearing Tcl down; calling
    `root.destroy()` from the assistant thread (or letting Python finalize
    while Tk is still alive) causes a hard tcl86t.dll APPCRASH (0x80000003).
"""

from __future__ import annotations

import math
import queue
import threading

# IMPORTANT: tkinter is imported inside the window thread (see _run()).
# Importing it on the main thread binds Tcl's async handler to the wrong
# thread, which crashes the whole process at shutdown with
# "Tcl_AsyncDelete: async handler deleted by the wrong thread".


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
        self._closed = threading.Event()
        self._explicit_stop = False
        self._thread = threading.Thread(target=self._run, name="orion-window", daemon=True)

    # ---------------- public API (called from the assistant thread) ----------

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(timeout=5)

    @property
    def explicit_stop(self) -> bool:
        """True when the user explicitly asked Orion to quit."""
        return self._explicit_stop

    def show(self, title: str = "ORION", subtitle: str = "Listening") -> None:
        self._events.put(("show", f"{title}|{subtitle}"))

    def hide(self) -> None:
        self._events.put(("hide", ""))

    def close(self) -> None:
        """Signal the window thread to close and WAIT for safe Tcl teardown."""
        self._events.put(("close", ""))
        # This wait is essential: the window thread must destroy its own Tk
        # root before Python starts finalizing modules on the main thread.
        self._closed.wait(timeout=5)

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

    def request_sleep(self) -> None:
        """Ask the assistant loop to go to sleep (used by the tray icon)."""
        self._control_events.put("sleep")

    def request_stop(self) -> None:
        """Ask the assistant loop to quit (used by the tray icon)."""
        self._explicit_stop = True
        self._control_events.put("stop")

    # ---------------- tkinter runner ----------------

    def _run(self) -> None:
        # Import here so Tcl binds its async handler to THIS thread.
        import tkinter as tk
        from tkinter import scrolledtext

        root = None
        stopping = False
        animation_id = None
        events_id = None

        try:
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

            canvas = tk.Canvas(header, width=72, height=72, highlightthickness=0,
                               bg=self.COLOR_BG)
            canvas.pack(side="left")
            canvas.create_oval(8, 8, 64, 64, fill="#101b48",
                               outline=self.COLOR_ACCENT, width=2, tags="orb")
            canvas.create_oval(14, 14, 58, 58, fill="#172766", outline="", tags="face")
            left_eye = canvas.create_oval(26, 30, 34, 38, fill="#8cf8ff",
                                          outline="", tags="eye")
            right_eye = canvas.create_oval(38, 30, 46, 38, fill="#8cf8ff",
                                           outline="", tags="eye")
            mouth = canvas.create_arc(28, 38, 44, 52, start=200, extent=140,
                                      style="arc", outline="#f7a7ff", width=3,
                                      tags="mouth")

            titles = tk.Frame(header, bg=self.COLOR_BG)
            titles.pack(side="left", padx=12)
            title = tk.Label(titles, text="ORION", bg=self.COLOR_BG, fg=self.COLOR_TEXT,
                             font=("Segoe UI", 15, "bold"))
            title.pack(anchor="w")
            status = tk.Label(titles, text="Listening...", bg=self.COLOR_BG,
                              fg=self.COLOR_MUTED, font=("Segoe UI", 9))
            status.pack(anchor="w")

            transcript = scrolledtext.ScrolledText(
                root, bg=self.COLOR_PANEL, fg=self.COLOR_TEXT,
                insertbackground=self.COLOR_TEXT, wrap="word",
                font=("Segoe UI", 10), relief="flat", height=8, state="disabled",
            )
            transcript.pack(fill="both", expand=True, padx=12, pady=(4, 6))

            buttons = tk.Frame(root, bg=self.COLOR_BG)
            buttons.pack(fill="x", padx=12, pady=(0, 10))

            def sleep_clicked():
                self._control_events.put("sleep")

            def stop_clicked():
                self._explicit_stop = True
                self._control_events.put("stop")

            sleep_button = tk.Button(
                buttons, text="Sleep", command=sleep_clicked, bg="#1d2a4d",
                fg=self.COLOR_TEXT, activebackground="#2a3c6b",
                activeforeground=self.COLOR_TEXT, relief="flat",
                font=("Segoe UI", 10, "bold"), padx=14,
            )
            sleep_button.pack(side="left")
            stop_button = tk.Button(
                buttons, text="Stop", command=stop_clicked, bg="#4d1d2a",
                fg=self.COLOR_TEXT, activebackground="#6b2a3c",
                activeforeground=self.COLOR_TEXT, relief="flat",
                font=("Segoe UI", 10, "bold"), padx=14,
            )
            stop_button.pack(side="right")

            # ---- dragging ----
            def start_drag(event):
                root._drag_x = event.x_root - root.winfo_x()
                root._drag_y = event.y_root - root.winfo_y()

            def do_drag(event):
                root.geometry(
                    f"+{event.x_root - root._drag_x}+{event.y_root - root._drag_y}"
                )

            header.bind("<Button-1>", start_drag)
            header.bind("<B1-Motion>", do_drag)
            titles.bind("<Button-1>", start_drag)
            titles.bind("<B1-Motion>", do_drag)
            root.protocol("WM_DELETE_WINDOW", stop_clicked)

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
                nonlocal animation_id
                if stopping:
                    return
                if visible:
                    nonlocal phase
                    phase += 0.18
                    breathe = math.sin(phase) * 3
                    blink = 5 + abs(math.sin(phase * 0.55)) * 18
                    canvas.coords(left_eye, 26, 34 - blink / 4, 34, 34 + blink / 4)
                    canvas.coords(right_eye, 38, 34 - blink / 4, 46, 34 + blink / 4)
                    canvas.coords(mouth, 28, 38 + breathe / 2, 44, 52 + breathe / 2)
                    glow = "#%02x%02x%02x" % (
                        50, int(90 + 45 * (math.sin(phase) + 1) / 2), 255,
                    )
                    canvas.itemconfig("orb", outline=glow)
                animation_id = root.after(45, animate)

            def process_events() -> None:
                nonlocal events_id, stopping
                if stopping:
                    return
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
                        stopping = True
                        # Leave mainloop now; Tcl is destroyed in finally below,
                        # on this same thread, with no callbacks left pending.
                        root.quit()
                        return
                events_id = root.after(30, process_events)

            events_id = root.after(30, process_events)
            animation_id = root.after(45, animate)
            self._ready.set()
            root.mainloop()
        except Exception:
            # A GUI problem must never take down the voice assistant.
            pass
        finally:
            # Only stop the event loop here. Do NOT call root.destroy(): with
            # repeating after() callbacks it deletes Tcl's async handler from
            # the wrong thread and hard-crashes the process at shutdown
            # (Tcl_AsyncDelete / tcl86t.dll 0x80000003). The callbacks above
            # see `stopping` and stop rescheduling themselves.
            if root is not None:
                try:
                    root.quit()
                except Exception:
                    pass
            self._closed.set()
