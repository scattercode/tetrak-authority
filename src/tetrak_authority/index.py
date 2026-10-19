"""The SQLite index a snapshot is looked up through.

A full snapshot is a third of a gigabyte of JSON holding millions of
names; parsing it into Python objects takes minutes and gigabytes, and a
lookup needs a few rows of it. So a snapshot carries ``authority.sqlite``
beside ``entities.jsonl``: every record as its JSON line, every name's
fold key with the record it belongs to, and every word of every key,
each indexed. Opening it costs nothing; a lookup reads the rows it
matches. The index is derived data, built by ``snapshot`` and ``rekey``
and rebuilt by :class:`~tetrak_authority.authority.Authority` when it is
missing or older than the entities file. The standard library's
``sqlite3`` is all it needs.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path

from .model import NAME_KINDS, PREFERRED_LANGUAGES, Entity

#: The name of the index file beside ``entities.jsonl``.
INDEX_FILE = "authority.sqlite"

SCHEMA = """
CREATE TABLE entity (id TEXT PRIMARY KEY, kind TEXT NOT NULL, record TEXT NOT NULL);
CREATE TABLE name (entity TEXT NOT NULL, pos INTEGER NOT NULL, rank INTEGER NOT NULL, key TEXT NOT NULL);
CREATE TABLE word (word TEXT NOT NULL, entity TEXT NOT NULL, PRIMARY KEY (word, entity)) WITHOUT ROWID;
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
INDEXES = """
CREATE INDEX name_key ON name (key, rank, pos);
CREATE INDEX entity_kind ON entity (kind);
"""


def preference(language: str, kind: str) -> int:
    """The order names are reported in: preferred languages first, labels before aliases."""
    rank = (
        PREFERRED_LANGUAGES.index(language)
        if language in PREFERRED_LANGUAGES
        else len(PREFERRED_LANGUAGES)
    )
    kind_rank = NAME_KINDS.index(kind) if kind in NAME_KINDS else len(NAME_KINDS)
    return rank * len(NAME_KINDS) + kind_rank


def build_index(
    entities: Iterable[Entity],
    target: Path | str,
    script: str = "hy",
    log: Callable[[str], None] | None = None,
) -> sqlite3.Connection:
    """Write the index for *entities* to *target* (a path, or ``:memory:``) and return it open.

    A name without a key (a script the fold does not handle) is kept in
    the record and left out of the name and word tables. Names written
    before keys were stored are keyed here.
    """
    say = log or (lambda line: None)
    if target != ":memory:":
        Path(target).unlink(missing_ok=True)
    connection = sqlite3.connect(str(target))
    connection.executescript(SCHEMA)
    count = 0
    names: list[tuple[str, int, int, str]] = []
    words: set[tuple[str, str]] = set()
    for entity in entities:
        connection.execute(
            "INSERT INTO entity VALUES (?, ?, ?)", (entity.id, entity.kind, entity.line())
        )
        for pos, name in enumerate(entity.names):
            key = (
                name.key
                if name.key
                else (name.keyed(script).key if name.kind in NAME_KINDS else "")
            )
            if not key:
                continue
            names.append((entity.id, pos, preference(name.language, name.kind), key))
            for word in key.split():
                words.add((word, entity.id))
        count += 1
        if count % 10000 == 0:
            connection.executemany("INSERT INTO name VALUES (?, ?, ?, ?)", names)
            connection.executemany("INSERT INTO word VALUES (?, ?)", sorted(words))
            names.clear()
            words.clear()
            say(f"{count} entities indexed")
    connection.executemany("INSERT INTO name VALUES (?, ?, ?, ?)", names)
    connection.executemany("INSERT INTO word VALUES (?, ?)", sorted(words))
    connection.executescript(INDEXES)
    connection.execute("INSERT INTO meta VALUES ('script', ?)", (script,))
    connection.execute("INSERT INTO meta VALUES ('entities', ?)", (str(count),))
    connection.commit()
    say(f"{count} entities indexed")
    return connection


def read_entities(path: Path) -> Iterable[Entity]:
    """The records in an ``entities.jsonl``, one at a time."""
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            if line.strip():
                yield Entity.from_json(json.loads(line))


__all__ = ["INDEX_FILE", "build_index", "preference", "read_entities"]
