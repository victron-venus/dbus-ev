# OpenSSF Best Practices evidence: dbus-ev

This index supports review against the [OpenSSF criteria](https://www.bestpractices.dev/en/criteria). The [live assessment](https://www.bestpractices.dev/projects/15456) is authoritative for awarded status. Current source review: `4ea5bfffa441e4c5259e5564f1348781fb7ee32b` (2026-10-13); later changes require corresponding evidence. This is a self-assessment, not a guarantee of security.

## Project and contribution process

Publishes vehicle and charger telemetry through a Venus OS D-Bus EV service.

- [Public repository and history](https://github.com/victron-venus/dbus-ev) provide source, commits and interim changes.
- [README](../README.md) describes installation, configuration and usage.
- [Contribution process](../CONTRIBUTING.md) documents reports, review, style and the policy to add automated tests for major changes.
- [Issues](https://github.com/victron-venus/dbus-ev/issues) and [pull requests](https://github.com/victron-venus/dbus-ev/pulls) provide searchable public discussion and change review.
- [Security policy](../SECURITY.md) documents confidential reporting, response goals, trust boundaries and delivery practices.

The root [LICENSE](../LICENSE) records the project license. Third-party components retain their own notices.

## Implementation and interfaces

- [dbus_ev](../dbus_ev)
- [config.py](../config.py)
- [local_config.example.py](../local_config.example.py)
- [ha/README.md](../ha/README.md)

Interface documentation must explain accepted configuration and inputs, outputs, failure handling and relevant permission boundaries. Verify it against the implementation when changing behavior; source links alone do not establish that every interface is documented.

## Build, test and analysis evidence

The local validation entry point is [scripts/ci.sh](../scripts/ci.sh). Its actual test and compiler/linter commands, not the presence of a workflow name, define the available coverage.

[GitHub Actions](https://github.com/victron-venus/dbus-ev/actions) provides run logs and results. The checked-in workflow definitions are:

- [auto-approve.yml](../.github/workflows/auto-approve.yml)
- [auto-merge.yml](../.github/workflows/auto-merge.yml)
- [ci.yml](../.github/workflows/ci.yml)
- [codeql.yml](../.github/workflows/codeql.yml)
- [coderabbit-autofix.yml](../.github/workflows/coderabbit-autofix.yml)
- [coderabbit-review.yml](../.github/workflows/coderabbit-review.yml)
- [dependency-review.yml](../.github/workflows/dependency-review.yml)
- [quality-gate.yml](../.github/workflows/quality-gate.yml)
- [release-build.yml](../.github/workflows/release-build.yml)
- [release-pipeline.yml](../.github/workflows/release-pipeline.yml)
- [release-security.yml](../.github/workflows/release-security.yml)
- [scorecards.yml](../.github/workflows/scorecards.yml)

Do not equate a green metadata or release job with successful application tests. Record actual test results, coverage limitations and security-analysis results for the submitted revision. Test execution does not establish physical-device behavior.

## Current assessment and remaining work

- [Governance](../GOVERNANCE.md), [code of conduct](../CODE_OF_CONDUCT.md) and [roadmap](../ROADMAP.md) define roles, review and open work.
- [Security assurance](security-assurance.md) records actual trust boundaries, cryptography and the scope of analysis.
- [Quality and build evidence](quality-and-build.md) distinguishes measured runtime coverage, whole-project gaps, builds and target acceptance.
- [Machine-readable review](evidence/assessment-2026-10-13.json) records source, checks and public GitHub findings. It contains no credentials or private reports.

The owner attested to knowledge of secure design and common Python/network vulnerabilities and reported no external bug, enhancement or vulnerability reports in the preceding 12 months. The public GitHub audit found no ordinary issues or security advisories. Private vulnerability reporting is enabled. These are dated observations and attestations, not promises about future history.

Access continuity remains Unmet. Do not infer signed releases, full-project coverage, complete reproducibility or production hardware acceptance from these checks. Later fuzzing or release changes require their own reviewed evidence.

## Release-note source

[CHANGELOG.md](../CHANGELOG.md) contains the current development line's change summary, upgrade impact and security notes. The release policy opts into commit-pinned notes; publication rejects missing or incomplete current-version sections. Historical release bodies still require a separate audit before claiming complete coverage.

The October 2026 maintenance imports the release identity and metadata parser
from `venus-os-ci-toolkit` revision `9dd211a`, including bounded TOML parsing and
source-bound release-note validation. Consumer release-contract suites verify
the imported engine. Workflow-validator refactoring preserves this repository's
existing policy; it does not imply all newer toolkit workflow guarantees are enabled.

Release guidance parsing also imports toolkit revision `ec99f37`: Markdown code
fences cannot provide or split the required version, Upgrade or Security headings.
The release contract suite tests matching fence markers and lengths, unclosed
examples, CRLF input and rejection before any remote publication writes.

Release guidance and validation helpers also import reviewed toolkit revision `cab6d07`: comments and empty code fences cannot satisfy upgrade/security guidance, while visible literal examples remain valid. Receipt size limits are enforced before parsing. The existing consumer workflow policy is retained.

The immutable-action fallback follows reviewed `inverter-control` revision `3830602`: even without a generator manifest, remote job/step references require a full commit SHA (or a Docker content digest), and generated workflows retain their generator marker. Tests exercise copies of the actual repository workflows.

[Toolkit revision `6f3bac8`](https://github.com/victron-venus/venus-os-ci-toolkit/commit/6f3bac867a101441e029ee7c20c5aa92541eb308) also makes same-level and higher-level ATX headings end release sections, including empty headings, while headings inside code or comments remain inert.

Release structure uses ATX headings (`#`, `##`, `###`), with up to three leading spaces. Setext-style or ambiguous text/comment/underline structures in the selected version are rejected; use ATX headings or a blank line before a thematic `---` separator. Literal fenced/indented examples and comments do not define sections.

Toolkit revision `3533a43322cb351433ca8e90b786f14edcea7725` validates staging inputs before creating output and removes only a newly created target after a failed copy, artifact check or receipt write. Regression tests cover retry and preservation of existing operator files.

Toolkit revision `4895f852f87ca1f27e2bc75e24c5c792e4f95aa6` includes verified staging cleanup and rejects release guidance made only of headings or separators. Regression tests cover retry, preservation of existing operator files, and visible guidance requirements.

Toolkit revision `d8089003f43637ee420fa4cbcccdf11f5d21e469` also rejects empty Markdown lists, task items and quotations as release guidance, while preserving literal examples and lists with substantive text.

The CodeQL configuration also analyzes GitHub Actions in its own analysis category; existing application-language analyses remain enabled.
