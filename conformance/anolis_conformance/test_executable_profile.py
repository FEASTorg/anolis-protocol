"""Anolis *provider executable profile* — conventions the Anolis runtime/tooling
expects of a provider binary, distinct from ADPP wire conformance: the CLI
surface, the WaitReady diagnostics the runtime reads, and process lifecycle.

These are NOT ADPP protocol requirements. A binary can be ADPP-conformant and
still diverge here; such gaps are tracked per-provider as xfails (see profiles.py).
"""

from __future__ import annotations

import subprocess

import pytest

from . import spec
from .client import AdppClient


# ---- readiness diagnostics ---------------------------------------------
def test_wait_ready_reports_init_time_ms(client: AdppClient, codes, status_text) -> None:
    # The runtime reads `init_time_ms` from WaitReady diagnostics. (Standardized
    # key set; not an ADPP wire requirement.)
    resp = client.hello()
    if resp.hello.metadata.get("supports_wait_ready") != "true":
        pytest.skip("provider does not advertise supports_wait_ready")
    wr = client.wait_ready()
    assert wr.status.code == codes.OK, status_text(wr)
    diags = dict(wr.wait_ready.diagnostics)
    assert "init_time_ms" in diags, f"wait_ready should report init_time_ms; got {sorted(diags)}"


# ---- process hygiene ----------------------------------------------------
def test_clean_shutdown_on_stdin_eof(client: AdppClient) -> None:
    client.hello()
    code = client.close(timeout=5.0)  # closes stdin -> EOF
    assert code == 0, f"provider must exit 0 on stdin EOF; got {code}\n{client.output_tail(40)}"


def test_multiple_roundtrips_stay_framed(ready_client: AdppClient, codes) -> None:
    # Re-exercises framing across requests: stray stdout bytes would break the
    # 2nd/3rd parse.
    for _ in range(3):
        assert ready_client.list_devices().status.code == codes.OK


# ---- CLI ----------------------------------------------------------------
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
