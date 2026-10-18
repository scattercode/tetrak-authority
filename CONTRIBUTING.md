# Contributing

Thanks for your interest in tetrak-authority. This document covers how we
work in this repository — the checks, the commit style, and the automation
they feed. It applies to us as much as to anyone sending a pull request.

## Before you start

Three constraints shape what we can accept:

- **The tests never touch the network.** Every response a test needs is
  recorded under `tests/data/recorded/` by `tests/record.py`, which makes
  about twenty polite requests. A new query shape means re-recording and
  looking at the diff, because Wikidata moves.
- **A snapshot is a date.** Any figure derived from one names the date in
  `snapshot.json` beside the library version. Full snapshots are never
  committed; `tests/data/snapshot/` is a six-entity fixture.
- **Wikidata is read politely.** One request at a time, a pause between
  them, a user agent with a contact, backoff on 429 and 5xx. A change that
  adds parallelism or removes the pause will not be accepted.

If you work with a coding agent — Claude Code, Codex, Cursor, Gemini CLI or
another — point it at `AGENTS.md`, which carries the repository's rules in
the form such tools read. The rules there are the same as here, stated for
an agent.

## Getting set up

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e '.[dev,apidocs]'
```

(`python -m venv` and `pip` work too.) Then activate the git hooks — one of:

```bash
lefthook install                          # if you have lefthook (brew install lefthook)
git config core.hooksPath .githooks       # dependency-free fallback (commit-msg only)
```

The lefthook hooks run Ruff and the lockfile check before each commit, the
test suite and mypy before each push, and the Conventional Commits check on
every commit message.

## The checks

Everything the hooks and CI run, runnable by hand:

```bash
ruff check src tests docs
ruff format --check src tests docs
mypy
pytest --cov
uv lock --check                           # the lockfile matches pyproject.toml
sphinx-build -W -b html docs docs/_build/html
```

All of these must pass before a pull request can merge. The Ruff rule set
is declared explicitly in `pyproject.toml`; do not fall back to defaults.
Coverage must stay at or above the floor in `pyproject.toml`.

## Dependencies and the lockfile

The package depends on tetrak-translit and nothing else; the network is
the standard library's. Keep it that way. The development and
documentation tooling is pinned in `uv.lock` so that security scanning
(Trivy in CI, Dependabot) sees real resolved versions rather than ranges.
After any change to a dependency or an extra:

```bash
uv lock
```

and commit `uv.lock` alongside `pyproject.toml`. CI fails on a stale lock.

## Commit style

Commits follow [Conventional Commits](https://www.conventionalcommits.org/),
enforced by the shared hook in `.githooks/`:

```
<type>[(scope)][!]: <description>
```

- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
  `build`, `ci`, `chore`, `revert`.
- The description is non-empty, has no trailing full stop, and the header is
  100 characters or fewer (72 or fewer preferred).

This is load-bearing, not cosmetic: the release automation computes the next
semantic version from the commit types (`fix` → patch, `feat` → minor,
`!` → major) and generates `CHANGELOG.md` from the messages. Write the
message for the changelog reader. Pull requests are squash-merged, so the
PR title must be a Conventional Commit too; a workflow checks it.

A change to the default scope's queries or to what a snapshot line holds
is at least a `feat`, since snapshots must be rebuilt; a change to the
snapshot format that older files cannot survive takes a `!`.

## Releases and the changelog

Releases are fully automated — never perform one by hand:

- Every push to `main` runs `release.yml`, which computes the next version
  from the commit history, updates `CHANGELOG.md`, tags, publishes a GitHub
  Release, builds the wheel, publishes it to PyPI with a Trusted Publisher,
  and then deploys the documentation for that tag.
- Never edit `CHANGELOG.md` manually and never create tags or Releases —
  fix the commit messages (or `cliff.toml`) instead.
- The package version comes from the git tag via `hatch-vcs`; there is no
  version literal to bump.

## Conventions

- British English throughout; sentence case for headings.
- Docs are written in the first person plural — this is a collaborative
  project.
- The use case is described as catalogue search across scripts; no partner,
  collection or endpoint is named.
- The audience is librarians' developers and search engineers, most of whom
  will never hear of Tetrak; write the README, the docs and the error
  messages for them.

## Security

Please report suspected vulnerabilities privately — see
[SECURITY.md](SECURITY.md), not the issue tracker.
