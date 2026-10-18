# AGENTS.md

Guidance for anyone working in this repository with a coding agent --
Claude Code, Codex, Cursor, Gemini CLI or whatever else reads this file --
and a fair summary of the house rules for contributors who use none. The
rules are the repository's, not any one tool's; `CONTRIBUTING.md` has the
checks and the commit style at more length.

## What this repository is

**tetrak-authority** builds a name authority from a dated snapshot of a
subset of Wikidata and answers lookups against it offline: for each
person, organisation or place, the established form, every label and
alias in every language, fold keys for retrieval, and the external
authority identifiers (VIAF, GND, ISNI, LCNAF, GeoNames). It exists for
catalogue search across scripts: a reader's name for someone has to find
the catalogue's, and the [fold](https://github.com/scattercode/tetrak-translit)
only reaches spellings, not other names.

Published to PyPI as `tetrak-authority`; the import package is
`tetrak_authority`; the command is `tetrak-authority`. MIT licensed; the
data is Wikidata's, CC0.

## Hard rules

### Describe the use case generically

"Catalogue search across scripts." Never name a partner, a collection, a
catalogue or an endpoint here, in an issue, or in a commit message. The
measurements that shape the package live in a private design project and
reach this repository only as counts and as generic examples.

### A snapshot is a date, and a measurement cites it

Wikidata changes daily and the QLever mirror lags it. `snapshot.json`
records the date, the endpoint, the queries, the counts and the request
count, and any figure derived from a snapshot names that date beside the
library version. Never present a snapshot as current, and never commit a
full snapshot: `snapshots/` is gitignored. The six-entity snapshot under
`tests/data/snapshot/` is a fixture, not data.

### Read Wikidata politely

The client identifies itself (name, version, contact), sends one request
at a time with a pause between them, retries 429 and 5xx with backoff and
counts what it sent. Keep it that way; never add parallel requests. The
Query Service cannot enumerate by label language within its limit, so
enumeration defaults to the QLever mirror; do not work around the limit
with more requests. The tests never touch the network: every response is
recorded under `tests/data/recorded/` by `tests/record.py`.

### Keys come from tetrak-translit, and move with it

A lookup matches on fold keys, and the fold is tetrak-translit's. Keys
are computed when a snapshot is built and stored beside each name, so a
release of tetrak-translit that changes keys changes this package's keys
too: the dependency is pinned to the major, `tetrak-authority rekey`
recomputes a snapshot's keys in place after a minor release, and
`snapshot.json` records the translit version. Nothing here folds
anything itself.

### The fetch is batched and the entity is the contract

`model.Entity` is what a snapshot line holds and what `Authority` reads.
A change to it bumps the manifest's `format`, is a breaking change (`!`),
and keeps `Entity.from_json` able to read the previous format or says in
the changelog that snapshots must be rebuilt.

### One dependency

`dependencies = ["tetrak-translit…"]` and nothing else. The network is
the standard library's.

## Layout

| Path | What |
|---|---|
| `src/tetrak_authority/model.py` | `Entity`, `Name`, `key_of`: the record and its keys |
| `src/tetrak_authority/wikidata.py` | The polite client: SPARQL `select`, API `search`, pacing, retries |
| `src/tetrak_authority/snapshot.py` | `Scope`, `Box`, the enumeration and fetch queries, `build`, `count` |
| `src/tetrak_authority/authority.py` | `Authority.load`, `match`, `names_for`: offline lookups |
| `src/tetrak_authority/cli.py` | `tetrak-authority`, argparse |
| `tests/` | pytest over recorded responses; `tests/record.py` refreshes them |
| `docs/` | Sphinx (furo, MyST), published to GitHub Pages at each release |

## Checks

```bash
ruff check src tests docs && ruff format --check src tests docs
mypy
pytest --cov
uv lock --check
sphinx-build -W -b html docs docs/_build/html
```

All must pass before a commit; the lefthook hooks run most of them. The
Ruff rule set is declared in `pyproject.toml`; never rely on defaults.

## Conventions

- British English; sentence case for headings; first person plural in docs
  (this is a collaborative project).
- Conventional Commits, enforced by `.githooks/commit-msg`; pull request
  titles must be conventional too (`pr-title.yml`). `fix` → patch, `feat`
  → minor, `!` → major. A change to the scope's default queries or to the
  snapshot format is at least `feat`, since snapshots must be rebuilt.
- Releases, tags, the changelog and PyPI publication are automated by
  `release.yml` on every push to `main`. Never do any of them by hand.
- `cliff.toml` and `.githooks/commit-msg` are byte-for-byte copies of the
  templates in `scattercode/release-pipelines`; CI checks they have not
  drifted. Change them there, not here.
- Docstrings are Google style and are the API reference: Sphinx builds
  with `-W`, so a broken cross-reference fails the build.

## Related repositories

- [tetrak-translit](https://github.com/scattercode/tetrak-translit) —
  detect, transliterate and fold; the keys this package matches on.
- [tetrak](https://github.com/scattercode/tetrak) — the OCR pipeline,
  whose entity enrichment is a second user of an authority.
