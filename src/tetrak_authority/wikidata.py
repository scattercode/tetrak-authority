"""A polite client for Wikidata's SPARQL endpoints and its search API.

Wikidata asks three things of a bulk reader: identify yourself in the
user agent, go one request at a time, and back off when told to. The
client does all three and counts its requests, so a snapshot can say how
many it made.

Two SPARQL endpoints are known. The Wikidata Query Service is live but
times out on the queries that enumerate a subset by label language; the
QLever mirror answers those in a second from a copy a little behind
live. The snapshot records which one it used.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: The Wikidata Query Service, live, 60-second query limit.
WDQS = "https://query.wikidata.org/sparql"
#: The QLever mirror of Wikidata at the University of Freiburg: a copy a
#: little behind live, no practical query limit.
QLEVER = "https://qlever.dev/api/wikidata"
#: The Wikidata API, for ``wbsearchentities``.
API = "https://www.wikidata.org/w/api.php"

PREFIXES = (
    "PREFIX wd: <http://www.wikidata.org/entity/> "
    "PREFIX wdt: <http://www.wikidata.org/prop/direct/> "
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
    "PREFIX skos: <http://www.w3.org/2004/02/skos/core#> "
    "PREFIX schema: <http://schema.org/> "
    "PREFIX geof: <http://www.opengis.net/def/function/geosparql/> "
)

#: What a transport does: take a URL and headers, return the body.
Transport = Callable[[str, dict[str, str]], bytes]


def user_agent(
    version: str, contact: str = "https://github.com/scattercode/tetrak-authority"
) -> str:
    """The user agent Wikimedia's policy asks for: a name, a version, a contact."""
    return f"tetrak-authority/{version} ({contact})"


@dataclass(frozen=True)
class Cell:
    """One bound value in a SPARQL result row.

    Attributes:
        value: The value as a string: an IRI, a literal, a number.
        language: The literal's language tag, if it has one.
    """

    value: str
    language: str | None = None

    @property
    def id(self) -> str:
        """The item id of an entity IRI (``Q380797``), or the value itself."""
        return (
            self.value.rsplit("/", 1)[-1]
            if self.value.startswith("http://www.wikidata.org/entity/")
            else self.value
        )


Row = dict[str, Cell]


class RequestFailed(RuntimeError):
    """A request failed after the retries the client allows, or the endpoint rejected the query."""


def _query_error(error: urllib.error.HTTPError) -> str | None:
    """The endpoint's own message when it rejected the query (a timeout, a parse error), else None.

    QLever answers a failed query with a JSON body carrying ``exception``,
    under a 429 or a 500; that is not rate limiting and is not retried.
    """
    try:
        body = json.loads(error.read().decode("utf-8", "replace"))
    except (ValueError, OSError):
        return None
    message = body.get("exception") if isinstance(body, dict) else None
    return str(message) if message else None


class Client:
    """A rate-limited reader of one SPARQL endpoint and the Wikidata API.

    Args:
        endpoint: The SPARQL endpoint for :meth:`select`.
        user_agent: Sent with every request; see :func:`user_agent`.
        pause: Seconds between the start of one request and the next.
        timeout: Seconds to wait for a response.
        retries: How many times a 429 or a 5xx is retried, with backoff.
        max_delay: The longest backoff, in seconds, when no Retry-After
            header says otherwise.
        transport: Replaces the network, for tests and recordings.
    """

    def __init__(
        self,
        endpoint: str = QLEVER,
        user_agent: str = "tetrak-authority/0 (https://github.com/scattercode/tetrak-authority)",
        pause: float = 1.0,
        timeout: float = 120.0,
        retries: int = 5,
        max_delay: float = 120.0,
        transport: Transport | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.pause = pause
        self.timeout = timeout
        self.retries = retries
        self.max_delay = max_delay
        self._transport = transport or self._http
        self.requests = 0
        self._last = 0.0

    def select(self, query: str) -> list[Row]:
        """Run a SELECT query and return its rows.

        The standard prefixes are prepended, so a query names ``wd:``,
        ``wdt:``, ``rdfs:``, ``skos:``, ``schema:`` and ``geof:`` freely.
        """
        url = (
            self.endpoint
            + "?"
            + urllib.parse.urlencode({"query": PREFIXES + query, "format": "json"})
        )
        data = json.loads(self._get(url, {"Accept": "application/sparql-results+json"}))
        rows: list[Row] = []
        for binding in data["results"]["bindings"]:
            rows.append(
                {name: Cell(cell["value"], cell.get("xml:lang")) for name, cell in binding.items()}
            )
        return rows

    def search(self, text: str, language: str = "hy", limit: int = 5) -> list[dict[str, Any]]:
        """Search items by name with the API's ``wbsearchentities``.

        A prefix search over labels and aliases in one language: good for a
        one-off check, not for matching, which is what a snapshot is for.
        Returns the API's hits: ``id``, ``label``, ``description``,
        ``match``.
        """
        params = {
            "action": "wbsearchentities",
            "search": text,
            "language": language,
            "type": "item",
            "limit": str(limit),
            "format": "json",
        }
        data = json.loads(self._get(API + "?" + urllib.parse.urlencode(params), {}))
        hits: list[dict[str, Any]] = data.get("search", [])
        return hits

    def _get(self, url: str, headers: dict[str, str]) -> bytes:
        headers = {"User-Agent": self.user_agent, **headers}
        delay = self.pause
        for attempt in range(self.retries + 1):
            wait = self._last + self.pause - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            try:
                return self._transport(url, headers)
            except urllib.error.HTTPError as error:
                reason = _query_error(error)
                if reason or error.code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise RequestFailed(
                        f"{error.code} from {url[:80]}: {reason or error.reason}"
                    ) from error
                retry_after = error.headers.get("Retry-After") if error.headers else None
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else min(max(delay * 2, 5.0), self.max_delay)
                )
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt == self.retries:
                    raise RequestFailed(f"{error} from {url[:80]}") from error
                delay = min(max(delay * 2, 5.0), self.max_delay)
            time.sleep(delay)
        raise RequestFailed(url)  # pragma: no cover - the loop returns or raises

    def _http(self, url: str, headers: dict[str, str]) -> bytes:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body: bytes = response.read()
            return body


__all__ = [
    "API",
    "PREFIXES",
    "QLEVER",
    "WDQS",
    "Cell",
    "Client",
    "RequestFailed",
    "Row",
    "Transport",
    "user_agent",
]
