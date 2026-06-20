"""ADPP conformance **level 2** ([L2]) tests.

The strengthened bar from `semantics.md`: pre-Hello handling (§3.2), bounds →
`OUT_OF_RANGE` + non-finite → `INVALID_ARGUMENT` (§8.3), deadlines (§8.4), and
value timestamp/quality (§7.1). The whole module is marked `conformance_level(2)`,
so the harness collects it only when the provider's manifest declares
`conformance_level >= 2`. An L1 provider never runs these.
"""

from __future__ import annotations

import time

import pytest

from .checks import assert_signalvalues_l2
from .client import AdppClient

pytestmark = pytest.mark.conformance_level(2)


# ---- discovery + valid-argument synthesis ------------------------------
def _first_device_with_functions(client: AdppClient):
    for d in client.list_devices().list_devices.devices:
        caps = client.describe_device(d.device_id).describe_device.capabilities
        if caps.functions:
            return d.device_id, list(caps.functions)
    return None, []


def _synth_value(protocol, arg):
    """A valid in-bounds Value for a required ArgSpec, or None if not synthesizable."""
    v = protocol.Value()
    v.type = arg.type
    if arg.type == protocol.VALUE_TYPE_BOOL:
        v.bool_value = False
    elif arg.type == protocol.VALUE_TYPE_INT64:
        v.int64_value = arg.min_int64 if arg.HasField("min_int64") else 0
    elif arg.type == protocol.VALUE_TYPE_UINT64:
        v.uint64_value = arg.min_uint64 if arg.HasField("min_uint64") else 0
    elif arg.type == protocol.VALUE_TYPE_DOUBLE:
        if arg.HasField("min_double") and arg.HasField("max_double"):
            v.double_value = (arg.min_double + arg.max_double) / 2.0
        elif arg.HasField("min_double"):
            v.double_value = arg.min_double
        elif arg.HasField("max_double"):
            v.double_value = arg.max_double
        else:
            v.double_value = 0.0
    elif arg.type == protocol.VALUE_TYPE_STRING:
        v.string_value = arg.allowed_values[0] if arg.allowed_values else ""
    elif arg.type == protocol.VALUE_TYPE_BYTES:
        v.bytes_value = b""
    else:
        return None
    return v


def _synth_required_args(protocol, fn):
    out = {}
    for a in fn.args:
        if not a.required:
            continue
        value = _synth_value(protocol, a)
        if value is None:
            return None
        out[a.name] = value
    return out


def _double(protocol, x: float):
    v = protocol.Value()
    v.type = protocol.VALUE_TYPE_DOUBLE
    v.double_value = x
    return v


def _isolatable_bounded_call(client: AdppClient, codes, protocol):
    """(device, fn, bounded_arg, valid_args) where valid_args are accepted, else None.

    Confirms the function's other required args are accepted (call returns OK or
    UNAVAILABLE), so a later out-of-bounds call isolates the bound, not a bad arg.
    """
    dev, fns = _first_device_with_functions(client)
    if not fns:
        return None
    for fn in fns:
        bounded = next(
            (
                a
                for a in fn.args
                if a.required
                and a.type == protocol.VALUE_TYPE_DOUBLE
                and (a.HasField("min_double") or a.HasField("max_double"))
            ),
            None,
        )
        if bounded is None:
            continue
        base = _synth_required_args(protocol, fn)
        if base is None:
            continue
        ok = client.call(dev, function_id=fn.function_id, args=base)
        if ok.status.code in (codes.OK, codes.UNAVAILABLE):
            return dev, fn, bounded, base
    return None


# ---- §3.2 pre-Hello ----------------------------------------------------
def test_l2_request_before_hello_rejected(client: AdppClient, codes, status_text) -> None:
    # A non-Hello request before a successful Hello → FAILED_PRECONDITION.
    resp = client.list_devices()  # deliberately no Hello first
    assert resp.status.code == codes.FAILED_PRECONDITION, (
        f"a request before Hello must be CODE_FAILED_PRECONDITION; got {status_text(resp)}"
    )


# ---- §7.1 value timestamp + quality ------------------------------------
def test_l2_ok_signalvalues_have_timestamp_and_quality(
    ready_client: AdppClient, codes, status_text
) -> None:
    devices = ready_client.list_devices().list_devices.devices
    if not devices:
        pytest.skip("no devices")
    resp = ready_client.read_signals(devices[0].device_id)
    if resp.status.code != codes.OK:
        pytest.skip(f"default read not OK ({status_text(resp)}); the L2 rule applies to OK reads")
    assert_signalvalues_l2(resp)


# ---- §8.3 bounds → OUT_OF_RANGE; non-finite → INVALID_ARGUMENT ----------
def test_l2_out_of_bounds_arg_is_out_of_range(
    ready_client: AdppClient, codes, status_text, protocol
) -> None:
    found = _isolatable_bounded_call(ready_client, codes, protocol)
    if found is None:
        pytest.skip("no isolatable bounded-double function to exercise")
    dev, fn, arg, base = found
    oob = dict(base)
    oob[arg.name] = _double(
        protocol, (arg.max_double + 1.0) if arg.HasField("max_double") else (arg.min_double - 1.0)
    )
    resp = ready_client.call(dev, function_id=fn.function_id, args=oob)
    assert resp.status.code == codes.OUT_OF_RANGE, (
        f"out-of-bounds arg must be CODE_OUT_OF_RANGE; got {status_text(resp)}"
    )


def test_l2_non_finite_double_arg_is_invalid_argument(
    ready_client: AdppClient, codes, status_text, protocol
) -> None:
    found = _isolatable_bounded_call(ready_client, codes, protocol)
    if found is None:
        pytest.skip("no isolatable bounded-double function to exercise")
    dev, fn, arg, base = found
    bad = dict(base)
    bad[arg.name] = _double(protocol, float("inf"))
    resp = ready_client.call(dev, function_id=fn.function_id, args=bad)
    assert resp.status.code == codes.INVALID_ARGUMENT, (
        f"non-finite double arg must be CODE_INVALID_ARGUMENT; got {status_text(resp)}"
    )


# ---- §8.4 deadlines (only when the provider advertises support) ---------
def test_l2_expired_deadline_exceeded(
    client: AdppClient, codes, status_text, protocol
) -> None:
    meta = dict(client.hello().hello.metadata)
    if meta.get("supports_deadlines") != "true":
        pytest.skip("provider does not advertise supports_deadlines")
    if meta.get("supports_wait_ready") == "true":
        client.wait_ready()
    dev, fns = _first_device_with_functions(client)
    if not fns:
        pytest.skip("no functions to call")
    fn = fns[0]
    base = _synth_required_args(protocol, fn)
    if base is None:
        pytest.skip("cannot synthesize valid arguments")
    past = time.time() - 3600.0  # an hour ago — already expired
    resp = client.call(dev, function_id=fn.function_id, args=base, deadline_epoch=past)
    assert resp.status.code == codes.DEADLINE_EXCEEDED, (
        f"an already-expired deadline must yield CODE_DEADLINE_EXCEEDED; got {status_text(resp)}"
    )
