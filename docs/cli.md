# Command line

```{eval-rst}
.. argparse::
   :module: tetrak_authority.cli
   :func: build_parser
   :prog: tetrak-authority
```

## Examples

```bash
tetrak-authority count                                   # the default scope, per kind
tetrak-authority count --kinds place --box 43 38.8 46.7 41.4
tetrak-authority snapshot --out snapshots/hy --contact you@example.org
tetrak-authority snapshot --out trial --limit 20         # a trial run, twenty items per kind
tetrak-authority lookup --snapshot snapshots/hy "Tumanyan, Hovhannes" "Tiflis"
tetrak-authority lookup --snapshot snapshots/hy --json "Գրիգոր Նարեկացի"
tetrak-authority show --snapshot snapshots/hy Q380797
tetrak-authority rekey --snapshot snapshots/hy          # after a tetrak-translit upgrade
tetrak-authority search "Նարեկացի"
```

Exit status is 0 on success, 1 when a lookup or search finds nothing,
and 2 for a bad argument or a failed request.
