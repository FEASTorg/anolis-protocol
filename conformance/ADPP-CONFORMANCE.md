# ADPP provider conformance harness

A binary-level acceptance harness that drives an Anolis provider **executable**
through the ADPP wire lifecycle and checks its behavior. It is the verifier for
cross-provider convergence work and the future provider-SDK's acceptance test
(anolis-protocol#25).

> **`docs/semantics.md` is normative, not this document.** The harness asserts
> the behavior specified there; where the spec permits a choice, the harness
> accepts every permitted behavior. If a check here ever conflicts with
> `semantics.md`, `semantics.md` wins and the check is the bug.

**Status:** *foundation.* This PR delivers the harness + verifier self-tests +
an in-repo canary. Per-provider CI lanes, the full assertion set, the version
alignment, and strict provider-owned waivers are tracked follow-ups under #25 —
do not read this as "all of #25 is done".

**Platform:** Linux/POSIX only for now (the client uses `select` on pipes).
Windows support is a tracked follow-up; don't present it as cross-platform yet.

## Running it

```bash
pip install anolis-protocol[conformance]
anolis-adpp-conformance \
  --provider-bin ./build/.../anolis-provider-X \
  --provider-config config/conformance.yaml \   # mock mode for CI (no real i2c)
  --profile X                                    # sim | ezo | bread
```

The console script loads the plugin explicitly and defaults to the gating set
(`-m "not experimental"`). The plugin is **not** a global `pytest11` entry point,
so installing the wheel never affects unrelated pytest runs.

## Three separate contracts

The harness tests three distinct contracts (kept in separate modules so they are
not conflated):

1. **ADPP core protocol** (`test_adpp_core.py`) — messages, status codes,
   `request_id` correlation, capabilities, and read/call **semantics** per
   `semantics.md`. Examples of deferring to the spec:
   - Unknown signal id → the provider must pick **one consistent** behavior:
     fail `NOT_FOUND` **or** return partial results omitting it (§7.1). The
     harness accepts either.
   - Both `function_id` and `function_name` given → the provider **MUST prefer
     `function_id`** (§6.2). The harness does **not** require rejecting a
     conflict.
   - Unsupported version → `FAILED_PRECONDITION` **or** `UNIMPLEMENTED` (§3).
2. **ADPP framed-stdio profile** (`test_framed_stdio.py`) — `uint32_le` framing,
   the 1 MiB cap, fragmentation/coalescing, and **controlled** handling of a
   malformed stream: a well-formed framed error response, or a clean documented
   exit (codes 0/2/3). A crash (process killed by a signal → negative return
   code), a hang, or an over-cap/malformed response is a **failure**.
3. **Anolis provider executable profile** (`test_executable_profile.py`) — CLI
   surface (`--version`, `--check-config`), the WaitReady diagnostics the runtime
   reads (`init_time_ms`), and process lifecycle. **These are Anolis conventions,
   not ADPP requirements** — a binary can be ADPP-conformant and still diverge
   here.

Concurrency note: `semantics.md` allows concurrent processing and out-of-order
responses (correlate by `request_id`). The runtime's one-in-flight serialization
is a runtime profile, **not** an ADPP restriction — the harness does not require it.

## Verifier self-tests

`test_selftest.py` drives the harness against deliberately-faulty fake providers
(hang, signal-crash, over-cap response, byte-drip, mid-frame close, wrong
`request_id`, missing status) and asserts the harness **rejects** each. These are
hermetic (no external binary) and are what make the verifier trustworthy.

## Waiver (`xfail`) policy

A provider's tracked gaps live in its `ProviderProfile` and apply as non-strict
`xfail`s (green-as-baseline; an xPASS means the gap was fixed — remove the entry).
Waivers cover **only executable-profile** gaps, never behavior `semantics.md`
permits. Current baseline:

| Provider | Waiver (executable profile) |
| --- | --- |
| sim | no `--version` |
| bread | `wait_ready` omits `init_time_ms` |
| ezo | none |

Follow-up (#25): make waivers strict + provider-owned (an issue URL/owner/expiry
per waiver, living in each provider repo), so the protocol package doesn't
re-release for every provider exception.

## Not yet covered (follow-ups, #25)

Positive calls (by id and name) with valid args; argument type/bound validation;
deadline behavior; typed-value/quality/timestamp assertions; full readiness
diagnostics; pre-Hello handling; capability id/name-convention checks; and the
per-provider CI/CTest `provider.conformance` lanes (sim/ezo/bread), plus an ezo
`mock://` conformance config and the sim Python wheel version-pin alignment.
