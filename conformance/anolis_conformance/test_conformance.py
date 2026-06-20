"""The cross-provider ADPP v1 conformance assertions.

Parametrized over a single provider per run via --provider-bin/--provider-config
/--profile (see plugin.py). Groups follow ADPP-CONFORMANCE.md. Status codes come
from the `codes` fixture (resolved from the proto enum), never hardcoded.
"""

from __future__ import annotations

import struct
import subprocess

import pytest

from . import spec
from .client import MAX_FRAME_BYTES, AdppClient, ProviderClosed


# ---- helpers ------------------------------------------------------------
def _assert_handles_malformed(client: AdppClient, timeout: float = 3.0) -> None:
    """A provider must RESPOND or TERMINATE on malformed input — never hang."""
    try:
        client.read_response(timeout=timeout)  # None (clean EOF) or a Response -> handled
    except ProviderClosed:
        pass  # stream closed -> provider terminated, acceptable
    except TimeoutError:
        if client.process.poll() is None:
            pytest.fail("provider neither responded nor exited on malformed input (hang)")


# ---- Group 1: handshake / version --------------------------------------
def test_hello_v1_ok(client: AdppClient, profile, codes, status_text) -> None:
    resp = client.hello()
    assert resp.status.code == codes.OK, status_text(resp)
    assert resp.request_id == 1, "Hello response must echo request_id"
    assert resp.hello.protocol_version == spec.PROTOCOL_VERSION
    assert resp.hello.provider_name == profile.expected_provider_name


def test_hello_metadata_standard_keys(client: AdppClient) -> None:
    meta = dict(client.hello().hello.metadata)
    missing = spec.REQUIRED_HELLO_METADATA_KEYS - meta.keys()
    assert not missing, f"Hello metadata missing required keys {missing}; got {sorted(meta)}"
    assert "uint32_le" in meta["transport"], f"unexpected transport metadata: {meta['transport']!r}"


def test_hello_bad_version_rejected(client: AdppClient, codes, status_text) -> None:
    resp = client.hello(protocol_version="v999")
    assert resp.status.code == codes.FAILED_PRECONDITION, (
        f"non-v1 Hello must be CODE_FAILED_PRECONDITION; got {status_text(resp)}"
    )


def test_request_id_echo(ready_client: AdppClient) -> None:
    resp = ready_client.list_devices()
    rid = resp.request_id
    resp2 = ready_client.list_devices()
    assert resp2.request_id == rid + 1, "request_id must increment and echo per request"


# ---- Group 2: framing robustness (no hang / no crash-loop) -------------
def test_framing_oversized_length_header(client: AdppClient) -> None:
    client.send_raw(struct.pack("<I", MAX_FRAME_BYTES * 2))  # claim > 1 MiB cap
    _assert_handles_malformed(client)


def test_framing_zero_length_frame(client: AdppClient) -> None:
    client.send_raw(struct.pack("<I", 0))  # len=0, empty payload
    _assert_handles_malformed(client)


def test_framing_truncated_frame(client: AdppClient) -> None:
    client.send_raw(struct.pack("<I", 64))  # promise 64 bytes...
    client.process.stdin.close()  # ...then EOF -> provider must exit cleanly, not hang
    _assert_handles_malformed(client)


def test_framing_garbage_payload(client: AdppClient) -> None:
    client.send_frame(b"\xde\xad\xbe\xef not a valid Request \x00\x01\x02")  # unparseable protobuf
    _assert_handles_malformed(client)


# ---- Group 3: lifecycle / readiness ------------------------------------
def test_wait_ready_diagnostics(client: AdppClient, profile, codes, status_text) -> None:
    client.hello()
    if not profile.supports_wait_ready:
        pytest.skip("provider does not advertise supports_wait_ready")
    resp = client.wait_ready()
    assert resp.status.code == codes.OK, status_text(resp)
    diags = dict(resp.wait_ready.diagnostics)
    assert "init_time_ms" in diags, f"wait_ready must report init_time_ms; got {sorted(diags)}"


# ---- Group 4: inventory / capabilities ---------------------------------
def test_list_devices_ok(ready_client: AdppClient, profile, codes, status_text) -> None:
    resp = ready_client.list_devices()
    assert resp.status.code == codes.OK, status_text(resp)
    if profile.has_mock_devices:
        assert len(resp.list_devices.devices) >= 1, "conformance config should yield >=1 device"


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


# ---- Group 5: read / call ----------------------------------------------
def test_read_signals_response_shape(ready_client: AdppClient, codes) -> None:
    devices = ready_client.list_devices().list_devices.devices
    if not devices:
        pytest.skip("no devices to read")
    resp = ready_client.read_signals(devices[0].device_id)  # default signal set
    # Mock backends may legitimately report data unavailable; only the shape is
    # mandatory. If OK, every value must carry a signal_id.
    if resp.status.code == codes.OK:
        for value in resp.read_signals.values:
            assert value.signal_id, "each SignalValue must carry a signal_id"


def test_read_mixed_known_unknown_signal_rejected(ready_client: AdppClient, codes, status_text) -> None:
    # A request mixing a valid and an unknown signal id must fail consistently
    # (semantics.md 7.4) — not silently drop the unknown and return partial data.
    devices = ready_client.list_devices().list_devices.devices
    if not devices:
        pytest.skip("no devices")
    caps = ready_client.describe_device(devices[0].device_id).describe_device.capabilities
    if not caps.signals:
        pytest.skip("device declares no signals")
    real = caps.signals[0].signal_id
    resp = ready_client.read_signals(devices[0].device_id, [real, "__no_such_signal__"])
    assert resp.status.code == codes.NOT_FOUND, (
        f"a read mixing a known + unknown signal must fail CODE_NOT_FOUND (not return "
        f"partial results); got {status_text(resp)}"
    )


def test_call_unknown_function_rejected(ready_client: AdppClient, codes, status_text) -> None:
    devices = ready_client.list_devices().list_devices.devices
    if not devices:
        pytest.skip("no devices")
    resp = ready_client.call(devices[0].device_id, function_id=999999)
    assert resp.status.code in (codes.NOT_FOUND, codes.UNIMPLEMENTED), (
        f"unknown function must be NOT_FOUND/UNIMPLEMENTED; got {status_text(resp)}"
    )


def test_call_function_id_name_conflict_rejected(ready_client: AdppClient, codes, status_text) -> None:
    devices = ready_client.list_devices().list_devices.devices
    if not devices:
        pytest.skip("no devices")
    caps = ready_client.describe_device(devices[0].device_id).describe_device.capabilities
    if len(caps.functions) < 2:
        pytest.skip("need >=2 functions to construct an id/name conflict")
    # function_id of fn[0] but function_name of fn[1] -> a genuine selector conflict,
    # which a compliant provider rejects at resolution (before arg validation).
    resp = ready_client.call(
        devices[0].device_id,
        function_id=caps.functions[0].function_id,
        function_name=caps.functions[1].name,
    )
    assert resp.status.code == codes.INVALID_ARGUMENT, (
        f"conflicting function_id/function_name must be CODE_INVALID_ARGUMENT; got {status_text(resp)}"
    )


# ---- Group 6: health (experimental — non-gating) -----------------------
def test_get_health_well_formed(ready_client: AdppClient) -> None:
    # GetHealth is defined but the runtime never calls it (experimental). Only
    # require a well-formed response, not a particular state.
    resp = ready_client.get_health()
    assert resp.HasField("status"), "GetHealth must return a status"


# ---- Group 7: process hygiene ------------------------------------------
def test_clean_shutdown_on_stdin_eof(client: AdppClient) -> None:
    client.hello()
    code = client.close(timeout=5.0)  # closes stdin -> EOF
    assert code == 0, f"provider must exit 0 on stdin EOF; got {code}\n{client.output_tail(40)}"


def test_multiple_roundtrips_stay_framed(ready_client: AdppClient, codes) -> None:
    # Re-exercises framing: stray stdout bytes would break the 2nd/3rd parse.
    for _ in range(3):
        resp = ready_client.list_devices()
        assert resp.status.code == codes.OK


# ---- CLI ---------------------------------------------------------------
def test_cli_version_flag(provider_bin) -> None:
    proc = subprocess.run([str(provider_bin), "--version"], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, f"`--version` must exit 0; got {proc.returncode} ({proc.stderr[:200]})"
    assert any(ch.isdigit() for ch in proc.stdout), f"`--version` should print a version; got {proc.stdout!r}"


def test_cli_check_config_ok(provider_bin, provider_config) -> None:
    proc = subprocess.run(
        [str(provider_bin), "--check-config", str(provider_config)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"`--check-config` on a valid config must exit 0; got {proc.returncode}"
