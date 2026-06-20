# Changelog

All notable changes to the Anolis Device Provider Protocol (ADPP) are documented here.

## [Unreleased]

## [v1.3.0] — 2026-06-20

### Added

- **Cross-provider ADPP conformance harness**, shipped in the wheel (#26): a
  generic verifier that drives any provider binary through the ADPP v1 wire
  lifecycle and asserts compliance. Adds a `[conformance]` optional-dependency
  extra and the `anolis-adpp-conformance` console script. Providers pull this
  versioned artifact and supply their own identity/config/waivers via
  `--provider-profile`; the contract ships **no implementer-specific data**.
- **Normative profile docs** that give the harness's transport/executable
  requirements an authority (so conventions don't become protocol law via tests
  alone):
  - `docs/profiles/framed-stdio-v1.md` — the stdio transport binding
    (`uint32_le` framing, 1 MiB frame cap, Hello metadata, malformed-stream
    behavior and exit codes). This is the named "mutual agreement" that
    `semantics.md` §2 leaves to a binding.
  - `docs/profiles/anolis-executable-profile-v1.md` — Anolis executable
    conventions (an organizational acceptance profile, **not** ADPP).

### Fixed

- `handshake.proto`: corrected the `protocol_version` comment (`"1"` → `"v1"`,
  the value the runtime and every provider actually require).

### CI

- Add CI OK aggregator gate: removed `paths-ignore`, added `dorny/paths-filter`
  to detect code-vs-docs changes, gated all jobs behind the filter, and added a
  final `ok` job as the sole required status check for `main` branch protection.
- Add a hermetic conformance lane on Python 3.10 + 3.12: verifier self-tests
  against in-repo fake providers, a plugin-isolation regression, and a
  misconfiguration gate (a misused invocation must exit non-zero, never green).

### Notes

- **No wire-contract change** — the proto schema is identical to v1.2.0. This is
  an additive packaging/tooling + docs release; versioned MINOR to signal the
  new conformance-harness capability shipped in the wheel.

## [v1.2.0] — 2026-04-24

### Added

- `ArgSpec` bounds fields (`min_double`, `max_double`, `min_int64`, `max_int64`,
  `min_uint64`, `max_uint64`) are now declared `optional` in proto3.

  This gives each field **explicit presence** — consumers gain `has_min_double()`,
  `has_max_double()`, etc. accessor methods. A bound explicitly set to `0` is now
  distinguishable from a bound that was never set.

  **Wire format is unchanged.** Field numbers and encoding are identical to v1.1.4.
  Old senders and new receivers interoperate correctly; old receivers see `0` as
  the field value when new senders set an explicit zero, which matches prior behaviour.

  **Buf breaking check:** This change alters the field's presence semantics (implicit →
  explicit) which `buf breaking --use FILE` flags as a cardinality change. It is a
  deliberate, wire-backward-compatible enhancement and constitutes a MINOR version bump
  per the ADPP versioning policy.

### Migration

Consumers that previously used a non-zero heuristic to detect whether a bound was set
(`min != 0 || max != 0`) should replace that logic with `has_min_*()` / `has_max_*()`
calls after updating their FetchContent URL to the v1.2.0 source tarball.

Consumers that do not call any bound-presence logic require no source changes — all
existing `set_min_*()` and `set_max_*()` calls continue to compile and behave as before.

## [v1.1.4] — 2025-11-10

Initial public release with full ADPP v1 message definitions.
