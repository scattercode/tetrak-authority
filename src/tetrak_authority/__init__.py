"""tetrak-authority: a name authority from a dated Wikidata snapshot.

For catalogue search across scripts, the fold in tetrak-translit makes
every spelling of one name find the same record. What it cannot reach is
a different name for the same person or place: *Gregory of Narek* for
Գրիգոր Նարեկացի, a pseudonym, a German or Russian form, *Tiflis* for
Tbilisi. Wikidata holds those names, and this package turns a chosen
subset of it into an authority file: for each entity the established
form, every label and alias in every language, fold keys for retrieval,
and the VIAF, GND, ISNI and GeoNames identifiers that link onward.

Three jobs:

- :func:`tetrak_authority.snapshot.build` enumerates a subset with SPARQL
  (people and organisations with a label in the script's languages or a
  tie to the region; places with coordinates inside a box and such a
  label), fetches names and facts in batches, and writes a dated snapshot:
  ``snapshot.json`` with the date, endpoint, queries and counts, and
  ``entities.jsonl`` with one record per entity.
- :class:`Authority` loads a snapshot and answers lookups by fold key, so
  an indexer or a discovery layer never touches the network.
- :class:`Client` is the polite SPARQL and API client the snapshot uses,
  kept public for one-off checks.
"""

from __future__ import annotations

from .authority import Authority, Match
from .model import Entity, Name, key_of
from .snapshot import ARMENIAN, HISTORIC_ARMENIA, Box, Scope
from .wikidata import QLEVER, WDQS, Client

try:
    from ._version import version as __version__
except ImportError:  # a bare checkout, not yet built with hatch-vcs
    __version__ = "0.0.0"

__all__ = [
    "ARMENIAN",
    "Authority",
    "Box",
    "Client",
    "Entity",
    "HISTORIC_ARMENIA",
    "Match",
    "Name",
    "QLEVER",
    "Scope",
    "WDQS",
    "__version__",
    "key_of",
]
