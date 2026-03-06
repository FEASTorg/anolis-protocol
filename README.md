# anolis-protocol

Canonical protocol contracts for the Anolis ecosystem.

## Scope

- Owns ADPP protobuf schema used by `anolis` and providers.
- Contains protocol-only artifacts (schema + semantics + compatibility docs).
- Contains no runtime/provider implementation code.

## Layout

```text
anolis-protocol/
├── spec/
│   └── device-provider/
│       └── protocol.proto
└── docs/
    ├── index.md
    ├── semantics.md
    └── versioning.md
```

## Versioning

- Repository uses semantic versioning tags: `MAJOR.MINOR.PATCH`.
- Breaking wire-contract changes require a major bump.
- See `docs/versioning.md`.
