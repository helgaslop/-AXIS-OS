"""
LogBridge — redirects stdout/stderr to the Panel JS log viewer.
Call install(push_fn) once after the window is ready.
"""
import sys
import threading
import time


class _StreamCapture:
    """Replaces sys.stdout / sys.stderr and forwards lines to JS."""

    def __init__(self, push_fn, level: str, original):
        self._push   = push_fn
        self._level  = level
        self._orig   = original
        self._buf    = ""
        self._lock   = threading.Lock()

    def write(self, text: str):
        # Also write to original so IDE/debugger still works
        try:
            self._orig.write(text)
        except Exception:
            pass
        with self._lock:
            self._buf += text
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                line = line.rstrip()
                if line:
                    self._push(self._level, line)

    def flush(self):
        try:
            self._orig.flush()
        except Exception:
            pass

    def fileno(self):
        return self._orig.fileno()

    def isatty(self):
        return False


def install(push_fn):
    """
    push_fn(level, message) — called for each log line.
    level = "info" | "error"
    """
    sys.stdout = _StreamCapture(push_fn, "info",  sys.stdout)
    sys.stderr = _StreamCapture(push_fn, "error", sys.stderr)
