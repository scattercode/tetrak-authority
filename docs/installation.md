# Installation

```bash
pip install tetrak-authority
```

Python 3.10 or later. The one dependency is tetrak-translit, whose fold
keys the names; a minor release of it can move keys, so a snapshot built
under one version is rebuilt after an upgrade (the manifest records
which version keyed it).

Building a snapshot needs the network, about an hour of polite requests
for the default scope, and nothing else. Looking names up needs only the
snapshot.
