# Documentation

A D-Bus service that exposes electric-vehicle data on Venus OS, covering the
Mercedes integration, optional multi-brand providers and the release records.

## Data sources

- [Mercedes protocol source](mercedes-upstream.md) — the upstream revision this integration was adapted from.
- [Mercedes migration and rollback](mercedes-migration.md) — the instance numbers one process owns and how to roll back.
- [Experimental multi-brand vehicle providers](vehicles.md) — the optional persistent engine selected by `DATA_SOURCE = "evcc"`.
- [Provider cryptography policy](provider-cryptography.md) — the 35 catalog templates the optional engine accepts.

## Assurance

- [Security assurance case](security-assurance.md) — the three data-reading paths and what the case covers.
- [Offline TLS dependencies on ARMv7](tls-dependencies.md) — the pinned cryptography stack the key policy needs.
- [Quality, build and assessment evidence](quality-and-build.md) — the machine-readable audit record and its security update.
- [OpenSSF Best Practices evidence: dbus-ev](openssf-evidence.md) — the index behind the assessment.

## Releases

- [Release operations](release-packaging.md) — what `release.sh` delegates and which events validate what.
- [Release version inputs](release-versioning.md) — the `versioning` fields that identify a release.
- [CI and release operations](release-workflow.md) — `.release-policy.json` and the required status.
- [CI orchestration](CI-ORCHESTRATION.md) — how the quality gate and release pipeline divide the events.
- [Version plans and manifest synchronization](VERSIONING.md) — the versioning opt-in.
- [Release-candidate fuzzing](fuzzing.md) — the illustrated RC fuzzing process.
- [Fuzzing release candidates](rc-fuzzing.md) — the reusable bounded fuzz workflow.
- [Release read recovery and rerun validation](release-read-safety.md) — the two fixes carried from the shared toolkit.
- [Early final-build runner check](runner-preflight.md) — why the check runs before the final build.
