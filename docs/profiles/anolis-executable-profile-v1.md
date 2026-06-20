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

- When the provider advertises `supports_wait_ready=true`, a `WaitReady` response
  SHOULD report `init_time_ms` in its diagnostics — the key the runtime reads.
- Additional diagnostics keys are allowed; the full standard key set is being
  settled (see the conformance epic).

## 3. Process hygiene

- The provider MUST exit cleanly (code `0`) on stdin EOF.
- The provider MUST NOT write anything other than framed responses to stdout
  (stray bytes corrupt the frame stream — this is enforced by the framed-stdio
  profile, not waivable).

## 4. Relationship to other documents

- `semantics.md` — core ADPP v1 (normative).
- `profiles/framed-stdio-v1.md` — the stdio transport binding (normative).
- This document — Anolis executable conventions (organizational; waivable).
