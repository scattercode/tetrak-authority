"""Re-record the fixtures the tests replay.

The tests never touch the network: every response they need is a file
under ``tests/data/recorded/``, named by a hash of the request URL, and
``tests/data/snapshot/`` is a six-entity snapshot built from the same
responses. Run this from the repository root to refresh them, which
takes about twenty polite requests::

    .venv/bin/python tests/record.py

Then look at the diff: Wikidata moves, and a changed label or alias may
change what a test expects.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tetrak_authority import ARMENIAN, Client, __version__  # noqa: E402
from tetrak_authority.snapshot import build, count, fetch  # noqa: E402
from tetrak_authority.wikidata import QLEVER, user_agent  # noqa: E402

HERE = Path(__file__).resolve().parent
RECORDED = HERE / "data" / "recorded"
SNAPSHOT = HERE / "data" / "snapshot"

#: The entities the hand-written tests know: two Tumanyans (the poet and an
#: economist who shares his name), Gregory of Narek, Yerevan, Tbilisi, Van.
FIXTURE_IDS = ["Q380797", "Q20513561", "Q969758", "Q1953", "Q994", "Q83061"]
FIXTURE_KINDS = {
    "Q380797": "person",
    "Q20513561": "person",
    "Q969758": "person",
    "Q1953": "place",
    "Q994": "place",
    "Q83061": "place",
}


def key_for(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def main() -> None:
    RECORDED.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    index: dict[str, str] = {}
    live = Client(
        QLEVER,
        user_agent=user_agent(
            __version__ or "0", "https://github.com/scattercode/tetrak-authority"
        ),
    )
    real = live._transport

    def recording(url: str, headers: dict[str, str]) -> bytes:
        body = real(url, headers)
        name = key_for(url)
        (RECORDED / f"{name}.json").write_bytes(body)
        index[name] = url
        print(f"recorded {name} ({len(body)} bytes)", file=sys.stderr)
        return body

    client = Client(QLEVER, user_agent=live.user_agent, transport=recording)

    # The counts of the default scope, for the count command.
    counts = count(client, ARMENIAN)
    print("counts", counts, file=sys.stderr)

    # A trial build with two items per kind, for the build and snapshot tests.
    build(
        client,
        HERE / "data" / "trial",
        ARMENIAN,
        limit=2,
        log=lambda line: print(line, file=sys.stderr),
    )

    # The six fixture entities, as a snapshot of their own.
    with (SNAPSHOT / "entities.jsonl").open("w", encoding="utf-8") as lines:
        for kind in ("person", "place"):
            ids = [id for id in FIXTURE_IDS if FIXTURE_KINDS[id] == kind]
            for entity in fetch(client, ids, kind):
                lines.write(entity.line() + "\n")
    manifest = {
        "format": 1,
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "endpoint": QLEVER,
        "scope": {"script": "hy", "languages": ["hy", "hyw"]},
        "queries": {},
        "counts": {"person": 3, "place": 3},
        "requests": client.requests,
        "note": "Six entities for the tests, fetched by tests/record.py; not a real snapshot.",
    }
    (SNAPSHOT / "snapshot.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    (RECORDED / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"{client.requests} requests recorded", file=sys.stderr)


if __name__ == "__main__":
    main()
