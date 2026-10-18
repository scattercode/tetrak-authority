"""The scope's queries, the fetch, and a trial build, over recorded responses."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import TRIAL, Replay

from tetrak_authority import ARMENIAN, HISTORIC_ARMENIA, Box, Client, Scope
from tetrak_authority.snapshot import (
    FACT_PROPERTIES,
    batches,
    build,
    count,
    facts_query,
    fetch,
    names_query,
)


class TestScope:
    def test_the_default_scope_is_armenian(self) -> None:
        assert ARMENIAN.script == "hy" and ARMENIAN.languages == ("hy", "hyw")
        assert ARMENIAN.box == HISTORIC_ARMENIA
        assert (
            HISTORIC_ARMENIA.west < HISTORIC_ARMENIA.east
            and HISTORIC_ARMENIA.south < HISTORIC_ARMENIA.north
        )

    def test_each_kind_has_a_query_with_the_language_filter_inside_each_branch(self) -> None:
        queries = ARMENIAN.queries()
        assert set(queries) == {"person", "organisation", "place"}
        for query in queries.values():
            assert query.startswith("SELECT DISTINCT ?item WHERE")
            assert query.count('FILTER(LANG(?l) IN ("hy", "hyw"))') == 2
        assert "wdt:P31 wd:Q5" in queries["person"]
        assert "wdt:P172" in queries["person"] and "wd:Q79797" in queries["person"]
        assert "wdt:P27" in queries["person"] and "wd:Q399" in queries["person"]
        assert "wd:Q43229" in queries["organisation"]
        assert (
            "geof:longitude(?loc) >= 26.0" in queries["place"]
            and "geof:latitude(?loc) <= 43.6" in queries["place"]
        )

    def test_counts_are_the_same_queries_counting(self) -> None:
        for kind, query in ARMENIAN.counts().items():
            assert query.startswith("SELECT (COUNT(DISTINCT ?item) AS ?n) WHERE")
            assert query.endswith(ARMENIAN.queries()[kind].removeprefix("SELECT DISTINCT ?item"))

    def test_a_scope_without_a_box_or_tags(self) -> None:
        scope = Scope(languages=("ka",), ethnicities=(), citizenships=(), box=None)
        queries = scope.queries()
        assert "geof:" not in queries["place"] and "?item wdt:P625 ?loc" in queries["place"]
        assert "wdt:P172" not in queries["person"] and "wdt:P27" not in queries["person"]
        assert 'IN ("ka")' in queries["person"]

    def test_a_box_filter(self) -> None:
        box = Box(west=43.0, south=38.8, east=46.7, north=41.4)
        assert box.filter("?p") == (
            "FILTER(geof:longitude(?p) >= 43.0 && geof:longitude(?p) <= 46.7"
            " && geof:latitude(?p) >= 38.8 && geof:latitude(?p) <= 41.4)"
        )


class TestQueries:
    def test_names_query_asks_for_labels_and_aliases_of_the_batch(self) -> None:
        query = names_query(["Q1", "Q2"])
        assert "VALUES ?item { wd:Q1 wd:Q2 }" in query
        assert "rdfs:label" in query and "skos:altLabel" in query

    def test_facts_query_asks_for_every_fact_property_and_the_description(self) -> None:
        query = facts_query(["Q1"])
        for prop in FACT_PROPERTIES:
            assert f"wdt:{prop}" in query
        assert "schema:description" in query and 'LANG(?value) = "en"' in query

    def test_batches(self) -> None:
        assert list(batches(["a", "b", "c"], 2)) == [["a", "b"], ["c"]]
        assert list(batches([], 2)) == []


class TestOverRecordings:
    def test_count_reads_one_number_per_kind(self, client: Client) -> None:
        counts = count(client, ARMENIAN)
        assert set(counts) == {"person", "organisation", "place"}
        assert (
            counts["person"] > 100_000
            and counts["place"] > 10_000
            and counts["organisation"] > 1_000
        )
        assert client.requests == 3

    def test_fetch_assembles_names_facts_and_keys(self, client: Client) -> None:
        poet, economist, monk = fetch(client, ["Q380797", "Q20513561", "Q969758"], "person")
        assert poet.id == "Q380797" and poet.kind == "person"
        assert poet.label == "Հովհաննես Թումանյան"
        assert poet.born == "1869" and poet.died == "1923"
        assert poet.identifiers["viaf"] == "84037592" and "gnd" in poet.identifiers
        assert "Q5" in poet.classes
        assert "ovanes tumanian" in poet.keys
        assert any(
            n.text == "Hovhannes Tumanyan" and n.language == "en" and n.kind == "label"
            for n in poet.names
        )
        assert poet.description and poet.description.startswith("Armenian writer")
        assert economist.label == poet.label and economist.born == "1904"
        assert monk.born == "951" and monk.died == "1003"
        assert client.requests == 2

    def test_fetch_keeps_a_places_official_name_and_coordinates(self, client: Client) -> None:
        yerevan, tbilisi, van = fetch(client, ["Q1953", "Q994", "Q83061"], "place")
        assert yerevan.coordinates == (40.181389, 44.514445)
        assert any(n.kind == "official" and n.text == "Երևան" for n in yerevan.names)
        assert yerevan.identifiers["geonames"] == "616051"
        assert "tiflis" in tbilisi.keys and "van" in van.keys

    def test_a_trial_build_writes_a_manifest_and_entities(
        self, client: Client, replay: Replay, tmp_path: Path
    ) -> None:
        lines: list[str] = []
        manifest = build(client, tmp_path / "trial", ARMENIAN, limit=2, log=lines.append)
        assert manifest["counts"] == {"person": 2, "organisation": 2, "place": 2}
        assert manifest["format"] == 1 and manifest["endpoint"] == client.endpoint
        assert manifest["scope"]["languages"] == ["hy", "hyw"] and manifest["limit"] == 2
        assert set(manifest["queries"]) == {"person", "organisation", "place"}
        assert manifest["requests"] == client.requests == 9
        assert manifest["fold"].startswith("tetrak-translit ")
        assert manifest["date"] and manifest["seconds"] >= 0
        written = json.loads((tmp_path / "trial" / "snapshot.json").read_text(encoding="utf-8"))
        assert written["counts"] == manifest["counts"]
        entities = [
            json.loads(line)
            for line in (tmp_path / "trial" / "entities.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        committed = [
            json.loads(line)
            for line in (TRIAL / "entities.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert [e["id"] for e in entities] == [e["id"] for e in committed]
        assert entities == committed
        assert all(
            "+LIMIT+2" in url
            for url in replay.urls
            if "COUNT" not in url and "VALUES+%3Fitem" not in url
        )
        assert lines[0] == "person: 2 items to fetch" and lines[-1].startswith(
            "place: batch 1, 2 written"
        )

    def test_build_can_leave_kinds_out(self, client: Client, tmp_path: Path) -> None:
        manifest = build(client, tmp_path / "places", ARMENIAN, kinds=("place",), limit=2)
        assert manifest["counts"] == {"place": 2} and list(manifest["queries"]) == ["place"]
        assert client.requests == 3
