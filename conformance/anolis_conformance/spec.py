"""Canonical ADPP v1 expectations the conformance suite pins.

Status-code *numbers* are resolved from the generated proto enum at runtime
(single source of truth) — never hardcoded, since the enum is not sequential.
"""

from __future__ import annotations

from types import ModuleType, SimpleNamespace

# The wire protocol version string the runtime requires. (handshake.proto's
# comment says "1" but the runtime + every provider require/emit "v1".)
PROTOCOL_VERSION = "v1"

# Hello metadata keys every provider must advertise (extras allowed) + the
# expected values for the framed-stdio profile.
REQUIRED_HELLO_METADATA_KEYS = frozenset({"transport", "max_frame_bytes", "supports_wait_ready"})
EXPECTED_TRANSPORT = "stdio+uint32_le"
EXPECTED_MAX_FRAME_BYTES = str(1024 * 1024)

# Documented framed-stdio exit codes a provider MAY use to terminate on a
# malformed/garbage stream: 0 = clean EOF, 2 = read-frame error, 3 = parse error.
# A NEGATIVE return code (killed by a signal: SIGSEGV/SIGABRT) is always a crash
# and never an acceptable malformed-input outcome.
ALLOWED_MALFORMED_EXIT_CODES = frozenset({0, 2, 3})

_CODE_NAMES = (
    "CODE_UNSPECIFIED",
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
