# Anolis provider executable profile v1 (organizational acceptance profile)

This document defines conventions the **Anolis runtime and tooling** expect of a
provider **binary**. It is an *organizational acceptance profile*, **not** part
of ADPP conformance: a binary can be fully ADPP-conformant (`semantics.md`) and
the framed-stdio profile while still diverging here.

Because these are conventions rather than protocol requirements, the conformance
harness marks them `executable_profile`, and a provider MAY waive an individual
expectation via its `--provider-profile` manifest (with an issue link), pending
a fix. Waivers may target **only** tests in this profile — never core ADPP or
framed-stdio (transport) tests.

## 1. CLI surface

- `--config <path>` — start the provider with the given config (the runtime
  launches the binary this way).
- `--version` — print a version string (containing a dotted `X.Y[.Z]` token) and
  exit `0`.
- `--check-config <path>` — validate a config without starting; exit `0` on a
  valid config.

## 2. Readiness diagnostics

When the provider advertises `supports_wait_ready=true`, a `WaitReady` response's
`diagnostics` map uses this standard key set (all values are strings):

| Key | Status | Meaning |
| --- | --- | --- |
| `init_time_ms` | **required** | Milliseconds spent initializing before ready — the key the runtime reads. Asserted by the harness (waivable). |
| `ready` | recommended | `"true"` / `"false"` — readiness as a value, pending a typed `ready` field in `readiness.proto`. |
| `device_count` | recommended | Number of devices the provider brought up. |
| `provider_impl` | recommended | Provider implementation identifier (e.g. name + version), for diagnostics. |

Provider-specific extra keys are allowed. Only `init_time_ms` is gated; the
recommended keys are conventions, not asserted.

## 3. Process hygiene

- The provider MUST exit cleanly (code `0`) on stdin EOF.
- The provider MUST NOT write anything other than framed responses to stdout
  (stray bytes corrupt the frame stream — this is enforced by the framed-stdio
  profile, not waivable).

## 4. Capability conventions

Conventions for the capability surface (`CapabilitySet`) a device reports via
`DescribeDevice`. These keep ids predictable across providers and a future SDK;
they are conventions, not core ADPP, and are waivable.

- **`signal_id` is snake_case** — matches `^[a-z][a-z0-9_]*$` (a lowercase letter
  first, then lowercase letters, digits, underscores). No dots (`ph.value`), no
  camelCase. Asserted by `test_signal_ids_snake_case`.
- **`function_id` is per-type, numbered from 1** — within each device type the
  function ids are the contiguous set `{1..N}` for N declared functions. Not a
  global counter (`1001`, `1002`, …) and not an arbitrary value (`10`). Asserted
  by `test_function_ids_per_type_from_one`.

## 5. Relationship to other documents

- `semantics.md` — core ADPP v1 (normative).
- `profiles/framed-stdio-v1.md` — the stdio transport binding (normative).
- This document — Anolis executable conventions (organizational; waivable).
