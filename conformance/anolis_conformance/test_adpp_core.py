"""ADPP v1 *core protocol* conformance — messages, status, correlation,
capabilities, and read/call semantics. Assertions follow docs/semantics.md (the
normative spec); where the spec permits a choice, the test accepts every
permitted behavior.
"""

from __future__ import annotations

import pytest

from . import spec
from .client import AdppClient


# ---- handshake / version ------------------------------------------------
def test_hello_v1_ok(client: AdppClient, profile, codes, status_text) -> None:
    resp = client.hello()
    assert resp.status.code == codes.OK, status_text(resp)
    assert resp.request_id == 1, "Hello response must echo request_id"
    assert resp.hello.protocol_version == spec.PROTOCOL_VERSION
    assert resp.hello.provider_name == profile.expected_provider_name


def test_hello_metadata_values(client: AdppClient) -> None:
    meta = dict(client.hello().hello.metadata)
    missing = spec.REQUIRED_HELLO_METADATA_KEYS - meta.keys()
    assert not missing, f"Hello metadata missing required keys {missing}; got {sorted(meta)}"
    assert meta["transport"] == spec.EXPECTED_TRANSPORT, f"transport={meta['transport']!r}"
    assert meta["max_frame_bytes"] == spec.EXPECTED_MAX_FRAME_BYTES, meta["max_frame_bytes"]
    assert meta["supports_wait_ready"] in ("true", "false"), meta["supports_wait_ready"]


def test_hello_unsupported_version_rejected(client: AdppClient, codes, status_text) -> None:
    # semantics.md 3: an unsupported version MUST be FAILED_PRECONDITION *or*
    # UNIMPLEMENTED (both conformant).
    resp = client.hello(protocol_version="v999")
    assert resp.status.code in (codes.FAILED_PRECONDITION, codes.UNIMPLEMENTED), (
        f"non-v1 Hello must be FAILED_PRECONDITION or UNIMPLEMENTED; got {status_text(resp)}"
    )


def test_request_id_correlation(ready_client: AdppClient) -> None:
    # semantics.md 4: providers MUST echo the request_id of each request.
    first = ready_client.list_devices().request_id
    second = ready_client.list_devices().request_id
    assert second == first + 1, "each response must echo its request's id"


# ---- inventory / capabilities ------------------------------------------
def test_list_devices_ok(ready_client: AdppClient, profile, codes, status_text) -> None:
    resp = ready_client.list_devices()
    assert resp.status.code == codes.OK, status_text(resp)
    if profile.has_mock_devices:
        assert len(resp.list_devices.devices) >= 1, "conformance config should yield >=1 device"


def test_list_devices_include_health(ready_client: AdppClient, codes, status_text) -> None:
    resp = ready_client.list_devices(include_health=True)
    assert resp.status.code == codes.OK, status_text(resp)
    # include_health=true: device_health entries (when present) reference real devices.
    device_ids = {d.device_id for d in resp.list_devices.devices}
    for dh in resp.list_devices.device_health:
        assert dh.device_id in device_ids, f"health for unknown device {dh.device_id!r}"


def test_describe_device(ready_client: AdppClient, codes, status_text) -> None:
    devices = ready_client.list_devices().list_devices.devices
    if not devices:
        pytest.skip("no devices to describe")
    resp = ready_client.describe_device(devices[0].device_id)
    assert resp.status.code == codes.OK, status_text(resp)
    caps = resp.describe_device.capabilities
    assert len(caps.signals) + len(caps.functions) >= 1, "device must declare >=1 signal or function"


def test_describe_unknown_device_not_found(ready_client: AdppClient, codes, status_text) -> None:
    resp = ready_client.describe_device("__no_such_device__")
    assert resp.status.code == codes.NOT_FOUND, (
        f"unknown device must be CODE_NOT_FOUND; got {status_text(resp)}"
    )


# ---- read / call --------------------------------------------------------
def test_read_signals_response_shape(ready_client: AdppClient, codes) -> None:
    devices = ready_client.list_devices().list_devices.devices
    if not devices:
        pytest.skip("no devices to read")
    resp = ready_client.read_signals(devices[0].device_id)  # default signal set
    # Mock backends may legitimately report data unavailable; only the shape is
    # mandatory. If OK, every value carries a signal_id and a populated value.
    if resp.status.code == codes.OK:
        for value in resp.read_signals.values:
            assert value.signal_id, "each SignalValue must carry a signal_id"
            assert value.HasField("value"), f"signal {value.signal_id} missing a value"


def test_read_unknown_signal_consistent(ready_client: AdppClient, codes, status_text) -> None:
    # semantics.md 7.1: a provider MUST choose ONE consistent behavior for an
    # unknown signal id — either fail CODE_NOT_FOUND, OR return partial results
    # that omit the unknown id. Both are conformant.
    devices = ready_client.list_devices().list_devices.devices
    if not devices:
        pytest.skip("no devices")
    caps = ready_client.describe_device(devices[0].device_id).describe_device.capabilities
    if not caps.signals:
        pytest.skip("device declares no signals")
    known = caps.signals[0].signal_id
    resp = ready_client.read_signals(devices[0].device_id, [known, "__no_such_signal__"])
    if resp.status.code == codes.NOT_FOUND:
        return  # fail-fast variant
    if resp.status.code == codes.OK:
        returned = {v.signal_id for v in resp.read_signals.values}
        assert "__no_such_signal__" not in returned, (
            "partial-result variant must omit the unknown signal id"
        )
        return
    pytest.fail(f"unknown-signal read must be NOT_FOUND or OK(partial); got {status_text(resp)}")


def test_call_unknown_function_by_id_rejected(ready_client: AdppClient, codes, status_text) -> None:
    devices = ready_client.list_devices().list_devices.devices
    if not devices:
        pytest.skip("no devices")
    resp = ready_client.call(devices[0].device_id, function_id=999999)
    assert resp.status.code in (codes.NOT_FOUND, codes.UNIMPLEMENTED), (
        f"unknown function_id must be NOT_FOUND/UNIMPLEMENTED; got {status_text(resp)}"
    )


def test_call_unknown_function_by_name_rejected(ready_client: AdppClient, codes, status_text) -> None:
    # Exercises the function_name resolution path with an unresolvable name.
    devices = ready_client.list_devices().list_devices.devices
    if not devices:
        pytest.skip("no devices")
    resp = ready_client.call(devices[0].device_id, function_name="__no_such_function__")
    assert resp.status.code in (codes.NOT_FOUND, codes.UNIMPLEMENTED, codes.INVALID_ARGUMENT), (
        f"unknown function_name must be a defined rejection; got {status_text(resp)}"
    )


def test_call_on_unknown_device_rejected(ready_client: AdppClient, codes, status_text) -> None:
    resp = ready_client.call("__no_such_device__", function_id=1)
    assert resp.status.code == codes.NOT_FOUND, (
        f"call on unknown device must be NOT_FOUND; got {status_text(resp)}"
    )


# ---- health (experimental, opt-in only — deselected from gating) -------
@pytest.mark.experimental
def test_get_health_well_formed(ready_client: AdppClient) -> None:
    # GetHealth is defined but the runtime never calls it (experimental). This
    # test is deselected from the default gating run (see pytest.ini markers).
    resp = ready_client.get_health()
    assert resp.HasField("status"), "GetHealth must return a status"
