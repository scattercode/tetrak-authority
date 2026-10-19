# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-19

### Changed

- Take tetrak-translit 4.0.0, whose fold moves the keys of initial հե

## [0.1.1] - 2026-10-19

### Fixed

- Ship the py.typed marker so dependants can type-check against the package

## [0.1.0] - 2026-10-19

### Added

- Add the repository scaffolding

### Changed

- Build a dated Wikidata snapshot and look names up by fold key
- Fetch on the Query Service, halve a refused batch, resume a run
- Store each name's key in the snapshot, and rekey after a translit upgrade
- Look names up through an SQLite index built beside the snapshot

### Fixed

- Compare a trial build without its keys, and take tetrak-translit 3.5.0

