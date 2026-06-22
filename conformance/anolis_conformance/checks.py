"""Reusable conformance assertions.

Factored out of the test modules so the verifier self-tests can exercise the
*real* validation logic against deliberately-faulty fake providers — rather than
a reimplementation that could drift from what the suite actually enforces.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from . import spec
from .client import AdppClient, ProviderHang


class ConformanceFailure(AssertionError):
    """A provider violated a conformance requirement."""


def assert_status_present(response) -> None:
    """Every Response MUST carry a Status (semantics.md §10)."""
    if not response.HasField("status"):
        raise ConformanceFailure("response is missing the required Status (semantics.md §10)")


# QUALITY_UNSPECIFIED is 0 in the proto enum (proto3 default).
_QUALITY_UNSPECIFIED = 0
# Valid google.protobuf.Timestamp range (0001-01-01 .. 9999-12-31, UTC).
_TS_MIN_SECONDS = -62135596800
_TS_MAX_SECONDS = 253402300799


def assert_signalvalues_l2(read_response) -> None:
    """semantics.md §7.1 [L2]: in a CODE_OK ReadSignalsResponse every SignalValue
    MUST set a **valid** ``timestamp`` and a ``quality`` that is a **defined**
    enum value other than ``QUALITY_UNSPECIFIED``. Caller checks the status is OK
    first."""
    for value in read_response.read_signals.values:
        sid = value.signal_id
        if not value.HasField("timestamp"):
            raise ConformanceFailure(f"signal {sid!r}: [L2] requires a timestamp on OK values")
        ts = value.timestamp
        if not (0 <= ts.nanos <= 999_999_999):
            raise ConformanceFailure(
                f"signal {sid!r}: timestamp.nanos {ts.nanos} is not in [0, 1e9)"
            )
        if not (_TS_MIN_SECONDS <= ts.seconds <= _TS_MAX_SECONDS):
            raise ConformanceFailure(
                f"signal {sid!r}: timestamp.seconds {ts.seconds} is outside the valid range"
            )
        valid_qualities = set(value.DESCRIPTOR.fields_by_name["quality"].enum_type.values_by_number)
        if value.quality not in valid_qualities:
            raise ConformanceFailure(
                f"signal {sid!r}: quality {value.quality} is not a value defined by the schema"
            )
        if value.quality == _QUALITY_UNSPECIFIED:
            raise ConformanceFailure(f"signal {sid!r}: quality must not be QUALITY_UNSPECIFIED")


_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")


def assert_signal_ids_snake_case(device_id: str, capabilities) -> None:
    """Anolis executable profile — capability convention: every ``signal_id`` is
    snake_case (``^[a-z][a-z0-9_]*$``: lowercase letter first, then lowercase
    letters / digits / underscores; no dots, no camelCase). A *convention*, not
    core ADPP — see ``docs/profiles/anolis-executable-profile-v1.md``; waivable."""
    bad = [s.signal_id for s in capabilities.signals if not _SNAKE_CASE.match(s.signal_id)]
    if bad:
        raise ConformanceFailure(
            f"device {device_id!r}: signal_id(s) must be snake_case "
            f"(^[a-z][a-z0-9_]*$); offending: {bad}"
        )


def assert_function_ids_per_type_from_one(device_id: str, capabilities) -> None:
    """Anolis executable profile — capability convention: a device's
    ``function_id``s are numbered per device type from 1, i.e. the contiguous set
    ``{1..N}`` for N declared functions (not a global counter like 1001+, not an
    arbitrary value like 10). A *convention*, not core ADPP — see
    ``docs/profiles/anolis-executable-profile-v1.md``; waivable."""
    ids = sorted(f.function_id for f in capabilities.functions)
    if ids and ids != list(range(1, len(ids) + 1)):
        raise ConformanceFailure(
            f"device {device_id!r}: function_ids should be per-type {{1..{len(ids)}}}; got {ids}"
        )


def _defined_error_codes(codes: SimpleNamespace) -> set[int]:
    """Every status code the proto enum defines, minus OK and UNSPECIFIED."""
    return set(vars(codes).values()) - {codes.OK, codes.UNSPECIFIED}


def assert_controlled_malformed(
    client: AdppClient,
    codes: SimpleNamespace,
    *,
    timeout: float = 3.0,
    settle: float = 0.5,
) -> None:
    """A provider's response to a malformed/garbage frame must be *controlled*.

    Accepted:
    - a well-formed framed response carrying a real **error** status, after which
      the process does not crash; or
    - a clean documented exit (codes 0/2/3).

    Rejected (raise :class:`ConformanceFailure`):
    - a hang;
    - a crash (killed by a signal -> negative return code), including
      respond-then-crash;
    - a response with no status, or one carrying ``CODE_OK`` / ``CODE_UNSPECIFIED``
      (garbage must never read as success);
    - an undocumented exit code, or an over-cap/unparseable response
      (``await_outcome`` surfaces these as exceptions to the caller).
    """
    try:
        outcome, value = client.await_outcome(timeout)
    except ProviderHang as exc:
        raise ConformanceFailure(str(exc)) from None

    if outcome == "response":
        if not value.HasField("status"):
            raise ConformanceFailure("malformed input produced a response with no status")
        code = value.status.code
        # Must be a DEFINED error code — not OK, not UNSPECIFIED, and not some
        # arbitrary integer outside the enum.
        if code not in _defined_error_codes(codes):
            raise ConformanceFailure(
                f"malformed input must yield a defined error status; got code={code} "
                f"message={value.status.message!r}"
            )
        # A provider may respond-then-exit, but only with a documented exit code;
        # a crash (negative) or an undocumented exit after responding is a failure.
        rc = client.settle_exit(settle)
        if rc is not None and rc not in spec.ALLOWED_MALFORMED_EXIT_CODES:
            raise ConformanceFailure(
                f"provider emitted a response then exited {rc} "
                f"(allowed: {sorted(spec.ALLOWED_MALFORMED_EXIT_CODES)}; negative = crash)"
            )
        return

    # outcome == "exit"
    if value is None:
        raise ConformanceFailure("provider did not produce an exit code")
    if value < 0:
        raise ConformanceFailure(
            f"provider crashed on malformed input (killed by signal, returncode={value})"
        )
    if value not in spec.ALLOWED_MALFORMED_EXIT_CODES:
        raise ConformanceFailure(
            f"provider exited {value} on malformed input "
            f"(allowed: {sorted(spec.ALLOWED_MALFORMED_EXIT_CODES)})"
        )
