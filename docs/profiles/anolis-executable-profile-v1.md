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
- `--config-schema` — print the provider's config **JSON Schema** in a versioned
  envelope on stdout and exit `0`; **configless** (takes no `--config` — you use
  it to learn how to author config). See §2.

## 2. Config schema discovery (`--config-schema`)

`--config-schema` lets a client learn a provider's config contract **before** it
can author a config. Unlike a capability it is a **configless** CLI verb: a
provider never enters ADPP without a valid config, so a capability-advertised
schema would be unreachable when you need it. The schema is **provider-owned**
and emitted by the binary itself — version-matched to the code, no separate
artifact to drift. A third-party provider needs no protocol coordination to
satisfy this.

- Takes **no** `--config` (or any other arg). Writes a single JSON object to
  **stdout** and exits `0`; diagnostics, if any, go to stderr.
- The JSON is a thin **envelope** wrapping the config schema:

| Key | Status | Meaning |
| --- | --- | --- |
| `config_schema_version` | **required** | Integer ≥ 1 — the version of **this envelope convention** (this document defines `1`), **not** the version of the `schema` it carries. It lets the envelope evolve (new keys, changed semantics) independently of any provider's config schema. Modeled on `conformance_level`. Gated by the harness (waivable). |
| `schema` | **required** | A JSON object that is a **JSON Schema** for the provider's config. Content is provider-owned; the provider SHOULD declare its dialect via the schema's own `$schema` key (e.g. Draft 2020-12). The harness asserts shape, not content. |
| `provider` | recommended | Provider identity — the `provider_name` from the `--provider-profile` manifest / Hello — so a client can map a config to the binary that owns it. |

Provider-specific extra top-level keys are allowed. Only `config_schema_version`
and `schema` are gated; `provider` is a recommended convention (as with the §3
diagnostics keys).

Bumping `config_schema_version` signals an **envelope** change (new required
keys, changed semantics), independent of the provider's own config-schema
evolution. Versioning of the config schema *itself* is **provider-owned and not
standardized in v1** — a provider MAY encode it in the schema's `$id` (JSON
Schema has no standard version keyword); this silence is deliberate, not an
omission. Like `--provider-profile`, each provider owns its schema in its own
repo; the protocol never re-releases for a provider-specific schema.

## 3. Readiness diagnostics

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

## 4. Process hygiene

- The provider MUST exit cleanly (code `0`) on stdin EOF.
- The provider MUST NOT write anything other than framed responses to stdout
  (stray bytes corrupt the frame stream — this is enforced by the framed-stdio
  profile, not waivable).

## 5. Capability conventions

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

## 6. Relationship to other documents

- `semantics.md` — core ADPP v1 (normative).
- `profiles/framed-stdio-v1.md` — the stdio transport binding (normative).
- This document — Anolis executable conventions (organizational; waivable).
