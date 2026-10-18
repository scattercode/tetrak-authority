"""The command line, over the fixture snapshot and the recordings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import SNAPSHOT, Replay

from tetrak_authority import cli
from tetrak_authority.wikidata import Client, RequestFailed


@pytest.fixture
def replayed(monkeypatch: pytest.MonkeyPatch, replay: Replay) -> Replay:
    """Make every client the command builds answer from the recordings."""

    def client_of(args: object, endpoint: str | None = None) -> Client:
        return Client(
            cli.QLEVER, user_agent="tetrak-authority/0 (test)", pause=0.0, transport=replay
        )

    monkeypatch.setattr(cli, "client_of", client_of)
    return replay


class TestLookup:
    def test_prints_what_each_name_reaches(self, capsys: pytest.CaptureFixture[str]) -> None:
        status = cli.main(["lookup", "--snapshot", str(SNAPSHOT), "Tumanyan, Hovhannes", "Tiflis"])
        out = capsys.readouterr().out
        assert status == 0
        assert "Q380797      exact    Հովհաննես Թումանյան (1869–1923)  [person]" in out
        assert "viaf 84037592" in out and "Q20513561" in out
        assert "Q994         exact    Թբիլիսի  [place]" in out
        assert "300 names, matched on 'Թիֆլիս' (hy)" in out

    def test_a_name_that_reaches_nothing_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli.main(["lookup", "--snapshot", str(SNAPSHOT), "Nobody At All"]) == 1
        assert "nothing" in capsys.readouterr().out

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert (
            cli.main(
                [
                    "lookup",
                    "--snapshot",
                    str(SNAPSHOT),
                    "--json",
                    "Gregory of Narek",
                    "--kinds",
                    "agent",
                ]
            )
            == 0
        )
        report = json.loads(capsys.readouterr().out)
        assert report[0]["query"] == "Gregory of Narek"
        match = report[0]["matches"][0]
        assert match["id"] == "Q969758" and match["exact"] and match["kind"] == "person"
        assert "Gregory of Narek" in match["names"] and match["identifiers"]["viaf"]

    def test_kinds_expand_agent(self) -> None:
        assert cli.kinds_of(["agent", "place"]) == ["person", "organisation", "place"]
        assert cli.kinds_of(None) is None

    def test_a_partial_match_is_marked(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli.main(["lookup", "--snapshot", str(SNAPSHOT), "Tadevosi Tumanyan"]) == 0
        assert "partial" in capsys.readouterr().out


class TestShow:
    def test_prints_the_record(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli.main(["show", "--snapshot", str(SNAPSHOT), "Q83061"]) == 0
        record = json.loads(capsys.readouterr().out)
        assert record["label"] == "Վան" and record["coordinates"] == [38.501944, 43.416667]

    def test_an_unknown_id_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli.main(["show", "--snapshot", str(SNAPSHOT), "Q0"]) == 1
        assert "not in the snapshot" in capsys.readouterr().err

    def test_a_missing_snapshot_exits_2(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        assert cli.main(["show", "--snapshot", str(tmp_path / "none"), "Q1"]) == 2
        assert "not found" in capsys.readouterr().err


class TestCount:
    def test_prints_a_number_per_kind(
        self, replayed: Replay, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli.main(["count"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("person") and "organisation" in out and "place" in out
        assert len(replayed.urls) == 3


class TestSnapshot:
    def test_a_trial_run_writes_the_snapshot_and_prints_the_manifest(
        self, replayed: Replay, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        assert cli.main(["snapshot", "--out", str(tmp_path / "s"), "--limit", "2"]) == 0
        captured = capsys.readouterr()
        manifest = json.loads(captured.out)
        assert manifest["counts"] == {"person": 2, "organisation": 2, "place": 2}
        assert (tmp_path / "s" / "entities.jsonl").exists()
        assert "person: 2 items to fetch" in captured.err

    def test_scope_arguments(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "count",
                "--box",
                "43",
                "38.8",
                "46.7",
                "41.4",
                "--languages",
                "hy",
                "--kinds",
                "place",
            ]
        )
        scope = cli.scope_of(args)
        assert scope.box is not None and scope.box.west == 43.0 and scope.languages == ("hy",)
        assert cli.scope_of(parser.parse_args(["count", "--no-box"])).box is None
        assert cli.scope_of(parser.parse_args(["count"])).box == cli.ARMENIAN.box

    def test_the_client_carries_the_contact(self) -> None:
        args = cli.build_parser().parse_args(
            ["count", "--contact", "me@example.org", "--pause", "2"]
        )
        client = cli.client_of(args)
        assert client.user_agent.endswith("(me@example.org)") and client.pause == 2.0


class TestSearch:
    def test_prints_the_hits(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def transport(url: str, headers: dict[str, str]) -> bytes:
            return json.dumps(
                {
                    "search": [
                        {
                            "id": "Q969758",
                            "label": "Gregory of Narek",
                            "description": "Armenian monk",
                        }
                    ]
                }
            ).encode()

        monkeypatch.setattr(cli, "client_of", lambda args: Client(pause=0.0, transport=transport))
        assert cli.main(["search", "Նարեկացի"]) == 0
        assert "Q969758      Gregory of Narek  Armenian monk" in capsys.readouterr().out

    def test_no_hits_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cli,
            "client_of",
            lambda args: Client(pause=0.0, transport=lambda u, h: b'{"search": []}'),
        )
        assert cli.main(["search", "zzz"]) == 1

    def test_a_failed_request_exits_2(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def failing(url: str, headers: dict[str, str]) -> bytes:
            raise RequestFailed("boom")

        monkeypatch.setattr(cli, "client_of", lambda args: Client(pause=0.0, transport=failing))
        assert cli.main(["search", "x"]) == 2
        assert "request failed: boom" in capsys.readouterr().err


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.startswith("tetrak-authority ")
