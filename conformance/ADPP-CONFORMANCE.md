# ADPP provider conformance harness

A binary-level acceptance harness that drives an Anolis provider **executable**
through the ADPP wire lifecycle and checks its behavior. It is the verifier for
cross-provider convergence work and the future provider-SDK's acceptance test
(anolis-protocol#25).

> **This document is not normative.** The normative sources are
> `docs/semantics.md` (core ADPP), `docs/profiles/framed-stdio-v1.md` (the stdio
> transport binding), and `docs/profiles/anolis-executable-profile-v1.md` (Anolis
> executable conventions — an organizational profile, not ADPP). Each test suite
> cites its source. Where a normative document permits a choice, the harness
> accepts every permitted behavior; if a check here ever conflicts with its
> source, the source wins and the check is the bug.

**Status:** *foundation.* This PR delivers the generic harness + hermetic
verifier self-tests. It ships **no implementer-specific data** — providers pull
this pinned artifact and supply their own `--provider-profile`. Per-provider CI
lanes (in each provider repo), the full assertion set, the version alignment, and
an org-level cross-version compatibility matrix are tracked follow-ups under #25 —
do not read this as "all of #25 is done".

**Platform:** Linux/POSIX only for now (the client uses `select` on pipes).
Windows support is a tracked follow-up; don't present it as cross-platform yet.

## Running it

```bash
pip install anolis-protocol[conformance]
# --provider-config is the mock-mode config for CI (no real i2c);
# --provider-profile is the provider-owned manifest (identity + waivers).
anolis-adpp-conformance \
  --provider-bin ./build/.../anolis-provider-X \
  --provider-config config/conformance.yaml \
  --provider-profile conformance.toml
```

`--provider-profile` points at a manifest **owned by the provider repo** — the
harness ships no knowledge of any specific provider. See *Waiver policy* below
for its format.

There are two explicit modes, and **a misconfigured run never reports green**:

- **provider mode** — all three `--provider-*` args are required; a partial set
  or a bare invocation is a usage error (nonzero exit), so a broken provider-CI
  command can't masquerade as conformant.
- **self-test mode** — `anolis-adpp-conformance --self-test` runs only the
  hermetic verifier self-tests (no provider args allowed).

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
     fail `NOT_FOUND` **or** return partial results omitting it (§7.4). The
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
and asserts the harness **rejects** each. These are hermetic (no external binary)
and are what make the verifier trustworthy. They cover:

- **transport faults** — hang, signal-crash, over-cap response, byte-drip,
  mid-frame close, wrong `request_id`, missing status;
- **the real malformed-input validator** (`checks.assert_controlled_malformed`,
  the same code the framed-stdio suite runs) against a provider that answers
  garbage with `CODE_OK`, with `CODE_UNSPECIFIED`, or with a response-then-crash
  — each must be rejected, while a framed *error* response is accepted;
- **the profile loader** — valid manifests, defaults, and every rejection path
  (missing/invalid fields, unknown keys, malformed TOML).

The CI also asserts at the command level that a misconfigured invocation (no
mode, partial provider args, or a waiver targeting a non-executable-profile test)
exits **nonzero** — the verifier must never report green having tested nothing.

## Waiver (`xfail`) policy

A provider's identity and tracked gaps live in a **provider-owned manifest** —
this repo ships only the schema + loader, never a provider's data. Pass it with
`--provider-profile conformance.toml`:

```toml
provider_name = "anolis-provider-<name>"    # required; asserted against Hello
has_mock_devices = true                     # optional, default true

[waivers]                                   # test base-name -> reason (issue link)
test_cli_version_flag = "no --version (<owner>/<repo>#<issue-number>)"
```

Waivers apply as **strict** `xfail`s and may target **only executable-profile**
tests (those carry the `executable_profile` marker). A waiver key naming any
other test — a core, framed-stdio, or verifier test — is rejected at collection,
so a waiver can never mask a real protocol/transport failure. Strict means a
fixed divergence fails as `XPASS` until its waiver is removed, rather than
silently preserving stale conformance debt. Because the manifest lives in the
provider repo, the protocol package never re-releases for a provider-specific
exception. Each waiver reason should carry an issue link (and ideally an
owner/expiry).

## Not yet covered (follow-ups, #25)

Positive calls (by id and name) with valid args; argument type/bound validation;
deadline behavior; typed-value/quality/timestamp assertions; full readiness
diagnostics; pre-Hello handling; and capability id/name-convention checks.
Provider-side concerns — each provider's `provider.conformance` CI lane (pulling
this pinned wheel), its `conformance.toml`/mock config, and version-pin alignment
— are tracked in the respective provider repos, plus an org-level cross-version
compatibility matrix. (ADPP is currently implemented by `anolis-provider-sim`,
`-ezo`, and `-bread`.)
