# Governance and maintenance

dbus-ev is maintained in public in the [project repository](https://github.com/victron-venus/dbus-ev).

## Roles and decisions

Contributors propose focused changes through issues and pull requests, preserve license notices, and supply tests and documentation. Reviewers examine correctness, compatibility, security boundaries and test evidence. Maintainers decide scope and merge only after the protected branch's required checks and reviews. Bots can assist review but are not human maintainers or successors.

The release maintainer checks reviewed source, validation, release notes and acceptance of exact artifacts before authorizing publication under [RELEASING.md](RELEASING.md). Repository administrators manage access, branch protection and revocation; administrative power must not substitute for normal review.

[4alvit](https://github.com/4alvit) is the current primary maintainer and administrator (administrative permission verified 2026-10-13), responsible for scope, final decisions, releases and security reports. These responsibilities do not imply an independent second maintainer.

Discuss changes to public interfaces, dependencies, supported platforms or security assumptions in an issue or pull request. Describe alternatives, compatibility and migration consequences. Maintainers should record a reasoned decision publicly; contributors may request reconsideration with new evidence. Confidential vulnerability reports follow [SECURITY.md](SECURITY.md). Conduct reports follow the private route in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), which also defines participation expectations.

## Continuity remains open

The owner confirmed on 2026-10-13 that there is **no backup person or verified emergency-access arrangement** able to restore repository, CI and release maintenance if the primary maintainer is unavailable. OpenSSF Silver `access_continuity` is therefore **Unmet**. Public clones, organization membership and automation do not establish this capability.

Before closing the gap, establish an authorized successor or controlled recovery mechanism, inventory critical repository/CI/release/security-reporting access, and verify recovery within one week without publishing credentials. Record the responsible role, scope, review date and test outcome here. Nobody is assigned responsibilities without consent. See [ROADMAP.md](ROADMAP.md).
