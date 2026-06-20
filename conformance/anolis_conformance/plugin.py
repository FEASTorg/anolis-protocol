"""pytest wiring for the cross-provider ADPP conformance suite."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from .client import AdppClient
from .profiles import ProviderProfile, get_profile


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("adpp-conformance")
    group.addoption("--provider-bin", action="store", help="Path to the provider executable.")
    group.addoption("--provider-config", action="store", help="Path to the provider config (mock-mode for CI).")
    group.addoption("--profile", action="store", help="Provider profile name (sim|ezo|bread).")
    group.addoption(
        "--provider-extra-arg",
        action="append",
        default=[],
        help="Extra CLI arg to pass to the provider (repeatable).",
    )


@pytest.fixture(scope="session")
def protocol():
    """The generated ADPP protobuf module (shipped by the anolis-protocol wheel)."""
    return importlib.import_module("protocol_pb2")


@pytest.fixture(scope="session")
def codes(protocol):
    """ADPP Status.Code values resolved from the proto enum (e.g. codes.NOT_FOUND)."""
    from . import spec

    return spec.resolve_codes(protocol)


@pytest.fixture(scope="session")
def status_text(protocol):
    """A `(resp) -> str` describer using the proto enum names."""
    from . import spec

    return lambda resp: spec.status_text(protocol, resp)


@pytest.fixture(scope="session")
def profile(request: pytest.FixtureRequest) -> ProviderProfile:
    name = request.config.getoption("--profile")
    if not name:
        pytest.fail("--profile is required (sim|ezo|bread)")
    return get_profile(name)


@pytest.fixture(scope="session")
def provider_bin(request: pytest.FixtureRequest) -> Path:
    raw = request.config.getoption("--provider-bin")
    if not raw:
        pytest.fail("--provider-bin is required")
    path = Path(raw)
    if not path.exists():
        pytest.fail(f"--provider-bin not found: {path}")
    return path


@pytest.fixture(scope="session")
def provider_config(request: pytest.FixtureRequest) -> Path:
    raw = request.config.getoption("--provider-config")
    if not raw:
        pytest.fail("--provider-config is required")
    path = Path(raw)
    if not path.exists():
        pytest.fail(f"--provider-config not found: {path}")
    return path


@pytest.fixture(scope="session")
def provider_extra_args(request: pytest.FixtureRequest) -> list[str]:
    return list(request.config.getoption("--provider-extra-arg"))


@pytest.fixture
def client(protocol, provider_bin, provider_config, provider_extra_args):
    """A freshly-spawned provider per test (isolation: tests may corrupt the session)."""
    c = AdppClient(protocol, provider_bin, provider_config, extra_args=provider_extra_args)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def ready_client(client, profile, codes, status_text):
    """A client that has completed the Hello (+ WaitReady) handshake."""
    resp = client.hello()
    assert resp.status.code == codes.OK, status_text(resp)
    if profile.supports_wait_ready:
        client.wait_ready()
    return client


@pytest.fixture(autouse=True)
def _apply_known_xfails(request: pytest.FixtureRequest, profile: ProviderProfile) -> None:
    """Apply a provider's tracked spec gaps as non-strict xfails (green-as-baseline)."""
    reason = profile.xfail_reason(request.node.name.split("[")[0])
    if reason:
        request.node.add_marker(pytest.mark.xfail(reason=reason, strict=False, run=True))
