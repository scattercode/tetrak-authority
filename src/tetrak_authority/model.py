"""The authority record: one entity, its names, its keys and its identifiers.

An :class:`Entity` is what a snapshot holds for one Wikidata item. Its
names are every label and alias Wikidata carries in every language, plus
a place's native and official names; its keys are the fold keys of those
names, which is what a lookup matches on; its identifiers are the external
authority numbers Wikidata records, so a catalogue record can be linked
onward to VIAF, the GND, ISNI or GeoNames.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import tetrak_translit

#: The kinds of entity a snapshot holds. "agent" in the command line means
#: the first two together, as Europeana's data model groups them.
KINDS = ("person", "organisation", "place")

#: Where a name comes from in Wikidata.
NAME_KINDS = ("label", "alias", "native", "official")

#: The languages whose label is preferred as the established form, in order.
#: The snapshot's script decides the first two; English is the fallback a
#: cataloguer is most likely to recognise; after that, any label at all.
PREFERRED_LANGUAGES = ("hy", "hyw", "en")


@dataclass(frozen=True)
class Name:
    """One name of an entity, as Wikidata records it.

    Attributes:
        text: The name.
        language: Its language code (``hy``, ``hyw``, ``en``, ``ru`` …).
        kind: ``label``, ``alias``, ``native`` (property P1559) or
            ``official`` (P1448).
    """

    text: str
    language: str
    kind: str


def key_of(text: str, script: str = "hy") -> str:
    """The fold key a lookup matches on: the folded words, sorted.

    Sorting makes *Tumanyan, Hovhannes* and *Hovhannes Tumanyan* one key,
    since catalogues invert names and Wikidata does not. A name in a
    script the fold does not handle (Cyrillic, Chinese) folds to nothing
    and gets no key; it is still kept as a name to index.

    Args:
        text: A name in any script or romanisation.
        script: The tetrak-translit script whose fold rules apply to
            Latin text.
    """
    return " ".join(sorted(tetrak_translit.fold(text, script=script).split()))


@dataclass
class Entity:
    """One authority record.

    Attributes:
        id: The Wikidata item id, ``Q380797``.
        kind: ``person``, ``organisation`` or ``place``.
        label: The established form: the label in the first preferred
            language the item has.
        names: Every name, labels first.
        keys: The distinct fold keys of the names, sorted.
        classes: The item's ``instance of`` (P31) values, as ids.
        identifiers: External authority identifiers by name: ``viaf``,
            ``gnd``, ``isni``, ``lcnaf``, ``geonames``; only those present.
        born: Year of birth as Wikidata gives it (``1869``; ``-500`` for
            500 BC), or ``None``.
        died: Year of death, the same way.
        coordinates: ``(latitude, longitude)`` for a place, or ``None``.
        description: The English description, or ``None``.
    """

    id: str
    kind: str
    label: str
    names: tuple[Name, ...]
    keys: tuple[str, ...]
    classes: tuple[str, ...] = ()
    identifiers: dict[str, str] | None = None
    born: str | None = None
    died: str | None = None
    coordinates: tuple[float, float] | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if self.identifiers is None:
            self.identifiers = {}

    @classmethod
    def build(
        cls,
        id: str,
        kind: str,
        names: Iterable[Name],
        *,
        script: str = "hy",
        classes: Iterable[str] = (),
        identifiers: dict[str, str] | None = None,
        born: str | None = None,
        died: str | None = None,
        coordinates: tuple[float, float] | None = None,
        description: str | None = None,
        preferred: tuple[str, ...] = PREFERRED_LANGUAGES,
    ) -> Entity:
        """Assemble a record, choosing the label and folding the keys."""
        ordered = tuple(
            sorted(set(names), key=lambda n: (NAME_KINDS.index(n.kind), n.language, n.text))
        )
        keys = sorted({key for key in (key_of(n.text, script) for n in ordered) if key})
        return cls(
            id=id,
            kind=kind,
            label=established_form(ordered, preferred),
            names=ordered,
            keys=tuple(keys),
            classes=tuple(classes),
            identifiers=dict(identifiers or {}),
            born=born,
            died=died,
            coordinates=coordinates,
            description=description,
        )

    def to_json(self) -> dict[str, Any]:
        """The record as a JSON-ready dict (one line of ``entities.jsonl``)."""
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "names": [[n.text, n.language, n.kind] for n in self.names],
            "keys": list(self.keys),
            "classes": list(self.classes),
            "identifiers": self.identifiers,
            "born": self.born,
            "died": self.died,
            "coordinates": list(self.coordinates) if self.coordinates else None,
            "description": self.description,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Entity:
        """The inverse of :meth:`to_json`."""
        coordinates = data.get("coordinates")
        return cls(
            id=data["id"],
            kind=data["kind"],
            label=data["label"],
            names=tuple(Name(*n) for n in data["names"]),
            keys=tuple(data["keys"]),
            classes=tuple(data.get("classes", ())),
            identifiers=dict(data.get("identifiers") or {}),
            born=data.get("born"),
            died=data.get("died"),
            coordinates=(float(coordinates[0]), float(coordinates[1])) if coordinates else None,
            description=data.get("description"),
        )

    def line(self) -> str:
        """The record as one line of JSON, for ``entities.jsonl``."""
        return json.dumps(self.to_json(), ensure_ascii=False)


def established_form(
    names: Iterable[Name], preferred: tuple[str, ...] = PREFERRED_LANGUAGES
) -> str:
    """The label in the first preferred language present, else any label, else any name."""
    labels = {n.language: n.text for n in names if n.kind == "label"}
    for language in preferred:
        if language in labels:
            return labels[language]
    if labels:
        return labels[min(labels)]
    for name in names:
        return name.text
    return ""


__all__ = [
    "KINDS",
    "NAME_KINDS",
    "PREFERRED_LANGUAGES",
    "Entity",
    "Name",
    "established_form",
    "key_of",
]
