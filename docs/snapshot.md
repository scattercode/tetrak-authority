# The snapshot

A snapshot is a directory of two files:

- `snapshot.json`, the manifest: the date, the endpoint, the scope, the
  enumeration queries, the counts per kind, the number of requests made,
  and the versions of this package and of tetrak-translit that keyed the
  names.
- `entities.jsonl`, one record per line, as `Entity.to_json` writes it.

The manifest is what a measurement cites. The same queries on another
day give another snapshot, because Wikidata changes daily and the mirror
that answers the enumeration lags it, so a figure derived from a snapshot
names its date beside the library version, and a snapshot is rebuilt on
a cadence rather than kept.

## The scope

`Scope` says what a snapshot covers. The default, `ARMENIAN`:

| Kind | Brought in by |
|---|---|
| person | human (P31 Q5) with a label or alias in `hy` or `hyw`; or Armenian ethnicity (P172); or Armenian citizenship (P27) |
| organisation | one of the usual organisation classes (organisation, business, university, library, museum, publisher, party, monastery, newspaper …) with such a label |
| place | coordinates (P625) inside the box, and such a label or alias |

Royalty and saints come in through the label, since they carry no modern
tag; a diaspora figure with no Armenian label comes in through the tag.

The **box** is an approximation of historic Armenia and the lands around
it, where a place is likeliest to carry names in several languages: the
far west of modern Turkey to Tehran, Jerusalem to the northern edge of
Georgia, which is longitude 26 to 51.6 and latitude 31.7 to 43.6. Pass
another box, or none, to change that. Counted on 18 October 2026 against
the QLever mirror: about 136,000 people, 7,800 organisations and 22,000
places; the box alone holds some 283,000 items with coordinates, which is
why the label filter matters.

Every part of the scope is an argument, on the command line or in Python:

```python
from tetrak_authority import Box, Client, Scope
from tetrak_authority.snapshot import build, count

scope = Scope(languages=("hy", "hyw", "ru"), box=Box(west=43.0, south=38.8, east=46.7, north=41.4))
count(Client(), scope)
build(Client(), out=Path("snapshots/armenia-only"), scope=scope)
```

## What is fetched

For every item, in batches of two hundred: every label and alias in
every language; the instance-of classes; the VIAF, GND, ISNI, LCNAF and
GeoNames identifiers; birth and death years; coordinates; a place's
native and official names; and the English description. Two queries per
batch, each a few seconds on the Query Service, so the default scope is
some sixteen hundred requests in about two and a half hours.

An item found under an earlier kind is not fetched again under a later
one: a monastery with coordinates is an organisation, not also a place.
A batch the endpoint refuses (one item with thousands of names can
exhaust its memory) is halved and retried down to single items, and an
item refused on its own is listed under `failed` in the manifest and
left out. A run that stops can be continued with `--resume`, which keeps
what `entities.jsonl` already holds.

## Endpoints

Enumerating a subset by label language over the whole of Wikidata is a
query the Wikidata Query Service cannot finish within its 60-second
limit. The [QLever mirror](https://qlever.dev/wikidata)
at the University of Freiburg answers it in a second from a copy a little
behind live, so enumeration defaults to it (`--endpoint`). Fetching
names and facts for a batch of ids is the other way round: the Query
Service answers a batch of two hundred in a few seconds where the mirror
takes several times as long, so the fetch defaults to the Query Service
(`--fetch-endpoint`). The manifest records both.

The full Wikidata dump is the other sanctioned bulk path. It is of the
order of a hundred gigabytes compressed and well over a terabyte
unpacked, refreshed weekly, for a sliver we want; a query does the
filtering in minutes that streaming the dump does in a day.

## Etiquette

Wikimedia's policy for bulk readers: identify yourself, go one request
at a time, back off when told to. The client sends a user agent naming
the package, its version and a contact, pauses a second between requests
(`--pause`), retries 429 and 5xx with backoff, and counts its requests
into the manifest. Make the contact yours with `--contact` when you
build a snapshot of your own.

## Keys and tetrak-translit

The keys in a snapshot are tetrak-translit's fold keys, with the words
sorted. A minor release of tetrak-translit can change keys (that is what
its minor releases are for), so after upgrading it, rebuild the snapshot,
and read the translit version in the manifest before comparing two.
