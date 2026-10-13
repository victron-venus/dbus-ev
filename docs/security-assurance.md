# Security assurance case

## Claim, architecture and assumptions

The Python service reads Home Assistant HTTP data, direct Mercedes OAuth/WebSocket data, or an optional local Go vehicle-provider process. It projects normalized vehicle and optional charger telemetry to Venus OS D-Bus. Optional MQTT output serves the included Home Assistant adapter; Cerbo MQTT input supplies independently aged local meter values. The GLib tick handles projection/freshness while blocking provider work is isolated.

The reviewed guarantee is telemetry projection with explicit freshness and command ownership. The charger compatibility paths are read-only: this bridge does not start charging, change EVSE current or own physical actuator arbitration. Assets include provider credentials, VIN/location/vehicle data, host access and honest unavailable readings. Operators restrict local configuration, token directories, MQTT publication and network access. Local administrator compromise is outside the guarantee.

## Argument and evidence

- [Service/control tests](../tests/test_control.py) ensure projected control paths cannot actuate hardware. [Charger freshness tests](../tests/test_charger_freshness.py) preserve independent cloud and meter freshness; retained MQTT data cannot refresh a local measurement. Unknown and nonfinite values remain unavailable.
- [Mercedes lifecycle](../tests/test_mercedes_lifecycle.py), [traffic](../tests/test_mercedes_traffic.py) and [recovery tests](../tests/test_mercedes_recovery.py) cover reconnect, account cooldown, Retry-After and explicit recovery. A private token-file lock prevents two local clients from concurrently rotating one account. Token writes use a private temporary file, flush/fsync and atomic replacement.
- [Protocol tests](../tests/test_mercedes.py) exercise controlled protobuf/JSON snapshots, VIN selection, partial updates and freshness. This is not a guarantee against every malicious provider message or unlimited resource consumption.
- [Provider tests](../tests/test_vehicle_providers.py) cover local child-process boundaries and failure handling. The configured executable is an operator trust decision, launched without a shell; do not select untrusted executables or config files.
- The optional Go engine uses pinned upstream source and mandatory reviewed patches. Its wrapper checks input hashes and builds in an isolated copy. Python wrapper tests and the Go race detector/vet checks cover that path. They do not validate all upstream providers against live accounts.

## Credentials and cryptography

Direct Mercedes OAuth uses SHA-256 PKCE with 32 cryptographically random bytes from Python `secrets`; request identifiers use secure randomness. The optional Go authorization state uses `crypto/rand`. Cloud connections use maintained HTTP/TLS libraries, TLS 1.2+ with ECDHE/AEAD suites and exact verified certificate-key minimums. The [provider cryptography policy](provider-cryptography.md) records the complete provider graph, secure randomness and eight legacy protocols disabled unless the operator explicitly enables compatibility. The reviewed source does not disable certificate verification. Renew/revoke credentials through the upstream provider, stop the old session, replace the protected local token/configuration, then reauthorize. Tokens and optional recovery credentials are client secrets, not a server password-verifier database; filesystem permissions do not encrypt them at rest.

The Home Assistant URL is operator-configured and can use plaintext HTTP. Cerbo and optional HA MQTT can likewise be plaintext. Isolate trusted-local transports or use independently authenticated encryption before crossing an untrusted network. This project does not claim universal encrypted transport, universal forward secrecy or encrypted local HTTP/MQTT. Never export live configuration, tokens or raw private snapshots in issues.

No first-party C/C++ source is maintained here, but Go runtime/cgo, Python, protobuf, D-Bus/GLib and system TLS libraries may include native code. Go race detection is not a proof of memory safety for third-party native dependencies. Keep the supported firmware and locked dependencies patched.

## Static-analysis triage

The dated Bandit review found only low-severity items: token-field/empty-string constants (not embedded credentials), fixed-command subprocess use in local tooling, and the explicitly configured provider executable. The full per-finding receipt records that review; these are not blanket suppressions. The source review found no medium/high Bandit findings. Required CodeQL/security CI remains authoritative for the current revision.

Scorecard reported GO-2026-5932 against the `golang.org/x/crypto` module. The [Go advisory](https://pkg.go.dev/vuln/GO-2026-5932) applies to its abandoned `openpgp` packages. The Linux ARMv7 and ARM64 dependency graphs of this project's engine each contain 949 packages and **no `golang.org/x/crypto/openpgp` package**. This is a scoped non-applicability finding for the current build, not a claim that the upstream module is vulnerability-free; keep the alert visible and recheck when imports/build tags change. Evidence is recorded in [the assessment receipt](evidence/assessment-2026-10-13.json).

## Limits

The local checks use synthetic fixtures and temporary files, with no live account, vehicle, charger or production deployment. [Quality evidence](quality-and-build.md) separates the measured Python subset from excluded vendor/HA/Go/tooling code. Release checksums are not cryptographic signatures. Reassess these arguments after changing providers, commands, storage, transports or delivery. [Access continuity](../GOVERNANCE.md) remains open.
