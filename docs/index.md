# tetrak-authority

A name authority from a dated Wikidata snapshot, for catalogue search
across scripts: for each person, organisation or place in a chosen subset
of Wikidata, the established form, every label and alias in every
language, fold keys for retrieval, and the identifiers that link a record
onward.

```{toctree}
:maxdepth: 2

installation
usage
snapshot
cli
api
```

## In one screen

```python
>>> from tetrak_authority import Authority
>>> authority = Authority.load("snapshots/hy")
>>> for match in authority.match("Tumanyan, Hovhannes"):
...     print(match.entity.id, match.entity.label, match.entity.born, match.exact)
Q380797 Հովհաննես Թումանյան 1869 True
Q20513561 Հովհաննես Թումանյան 1930 True
```

The lookup folds the name with [tetrak-translit](https://github.com/scattercode/tetrak-translit)
and sorts the words, so an inverted catalogue form, a classical spelling
and a diaspora romanisation reach the same record; the two results are
two people who share a name, which the years and the identifiers tell
apart.
