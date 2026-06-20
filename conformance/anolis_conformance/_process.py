"""Process lifecycle + output capture helpers (promoted from the sim harness)."""

from __future__ import annotations

import subprocess
import threading
from typing import Any


class LineCapture:
    """Capture a text/bytes stream's lines in a background thread (diagnostics)."""

    def __init__(self, stream: Any | None):
        self._stream = stream
        self._lines: list[str] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._stream is None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        assert self._stream is not None
        try:
            while not self._stop.is_set():
                line = self._stream.readline()
                if isinstance(line, bytes):
                    if line == b"":
                        break
                    cleaned = line.decode("utf-8", errors="replace").rstrip("\r\n")
                else:
                    if line == "":
                        break
                    cleaned = line.rstrip("\r\n")
                with self._lock:
                    self._lines.append(cleaned)
        except Exception as exc:  # best-effort diagnostics only
            with self._lock:
                self._lines.append(f"[capture-error] {exc}")

    def tail(self, lines: int = 80) -> str:
        with self._lock:
            chosen = self._lines[-lines:] if lines > 0 else self._lines
            return "\n".join(chosen)

    def stop(self, timeout: float = 1.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)


def terminate_process(proc: subprocess.Popen, timeout: float = 5.0) -> None:
    """Terminate a process, graceful (SIGTERM) then forced (SIGKILL)."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    proc.kill()
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        pass
