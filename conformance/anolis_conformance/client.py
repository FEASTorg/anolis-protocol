"""Synchronous ADPP client over stdio + uint32-LE framing.

Provider-agnostic: give it the generated protocol module, a binary, and a config.
"""

from __future__ import annotations

import select
import struct
import subprocess
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

from ._process import LineCapture, terminate_process

MAX_FRAME_BYTES = 1024 * 1024  # ADPP guardrail (1 MiB), enforced both directions


class ProviderClosed(RuntimeError):
    """Raised when the provider stream closes unexpectedly mid-exchange."""


class ProviderHang(RuntimeError):
    """Raised when the provider neither responds nor exits within the deadline."""


class OversizedResponse(RuntimeError):
    """Raised when a provider advertises a response frame larger than the cap."""


class CorrelationError(RuntimeError):
    """Raised when a response does not echo the request's request_id."""


class AdppClient:
    """Drive a provider binary over the ADPP wire protocol."""

    def __init__(
        self,
        protocol: ModuleType,
        binary: Path | str,
        config: Path | str,
        *,
        extra_args: Sequence[str] | None = None,
        client_name: str = "anolis-adpp-conformance",
        client_version: str = "0.1.0",
    ) -> None:
        self.protocol = protocol
        self.client_name = client_name
        self.client_version = client_version
        self._next_request_id = 1

        cmd = [str(binary), "--config", str(config), *(extra_args or [])]
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self.stderr_capture = LineCapture(self.process.stderr)
        self.stderr_capture.start()

    # ---- lifecycle ------------------------------------------------------
    def is_running(self) -> bool:
        return self.process.poll() is None

    def output_tail(self, lines: int = 80) -> str:
        return self.stderr_capture.tail(lines)

    def close(self, timeout: float = 3.0) -> int | None:
        """Close stdin (EOF) and wait for a graceful exit; return exit code."""
        stdin = self.process.stdin
        if stdin is not None and not stdin.closed:
            try:
                stdin.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_process(self.process, timeout=timeout)
        self.stderr_capture.stop()
        return self.process.poll()

    # ---- low-level framing (for robustness tests) -----------------------
    def _request_id(self) -> int:
        rid = self._next_request_id
        self._next_request_id += 1
        return rid

    def send_raw(self, data: bytes) -> None:
        """Write arbitrary bytes to the provider's stdin."""
        stdin = self.process.stdin
        if stdin is None:
            raise ProviderClosed("provider stdin unavailable")
        stdin.write(data)
        stdin.flush()

    def send_frame(self, payload: bytes) -> None:
        self.send_raw(struct.pack("<I", len(payload)) + payload)

    def _read_exact(self, length: int, deadline: float) -> bytes | None:
        """Read exactly ``length`` bytes before the absolute ``deadline``
        (``time.monotonic`` clock); None on clean EOF at a frame boundary."""
        stream = self.process.stdout
        assert stream is not None
        fd = stream.fileno()
        out = bytearray()
        while len(out) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out reading {length} bytes (got {len(out)})")
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                continue  # re-check the absolute deadline (a slow drip cannot stretch it)
            chunk = stream.read(length - len(out))
            if not chunk:
                if not out:
                    return None  # clean EOF at a frame boundary
                raise ProviderClosed(
                    f"stream closed mid-frame ({len(out)}/{length} bytes)\n{self.output_tail(40)}"
                )
            out.extend(chunk)
        return bytes(out)

    def read_response(self, timeout: float = 5.0) -> Any | None:
        """Read one framed Response; None if the provider closed cleanly.

        Enforces the 1 MiB frame cap on the *response* too — a broken provider
        must not be able to make the harness allocate gigabytes.
        """
        deadline = time.monotonic() + timeout
        header = self._read_exact(4, deadline)
        if header is None:
            return None
        (length,) = struct.unpack("<I", header)
        if length > MAX_FRAME_BYTES:
            raise OversizedResponse(f"response frame length {length} exceeds {MAX_FRAME_BYTES}")
        body = self._read_exact(length, deadline)
        if body is None:
            raise ProviderClosed("stream closed after length prefix")
        response = self.protocol.Response()
        response.ParseFromString(body)
        return response

    def await_outcome(self, timeout: float = 3.0) -> tuple[str, Any]:
        """For malformed-input tests: classify what the provider does next.

        Returns one of:
        - ("response", Response)  — a well-formed framed response was emitted
        - ("exit", returncode)    — the process terminated (inspect the code)
        Raises ProviderHang if it neither responds nor exits in time, and
        OversizedResponse if it advertises an over-cap frame.
        """
        try:
            resp = self.read_response(timeout=timeout)
        except ProviderClosed:
            return ("exit", self._wait_exit(timeout))
        except TimeoutError:
            if self.process.poll() is None:
                raise ProviderHang(f"no response, no exit within {timeout}s\n{self.output_tail(40)}")
            return ("exit", self.process.poll())
        if resp is None:  # clean EOF -> the process exited
            return ("exit", self._wait_exit(timeout))
        return ("response", resp)

    def _wait_exit(self, timeout: float) -> int | None:
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_process(self.process, timeout=timeout)
        return self.process.poll()

    def settle_exit(self, settle: float) -> int | None:
        """Wait up to ``settle`` seconds for the process to exit on its own.

        Returns its exit code if it terminated, or None if it is still running.
        Used to catch respond-then-crash: a provider that emits a response and
        then dies (e.g. by signal) must not be reported as conformant.
        """
        try:
            self.process.wait(timeout=settle)
        except subprocess.TimeoutExpired:
            return None
        return self.process.poll()

    def send_request(self, request: Any, timeout: float = 5.0) -> Any:
        if not self.is_running():
            raise ProviderClosed(
                f"provider exited before request (code={self.process.poll()})\n{self.output_tail(60)}"
            )
        self.send_frame(request.SerializeToString())
        response = self.read_response(timeout)
        if response is None:
            raise ProviderClosed(f"no response (provider closed)\n{self.output_tail(60)}")
        if response.request_id != request.request_id:
            raise CorrelationError(
                f"response request_id {response.request_id} != request {request.request_id}"
            )
        return response

    # ---- typed ADPP operations ------------------------------------------
    def hello(self, *, protocol_version: str = "v1") -> Any:
        req = self.protocol.Request(request_id=self._request_id())
        req.hello.protocol_version = protocol_version
        req.hello.client_name = self.client_name
        req.hello.client_version = self.client_version
        return self.send_request(req)

    def wait_ready(self, max_wait_ms_hint: int = 5000) -> Any:
        req = self.protocol.Request(request_id=self._request_id())
        req.wait_ready.max_wait_ms_hint = max_wait_ms_hint
        return self.send_request(req)

    def list_devices(self, include_health: bool = False) -> Any:
        req = self.protocol.Request(request_id=self._request_id())
        req.list_devices.include_health = include_health
        return self.send_request(req)

    def describe_device(self, device_id: str) -> Any:
        req = self.protocol.Request(request_id=self._request_id())
        req.describe_device.device_id = device_id
        return self.send_request(req)

    def read_signals(self, device_id: str, signal_ids: Sequence[str] | None = None) -> Any:
        req = self.protocol.Request(request_id=self._request_id())
        req.read_signals.device_id = device_id
        if signal_ids:
            req.read_signals.signal_ids.extend(signal_ids)
        return self.send_request(req)

    def call(
        self,
        device_id: str,
        *,
        function_id: int = 0,
        function_name: str | None = None,
        args: dict[str, Any] | None = None,
        deadline: tuple[int, int] | None = None,
    ) -> Any:
        req = self.protocol.Request(request_id=self._request_id())
        req.call.device_id = device_id
        req.call.function_id = function_id
        if function_name is not None:
            req.call.function_name = function_name
        for key, value in (args or {}).items():
            req.call.args[key].CopyFrom(value)
        if deadline is not None:
            # (seconds, nanos) set verbatim — callers may pass a malformed value
            # (e.g. nanos out of range) on purpose to test validation.
            req.call.deadline.seconds, req.call.deadline.nanos = deadline
        return self.send_request(req)

    def get_health(self) -> Any:
        req = self.protocol.Request(request_id=self._request_id())
        req.get_health.SetInParent()
        return self.send_request(req)
