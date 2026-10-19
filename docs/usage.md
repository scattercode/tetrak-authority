# Usage

## Loading a snapshot

```python
from tetrak_authority import Authority

authority = Authority.load("snapshots/hy")
len(authority)  # entities
authority.manifest["date"]
authority.get("Q380797")  # one Entity, or None
```

`load` takes a snapshot directory (`snapshot.json` beside
`entities.jsonl`) or a `.jsonl` file alone. The script that keys the
names is read from the manifest and defaults to Armenian. Loading opens
the SQLite index beside the entities file (`authority.sqlite`, built by
`snapshot` and `rekey`), so it costs nothing and a lookup reads only the
rows it matches; a snapshot without an index, or whose entities file is
newer than it, is indexed first, once, which takes a few minutes for a
full snapshot. `Authority.from_entities(records)` indexes records in
memory.

## Looking a name up

```python
for match in authority.match("Tumanyan, Hovhannes"):
    match.entity  # the record
    match.name  # the Name whose key matched
    match.exact  # True when the whole key matched
```

A lookup is folded the way the snapshot's names were, and the words are
sorted, so these all reach the poet:

| Typed | Why it matches |
|---|---|
| `Tumanyan, Hovhannes` | the catalogue's inverted form |
| `Թումանեան Յովհաննէս` | classical orthography |
| `Toumanian, Hovannes` | a French-mediated diaspora spelling |
| `Howhannes Tumanjan` | a German label Wikidata holds |

An **exact** match shares the whole key. Failing that, a lookup of two or
more words matches a name that contains all of them (*Heinrich Heine* in
*Christian Johann Heinrich Heine*). One word alone never matches
partially, since *Hovhannes* would reach every Hovhannes there is.
Exact matches come first; `kinds=("person",)` restricts the kinds.

`names_for(text)` returns every distinct name of the exact matches, which
is what an indexer adds to a record as alternative names:

```python
authority.names_for("Գրիգոր Նարեկացի")
# ['Գրիգոր Նարեկացի', 'Gregory of Narek', 'Grégoire de Narek', 'Григор Нарекаци', …]
```

## What a record holds

```python
entity = authority.get("Q380797")
entity.label  # 'Հովհաննես Թումանյան': the first preferred language's label
entity.names  # every Name(text, language, kind)
entity.keys  # the distinct fold keys of those names
entity.identifiers  # {'viaf': '…', 'gnd': '…', 'isni': '…', 'lcnaf': '…'}
entity.born, entity.died
entity.classes  # instance-of ids
entity.description  # the English description
```

Places carry `coordinates` as `(latitude, longitude)` and, where Wikidata
has them, their native and official names among the names.

## Deciding which person a record means

The package does not. Two people can share a key, and a lookup returns
both and says what it matched on. An indexer that adds names should keep
a confidence rule of its own (a single exact match; a birth year within
the record's dates; an identifier the record already carries) and should
sample its matches and judge them by hand before trusting the figures
that follow. A lookup against a snapshot is also a date: cite it.

## Checking one name live

```python
from tetrak_authority import Client

Client().search("Նարեկացի", language="hy")
```

A prefix search over labels in one language, through Wikidata's API,
for a one-off check. It is not how a snapshot matches, and the half of
names it misses is why there is a snapshot.
