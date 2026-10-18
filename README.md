# tetrak-authority

A name authority from a dated Wikidata snapshot, for catalogue search
across scripts. For each person, organisation or place in a chosen
subset of Wikidata: the established form, every label and alias in every
language, fold keys for retrieval, and the VIAF, GND, ISNI and GeoNames
identifiers that link a record onward. A Python library and a
command-line tool, with one dependency, [tetrak-translit][translit].

> **Status: alpha.** The snapshot format, the scope and the lookup rules
> are settling against measurement in a working aggregator; the API may
> change before 1.0. What it reads is Wikidata, CC0, with the etiquette
> Wikimedia asks of a bulk reader built in.

```bash
pip install tetrak-authority
```

## Why

The [fold][fold] in tetrak-translit makes every *spelling* of one name
find the same record: *Tumanyan*, *Թումանեան*, *Toumanian* and
*Thoumanian* are one key. What it cannot reach is a different *name*
for the same person or place: *Gregory of Narek* for Գրիգոր Նարեկացի, a
pseudonym, the German *Tscharenz* or the Russian *Ovanes*, *Tiflis* for
Tbilisi. Measured in catalogue search across scripts, the fold finds
about a third of the real spellings readers use for authors, a near-miss
clause about half, and the rest are other names, not typos. Wikidata
holds those names. This package turns a subset of it into an authority
file an indexer can add to each record as alternative names, so that a
search for any of them finds it.

The words are the cataloguer's: an **authority** fixes one established
form of a name and lists the **variant names** that lead to it. In SKOS,
which Europeana uses for its agents, those are `prefLabel`, `altLabel`
and, for the fold keys, `hiddenLabel`. They are not synonyms, which is a
relation between words; Solr's synonym filter is at most one way to
apply the file at query time.

## Three jobs

**Build a snapshot.** A subset of Wikidata is enumerated with SPARQL,
fetched in batches, and written with the date, the endpoint, the queries
and the counts, so that a measurement can cite exactly what it used:

```bash
tetrak-authority count                          # how big the scope is, per kind
tetrak-authority snapshot --out snapshots/hy    # build it: a few hours of polite requests
```

The default scope is Armenian: people with a label or alias in Armenian
or Western Armenian, or with Armenian ethnicity or citizenship (so that
royalty and saints with a label but no modern tag come in, and a diaspora
figure with no Armenian label comes in through the tag); organisations
of the usual kinds with such a label; and places with coordinates inside
an approximation of historic Armenia and the lands around it, the far
west of Turkey to Tehran and Jerusalem to the northern edge of Georgia,
where a place is likeliest to carry names in several languages. Counted
on 18 October 2026: about 136,000 people, 7,800 organisations and 22,000
places. Every part of that is an argument: `--languages`, `--box`,
`--kinds`, or a `Scope` of your own in Python.

**Look names up, offline.** The snapshot is loaded once and matched on
fold keys, so an inverted catalogue form, a classical spelling and a
diaspora romanisation all reach the same record, and nothing touches the
network at index time, in CI or in a discovery layer:

```python
>>> from tetrak_authority import Authority
>>> authority = Authority.load("snapshots/hy")
>>> [m.entity.label for m in authority.match("Tumanyan, Hovhannes")]
['Հովհաննես Թումանյան', 'Հովհաննես Թումանյան']
>>> authority.names_for("Թումանեան Յովհաննէս")[:6]
['Հովհաննես Թումանյան', 'Hovhannes Tumanyan', 'Hovhannes Tumanian', 'Ованес Туманян', 'Howhannes Tumanjan', 'Հովհաննէս Թումանեան']
```

Two Tumanyans come back because Wikidata has two, the poet and an
economist. A match carries the birth and death years, the description
and the identifiers, which is what tells them apart; the join into a
catalogue is the caller's, with whatever confidence rule its data
allows.

**Check one name live.** For a one-off, the client that the snapshot uses
is public: `tetrak-authority search "Նարեկացի"`.

## What it does not do

- **Decide which person a record means.** A lookup returns every entity
  a name reaches, exact matches first, and says what it matched on. Two
  people can share a key; an indexer that adds names should sample its
  matches and judge them before trusting them.
- **Match a single word partially.** *Hovhannes* alone would reach every
  Hovhannes there is. A lookup of two or more words may match a longer
  name that contains them all (*Heinrich Heine* in *Christian Johann
  Heinrich Heine*); one word matches only whole keys.
- **Key names in scripts the fold does not handle.** A Russian or Chinese
  label gets no key, but it is kept as a name to index.
- **Stay current by itself.** A snapshot is a date. Rebuild it on a
  cadence and re-run whatever measure depends on it, citing the date.
  After a tetrak-translit upgrade, `rekey` recomputes the keys in place
  without a refetch.

## Etiquette

Wikidata asks a bulk reader to identify itself, to go one request at a
time and to back off when told to. The client sends a user agent naming
the package, its version and a contact (`--contact` to make it yours),
waits a second between requests, retries on 429 and 5xx with backoff,
and counts its requests into the manifest. Enumeration runs against the
[QLever mirror][qlever] of Wikidata by default, because the Query Service
cannot filter the whole of Wikidata by label language within its
60-second limit; the mirror is a copy a little behind live, which the
manifest records. The fetch of names and facts runs against the Query
Service, which answers a batch of ids several times faster than the
mirror. A refused batch is halved and retried, and a stopped run resumes.

## Documentation

[scattercode.github.io/tetrak-authority][docs]: the snapshot format and
scope, the lookup rules, the API reference and the command line.

## Where it comes from

Built for [Tetrak][tetrak], a toolkit for Armenian cultural heritage,
where an aggregator's search index needs a reader's spelling of a name
to find the catalogue's. The measurements that shaped it are in that
project's design notes; the package itself knows nothing of any
particular catalogue.

## Contributing and licence

See [CONTRIBUTING.md](CONTRIBUTING.md) for the checks and the commit
style, and [AGENTS.md](AGENTS.md) if you work with a coding agent. MIT
licensed; the data it reads is Wikidata's, CC0.

[translit]: https://github.com/scattercode/tetrak-translit
[fold]: https://scattercode.github.io/tetrak-translit/fold.html
[qlever]: https://qlever.dev/wikidata
[docs]: https://scattercode.github.io/tetrak-authority/
[tetrak]: https://tetrak.dev/
