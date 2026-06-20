"""Provider conformance profile: the **schema** + a loader for a manifest the
provider supplies at run time.

A profile declares a provider's expected identity and its **known divergences** —
checks it is expected to fail today because of a tracked gap. Divergences apply
as non-strict ``xfail``s (green-as-baseline; an xPASS means the gap was fixed —
remove the entry). They cover only **Anolis executable-profile** expectations
(CLI, runtime-read diagnostics), NOT ADPP wire behavior the spec already permits.

This module ships **no** implementer-specific data. Each provider owns its own
manifest in its own repo and passes it via ``--provider-profile``, so the
protocol package never re-releases for a provider-specific exception.

Manifest format (TOML)::

    provider_name = "anolis-provider-<name>"    # required; asserted against Hello
    has_mock_devices = true                     # optional, default true

    [waivers]                                   # optional; test base-name -> reason
    test_cli_version_flag = "no --version (<owner>/<repo>#<issue-number>)"
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on 3.10
    import tomli as tomllib


@dataclass(frozen=True)
class ProviderProfile:
    expected_provider_name: str
    has_mock_devices: bool = True  # config yields at least one describable device
    # test-function base name -> reason (applied as xfail(strict=False))
    known_xfails: dict[str, str] = field(default_factory=dict)

    def xfail_reason(self, test_name: str) -> str | None:
        return self.known_xfails.get(test_name)


@lru_cache(maxsize=None)
def load_profile(path: Path) -> ProviderProfile:
    """Build a :class:`ProviderProfile` from a provider-supplied TOML manifest.

    Validation failures raise ``SystemExit`` with an actionable message (the
    manifest is provider-authored input, not an internal invariant).
    """
    try:
        data = tomllib.loads(Path(path).read_text())
    except OSError as exc:
        raise SystemExit(f"--provider-profile {path}: cannot read ({exc})") from None
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"--provider-profile {path}: invalid TOML ({exc})") from None

    unknown_keys = set(data) - {"provider_name", "has_mock_devices", "waivers"}
    if unknown_keys:
        raise SystemExit(
            f"--provider-profile {path}: unknown key(s) {sorted(unknown_keys)} "
            f"(allowed: provider_name, has_mock_devices, waivers). Check for a typo."
        )

    provider_name = data.get("provider_name")
    if not isinstance(provider_name, str) or not provider_name:
        raise SystemExit(
            f"--provider-profile {path}: missing required string key 'provider_name'"
        )

    has_mock_devices = data.get("has_mock_devices", True)
    if not isinstance(has_mock_devices, bool):
        raise SystemExit(
            f"--provider-profile {path}: 'has_mock_devices' must be a boolean"
        )

    waivers = data.get("waivers", {})
    if not isinstance(waivers, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in waivers.items()
    ):
        raise SystemExit(
            f"--provider-profile {path}: '[waivers]' must map test names to reason strings"
        )

    return ProviderProfile(
        expected_provider_name=provider_name,
        has_mock_devices=has_mock_devices,
        known_xfails=dict(waivers),
    )
