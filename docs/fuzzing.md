# Release-candidate fuzzing

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
