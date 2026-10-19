"""Lookups against the six-entity fixture snapshot."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest
from conftest import SNAPSHOT

from tetrak_authority import Authority, Entity, Name


class TestLoading:
    def test_a_directory_loads_its_manifest_and_entities(self, authority: Authority) -> None:
        assert len(authority) == 6
        assert authority.script == "hy"
        assert authority.manifest["counts"] == {"person": 3, "place": 3}
        assert {e.kind for e in authority} == {"person", "place"}
        assert authority.get("Q1953") is not None and authority.get("Q0") is None

    def test_a_jsonl_file_loads_alone(self) -> None:
        authority = Authority.load(SNAPSHOT / "entities.jsonl")
        assert len(authority) == 6 and authority.manifest == {}

    def test_the_index_is_built_once_and_reopened_read_only(self, tmp_path: Path) -> None:
        shutil.copytree(SNAPSHOT, tmp_path / "s", ignore=shutil.ignore_patterns("*.sqlite"))
        index = tmp_path / "s" / "authority.sqlite"
        assert not index.exists()
        first = Authority.load(tmp_path / "s")
        assert index.exists() and len(first) == 6
        stamp = index.stat().st_mtime
        second = Authority.load(tmp_path / "s")
        assert index.stat().st_mtime == stamp and len(second) == 6
        with pytest.raises(sqlite3.OperationalError):
            second._db.execute("DELETE FROM entity")
        # An entities file newer than the index means a rebuild.
        inode = index.stat().st_ino
        os.utime(tmp_path / "s" / "entities.jsonl", (stamp + 10, stamp + 10))
        Authority.load(tmp_path / "s")
        assert index.stat().st_ino != inode and index.stat().st_mtime > stamp

    def test_a_directory_that_cannot_be_written_indexes_in_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shutil.copytree(SNAPSHOT, tmp_path / "s", ignore=shutil.ignore_patterns("*.sqlite"))
        real = sqlite3.connect

        def refuse(target: str, *args: object, **kwargs: object) -> sqlite3.Connection:
            if target.endswith("authority.sqlite"):
                raise sqlite3.OperationalError("unable to open database file")
            return real(target, *args, **kwargs)

        monkeypatch.setattr("tetrak_authority.index.sqlite3.connect", refuse)
        authority = Authority.load(tmp_path / "s")
        assert len(authority) == 6 and not (tmp_path / "s" / "authority.sqlite").exists()

    def test_from_entities(self) -> None:
        authority = Authority.from_entities(
            [Entity.build("Q1", "place", [Name("Tiflis", "en", "label")])]
        )
        assert [m.entity.id for m in authority.match("Թիֆլիս")] == ["Q1"]
        assert [e.id for e in authority] == ["Q1"]

    def test_a_missing_snapshot_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            Authority.load(tmp_path / "none")

    def test_a_snapshot_written_before_keys_were_stored_still_matches(self, tmp_path: Path) -> None:
        old = Entity.build("Q1", "person", [Name("Hovhannes Tumanyan", "en", "label")]).to_json()
        old["names"] = [n[:3] for n in old["names"]]
        (tmp_path / "entities.jsonl").write_text(json.dumps(old, ensure_ascii=False) + "\n")
        authority = Authority.load(tmp_path)
        assert [m.entity.id for m in authority.match("Tumanyan, Hovhannes")] == ["Q1"]
        assert [m.entity.id for m in authority.match("Tumanyan Hovhannes Tadevosi")] == []

    def test_a_directory_without_a_manifest(self, tmp_path: Path) -> None:
        (tmp_path / "entities.jsonl").write_text(
            Entity.build("Q1", "person", [Name("X Y", "en", "label")]).line() + "\n"
        )
        authority = Authority.load(tmp_path)
        assert len(authority) == 1 and authority.script == "hy"


class TestMatching:
    def test_every_spelling_and_order_reaches_the_record(self, authority: Authority) -> None:
        for typed in (
            "Tumanyan, Hovhannes",
            "Hovhannes Tumanyan",
            "Թումանեան Յովհաննէս",
            "Toumanian, Hovannes",
        ):
            matches = authority.match(typed)
            assert [m.entity.id for m in matches] == ["Q380797", "Q20513561"], typed
            assert all(m.exact for m in matches)

    def test_a_match_reports_the_name_in_a_preferred_language(self, authority: Authority) -> None:
        match = authority.match("Tumanyan, Hovhannes")[0]
        assert match.name.text == "Հովհաննես Թումանյան" and match.name.language == "hy"

    def test_namesakes_are_told_apart_by_what_the_record_carries(
        self, authority: Authority
    ) -> None:
        poet, economist = (m.entity for m in authority.match("Tumanyan, Hovhannes"))
        assert poet.born == "1869" and economist.born == "1904"
        assert poet.identifiers and not economist.identifiers

    def test_other_names_reach_the_same_record(self, authority: Authority) -> None:
        assert [m.entity.id for m in authority.match("Gregory of Narek")] == ["Q969758"]
        assert [m.entity.id for m in authority.match("Նարեկացի Գրիգոր")] == ["Q969758"]
        assert [m.entity.id for m in authority.match("Tiflis")] == ["Q994"]
        assert [m.entity.id for m in authority.match("Erivan")] == ["Q1953"]
        assert [m.entity.id for m in authority.match("Վան")] == ["Q83061"]

    def test_one_word_never_matches_partially(self, authority: Authority) -> None:
        assert authority.match("Hovhannes") == []
        assert authority.match("Tumanyan") == []

    def test_two_words_match_a_longer_name_that_contains_them(self, authority: Authority) -> None:
        # The poet's Armenian alias carries his patronymic: Թումանյան, Հովհաննես Թադևոսի.
        matches = authority.match("Tadevosi Tumanyan")
        assert [(m.entity.id, m.exact) for m in matches] == [("Q380797", False)]
        assert "Թադևոսի" in matches[0].name.text

    def test_a_word_not_in_any_name_blocks_a_partial_match(self, authority: Authority) -> None:
        assert authority.match("Hovhannes Tumanyan poet") == []

    def test_kinds_restrict(self, authority: Authority) -> None:
        assert authority.match("Van", kinds=("person",)) == []
        assert [m.entity.id for m in authority.match("Van", kinds=("place",))] == ["Q83061"]
        assert authority.match("Tadevosi Tumanyan", kinds=("place",)) == []

    def test_nothing_folds_to_nothing(self, authority: Authority) -> None:
        assert authority.match("") == [] and authority.match("Ованес") == []

    def test_by_key(self, authority: Authority) -> None:
        assert [e.id for e in authority.by_key("tiflis")] == ["Q994"]
        assert authority.by_key("nobody") == []


class TestNamesFor:
    def test_the_names_of_the_exact_matches_without_repeats(self, authority: Authority) -> None:
        names = authority.names_for("Gregory of Narek")
        assert "Գրիգոր Նարեկացի" in names and "Gregory of Narek" in names
        assert any(n.startswith("Григор") for n in names)
        assert len(names) == len(set(names))

    def test_partial_matches_are_left_out_unless_asked_for(self, authority: Authority) -> None:
        assert authority.names_for("Tadevosi Tumanyan") == []
        assert "Hovhannes Tumanyan" in authority.names_for("Tadevosi Tumanyan", exact_only=False)
