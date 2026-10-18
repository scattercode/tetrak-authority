# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/scattercode/tetrak-authority/security/advisories/new)
(Security tab → "Report a vulnerability"). Do not open a public issue for a
security problem.

We aim to acknowledge reports within seven days. This is a small
collaborative project, not a company with a security team — but we take
reports seriously and will keep you informed as we investigate.

## Supported versions

Only the latest release receives fixes. There are no maintenance branches.

## What we do ourselves

- The package has no runtime dependencies, so there is no dependency tree
  to compromise at install time.
- The development and documentation tooling is pinned in `uv.lock` and
  scanned by Trivy on every push and weekly on a schedule; Dependabot keeps
  the lock and the workflow actions current.
- Releases are built in CI from the tagged commit and published to PyPI with
  a Trusted Publisher (OIDC): no long-lived token exists anywhere, and every
  release carries PEP 740 attestations.
- The library never reads files, opens sockets or executes anything: it
  takes strings and returns strings.
