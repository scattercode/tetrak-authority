"""Build a dated snapshot: the subset, the fetch, the files.

A snapshot is a directory holding ``snapshot.json``, the manifest (when
it was made, from which endpoint, with which queries, how many of each
kind, how many requests), and ``entities.jsonl``, one :class:`Entity`
per line. The manifest is what a measurement cites, beside the library
version: the same queries on another day give another snapshot.

The subset is a :class:`Scope`:

- **People**: items that are human (P31 Q5) with a label or alias in the
  scope's languages, or with one of the scope's ethnicities (P172) or
  citizenships (P27), so that royalty and saints with a label but no
  modern tag come in through the label and a diaspora figure with no
  Armenian label comes in through the tag.
- **Organisations**: items of the scope's organisation classes with a
  label in the languages.
- **Places**: items with coordinates (P625) inside the scope's box and a
  label or alias in the languages. The default box is an approximation
  of historic Armenia and the lands around it, where a place is likeliest
  to carry names in several languages: the far west of Turkey to Tehran,
  Jerusalem to the northern edge of Georgia.

Enumeration needs an endpoint that can filter by label language over
the whole of Wikidata, which the Query Service cannot within its limit
and the QLever mirror can; the fetch of names and facts, in batches of
item ids, works on either.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import tetrak_translit

from .model import KINDS, Entity, Name
from .wikidata import Client, RequestFailed, Row

#: Wikidata classes that count as an organisation here: organisation and
#: the kinds a catalogue meets as a creator or a subject.
ORGANISATION_CLASSES = (
    "Q43229",  # organization
    "Q4830453",  # business
    "Q31855",  # research institute
    "Q3918",  # university
    "Q7075",  # library
    "Q33506",  # museum
    "Q2085381",  # publisher
    "Q1664720",  # institute
    "Q48204",  # association
    "Q7278",  # political party
    "Q163740",  # nonprofit organization
    "Q2385804",  # educational institution
    "Q1530022",  # religious organization
    "Q1370598",  # place of worship
    "Q44613",  # monastery
    "Q11032",  # newspaper
    "Q41298",  # magazine
)

#: The facts fetched for every entity: property → the name it is kept under.
FACT_PROPERTIES = {
    "P31": "class",
    "P214": "viaf",
    "P227": "gnd",
    "P213": "isni",
    "P244": "lcnaf",
    "P1566": "geonames",
    "P569": "born",
    "P570": "died",
    "P625": "coordinates",
    "P1559": "native",
    "P1448": "official",
}
IDENTIFIERS = ("viaf", "gnd", "isni", "lcnaf", "geonames")


@dataclass(frozen=True)
class Box:
    """A bounding box in degrees: west and east longitudes, south and north latitudes."""

    west: float
    south: float
    east: float
    north: float

    def filter(self, variable: str = "?loc") -> str:
        """The SPARQL filter that keeps a coordinate inside the box."""
        return (
            f"FILTER(geof:longitude({variable}) >= {self.west} && geof:longitude({variable}) <= {self.east}"
            f" && geof:latitude({variable}) >= {self.south} && geof:latitude({variable}) <= {self.north})"
        )


#: Historic Armenia and the lands around it, approximately: the far west of
#: modern Turkey to Tehran, Jerusalem to the northern edge of Georgia.
HISTORIC_ARMENIA = Box(west=26.0, south=31.7, east=51.6, north=43.6)


@dataclass(frozen=True)
class Scope:
    """What a snapshot covers.

    Attributes:
        script: The tetrak-translit script whose fold keys the names.
        languages: Label languages that bring an item in.
        ethnicities: Item ids for P172 that bring a person in.
        citizenships: Item ids for P27 that bring a person in.
        organisation_classes: P31 values that make an item an organisation.
        box: Where a place must lie, or ``None`` for places anywhere with
            a label in the languages.
    """

    script: str = "hy"
    languages: tuple[str, ...] = ("hy", "hyw")
    ethnicities: tuple[str, ...] = ("Q79797",)  # Armenians
    citizenships: tuple[str, ...] = ("Q399",)  # Armenia
    organisation_classes: tuple[str, ...] = ORGANISATION_CLASSES
    box: Box | None = HISTORIC_ARMENIA

    def _languages(self) -> str:
        return ", ".join(f'"{language}"' for language in self.languages)

    def _labelled(self, variable: str = "?item") -> str:
        # The language filter sits inside each branch: over the union it
        # defeats the endpoints' label indexes and the query times out.
        languages = self._languages()
        return (
            f"{{ {variable} rdfs:label ?l . FILTER(LANG(?l) IN ({languages})) }}"
            f" UNION {{ {variable} skos:altLabel ?l . FILTER(LANG(?l) IN ({languages})) }}"
        )

    def queries(self) -> dict[str, str]:
        """The enumeration query for each kind, returning ``?item``."""
        people = f"SELECT DISTINCT ?item WHERE {{ ?item wdt:P31 wd:Q5 . {{ {self._labelled()} }}"
        for prop, values in (("P172", self.ethnicities), ("P27", self.citizenships)):
            if values:
                people += (
                    " UNION { VALUES ?v { "
                    + " ".join(f"wd:{v}" for v in values)
                    + " } ?item wdt:"
                    + prop
                    + " ?v }"
                )
        people += " }"
        organisations = (
            "SELECT DISTINCT ?item WHERE { VALUES ?c { "
            + " ".join(f"wd:{c}" for c in self.organisation_classes)
            + f" }} ?item wdt:P31 ?c . {self._labelled()} }}"
        )
        box = (
            f"?item wdt:P625 ?loc . {self.box.filter()} " if self.box else "?item wdt:P625 ?loc . "
        )
        places = f"SELECT DISTINCT ?item WHERE {{ {box}{self._labelled()} }}"
        return {"person": people, "organisation": organisations, "place": places}

    def counts(self) -> dict[str, str]:
        """The same queries, counting instead of listing."""
        return {
            kind: query.replace("SELECT DISTINCT ?item", "SELECT (COUNT(DISTINCT ?item) AS ?n)", 1)
            for kind, query in self.queries().items()
        }


#: The Armenian scope: Armenian and Western Armenian labels, Armenians,
#: Armenia, and the historic region.
ARMENIAN = Scope()


def names_query(ids: Sequence[str]) -> str:
    """Every label and alias, in every language, of the given items."""
    values = " ".join(f"wd:{id}" for id in ids)
    return (
        f"SELECT ?item ?name ?kind WHERE {{ VALUES ?item {{ {values} }}"
        ' { ?item rdfs:label ?name . BIND("label" AS ?kind) }'
        ' UNION { ?item skos:altLabel ?name . BIND("alias" AS ?kind) } }'
    )


def facts_query(ids: Sequence[str]) -> str:
    """The facts in :data:`FACT_PROPERTIES` and the English description of the given items."""
    values = " ".join(f"wd:{id}" for id in ids)
    props = " ".join(f"wdt:{p}" for p in FACT_PROPERTIES)
    return (
        f"SELECT ?item ?prop ?value WHERE {{ VALUES ?item {{ {values} }}"
        f" {{ VALUES ?prop {{ {props} }} ?item ?prop ?value }}"
        ' UNION { ?item schema:description ?value . FILTER(LANG(?value) = "en") BIND("description" AS ?prop) } }'
    )


def count(client: Client, scope: Scope = ARMENIAN, kinds: Iterable[str] = KINDS) -> dict[str, int]:
    """How many items each kind of the scope holds, one query per kind."""
    counts = {}
    for kind, query in scope.counts().items():
        if kind in kinds:
            rows = client.select(query)
            counts[kind] = int(rows[0]["n"].value) if rows else 0
    return counts


def enumerate_ids(client: Client, scope: Scope, kind: str, limit: int | None = None) -> list[str]:
    """The item ids of one kind, in a stable order."""
    query = scope.queries()[kind]
    if limit is not None:
        query += f" LIMIT {limit}"
    return sorted({row["item"].id for row in client.select(query)}, key=_item_order)


def _item_order(id: str) -> tuple[int, str]:
    return (int(id[1:]), id) if id[1:].isdigit() else (0, id)


def fetch(client: Client, ids: Sequence[str], kind: str, script: str = "hy") -> list[Entity]:
    """Fetch names and facts for one batch of ids and assemble their records."""
    names: dict[str, set[Name]] = {id: set() for id in ids}
    for row in client.select(names_query(ids)):
        cell = row["name"]
        names[row["item"].id].add(Name(cell.value, cell.language or "", row["kind"].value))
    facts: dict[str, list[tuple[str, Row]]] = {id: [] for id in ids}
    for row in client.select(facts_query(ids)):
        prop = row["prop"].value
        facts[row["item"].id].append((FACT_PROPERTIES.get(prop.rsplit("/", 1)[-1], prop), row))
    return [assemble(id, kind, names[id], facts[id], script) for id in ids if names[id]]


def assemble(
    id: str, kind: str, names: set[Name], facts: list[tuple[str, Row]], script: str = "hy"
) -> Entity:
    """One record from a batch's rows."""
    classes: list[str] = []
    identifiers: dict[str, str] = {}
    born = died = description = None
    coordinates = None
    for name, row in facts:
        cell = row["value"]
        if name == "class":
            classes.append(cell.id)
        elif name in IDENTIFIERS:
            identifiers.setdefault(name, cell.value)
        elif name == "born":
            born = born or year(cell.value)
        elif name == "died":
            died = died or year(cell.value)
        elif name == "coordinates":
            coordinates = coordinates or point(cell.value)
        elif name in ("native", "official"):
            names.add(Name(cell.value, cell.language or "", name))
        elif name == "description":
            description = description or cell.value
    return Entity.build(
        id,
        kind,
        names,
        script=script,
        classes=sorted(set(classes), key=_item_order),
        identifiers=identifiers,
        born=born,
        died=died,
        coordinates=coordinates,
        description=description,
    )


def year(value: str) -> str | None:
    """The year of a Wikidata time value (``1869-02-19T00:00:00Z`` → ``1869``, ``-0500-…`` → ``-500``)."""
    sign = "-" if value.startswith("-") else ""
    digits = value.lstrip("+-").split("-", 1)[0]
    return f"{sign}{int(digits)}" if digits.isdigit() else None


def point(value: str) -> tuple[float, float] | None:
    """``(latitude, longitude)`` from a WKT point (``Point(44.5 40.18)``), or ``None``."""
    inner = value.strip()
    if "(" not in inner or ")" not in inner:
        return None
    parts = inner[inner.index("(") + 1 : inner.rindex(")")].split()
    if len(parts) != 2:
        return None
    try:
        longitude, latitude = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    return (latitude, longitude)


def fetch_resilient(
    client: Client,
    ids: Sequence[str],
    kind: str,
    script: str = "hy",
    failed: list[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[Entity]:
    """Fetch a batch, halving it when the endpoint refuses it, and skipping an item it will not answer.

    An endpoint can run out of memory or time on one batch (a few items
    with thousands of names), so a refused batch is split and each half
    tried, down to single items. An item refused on its own is recorded
    in *failed* and left out, so one bad item does not stop a snapshot.
    """
    try:
        return fetch(client, ids, kind, script)
    except RequestFailed as error:
        if len(ids) == 1:
            if failed is not None:
                failed.append(ids[0])
            if log:
                log(f"{kind}: {ids[0]} skipped: {error}")
            return []
        if log:
            log(f"{kind}: a batch of {len(ids)} refused ({str(error)[:80]}); trying halves")
        middle = len(ids) // 2
        return fetch_resilient(client, ids[:middle], kind, script, failed, log) + fetch_resilient(
            client, ids[middle:], kind, script, failed, log
        )


def batches(items: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    """Consecutive slices of *items*, each at most *size* long."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def build(
    client: Client,
    out: Path,
    scope: Scope = ARMENIAN,
    kinds: Iterable[str] = KINDS,
    batch: int = 200,
    limit: int | None = None,
    log: Callable[[str], None] | None = None,
    fetch_client: Client | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Enumerate, fetch and write a snapshot; return its manifest.

    Args:
        client: The endpoint that enumerates the subset; see :mod:`.wikidata`.
        out: The directory to write ``snapshot.json`` and ``entities.jsonl`` into.
        scope: What to cover.
        kinds: Which of ``person``, ``organisation`` and ``place`` to include.
        batch: Items per fetch query. Two hundred keeps a names query to
            some thirty thousand rows, which the Query Service answers in
            a few seconds.
        limit: Items per kind, for a trial run.
        log: Where progress lines go, if anywhere.
        fetch_client: The endpoint that fetches names and facts, when it
            is not the one that enumerates. The Query Service is several
            times faster than the mirror at a batch of ids, and the
            mirror alone can enumerate, so the command line uses both.
        resume: Keep the entities already in ``entities.jsonl`` and fetch
            only the rest, for a run that stopped.

    An item found under an earlier kind is not fetched again under a
    later one: a monastery that is also a place is an organisation. A
    batch the endpoint refuses is halved and retried; an item refused on
    its own is listed under ``failed`` in the manifest and left out.
    """
    say = log or (lambda line: None)
    fetcher = fetch_client or client
    started = time.monotonic()
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    failed: list[str] = []
    seen: set[str] = set()
    lines_file = out / "entities.jsonl"
    if resume and lines_file.exists():
        with lines_file.open(encoding="utf-8") as existing:
            seen.update(json.loads(line)["id"] for line in existing if line.strip())
        say(f"resuming: {len(seen)} entities already written")
    translit = f"tetrak-translit {tetrak_translit.__version__}"
    with lines_file.open("a" if resume else "w", encoding="utf-8") as lines:
        for kind in KINDS:
            if kind not in kinds:
                continue
            everything = enumerate_ids(client, scope, kind, limit)
            ids = [id for id in everything if id not in seen]
            seen.update(everything)
            counts[kind] = len(everything) - len(ids)
            say(f"{kind}: {len(ids)} items to fetch")
            for number, chunk in enumerate(batches(ids, batch), 1):
                for entity in fetch_resilient(fetcher, chunk, kind, scope.script, failed, say):
                    lines.write(entity.line() + "\n")
                    counts[kind] += 1
                lines.flush()
                say(
                    f"{kind}: batch {number}, {counts[kind]} written, {client.requests + (fetcher.requests if fetcher is not client else 0)} requests"
                )
    requests = client.requests + (fetcher.requests if fetcher is not client else 0)
    manifest = {
        "format": 1,
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "endpoint": client.endpoint,
        "fetch_endpoint": fetcher.endpoint,
        "scope": scope_json(scope),
        "queries": {kind: query for kind, query in scope.queries().items() if kind in kinds},
        "limit": limit,
        "counts": counts,
        "failed": failed,
        "requests": requests,
        "seconds": round(time.monotonic() - started, 1),
        "library": f"tetrak-authority {_version()}",
        "fold": translit,
    }
    (out / "snapshot.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def scope_json(scope: Scope) -> dict[str, Any]:
    """The scope as the manifest records it."""
    return {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in asdict(scope).items()
    }


def _version() -> str:
    from . import __version__

    return __version__


__all__ = [
    "ARMENIAN",
    "FACT_PROPERTIES",
    "HISTORIC_ARMENIA",
    "ORGANISATION_CLASSES",
    "Box",
    "Scope",
    "assemble",
    "batches",
    "build",
    "count",
    "enumerate_ids",
    "facts_query",
    "fetch",
    "fetch_resilient",
    "names_query",
    "point",
    "year",
]
