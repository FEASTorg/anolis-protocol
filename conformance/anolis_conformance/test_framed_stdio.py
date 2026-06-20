"""ADPP *framed-stdio profile* conformance — the uint32-LE framing, the 1 MiB
cap, the framed-stdio Hello metadata, and behavior on a malformed/garbage stream.

A malformed frame must yield a CONTROLLED outcome — a well-formed framed *error*
response, or a clean documented exit (codes 0/2/3). A crash (process killed by a
signal -> negative return code), a hang, a success status on garbage, or a
malformed/over-cap response is a conformance FAILURE.
"""

from __future__ import annotations

import struct
import time

from . import spec
from .checks import assert_controlled_malformed
from .client import MAX_FRAME_BYTES, AdppClient


# ---- framed-stdio Hello metadata (a framing-profile fact, not core ADPP) ----
def test_hello_metadata_values(client: AdppClient) -> None:
    meta = dict(client.hello().hello.metadata)
    missing = spec.REQUIRED_HELLO_METADATA_KEYS - meta.keys()
    assert not missing, f"Hello metadata missing required keys {missing}; got {sorted(meta)}"
    assert meta["transport"] == spec.EXPECTED_TRANSPORT, f"transport={meta['transport']!r}"
    assert meta["max_frame_bytes"] == spec.EXPECTED_MAX_FRAME_BYTES, meta["max_frame_bytes"]
    assert meta["supports_wait_ready"] in ("true", "false"), meta["supports_wait_ready"]


def test_framing_oversized_length_header(client: AdppClient, codes) -> None:
    client.send_raw(struct.pack("<I", MAX_FRAME_BYTES * 2))  # claim > 1 MiB cap
    assert_controlled_malformed(client, codes)


def test_framing_zero_length_frame(client: AdppClient, codes) -> None:
    client.send_raw(struct.pack("<I", 0))  # len=0, empty payload
    assert_controlled_malformed(client, codes)


def test_framing_truncated_frame(client: AdppClient, codes) -> None:
    client.send_raw(struct.pack("<I", 64))  # promise 64 bytes...
    client.process.stdin.close()  # ...then EOF -> controlled exit, not a hang
    assert_controlled_malformed(client, codes)


def test_framing_garbage_payload(client: AdppClient, codes) -> None:
    client.send_frame(b"\xde\xad\xbe\xef not a valid Request \x00\x01\x02")  # unparseable protobuf
    assert_controlled_malformed(client, codes)


def _hello_frame(client: AdppClient, rid: int, client_name: str = "frag") -> bytes:
    req = client.protocol.Request(request_id=rid)
    req.hello.protocol_version = "v1"
    req.hello.client_name = client_name
    req.hello.client_version = "0.1"
    body = req.SerializeToString()
    return struct.pack("<I", len(body)) + body


def test_framing_trailing_garbage_after_valid_request(client: AdppClient, codes, status_text) -> None:
    # A valid Hello followed by trailing junk: the Hello must be answered, then
    # the trailing bytes (a new bogus frame) must be handled in a controlled way.
    client.send_raw(_hello_frame(client, 1) + b"\x07\x00\x00\x00garbage")
    resp = client.read_response(timeout=5.0)
    assert resp is not None and resp.status.code == codes.OK, (
        f"valid Hello before trailing garbage must be answered OK; "
        f"got {status_text(resp) if resp else 'EOF'}"
    )
    assert_controlled_malformed(client, codes)


def test_framing_fragmented_request_reassembled(client: AdppClient, codes, status_text) -> None:
    # A valid Hello delivered as a length prefix + payload split across writes
    # with a delay must be reassembled by the provider's read_exact loop.
    frame = _hello_frame(client, 1)
    half = len(frame) // 2
    client.send_raw(frame[:half])
    time.sleep(0.05)
    client.send_raw(frame[half:])
    resp = client.read_response(timeout=5.0)
    assert resp is not None and resp.status.code == codes.OK, (
        f"fragmented Hello must reassemble to OK; got {status_text(resp) if resp else 'EOF'}"
    )
    assert resp.request_id == 1, "reassembled response must echo request_id"
    assert resp.hello.protocol_version == spec.PROTOCOL_VERSION, "reassembled response must be a Hello"


def test_framing_two_coalesced_requests(client: AdppClient, codes, status_text) -> None:
    # Two frames written back-to-back in one buffer must each get an OK response.
    client.send_raw(_hello_frame(client, 1, "coalesce") + _hello_frame(client, 2, "coalesce"))
    r1 = client.read_response(timeout=5.0)
    r2 = client.read_response(timeout=5.0)
    assert r1 is not None and r2 is not None, "both coalesced requests must be answered"
    assert {r1.request_id, r2.request_id} == {1, 2}, "responses must echo both request_ids"
    for r in (r1, r2):
        assert r.status.code == codes.OK, f"coalesced Hello must be OK; got {status_text(r)}"
