# anolis-protocol

[![buf](https://github.com/anolishq/anolis-protocol/actions/workflows/buf.yml/badge.svg)](https://github.com/anolishq/anolis-protocol/actions/workflows/buf.yml)

Canonical protocol contracts for the Anolis ecosystem.

## Quick Start

### Consume a pinned release (recommended)

**C++ (CMake FetchContent):**

```cmake
include(FetchContent)
FetchContent_Declare(
    anolis_protocol
    URL https://github.com/anolishq/anolis-protocol/releases/download/v1.1.4/anolis-protocol-1.1.4-source.tar.gz
    URL_HASH SHA256=e79f21ee14ea988669353d5ac55942f194630af033e64bcb85abda4d3b9081e4
)
FetchContent_MakeAvailable(anolis_protocol)
# proto files are at ${anolis_protocol_SOURCE_DIR}/proto/
```

Replace the version and hash from the [latest release](https://github.com/anolishq/anolis-protocol/releases/latest) `SHA256SUMS` file.

**Python (PyPI wheel):**

```sh
pip install anolis-protocol
```

The PyPI package is published on each tagged release and includes the generated protobuf bindings.

**buf BSR (code generation):**

```yaml
# buf.yaml deps
deps:
  - buf.build/anolishq/anolis-protocol
```

### Work with the schema directly (contributors)

Requires [Buf CLI](https://buf.build/docs/installation) v1.x.

```bash
# Verify schema compiles
buf build

# Lint
buf lint

# Check breaking changes vs main
buf breaking --against "https://github.com/anolishq/anolis-protocol.git#branch=main"

# Generate C++ and Python bindings (outputs to gen/, not committed)
buf generate
```

- Owns ADPP protobuf schema used by `anolis` and providers.
- Contains protocol-only artifacts (schema + semantics + compatibility docs).
- Contains no runtime/provider implementation code.

## Layout

```text
anolis-protocol/
├── buf.yaml              # Buf v2 module config (lint, breaking, deps)
├── buf.gen.yaml          # Canonical generation config (C++, Python)
├── buf.lock              # Pinned dependency hashes
├── proto/
│   └── anolis/
│       └── deviceprovider/
│           └── v1/
│               ├── envelope.proto    # Request / Response top-level envelopes
│               ├── status.proto      # Status and error codes
│               ├── handshake.proto   # Hello request/response
│               ├── inventory.proto   # ListDevices / DescribeDevice
│               ├── telemetry.proto   # ReadSignals / SignalValue
│               ├── call.proto        # CallRequest / CallResponse
│               ├── health.proto      # ProviderHealth / DeviceHealth
│               ├── readiness.proto   # WaitReady request/response
│               ├── types.proto       # Device, CapabilitySet, FunctionSpec, ArgSpec
│               └── value.proto       # Value, ValueType
└── docs/
    ├── index.md
    ├── semantics.md
    └── versioning.md
```

## Development

Requires [Buf CLI](https://buf.build/docs/installation) v1.x.

```bash
# Verify the schema compiles
buf build

# Check lint rules
buf lint

# Check formatting
buf format --diff

# Check for breaking changes vs main
buf breaking --against "https://github.com/anolishq/anolis-protocol.git#branch=main"

# Generate C++ and Python bindings (outputs to gen/, not committed)
buf generate
```

## Versioning

- Repository uses semantic versioning tags: `MAJOR.MINOR.PATCH`.
- Breaking wire-contract changes require a major bump.
- `buf breaking` enforces this automatically on every PR.
- See `docs/versioning.md`.

## Future Work

- long-term: add `CMakeLists.txt` + cmake config; cut consumers to `find_package` — defer until FetchContent causes pain
