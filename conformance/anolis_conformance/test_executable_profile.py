"""Anolis *provider executable profile* — conventions the Anolis runtime/tooling
expects of a provider binary, distinct from ADPP wire conformance: the CLI
surface, the WaitReady diagnostics the runtime reads, and process lifecycle.

Normative source: ``docs/profiles/anolis-executable-profile-v1.md`` — an
organizational acceptance profile, NOT ADPP conformance. A binary can be
ADPP-conformant and still diverge here; such gaps are declared as xfails in the
provider's own `--provider-profile` manifest (see profiles.py for the schema).
"""

from __future__ import annotations

import re
import subprocess

import pytest

from .client import AdppClient

# Every test here is an Anolis executable-profile convention — the only tests a
# provider's --provider-profile waiver is permitted to xfail.
pytestmark = pytest.mark.executable_profile


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


# ---- CLI ----------------------------------------------------------------
def test_cli_version_flag(provider_bin) -> None:
    proc = subprocess.run([str(provider_bin), "--version"], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, f"`--version` must exit 0; got {proc.returncode} ({proc.stderr[:200]})"
    # Require a dotted version token (e.g. 1.2.0), not merely "some digit
    # somewhere" — unrelated diagnostic output must not satisfy --version.
    assert re.search(r"\d+\.\d+", proc.stdout), (
        f"`--version` should print a version like X.Y[.Z]; got {proc.stdout!r}"
    )


def test_cli_check_config_ok(provider_bin, provider_config) -> None:
    proc = subprocess.run(
        [str(provider_bin), "--check-config", str(provider_config)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"`--check-config` on a valid config must exit 0; got {proc.returncode}"
