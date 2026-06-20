"""Reusable conformance assertions.

Factored out of the test modules so the verifier self-tests can exercise the
*real* validation logic against deliberately-faulty fake providers — rather than
a reimplementation that could drift from what the suite actually enforces.
"""

from __future__ import annotations

from types import SimpleNamespace

from . import spec
from .client import AdppClient, ProviderHang


class ConformanceFailure(AssertionError):
    """A provider violated a conformance requirement."""


def assert_status_present(response) -> None:
    """Every Response MUST carry a Status (semantics.md §10)."""
    if not response.HasField("status"):
        raise ConformanceFailure("response is missing the required Status (semantics.md §10)")


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
