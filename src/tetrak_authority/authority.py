"""Look names up in a snapshot, by fold key, offline.

:class:`Authority` opens a snapshot's SQLite index (see
:mod:`tetrak_authority.index`) and matches a name on the fold keys of
every name in it. A lookup folds what it is given the same way, so
*Tumanyan, Hovhannes*, *Թումանեան Յովհաննէս* and *Toumanian Hovannes* all
reach the same record. Nothing here touches the network, and nothing is
read until a lookup asks for it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .index import INDEX_FILE, build_index, read_entities
from .model import Entity, Name, key_of


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
    """A snapshot open for lookups.

    Args:
        connection: The snapshot's index, open.
        script: The tetrak-translit script that keys the names; must be
            the one the snapshot was built with.
        manifest: The snapshot's ``snapshot.json``, if there is one.

    Build one with :meth:`load` for a snapshot on disk, or
    :meth:`from_entities` for records in memory.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        script: str = "hy",
        manifest: dict[str, Any] | None = None,
    ) -> None:
        self._db = connection
        self.script = script
        self.manifest = manifest or {}

    @classmethod
    def load(cls, path: Path | str) -> Authority:
        """Open a snapshot directory (``snapshot.json`` beside ``entities.jsonl``) or a ``.jsonl`` file alone.

        The index beside the entities file is opened when it is there and
        at least as new as the file, and built there otherwise, which
        takes a few minutes for a full snapshot and happens once. If the
        directory cannot be written to, the index is built in memory.
        """
        path = Path(path)
        manifest: dict[str, Any] = {}
        if path.is_dir():
            manifest_file = path / "snapshot.json"
            if manifest_file.exists():
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            path = path / "entities.jsonl"
        if not path.exists():
            raise FileNotFoundError(str(path))
        script = str(manifest.get("scope", {}).get("script", "hy"))
        index = path.parent / INDEX_FILE
        if index.exists() and index.stat().st_mtime >= path.stat().st_mtime:
            return cls(sqlite3.connect(f"file:{index}?mode=ro", uri=True), script, manifest)
        try:
            connection = build_index(read_entities(path), index, script)
        except sqlite3.OperationalError:
            connection = build_index(read_entities(path), ":memory:", script)
        return cls(connection, script, manifest)

    @classmethod
    def from_entities(cls, entities: Iterable[Entity], script: str = "hy") -> Authority:
        """An authority over records in memory, indexed there."""
        return cls(build_index(entities, ":memory:", script), script)

    def __len__(self) -> int:
        row = self._db.execute("SELECT COUNT(*) FROM entity").fetchone()
        return int(row[0])

    def __iter__(self) -> Iterator[Entity]:
        for (record,) in self._db.execute("SELECT record FROM entity ORDER BY rowid"):
            yield Entity.from_json(json.loads(record))

    def get(self, id: str) -> Entity | None:
        """The record with this Wikidata id, or ``None``."""
        row = self._db.execute("SELECT record FROM entity WHERE id = ?", (id,)).fetchone()
        return Entity.from_json(json.loads(row[0])) if row else None

    def by_key(self, key: str) -> list[Entity]:
        """The entities one of whose names folds to exactly this key."""
        return [entity for entity, _ in self._exact(key, None)]

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
        wanted = tuple(kinds) if kinds is not None else None
        key = key_of(text, self.script)
        if not key:
            return []
        matches = [Match(entity, name, exact=True) for entity, name in self._exact(key, wanted)]
        seen = {match.entity.id for match in matches}
        words = key.split()
        if len(words) >= 2:
            for id in self._with_all_words(words, wanted):
                if id in seen:
                    continue
                entity = self.get(id)
                if entity is None:  # pragma: no cover - the index and the records agree
                    continue
                for name in entity.names:
                    name_words = set((name.key or key_of(name.text, self.script)).split())
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

    def _exact(self, key: str, kinds: tuple[str, ...] | None) -> list[tuple[Entity, Name]]:
        """Entities with a name of this key, each once, with the best-ranked such name."""
        query = (
            "SELECT e.id, e.record, n.pos FROM name n JOIN entity e ON e.id = n.entity"
            " WHERE n.key = ?"
        )
        params: list[Any] = [key]
        if kinds is not None:
            query += f" AND e.kind IN ({','.join('?' * len(kinds))})"
            params.extend(kinds)
        query += " ORDER BY n.rank, n.pos"
        found: dict[str, tuple[Entity, Name]] = {}
        for id, record, pos in self._db.execute(query, params):
            if id not in found:
                entity = Entity.from_json(json.loads(record))
                found[id] = (entity, entity.names[pos])
        return sorted(found.values(), key=lambda pair: _item_order(pair[0].id))

    def _with_all_words(self, words: list[str], kinds: tuple[str, ...] | None) -> list[str]:
        """Ids of entities one of whose keys holds every one of these words."""
        query = " INTERSECT ".join("SELECT entity FROM word WHERE word = ?" for _ in words)
        params: list[Any] = list(words)
        if kinds is not None:
            query = (
                f"SELECT id FROM entity WHERE id IN ({query})"
                f" AND kind IN ({','.join('?' * len(kinds))})"
            )
            params.extend(kinds)
        return sorted((row[0] for row in self._db.execute(query, params)), key=_item_order)


def _item_order(id: str) -> tuple[int, str]:
    return (int(id[1:]), id) if id[1:].isdigit() else (0, id)


__all__ = ["Authority", "Match"]
