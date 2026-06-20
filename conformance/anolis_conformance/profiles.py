"""Per-provider conformance profiles.

A profile names a provider's invariant expectations (provider name, whether it
supports wait_ready, whether its conformance config yields mock devices) and its
**known divergences** — assertions it is expected to fail today because of a
tracked ADPP spec gap. Known divergences are applied as non-strict ``xfail``s so
the suite is green-as-baseline; an xPASS means the gap was fixed and the entry
should be removed. See ADPP-CONFORMANCE.md and anolis-protocol#25 (Wave 0).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    expected_provider_name: str
    supports_wait_ready: bool = True
    has_mock_devices: bool = True  # config yields at least one describable device
    # test-function base name -> reason (applied as xfail(strict=False))
    known_xfails: dict[str, str] = field(default_factory=dict)

    def xfail_reason(self, test_name: str) -> str | None:
        return self.known_xfails.get(test_name)


# Registry keyed by --profile. Binary + config come from the CLI so the harness
# isn't tied to fixed paths.
PROFILES: dict[str, ProviderProfile] = {
    "sim": ProviderProfile(
        name="sim",
        expected_provider_name="anolis-provider-sim",
        known_xfails={
            # T0.1 — sim returns partial results and silently drops unknown ids
            # instead of failing the request (semantics.md 7.4).
            "test_read_mixed_known_unknown_signal_rejected": "sim drops unknown signal ids (T0.1, #25)",
            # sim has no --version flag and swallows unknown flags (CLI parity).
            "test_cli_version_flag": "sim lacks --version (CLI parity, #25)",
        },
    ),
    "ezo": ProviderProfile(
        name="ezo",
        expected_provider_name="anolis-provider-ezo",
        # ezo runs in mock mode (bus_path: mock://...) for conformance.
        known_xfails={},
    ),
    "bread": ProviderProfile(
        name="bread",
        expected_provider_name="anolis-provider-bread",
        known_xfails={
            # T0.4 — bread does not reject a conflicting function_id/function_name.
            "test_call_function_id_name_conflict_rejected": (
                "bread ignores a conflicting function_name (T0.4, #25)"
            ),
            # T2 — bread's wait_ready diagnostics omit `init_time_ms` (the one key
            # the runtime reads); sim/ezo include it.
            "test_wait_ready_diagnostics": "bread wait_ready omits init_time_ms (T2 diagnostics, #25)",
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
