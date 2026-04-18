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
