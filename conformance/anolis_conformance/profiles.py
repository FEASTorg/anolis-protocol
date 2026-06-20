"""Per-provider conformance profiles.

A profile names a provider's invariants and its **known divergences** — checks
it is expected to fail today because of a tracked gap. Divergences are applied as
non-strict ``xfail``s (green-as-baseline; an xPASS means the gap was fixed —
remove the entry). They cover only **Anolis executable-profile** expectations
(CLI, runtime-read diagnostics), NOT ADPP wire behavior the spec already permits.

Follow-up (tracked, #25): make waivers strict + provider-owned (live in each
provider repo with an issue URL/owner/expiry), so the protocol package doesn't
re-release for every provider-specific exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    expected_provider_name: str
    has_mock_devices: bool = True  # config yields at least one describable device
    # test-function base name -> reason (applied as xfail(strict=False))
    known_xfails: dict[str, str] = field(default_factory=dict)

    def xfail_reason(self, test_name: str) -> str | None:
        return self.known_xfails.get(test_name)


PROFILES: dict[str, ProviderProfile] = {
    "sim": ProviderProfile(
        name="sim",
        expected_provider_name="anolis-provider-sim",
        known_xfails={
            # Executable-profile gap: sim has no --version flag (CLI parity).
            "test_cli_version_flag": "sim lacks --version (executable-profile, #25)",
        },
    ),
    "ezo": ProviderProfile(
        name="ezo",
        expected_provider_name="anolis-provider-ezo",
        known_xfails={},
    ),
    "bread": ProviderProfile(
        name="bread",
        expected_provider_name="anolis-provider-bread",
        known_xfails={
            # Executable-profile gap: bread's wait_ready omits init_time_ms (the
            # one diagnostics key the runtime reads); sim/ezo include it.
            "test_wait_ready_reports_init_time_ms": (
                "bread wait_ready omits init_time_ms (executable-profile, #25)"
            ),
        },
    ),
}


def get_profile(name: str) -> ProviderProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise SystemExit(
            f"unknown --profile {name!r}; known profiles: {', '.join(sorted(PROFILES))}"
        ) from None
