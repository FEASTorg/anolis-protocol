"""Verifier self-tests: drive the harness against deliberately-faulty fake
providers and prove it REJECTS them. Hermetic — no external binary, no provider
options required. This is what makes the harness trustworthy as a verifier.
"""

from __future__ import annotations

import os
import stat
import struct
import sys
import time

import pytest

from .client import (
    AdppClient,
    CorrelationError,
    OversizedResponse,
    ProviderClosed,
    ProviderHang,
)
from .profiles import load_profile

# A single fake provider; FAKE_MODE selects the misbehavior. It reads one request
# frame, then acts. Response-building modes import the installed protobufs. The
# shebang is filled in with the test interpreter (which has protobuf available).
_FAKE_SRC = r'''import os, sys, struct, time
mode = os.environ.get("FAKE_MODE", "good")
def read_exact(n):
    b = b""
    while len(b) < n:
        c = sys.stdin.buffer.read(n - len(b))
        if not c:
            sys.exit(0)
        b += c
    return b
body = read_exact(struct.unpack("<I", read_exact(4))[0])
out = sys.stdout.buffer
if mode == "hang":
    time.sleep(60)
elif mode == "crash_signal":
    os.abort()                                   # SIGABRT -> negative returncode
elif mode == "exit_bad":
    sys.exit(7)                                  # undocumented exit code
elif mode == "oversized":
    out.write(struct.pack("<I", 1 << 30)); out.flush(); time.sleep(10)
elif mode == "drip":
    out.write(struct.pack("<I", 100)); out.flush()
    for _ in range(100):
        out.write(b"x"); out.flush(); time.sleep(0.5)
elif mode == "mid_frame":
    out.write(struct.pack("<I", 100)); out.write(b"abc"); out.flush(); sys.exit(0)
else:
    import protocol_pb2 as p
    req = p.Request(); req.ParseFromString(body)
    resp = p.Response()
    resp.request_id = req.request_id + (1000 if mode == "wrong_id" else 0)
    if mode != "no_status":
        resp.status.code = p.Status.Code.Value("CODE_OK")
    resp.hello.protocol_version = "v1"; resp.hello.provider_name = "fake"
    data = resp.SerializeToString()
    out.write(struct.pack("<I", len(data)) + data); out.flush()
    time.sleep(60)
'''


@pytest.fixture(scope="session")
def fake_provider(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("fake") / "fake_provider.py"
    # Run the fake with the SAME interpreter as the tests (it has protobuf).
    path.write_text(f"#!{sys.executable}\n{_FAKE_SRC}")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)
    return str(path)


@pytest.fixture
def make_client(protocol, fake_provider, tmp_path, monkeypatch):
    cfg = tmp_path / "dummy.yaml"
    cfg.write_text("{}\n")

    def _make(mode: str) -> AdppClient:
        monkeypatch.setenv("FAKE_MODE", mode)
        return AdppClient(protocol, fake_provider, cfg)

    return _make


def _send_hello(client: AdppClient) -> None:
    req = client.protocol.Request(request_id=1)
    req.hello.protocol_version = "v1"
    req.hello.client_name = "selftest"
    req.hello.client_version = "0.1"
    client.send_frame(req.SerializeToString())


def test_selftest_good_provider_accepted(make_client) -> None:
    client = make_client("good")
    try:
        assert client.hello().status.code != 0  # CODE_OK == 1; sanity that it round-trips
    finally:
        client.close()


def test_selftest_hang_detected(make_client) -> None:
    client = make_client("hang")
    try:
        _send_hello(client)
        with pytest.raises(ProviderHang):
            client.await_outcome(timeout=1.0)
    finally:
        client.close()


def test_selftest_crash_signal_detected(make_client) -> None:
    client = make_client("crash_signal")
    try:
        _send_hello(client)
        outcome, code = client.await_outcome(timeout=3.0)
        assert outcome == "exit" and code is not None and code < 0, (
            f"a signal-killed provider must surface a negative exit code; got {outcome},{code}"
        )
    finally:
        client.close()


def test_selftest_oversized_response_rejected(make_client) -> None:
    client = make_client("oversized")
    try:
        _send_hello(client)
        with pytest.raises(OversizedResponse):
            client.read_response(timeout=3.0)
    finally:
        client.close()


def test_selftest_drip_respects_deadline(make_client) -> None:
    client = make_client("drip")
    try:
        _send_hello(client)
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            client.read_response(timeout=1.0)
        assert time.monotonic() - start < 3.0, "a byte-drip must not stretch the deadline"
    finally:
        client.close()


def test_selftest_mid_frame_close_detected(make_client) -> None:
    client = make_client("mid_frame")
    try:
        _send_hello(client)
        with pytest.raises(ProviderClosed):
            client.read_response(timeout=3.0)
    finally:
        client.close()


def test_selftest_wrong_request_id_detected(make_client) -> None:
    client = make_client("wrong_id")
    try:
        with pytest.raises(CorrelationError):
            client.hello()
    finally:
        client.close()


def test_selftest_missing_status_detected(make_client) -> None:
    client = make_client("no_status")
    try:
        resp = client.hello()
        assert not resp.HasField("status"), "self-test expects the fake to omit status"
    finally:
        client.close()


# --- provider-profile loader (the generic schema; ships no implementer data) ---


def test_selftest_profile_loader_accepts_valid(tmp_path) -> None:
    f = tmp_path / "conformance.toml"
    f.write_text(
        'provider_name = "anolis-provider-example"\n'
        "has_mock_devices = false\n"
        "[waivers]\n"
        'test_cli_version_flag = "no --version (example/repo#1)"\n'
    )
    load_profile.cache_clear()
    p = load_profile(f)
    assert p.expected_provider_name == "anolis-provider-example"
    assert p.has_mock_devices is False
    assert p.xfail_reason("test_cli_version_flag") == "no --version (example/repo#1)"
    assert p.xfail_reason("test_unwaived") is None


def test_selftest_profile_loader_defaults(tmp_path) -> None:
    f = tmp_path / "minimal.toml"
    f.write_text('provider_name = "x"\n')
    load_profile.cache_clear()
    p = load_profile(f)
    assert p.has_mock_devices is True and p.known_xfails == {}


@pytest.mark.parametrize(
    "body",
    [
        'has_mock_devices = true\n',  # missing provider_name
        "provider_name = 42\n",  # non-string provider_name
        'provider_name = "x"\nhas_mock_devices = "yes"\n',  # non-bool flag
        'provider_name = "x"\n[waivers]\nt = 5\n',  # non-string waiver reason
        'provider_name = "x"\nnot valid toml\n',  # malformed TOML
    ],
)
def test_selftest_profile_loader_rejects_invalid(tmp_path, body) -> None:
    f = tmp_path / "bad.toml"
    f.write_text(body)
    load_profile.cache_clear()
    with pytest.raises(SystemExit):
        load_profile(f)
