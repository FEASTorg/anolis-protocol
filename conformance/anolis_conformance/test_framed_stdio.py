"""ADPP *framed-stdio profile* conformance — the uint32-LE framing, the 1 MiB
cap, and behavior on a malformed/garbage stream.

A malformed frame must yield a CONTROLLED outcome — a well-formed framed error
response, or a clean documented exit (codes 0/2/3). A crash (process killed by a
signal -> negative return code), a hang, or a malformed/over-cap response is a
conformance FAILURE.
"""

from __future__ import annotations

import struct
import time

import pytest

from . import spec
from .client import MAX_FRAME_BYTES, AdppClient, ProviderHang


def _assert_controlled_malformed(client: AdppClient, timeout: float = 3.0) -> None:
    try:
        outcome, value = client.await_outcome(timeout)
    except ProviderHang as exc:
        pytest.fail(str(exc))
    if outcome == "response":
        assert value.HasField("status"), "malformed input produced a response with no status"
        return
    # outcome == "exit"
    assert value is not None, "provider did not produce an exit code"
    assert value >= 0, f"provider crashed on malformed input (killed by signal, returncode={value})"
    assert value in spec.ALLOWED_MALFORMED_EXIT_CODES, (
        f"provider exited {value} on malformed input (allowed: {sorted(spec.ALLOWED_MALFORMED_EXIT_CODES)})"
    )


def test_framing_oversized_length_header(client: AdppClient) -> None:
    client.send_raw(struct.pack("<I", MAX_FRAME_BYTES * 2))  # claim > 1 MiB cap
    _assert_controlled_malformed(client)


def test_framing_zero_length_frame(client: AdppClient) -> None:
    client.send_raw(struct.pack("<I", 0))  # len=0, empty payload
    _assert_controlled_malformed(client)


def test_framing_truncated_frame(client: AdppClient) -> None:
    client.send_raw(struct.pack("<I", 64))  # promise 64 bytes...
    client.process.stdin.close()  # ...then EOF -> controlled exit, not a hang
    _assert_controlled_malformed(client)


def test_framing_garbage_payload(client: AdppClient) -> None:
    client.send_frame(b"\xde\xad\xbe\xef not a valid Request \x00\x01\x02")  # unparseable protobuf
    _assert_controlled_malformed(client)


def test_framing_fragmented_request_reassembled(client: AdppClient, codes, status_text) -> None:
    # A valid Hello delivered as a length prefix + payload split across writes
    # with a delay must be reassembled by the provider's read_exact loop.
    req = client.protocol.Request(request_id=1)
    req.hello.protocol_version = "v1"
    req.hello.client_name = "frag"
    req.hello.client_version = "0.1"
    payload = req.SerializeToString()
    client.send_raw(struct.pack("<I", len(payload)))
    client.send_raw(payload[: len(payload) // 2])
    time.sleep(0.05)
    client.send_raw(payload[len(payload) // 2 :])
    resp = client.read_response(timeout=5.0)
    assert resp is not None and resp.status.code == codes.OK, (
        f"fragmented Hello must reassemble to OK; got {status_text(resp) if resp else 'EOF'}"
    )


def test_framing_two_coalesced_requests(client: AdppClient, codes) -> None:
    # Two frames written back-to-back in one buffer must each get a response.
    def hello_frame(rid: int) -> bytes:
        req = client.protocol.Request(request_id=rid)
        req.hello.protocol_version = "v1"
        req.hello.client_name = "coalesce"
        req.hello.client_version = "0.1"
        body = req.SerializeToString()
        return struct.pack("<I", len(body)) + body

    client.send_raw(hello_frame(1) + hello_frame(2))
    r1 = client.read_response(timeout=5.0)
    r2 = client.read_response(timeout=5.0)
    assert r1 is not None and r2 is not None, "both coalesced requests must be answered"
    assert {r1.request_id, r2.request_id} == {1, 2}, "responses must echo both request_ids"
