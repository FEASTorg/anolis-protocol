# Protocol Versioning Policy

## Scheme

This repository uses semantic versioning tags:

- `MAJOR.MINOR.PATCH`

## Change Classification

- `PATCH`
  - Documentation fixes, non-functional clarifications, tooling updates.
  - No wire-contract changes.
- `MINOR`
  - Backward-compatible schema additions.
  - Typical example: adding optional fields with new field numbers.
- `MAJOR`
  - Breaking wire-contract changes.
  - Examples: removing fields, reusing field numbers, incompatible type/meaning changes.

## Conformance Changes (semantic contract)

A change can break the **conformance contract** (what a provider must do) without
touching the **wire contract** (the bytes on the stream). Tightening conformance
— a new `MUST` that can make a previously-conformant provider non-conformant — is
a breaking change to implementers even though `buf breaking` sees nothing. It is
**not** a silent `MINOR`/`PATCH`.

Such changes are introduced as a new **conformance level** (see `semantics.md`,
requirements tagged `[L2]`, `[L3]`, …) and rolled out as a **staged transition**:

1. The new requirements are documented in `semantics.md`, tagged with their level.
2. The conformance harness adds the corresponding tests **non-gating** (marked
   `experimental`), so existing providers do not break when they bump the pinned
   harness.
3. All known providers are brought into compliance.
4. The tests **graduate to gating** in a named release — the enforcement
   milestone for that level, called out in the changelog.

Out-of-tree providers will (future) declare their target conformance level in
their provider manifest, so they can adopt levels on their own schedule rather
than being broken by a harness bump. Until any out-of-tree providers exist, the
staged transition above is sufficient.

## Proto Rules

- Never reuse removed or deprecated field numbers.
- Reserve removed field numbers and names.
- Keep package naming/versioning consistent with the current major contract.

## Enforcement

`buf breaking` is run on every PR against the `main` branch baseline.
Breaking changes will fail CI and must be accompanied by a major version bump.

## Consumer Expectations

- Consumers pin explicit `anolis-protocol` versions.
- Consumer releases should document supported ADPP major version(s).
