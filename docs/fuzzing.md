# Release-candidate fuzzing

See the [illustrated RC fuzzing process and verified rollout results](https://github.com/victron-venus/venus-os-ci-toolkit/blob/main/docs/rc-fuzzing-results.md)
for the shared release flow, evidence requirements and a dated cross-project
snapshot. The project-specific scope and reproduction guidance below still apply.

The optional Go vehicle engine handles cloud-provider values and OAuth redirects.
Its native fuzz tests exercise that normalization boundary using only synthetic
providers and in-memory HTTP metadata. They do not log in to a manufacturer,
poll a vehicle, wake a car, publish D-Bus values or issue control commands.

## Target scope

- `FuzzVehicleTelemetry`: arbitrary floating-point SOC, capacity, position and
  power values through the production sampler. Invalid SOC is rejected; valid
  measured SOC is preserved; coordinates stay bounded; every reply can be
  encoded as JSON, including NaN/infinity edge cases.
- `FuzzProviderRetryAfter`: arbitrary Retry-After text and status codes through
  the production provider-error normalizer. Delays remain finite/nonnegative,
  auth/rate-limit categories remain correct and private provider data stays out
  of replies. HTTP-date delays use the real clock; assertions intentionally test
  bounds rather than an exact elapsed interval.
- `FuzzOAuthStateBoundary`: arbitrary state values through the production OAuth
  completion helper and a fake provider. Only the exact generated state may
  reach the callback. No browser, token endpoint or account is involved.

## Local reproduction and mandatory provider patches

Use the Go version in `vehicle-engine/go.mod` and Python 3.11+. Always use the
project wrapper: the production engine requires verified patches to pinned evcc
providers; unpatched `go test` is not an equivalent test build.

```sh
go -C vehicle-engine mod download
python3 vehicle-engine/build.py test -race ./...
python3 vehicle-engine/build.py fuzz-build
python3 vehicle-engine/build.py fuzz '-fuzz=^FuzzVehicleTelemetry$' -fuzztime=60s
python3 vehicle-engine/build.py fuzz '-fuzz=^FuzzProviderRetryAfter$' -fuzztime=60s
python3 vehicle-engine/build.py fuzz '-fuzz=^FuzzOAuthStateBoundary$' -fuzztime=60s
```

`fuzz-build` compiles instrumented tests without executing them. The wrapper
verifies upstream input checksums and applies the same mandatory patch used for
normal builds in a disposable dependency copy. It never edits the project's
`go.mod`, `go.sum` or the shared Go module cache. Test execution remains rooted in
`vehicle-engine`, so generated failure seeds survive dependency cleanup under
`vehicle-engine/testdata/fuzz/` and can be retained by the shared runner.
The wrapper only accepts an exact anchored target, bounded durations and at most
two workers; it does not expose arbitrary `-modfile`, `-overlay` or `-exec` flags.

## Release policy and evidence

Mutation fuzzing runs only for an explicit **release candidate** request from
the default branch of this public repository, through the shared
`venus-os-ci-toolkit` release pipeline. Pull requests, pushes, betas and nightly
builds do not run mutation campaigns. The shared workflow rejects private
repositories and non-RC events. This is project-operated testing in GitHub
Actions; it does not claim enrollment in Google's hosted OSS-Fuzz service.

The manifest [`.github/fuzz.json`](../.github/fuzz.json) owns the project-specific
commands. The shared runner owns isolation, budgets and retained diagnostics.
Each of the three targets receives 60 seconds with two workers: a total of
180 seconds of mutation time, plus bounded preparation/compilation. Dependency
download and instrumented compilation happen during setup; the campaigns run
without network access. A missing target or failed campaign cannot qualify an RC.

The README **Fuzzing: RC only** badge describes this policy, not the last result.
Inspect the exact release Actions run and its retained logs/report for actual
source-bound results. Fuzz failures block candidate publication. Fix the cause,
review and merge the change, then request a new RC. Stable promotion reuses the
accepted RC's source and artifact evidence without another campaign or rebuild.
Ordinary tests continue replaying checked-in seed/regression cases on PRs and
betas; that deterministic replay does not enable random mutation there.

## Findings and maintenance

Go reports the minimized failing input path under `testdata/fuzz/<FuzzName>/`
and a command to replay it. Keep that file with the corrected code, run the
printed regression command, then the regular tests and a fresh campaign. The
shared workflow retains failing inputs and logs so a hosted failure can be
reproduced locally. Do not put real tokens, account identifiers, private captures
or device data into a public corpus or report. Use [SECURITY.md](../SECURITY.md)
for confidential vulnerabilities.

New targets should call application boundaries and check independent properties,
not only re-test the standard library. Keep inputs bounded and execution
deterministic, with no network or physical device operations. Update the manifest
and this document together. See [Go's fuzzing guide](https://go.dev/doc/security/fuzz/)
for corpus format and minimization. Passing these campaigns is additional test
evidence, not proof that every possible input is safe or hardware acceptance.

## Release workflow retries

Fresh release inputs are selected by the exact GitHub workflow run ID and run
attempt.

Before publication starts, use **Re-run all jobs** only if the allocator and
release policy permit reuse of that run's reservation. Recreate every required
input in the same attempt; failed-only or individual retries can leave inputs
missing, and older artifacts must not fill those gaps.

For a fresh candidate or final build, once publication has started
(`begin_publication`), or its external publication result is partial or uncertain,
inspect the existing release, tags and assets before retrying. A consumed build
number requires a new workflow run and reservation authorized by the release
policy; an existing immutable tag may also require a new base version. Never
reset the release ledger, overwrite assets or retag to force a retry. Historical
byte promotion of an accepted RC keeps its reserved number and follows the
existing promotion policy.

Artifacts from older attempts may remain available for diagnostics; they are not
inputs to the new attempt and do not need to be deleted. Filtering artifact names
alone does not prove package completeness or receipt identity. Complete package
inventory and receipt identity checks remain separate release requirements.

See the shared [package identity and retry contract](https://github.com/victron-venus/venus-os-ci-toolkit/blob/main/docs/VERSIONING.md#package-identity-across-reruns).

### Package receipt identity

Fresh publication verifies each staged package receipt against the independently
supplied repository, source commit, workflow run and attempt. Receipts created
before this migration, or offline without an Actions identity, cannot qualify a
fresh publication. Run all required producers in one complete workflow attempt
after migration; an earlier attempt cannot fill missing inputs.

Historical promotion and retained-evidence validation keep their existing checks.
Receipt coverage validates the staged files; the expected packages and platforms
still require a separate completeness check. Existing release approval and device
acceptance policies continue to apply.

See the shared [receipt migration guide](https://github.com/victron-venus/venus-os-ci-toolkit/blob/main/docs/release-workflow.md#migrate-package-receipt-identity-without-replacing-the-release-engine).

### Complete package producer inventory

`versioning.required_build_receipts` declares the exact package and signature
receipt filenames required by this project's final publisher. Each authenticated
receipt must match the repository, source commit, workflow run and attempt. A
missing producer or an unexpected receipt stops fresh publication, even when the
remaining packages are valid. RC fuzz evidence is checked separately; pre-signing
checks do not require a signature receipt that has not been created yet.

Before publication begins, rerun all required producers only when the allocator
and release policy permit reusing that reservation. After publication begins or
its outcome is uncertain, inspect existing tags, releases and assets before a
policy-authorized new run; never reset the ledger or mix earlier-attempt packages.
Historical RC promotion keeps its accepted source policy. Keep this explicit
inventory aligned with producer changes; it does not replace package-format,
signature or device acceptance checks.
