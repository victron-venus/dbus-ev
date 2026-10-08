# CI orchestration

Quality gate owns pull request and merge queue validation. The release pipeline
owns default branch and nightly checks for applications; validation-only projects
run those events through Quality gate. Callable validators do not launch duplicate
runs. Superseded PR runs are cancelled, and validation jobs have explicit timeouts.

The required CI configuration contracts check CodeQL pin compatibility, validation
triggers, timeouts, and complete gate dependencies. Dependency Review, where present,
blocks the same gate for pull requests and reports other events as not applicable.
CodeQL action updates are grouped where Dependabot Actions updates are configured.

Auto-merge retains the check-waiting mode because the conditional Gitar review
check does not appear on every PR. It waits for all observed checks, including Gitar,
without making absent conditional checks a permanent merge blocker. BOT_PAT remains
the merger token; approval token policies are unchanged. The gate and external
security checks retain strict branch protection and verified source GitHub Apps.

## Selective toolkit maintenance

The existing vendored baseline is retained. The following behavior-preserving
changes are backported from [toolkit ba1e3e7](https://github.com/victron-venus/venus-os-ci-toolkit/commit/ba1e3e7810783dca5ba6dec85274e2df60bdeef1):

- ASCII-only NIGHTLY identity pattern.
- Prepare exception-test fixtures before entering the expected-error assertion.

The repository-specific imports, type annotations, policy and workflow inputs
remain authoritative; this is not a full generator upgrade.

Shared CI is pinned to [toolkit b8154df](https://github.com/victron-venus/venus-os-ci-toolkit/commit/b8154dfcf2d4cf829cb41514ef3cbf82c68a418f). The shared Python CI workflow installs the committed `uv.lock` with `dev` extras. The `build` group bootstraps wheel-only build backends before the local project is installed without build isolation. Existing test, type-check, and coverage settings are retained.
