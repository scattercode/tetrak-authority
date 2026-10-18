"""The client: result parsing, pacing, retries, and the error an endpoint returns."""

from __future__ import annotations

import io
import json
import time
import urllib.error
from email.message import Message

import pytest

from tetrak_authority import Client
from tetrak_authority.wikidata import QLEVER, Cell, RequestFailed, user_agent


def http_error(
    code: int, body: bytes = b"", headers: dict[str, str] | None = None
) -> urllib.error.HTTPError:
    message = Message()
    for name, value in (headers or {}).items():
        message[name] = value
    return urllib.error.HTTPError("http://x", code, "err", message, io.BytesIO(body))


def sparql(rows: list[dict[str, dict[str, str]]]) -> bytes:
    return json.dumps({"head": {"vars": []}, "results": {"bindings": rows}}).encode()


class TestSelect:
    def test_rows_carry_values_and_languages(self) -> None:
        body = sparql(
            [
                {
                    "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q1953"},
                    "name": {"type": "literal", "value": "Երևան", "xml:lang": "hy"},
                }
            ]
        )
        seen: list[tuple[str, dict[str, str]]] = []

        def transport(url: str, headers: dict[str, str]) -> bytes:
            seen.append((url, headers))
            return body

        client = Client("http://endpoint", user_agent="ua", pause=0.0, transport=transport)
        rows = client.select("SELECT ?item ?name WHERE {}")
        assert rows == [
            {"item": Cell("http://www.wikidata.org/entity/Q1953"), "name": Cell("Երևան", "hy")}
        ]
        assert rows[0]["item"].id == "Q1953" and rows[0]["name"].id == "Երևան"
        url, headers = seen[0]
        assert url.startswith("http://endpoint?query=PREFIX+wd") and "format=json" in url
        assert headers["User-Agent"] == "ua" and headers["Accept"].startswith(
            "application/sparql-results"
        )
        assert client.requests == 1

    def test_requests_are_paced(self) -> None:
        client = Client(QLEVER, pause=0.05, transport=lambda url, headers: sparql([]))
        started = time.monotonic()
        client.select("a")
        client.select("b")
        client.select("c")
        assert time.monotonic() - started >= 0.1
        assert client.requests == 3


class TestRetries:
    def test_a_429_is_retried_with_backoff_and_retry_after(self) -> None:
        attempts: list[float] = []

        def transport(url: str, headers: dict[str, str]) -> bytes:
            attempts.append(time.monotonic())
            if len(attempts) < 3:
                raise http_error(429, headers={"Retry-After": "0"})
            return sparql([])

        client = Client(QLEVER, pause=0.0, transport=transport)
        assert client.select("x") == []
        assert len(attempts) == 3 and client.requests == 3

    def test_a_server_error_is_retried_then_given_up(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> bytes:
            raise http_error(503)

        client = Client(QLEVER, pause=0.0, retries=1, max_delay=0.01, transport=transport)
        with pytest.raises(RequestFailed, match="503"):
            client.select("x")
        assert client.requests == 2

    def test_a_client_error_is_not_retried(self) -> None:
        calls = 0

        def transport(url: str, headers: dict[str, str]) -> bytes:
            nonlocal calls
            calls += 1
            raise http_error(400)

        with pytest.raises(RequestFailed, match="400"):
            Client(QLEVER, pause=0.0, transport=transport).select("x")
        assert calls == 1

    def test_an_endpoints_query_error_is_reported_and_not_retried(self) -> None:
        calls = 0

        def transport(url: str, headers: dict[str, str]) -> bytes:
            nonlocal calls
            calls += 1
            raise http_error(429, json.dumps({"exception": "Operation timed out"}).encode())

        with pytest.raises(RequestFailed, match="Operation timed out"):
            Client(QLEVER, pause=0.0, transport=transport).select("x")
        assert calls == 1

    def test_a_network_error_is_retried(self) -> None:
        calls = 0

        def transport(url: str, headers: dict[str, str]) -> bytes:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise urllib.error.URLError("reset")
            return sparql([])

        client = Client(QLEVER, pause=0.0, max_delay=0.01, transport=transport)
        assert client.select("x") == [] and calls == 2

        def always(url: str, headers: dict[str, str]) -> bytes:
            raise TimeoutError("slow")

        with pytest.raises(RequestFailed, match="slow"):
            Client(QLEVER, pause=0.0, retries=0, transport=always).select("x")


class TestSearch:
    def test_search_asks_the_api_and_returns_its_hits(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> bytes:
            assert (
                url.startswith("https://www.wikidata.org/w/api.php?") and "wbsearchentities" in url
            )
            assert "language=hy" in url and "limit=2" in url
            return json.dumps({"search": [{"id": "Q969758", "label": "Gregory of Narek"}]}).encode()

        hits = Client(pause=0.0, transport=transport).search("Նարեկացի", limit=2)
        assert hits == [{"id": "Q969758", "label": "Gregory of Narek"}]


def test_the_user_agent_names_the_package_its_version_and_a_contact() -> None:
    assert user_agent("1.2.0", "you@example.org") == "tetrak-authority/1.2.0 (you@example.org)"
    assert "github.com/scattercode/tetrak-authority" in user_agent("0")
