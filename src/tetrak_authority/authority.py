"""Look names up in a snapshot, by fold key, offline.

:class:`Authority` loads a snapshot and indexes every entity by the fold
keys of its names. A lookup folds what it is given the same way, so
*Tumanyan, Hovhannes*, *Թումանեան Յովհաննէս* and *Toumanian Hovannes*
all reach the same record. Nothing here touches the network.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import NAME_KINDS, PREFERRED_LANGUAGES, Entity, Name, key_of


@dataclass(frozen=True)
class Match:
    """One entity a lookup matched, and how.

    Attributes:
        entity: The record.
        name: The name whose key matched.
        exact: Whether the whole key matched (the same words, in any
            order), as against every word of the lookup appearing in a
            longer name (*Heinrich Heine* in *Christian Johann Heinrich
            Heine*).
    """

    entity: Entity
    name: Name
    exact: bool


class Authority:
    """A snapshot loaded for lookups.

    Args:
        entities: The records.
        script: The tetrak-translit script that keys the names; must be
            the one the snapshot was built with.
        manifest: The snapshot's ``snapshot.json``, if there is one.
    """

    def __init__(
        self, entities: Iterable[Entity], script: str = "hy", manifest: dict[str, Any] | None = None
    ) -> None:
        self.script = script
        self.manifest = manifest or {}
        self._entities: dict[str, Entity] = {}
        self._by_key: dict[str, list[tuple[Entity, Name]]] = {}
        self._by_word: dict[str, set[str]] = {}
        for entity in entities:
            self._entities[entity.id] = entity
            # Index the preferred languages' names first, so that a match
            # reports the form a cataloguer recognises rather than the first
            # language alphabetically.
            for name in sorted(entity.names, key=_preference):
                key = key_of(name.text, script)
                if not key:
                    continue
                self._by_key.setdefault(key, []).append((entity, name))
                for word in key.split():
                    self._by_word.setdefault(word, set()).add(entity.id)

    @classmethod
    def load(cls, path: Path | str) -> Authority:
        """Load a snapshot directory (``snapshot.json`` beside ``entities.jsonl``) or a ``.jsonl`` file."""
        path = Path(path)
        manifest: dict[str, Any] = {}
        if path.is_dir():
            manifest_file = path / "snapshot.json"
            if manifest_file.exists():
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            path = path / "entities.jsonl"
        script = str(manifest.get("scope", {}).get("script", "hy"))
        with path.open(encoding="utf-8") as lines:
            entities = [Entity.from_json(json.loads(line)) for line in lines if line.strip()]
        return cls(entities, script=script, manifest=manifest)

    def __len__(self) -> int:
        return len(self._entities)

    def __iter__(self) -> Iterator[Entity]:
        return iter(self._entities.values())

    def get(self, id: str) -> Entity | None:
        """The record with this Wikidata id, or ``None``."""
        return self._entities.get(id)

    def by_key(self, key: str) -> list[Entity]:
        """The entities one of whose names folds to exactly this key."""
        seen: dict[str, Entity] = {}
        for entity, _ in self._by_key.get(key, ()):
            seen.setdefault(entity.id, entity)
        return list(seen.values())

    def match(self, text: str, kinds: Iterable[str] | None = None) -> list[Match]:
        """The entities a name reaches, exact matches first.

        An exact match shares the whole key: the same folded words in any
        order, so a catalogue's inverted form matches Wikidata's. Failing
        that, a lookup of two or more words matches a name that contains
        all of them. One word alone never matches partially: *Hovhannes*
        would reach every Hovhannes there is.

        Args:
            text: The name as a catalogue or a reader wrote it.
            kinds: Restrict to ``person``, ``organisation`` or ``place``.
        """
        wanted = set(kinds) if kinds is not None else None
        key = key_of(text, self.script)
        if not key:
            return []
        matches: list[Match] = []
        seen: set[str] = set()
        for entity, name in self._by_key.get(key, ()):
            if entity.id not in seen and (wanted is None or entity.kind in wanted):
                seen.add(entity.id)
                matches.append(Match(entity, name, exact=True))
        words = key.split()
        if len(words) >= 2:
            candidates: set[str] | None = None
            for word in words:
                ids = self._by_word.get(word, set())
                candidates = ids if candidates is None else candidates & ids
            for id in sorted(candidates or (), key=_item_order):
                entity = self._entities[id]
                if id in seen or (wanted is not None and entity.kind not in wanted):
                    continue
                for name in entity.names:
                    name_words = set(key_of(name.text, self.script).split())
                    if name_words >= set(words):
                        seen.add(id)
                        matches.append(Match(entity, name, exact=False))
                        break
        return matches

    def names_for(
        self, text: str, kinds: Iterable[str] | None = None, exact_only: bool = True
    ) -> list[str]:
        """Every distinct name of the entities a lookup reaches: what an indexer adds as alternative names."""
        names: dict[str, None] = {}
        for match in self.match(text, kinds):
            if exact_only and not match.exact:
                continue
            for name in match.entity.names:
                names.setdefault(name.text, None)
        return list(names)


def _preference(name: Name) -> tuple[int, int, str]:
    rank = (
        PREFERRED_LANGUAGES.index(name.language)
        if name.language in PREFERRED_LANGUAGES
        else len(PREFERRED_LANGUAGES)
    )
    return (
        rank,
        NAME_KINDS.index(name.kind) if name.kind in NAME_KINDS else len(NAME_KINDS),
        name.language,
    )


def _item_order(id: str) -> tuple[int, str]:
    return (int(id[1:]), id) if id[1:].isdigit() else (0, id)


__all__ = ["Authority", "Match"]
