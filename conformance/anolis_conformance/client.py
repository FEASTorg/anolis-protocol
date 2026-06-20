"""Synchronous ADPP client over stdio + uint32-LE framing.

Provider-agnostic: give it the generated protocol module, a binary, and a config.
Promoted and generalized from the provider-sim test harness.
"""

from __future__ import annotations

import select
import struct
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

from ._process import LineCapture, terminate_process

MAX_FRAME_BYTES = 1024 * 1024  # ADPP guardrail (1 MiB)


class ProviderClosed(RuntimeError):
    """Raised when the provider stream closes unexpectedly mid-exchange."""


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

    def _read_exact(self, length: int, timeout: float) -> bytes | None:
        """Read exactly ``length`` bytes within ``timeout``; None on clean EOF."""
        stream = self.process.stdout
        assert stream is not None
        fd = stream.fileno()
        out = bytearray()
        deadline_budget = timeout
        while len(out) < length:
            ready, _, _ = select.select([fd], [], [], deadline_budget)
            if not ready:
                raise TimeoutError(f"timed out reading {length} bytes (got {len(out)})")
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
        """Read one framed Response; None if the provider closed cleanly."""
        header = self._read_exact(4, timeout)
        if header is None:
            return None
        (length,) = struct.unpack("<I", header)
        body = self._read_exact(length, timeout)
        if body is None:
            raise ProviderClosed("stream closed after length prefix")
        response = self.protocol.Response()
        response.ParseFromString(body)
        return response

    def send_request(self, request: Any, timeout: float = 5.0) -> Any:
        if not self.is_running():
            raise ProviderClosed(
                f"provider exited before request (code={self.process.poll()})\n{self.output_tail(60)}"
            )
        self.send_frame(request.SerializeToString())
        response = self.read_response(timeout)
        if response is None:
            raise ProviderClosed(f"no response (provider closed)\n{self.output_tail(60)}")
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
    ) -> Any:
        req = self.protocol.Request(request_id=self._request_id())
        req.call.device_id = device_id
        req.call.function_id = function_id
        if function_name is not None:
            req.call.function_name = function_name
        for key, value in (args or {}).items():
            req.call.args[key].CopyFrom(value)
        return self.send_request(req)

    def get_health(self) -> Any:
        req = self.protocol.Request(request_id=self._request_id())
        req.get_health.SetInParent()
        return self.send_request(req)
