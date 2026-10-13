# Quality, build and assessment evidence

The [machine-readable review](evidence/assessment-2026-10-13.json) records checks on application source `4ea5bfffa441e4c5259e5564f1348781fb7ee32b` on 2026-10-13. Documentation additions do not substitute for these checks.

## Reproduction and results

Use the locked Python 3.12.13 environment described in [CONTRIBUTING.md](../CONTRIBUTING.md). The application pytest suite passed **288 tests**, with **1 skipped**; the receipt explains the optional-environment skips. A separate release-contract run passed **342 tests**. Ruff lint and formatting passed. Local wheel construction passed; it does not install or validate Venus OS native libraries.

Runtime-only statement coverage, excluding tests, measured **1612/1794 (89.86%)** in the listed Python files. The generic `--cov=.` total includes tests and is not a defensible whole-project percentage. This review therefore does **not** claim OpenSSF Silver 80% whole-project coverage: release helpers, shell code, optional integrations and native dependencies need an explicit accounting. Do not silently remove these components from the denominator.

The all-severity Bandit 1.9.2 review found 32 low-severity warnings and no medium/high findings. The receipt includes each location and review; the warnings concern placeholder/key-name strings and local subprocess trust boundaries. The optional Go engine passed its mandatory-patch wrapper's race tests and vet on macOS ARM64. Target Linux ARMv7/ARM64 import graphs support the scoped GO-2026-5932 non-applicability finding in the security case. This is not a live-provider test or a claim that every module is free of advisories.

## Dependencies, installation and delivery

`pyproject.toml` and `uv.lock` record Python dependencies and the build group; the README identifies Venus OS D-Bus/GLib prerequisites. The optional engine records Go modules/checksums and patch inputs under `vehicle-engine`; the HA adapter retains its upstream notices. Dependabot and scheduled security checks monitor dependencies. Resolve findings and re-test lockfile updates; do not modify installed third-party source without a reviewed, recorded patch.

The native installer intentionally uses Venus OS `/data` and supervisor locations and is not a generic prefix/DESTDIR installer. Editable Python development installation provides fast application iteration, but does not provision all native/optional hardware dependencies. A full standard-variable installation claim remains open.

Source and release downloads use GitHub HTTPS. Existing release assets include SHA-256 inventories; this review does not claim signed releases, signed tags, full artifact reproducibility or target acceptance. A real cryptographic signature must be checked against the expected publishing identity, and exact RC bytes must pass the target acceptance required by [RELEASING.md](../RELEASING.md) before stable promotion.

## Review limits and next work

The public GitHub review found enabled private vulnerability reporting and no open Dependabot or secret alerts. Code-scanning observations are listed individually in the receipt. Release bodies are present; older retrospective release notes still require the separate release-note quality review before claiming complete coverage. No public project vulnerability advisory or ordinary issue was found, and the owner reported no external reports in the preceding twelve months.

The Markdown uses headings and descriptive links, but this review is not an accessibility certification or a tested translation system. Full release reproducibility, cryptographic signing, comprehensive coverage, optional-runtime accessibility and actual [access continuity](../GOVERNANCE.md) remain work in [the roadmap](../ROADMAP.md). Unsupported criteria must stay unmet in the public assessment.
