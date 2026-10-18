"""Shared fixtures: a client that replays recorded responses, never the network."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tetrak_authority import Authority, Client
from tetrak_authority.wikidata import QLEVER

DATA = Path(__file__).resolve().parent / "data"
RECORDED = DATA / "recorded"
SNAPSHOT = DATA / "snapshot"
TRIAL = DATA / "trial"


def key_for(url: str) -> str:
    """The file name a recording of this request has; the same rule as tests/record.py."""
    return hashlib.sha1(url.encode()).hexdigest()[:16]


class Replay:
    """A transport that answers from ``tests/data/recorded/`` and refuses anything else."""

    def __init__(self) -> None:
        self.urls: list[str] = []
        self.index: dict[str, str] = json.loads(
            (RECORDED / "index.json").read_text(encoding="utf-8")
        )

    def __call__(self, url: str, headers: dict[str, str]) -> bytes:
        self.urls.append(url)
        name = key_for(url)
        recording = RECORDED / f"{name}.json"
        if not recording.exists():
            raise AssertionError(f"no recording for {url[:120]}; run tests/record.py")
        assert headers["User-Agent"].startswith("tetrak-authority/")
        return recording.read_bytes()


@pytest.fixture
def replay() -> Replay:
    return Replay()


@pytest.fixture
def client(replay: Replay) -> Client:
    """A client over the recordings, with no pause so the suite stays fast."""
    return Client(QLEVER, user_agent="tetrak-authority/0 (test)", pause=0.0, transport=replay)


@pytest.fixture(scope="session")
def authority() -> Authority:
    """The six-entity fixture snapshot."""
    return Authority.load(SNAPSHOT)
