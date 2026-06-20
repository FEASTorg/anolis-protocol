"""Canonical ADPP v1 expectations the conformance suite pins.

Status-code *numbers* are resolved from the generated proto enum at runtime
(single source of truth) — never hardcoded, since the enum is not sequential.
"""

from __future__ import annotations

from types import ModuleType, SimpleNamespace

# The wire protocol version string the runtime requires. (handshake.proto's
# comment says "1" but the runtime + every provider require/emit "v1".)
PROTOCOL_VERSION = "v1"

# Hello metadata keys every provider must advertise (extras allowed).
REQUIRED_HELLO_METADATA_KEYS = frozenset({"transport", "max_frame_bytes", "supports_wait_ready"})

# WaitReady diagnostics keys the standard expects (decision: standardize the key
# set, no proto change). Only `init_time_ms` is read by the runtime today.
STANDARD_WAIT_READY_DIAGNOSTICS_KEYS = frozenset({"init_time_ms", "provider_impl", "device_count"})

_CODE_NAMES = (
    "CODE_OK",
    "CODE_INVALID_ARGUMENT",
    "CODE_NOT_FOUND",
    "CODE_FAILED_PRECONDITION",
    "CODE_OUT_OF_RANGE",
    "CODE_UNIMPLEMENTED",
    "CODE_DEADLINE_EXCEEDED",
    "CODE_UNAVAILABLE",
    "CODE_RESOURCE_EXHAUSTED",
    "CODE_INTERNAL",
    "CODE_DATA_LOSS",
)


def resolve_codes(protocol: ModuleType) -> SimpleNamespace:
    """Resolve ADPP Status.Code names -> numeric values from the proto enum."""
    code = protocol.Status.Code
    ns = {name.removeprefix("CODE_"): code.Value(name) for name in _CODE_NAMES}
    return SimpleNamespace(**ns)


def status_text(protocol: ModuleType, resp: object) -> str:
    status = getattr(resp, "status", None)
    if status is None:
        return "<no status>"
    try:
        name = protocol.Status.Code.Name(status.code)
    except ValueError:
        name = "CODE_?"
    return f"{name}({status.code}) message={status.message!r}"
