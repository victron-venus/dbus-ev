# Maintenance roadmap

This roadmap covers October 2026 through October 2027. Review priorities in public issues; these are work items, not promised dates or awarded certification.

1. Establish and verify the real access-continuity arrangement described in [GOVERNANCE.md](GOVERNANCE.md).
2. Keep the documented telemetry freshness, input validation and command-ownership boundaries covered by regressions when changing behavior.
3. Extend coverage accounting to the complete maintained software, including delivery tooling and optional components. Do not infer whole-project coverage from a runtime-only percentage or count tests as application statements.
4. Publish and independently verify cryptographically signed release assets; a SHA-256 file served beside an archive is not a cryptographic signature. Exact target acceptance remains required before stable promotion.
5. Keep dependency and static-analysis reviews current. Reassess native dependencies and optional integrations when their trust boundaries change.
6. Improve staged development installation, accessibility evidence and reproducible-build verification before claiming the corresponding Silver criteria. Maintain the public [evidence index](docs/openssf-evidence.md) against merged source and actual CI results.

## Scope and non-goals

Maintain the Venus OS vehicle/charger telemetry bridge and optional account integrations. The charger D-Bus projection is read-only; this project does not replace the physical EVSE controller or independent equipment safeguards. Optional multi-brand providers remain experimental.
