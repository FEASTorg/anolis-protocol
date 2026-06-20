# ADPP provider conformance

The executable acceptance spec for an Anolis Device Provider Protocol (ADPP) v1
provider. The harness in `anolis_conformance/` drives a provider **binary**
through the wire lifecycle and asserts the behavior below. It is the verifier
for cross-provider convergence work and the future provider-SDK's acceptance
test (anolis-protocol#25).

## Running it

```bash
pip install anolis-protocol[conformance]
anolis-adpp-conformance \
  --provider-bin ./build/.../anolis-provider-X \
  --provider-config config/conformance.yaml \
  --profile X            # sim | ezo | bread
```

(Equivalently `pytest --pyargs anolis_conformance --provider-bin ...`.) Each
provider runs it as a CTest `provider.conformance` lane in its own CI. The
config should put hardware-backed providers in **mock mode** so the suite runs
without real i2c (ezo/bread: `bus_path: mock://...`; sim is always simulated).

## Wire facts the suite pins

- **Transport:** `uint32` little-endian length prefix + serialized protobuf;
  1 MiB max frame; one in-flight request per session; every `Response` echoes
  `request_id` and carries a `Status`.
- **Protocol version:** the literal string **`v1`** (the `handshake.proto`
  comment historically said `"1"` — the runtime and every provider use `v1`).
- **Status codes** are resolved from the proto enum at runtime — never
  hardcoded (the enum is not sequential: `OK=1`, `INVALID_ARGUMENT=10`,
  `NOT_FOUND=11`, `FAILED_PRECONDITION=12`, `UNIMPLEMENTED=14`,
  `DEADLINE_EXCEEDED=20`, `UNAVAILABLE=21`, `INTERNAL=30`, …).

## Assertion groups

1. **Handshake / version** — `hello(v1)` → `OK`, echoes `provider_name` +
   `protocol_version=v1` + `request_id`; required metadata keys present
   (`transport`, `max_frame_bytes`, `supports_wait_ready`); non-`v1` →
   `FAILED_PRECONDITION`; `request_id` increments and echoes.
2. **Framing robustness** — oversized length header, zero-length frame,
   truncated frame, garbage payload → the provider must **respond or terminate
   promptly, never hang**.
3. **Lifecycle / readiness** — if `supports_wait_ready`, `wait_ready` → `OK`
   with the standard diagnostics (minimum `init_time_ms`).
4. **Inventory / capabilities** — `list_devices` → `OK` (≥1 device in mock
   mode); `describe_device` → `OK` with ≥1 signal or function; unknown device →
   `NOT_FOUND`.
5. **Read / call** — `read_signals` default set returns a well-formed response
   (mock backends may report data unavailable); a read mixing a known + unknown
   signal id must fail `NOT_FOUND` (not return partial); unknown function →
   `NOT_FOUND`/`UNIMPLEMENTED`; a conflicting `function_id`/`function_name` →
   `INVALID_ARGUMENT`.
6. **Health (experimental)** — `get_health` must return a well-formed status.
   Non-gating: the runtime does not call it today.
7. **Process hygiene** — clean exit (code 0) on stdin EOF; multiple round-trips
   stay correctly framed (no stray stdout bytes).
8. **CLI** — `--version` exits 0 with a version string; `--check-config` on a
   valid config exits 0.

## Canonical conventions (locked)

- **Capability ids:** per-type `function_id`s starting at 1; snake_case
  `signal_id`s.
- **Hello metadata:** the three required keys above are standard; providers may
  add extras.
- **WaitReady diagnostics:** standardize on a small key set (`init_time_ms`,
  `provider_impl`, `device_count`, `ready`) — no proto change. (A typed `ready`
  field is a tracked future consideration.)

## Known-divergence policy

A provider's tracked spec gaps are declared in its `ProviderProfile`
(`profiles.py`) and applied as **non-strict `xfail`s**, so the suite is
green-as-baseline while documenting the gap. An xPASS means the gap was fixed —
remove the entry and the assertion becomes a hard requirement. Current baseline
divergences (all tracked under anolis-protocol#25):

| Provider | Divergence |
| --- | --- |
| sim | read mixing known+unknown ids returns partial instead of `NOT_FOUND` (T0.1); no `--version` |
| bread | conflicting `function_id`/`function_name` not rejected (T0.4); `wait_ready` omits `init_time_ms` |
| ezo | none — fully conformant at baseline |

These are exactly the kinds of inconsistencies the convergence waves will fix;
the harness is what verifies each fix.
