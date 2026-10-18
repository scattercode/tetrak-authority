"""The ``tetrak-authority`` command.

::

    tetrak-authority count                         # how big the default scope is, per kind
    tetrak-authority snapshot --out snapshots/hy   # build a dated snapshot
    tetrak-authority lookup --snapshot snapshots/hy "Tumanyan, Hovhannes"
    tetrak-authority show --snapshot snapshots/hy Q380797
    tetrak-authority search "Նարեկացի"             # a one-off live search

Exit status is 0 on success, 1 when a lookup finds nothing, and 2 for a
bad argument or a failed request.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .authority import Authority
from .model import KINDS
from .snapshot import ARMENIAN, Box, Scope, build, count
from .wikidata import QLEVER, WDQS, Client, RequestFailed, user_agent

KIND_CHOICES = (*KINDS, "agent")


def build_parser() -> argparse.ArgumentParser:
    """The argument parser; also what the documentation renders."""
    parser = argparse.ArgumentParser(
        prog="tetrak-authority",
        description="A name authority from a dated Wikidata snapshot: variant names, fold keys and identifiers for catalogue search across scripts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    def scope_arguments(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--endpoint",
            default=QLEVER,
            help=f"SPARQL endpoint: the QLever mirror (default, {QLEVER}) or the Query Service ({WDQS}), which times out on the enumeration queries",
        )
        sub.add_argument(
            "--contact",
            default=None,
            help="a URL or email for the user agent, as Wikimedia's policy asks",
        )
        sub.add_argument(
            "--fetch-endpoint",
            default=WDQS,
            help=f"SPARQL endpoint that fetches names and facts by batch of ids (default the Query Service, {WDQS}, which is faster at that than the mirror)",
        )
        sub.add_argument(
            "--pause", type=float, default=1.0, help="seconds between requests (default 1)"
        )
        sub.add_argument(
            "--kinds",
            nargs="+",
            choices=KIND_CHOICES,
            default=list(KINDS),
            help="which kinds to include; 'agent' is person and organisation",
        )
        sub.add_argument(
            "--languages",
            nargs="+",
            default=list(ARMENIAN.languages),
            help="label languages that bring an item in (default hy hyw)",
        )
        sub.add_argument(
            "--script",
            default=ARMENIAN.script,
            help="the tetrak-translit script that keys the names (default hy)",
        )
        sub.add_argument(
            "--box",
            nargs=4,
            type=float,
            metavar=("WEST", "SOUTH", "EAST", "NORTH"),
            default=None,
            help="where a place must lie, in degrees; default an approximation of historic Armenia (26 31.7 51.6 43.6)",
        )
        sub.add_argument(
            "--no-box", action="store_true", help="places anywhere with a label in the languages"
        )

    counting = commands.add_parser(
        "count", help="how many items the scope holds, per kind, without fetching them"
    )
    scope_arguments(counting)

    snapshot = commands.add_parser("snapshot", help="build a dated snapshot")
    scope_arguments(snapshot)
    snapshot.add_argument(
        "--out", type=Path, required=True, help="directory for snapshot.json and entities.jsonl"
    )
    snapshot.add_argument(
        "--batch", type=int, default=200, help="items per fetch query (default 200)"
    )
    snapshot.add_argument("--limit", type=int, default=None, help="items per kind, for a trial run")
    snapshot.add_argument(
        "--resume",
        action="store_true",
        help="keep the entities already in the output and fetch only the rest",
    )

    lookup = commands.add_parser(
        "lookup", help="the entities a name reaches in a snapshot, and their names"
    )
    lookup.add_argument("--snapshot", type=Path, required=True, help="the snapshot directory")
    lookup.add_argument(
        "--kinds", nargs="+", choices=KIND_CHOICES, default=None, help="restrict to these kinds"
    )
    lookup.add_argument("--json", action="store_true", help="print the matches as JSON")
    lookup.add_argument("names", nargs="+", help="names as a catalogue or a reader wrote them")

    show = commands.add_parser("show", help="one record by its Wikidata id")
    show.add_argument("--snapshot", type=Path, required=True)
    show.add_argument("ids", nargs="+", metavar="QID")

    search = commands.add_parser("search", help="a one-off live search of Wikidata by name")
    search.add_argument(
        "--language", default="hy", help="language to search labels in (default hy)"
    )
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--contact", default=None)
    search.add_argument("text")
    return parser


def kinds_of(names: Sequence[str] | None) -> list[str] | None:
    """Expand ``agent`` into person and organisation."""
    if names is None:
        return None
    kinds: list[str] = []
    for name in names:
        for kind in ("person", "organisation") if name == "agent" else (name,):
            if kind not in kinds:
                kinds.append(kind)
    return kinds


def scope_of(args: argparse.Namespace) -> Scope:
    """The scope the command-line arguments describe."""
    box: Box | None
    if args.no_box:
        box = None
    elif args.box is not None:
        box = Box(*args.box)
    else:
        box = ARMENIAN.box
    return Scope(script=args.script, languages=tuple(args.languages), box=box)


def client_of(args: argparse.Namespace, endpoint: str | None = None) -> Client:
    """A client with the user agent the arguments ask for, on the enumeration endpoint or the one given."""
    contact = args.contact or "https://github.com/scattercode/tetrak-authority"
    return Client(
        endpoint=endpoint if endpoint is not None else str(getattr(args, "endpoint", QLEVER)),
        user_agent=user_agent(__version__, contact),
        pause=getattr(args, "pause", 1.0),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command; returns the exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "count":
            counts = count(client_of(args), scope_of(args), kinds_of(args.kinds) or KINDS)
            for kind, n in counts.items():
                print(f"{kind:<13} {n:>8}")
            return 0
        if args.command == "snapshot":
            manifest = build(
                client_of(args),
                args.out,
                scope_of(args),
                kinds=kinds_of(args.kinds) or KINDS,
                batch=args.batch,
                limit=args.limit,
                log=lambda line: print(line, file=sys.stderr),
                fetch_client=client_of(args, args.fetch_endpoint),
                resume=args.resume,
            )
            print(json.dumps(manifest, indent=2, ensure_ascii=False))
            return 0
        if args.command == "lookup":
            return run_lookup(
                Authority.load(args.snapshot), args.names, kinds_of(args.kinds), args.json
            )
        if args.command == "show":
            authority = Authority.load(args.snapshot)
            status = 0
            for id in args.ids:
                entity = authority.get(id)
                if entity is None:
                    print(f"{id}: not in the snapshot", file=sys.stderr)
                    status = 1
                else:
                    print(json.dumps(entity.to_json(), indent=2, ensure_ascii=False))
            return status
        if args.command == "search":
            hits = client_of(args).search(args.text, language=args.language, limit=args.limit)
            for hit in hits:
                print(f"{hit['id']:<12} {hit.get('label', '')}  {hit.get('description', '')}")
            return 0 if hits else 1
    except RequestFailed as error:
        print(f"request failed: {error}", file=sys.stderr)
        return 2
    except FileNotFoundError as error:
        print(f"not found: {error.filename}", file=sys.stderr)
        return 2
    parser.error(f"unknown command {args.command}")  # pragma: no cover


def run_lookup(
    authority: Authority, names: Sequence[str], kinds: Sequence[str] | None, as_json: bool
) -> int:
    """Print what each name reaches; 1 if any name reaches nothing."""
    status = 0
    report: list[dict[str, Any]] = []
    for text in names:
        matches = authority.match(text, kinds)
        if not matches:
            status = 1
        if as_json:
            report.append(
                {
                    "query": text,
                    "matches": [
                        {
                            "id": m.entity.id,
                            "kind": m.entity.kind,
                            "label": m.entity.label,
                            "exact": m.exact,
                            "matched": m.name.text,
                            "names": [n.text for n in m.entity.names],
                            "identifiers": m.entity.identifiers,
                        }
                        for m in matches
                    ],
                }
            )
            continue
        print(text)
        if not matches:
            print("  nothing")
        for m in matches:
            how = "exact" if m.exact else "partial"
            years = (
                f" ({m.entity.born or '?'}–{m.entity.died or ''})"
                if m.entity.kind == "person" and (m.entity.born or m.entity.died)
                else ""
            )
            ids = ", ".join(f"{k} {v}" for k, v in sorted((m.entity.identifiers or {}).items()))
            print(
                f"  {m.entity.id:<12} {how:<8} {m.entity.label}{years}  [{m.entity.kind}]"
                + (f"  {ids}" if ids else "")
            )
            print(
                f"    {len(m.entity.names)} names, matched on {m.name.text!r} ({m.name.language})"
            )
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return status


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
