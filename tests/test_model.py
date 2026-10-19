"""The record, its keys and its JSON form."""

from __future__ import annotations

import json

from tetrak_authority import Entity, Name, key_of
from tetrak_authority.model import established_form
from tetrak_authority.snapshot import point, year


class TestKeys:
    def test_a_key_is_the_folded_words_sorted(self) -> None:
        assert key_of("Tumanyan, Hovhannes") == "ovanes tumanian"
        assert key_of("Hovhannes Tumanyan") == "ovanes tumanian"
        assert key_of("Թումանեան Յովհաննէս") == "ovanes tumanian"

    def test_a_script_the_fold_does_not_handle_gets_no_key(self) -> None:
        assert key_of("Ованес Туманян") == ""
        assert key_of("") == ""

    def test_the_script_governs_latin_text(self) -> None:
        assert key_of("Batumi", script="hy") != key_of("Batumi", script="ka")


class TestEntity:
    names = [
        Name("Hovhannes Tumanyan", "en", "label"),
        Name("Հովհաննես Թումանյան", "hy", "label"),
        Name("Ованес Туманян", "ru", "label"),
        Name("Hovhannes Toumanian", "fr", "alias"),
    ]

    def test_build_chooses_the_label_and_folds_the_keys(self) -> None:
        entity = Entity.build("Q1", "person", self.names, born="1869", died="1923")
        assert entity.label == "Հովհաննես Թումանյան"
        assert entity.keys == ("ovanes tumanian",)  # the Russian label has no key
        assert entity.names[0].kind == "label" and entity.names[-1].kind == "alias"
        assert entity.identifiers == {}

    def test_the_label_falls_back_through_the_preferred_languages(self) -> None:
        assert (
            established_form([Name("Heine", "de", "label"), Name("Heine", "en", "label")])
            == "Heine"
        )
        assert established_form([Name("Only", "zz", "alias")]) == "Only"
        assert established_form([]) == ""
        assert established_form([Name("b", "fr", "label"), Name("a", "de", "label")]) == "a"

    def test_every_name_carries_its_key(self) -> None:
        entity = Entity.build("Q1", "person", self.names)
        assert {n.text: n.key for n in entity.names} == {
            "Hovhannes Tumanyan": "ovanes tumanian",
            "Հովհաննես Թումանյան": "ovanes tumanian",
            "Hovhannes Toumanian": "ovanes tumanian",
            "Ованес Туманян": "",
        }
        assert Name("Erevan", "en", "label").keyed().key == "erevan"

    def test_a_record_can_be_rekeyed(self) -> None:
        stale = Entity(
            "Q1", "person", "x", (Name("Hovhannes Tumanyan", "en", "label", "old"),), ("old",)
        )
        fresh = stale.rekeyed()
        assert fresh.names[0].key == "ovanes tumanian" and fresh.keys == ("ovanes tumanian",)
        assert fresh.label == "x" and fresh.id == "Q1"

    def test_json_round_trips(self) -> None:
        entity = Entity.build(
            "Q1953",
            "place",
            self.names,
            classes=["Q515"],
            identifiers={"geonames": "616051"},
            coordinates=(40.18, 44.51),
            description="capital",
        )
        line = entity.line()
        again = Entity.from_json(json.loads(line))
        assert again == entity
        assert again.coordinates == (40.18, 44.51)

    def test_from_json_tolerates_missing_optional_fields(self) -> None:
        entity = Entity.from_json(
            {
                "id": "Q1",
                "kind": "person",
                "label": "x",
                "names": [["x", "en", "label"]],
                "keys": ["kh"],
            }
        )
        assert entity.identifiers == {} and entity.classes == () and entity.coordinates is None
        assert entity.names[0].key == ""  # a line written before keys were stored


class TestFactParsing:
    def test_years(self) -> None:
        assert year("1869-02-19T00:00:00Z") == "1869"
        assert year("-0500-01-01T00:00:00Z") == "-500"
        assert year("+0951-00-00T00:00:00Z") == "951"
        assert year("not a date") is None

    def test_points(self) -> None:
        assert point("Point(44.514445 40.181389)") == (40.181389, 44.514445)
        assert point("POINT(44.5 40.1)") == (40.1, 44.5)
        assert point("nowhere") is None
        assert point("Point(1 2 3)") is None
        assert point("Point(a b)") is None
