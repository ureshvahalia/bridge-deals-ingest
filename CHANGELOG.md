# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- RBN play: a rank without a suit follows the suit led, not the previous card's suit.
  Plays with a discard were corrupted from that point ("SJQH47" read as ... H4 H7, not ... H4 S7).
- LIN results: a board's `rs|` entry is found by board number and room (two entries per board from
  the segment's first board, `vg|` field 4), not by its position in the file. Files that skip boards
  or record one room (most pairs events) gave boards another board's Contract, Declarer and
  TricksMade; such boards were mostly dropped by the contract Mismatch filter, so FullBoards grows.
- LIN claims (`mc|n|`) are read; they were never read before.
- Par analysis no longer fails on boards with a missing Declarer or Strain.

### Changed
- endplay (the double-dummy solver) is now a declared dependency; it was always required but had to be
  installed by hand.
- Python 3.10 or higher is required (the code already needed it; the package claimed 3.9).
- `Play` in boards.csv and all.csv is now one encoding for every source: cards in play order,
  separated by `_` (e.g. `SJ_SK_S2_S4`). PBN seat-column plays are reordered using the deal.
  RawData.csv keeps the play as parsed. Needs PlayDD installed; without it Play is left as parsed.

### Added
- `PlayEncoding` column (boards.csv, all.csv): how Play was recorded: `order`, `pbn` (reordered from
  PBN seat columns), `pbn_raw` (PBN without a contract to reorder by; kept as recorded), `bad`.
- `Claim` column: declarer's claimed total, from LIN `mc|n|` and from `Play.Claim` in EBL/WBF JSON.
  PBN, RBN and CSV sources carry no claim.
- `--reuse-dd HANDS`: double-dummy results copied from an earlier hands.csv (file or DB folder) for
  the same hands, dealer and vulnerability; only new hands are computed. Implies `-d`.
- `--play`, `--playonly`: card-by-card play analysis with PlayDD, written to `<db>/play/`.
- `--normalizeplay`, `--repairplay FILES`: fix Play in an existing DB without a re-ingest.

### Removed
- dds.dll: unused, since double-dummy analysis goes through endplay, which bundles DDS.

## [0.1.4] - 2026-03-13

### Added
- CSV input: files in the RawData.csv column layout (used for the lovebridge vugraph data).

### Changed
- Hands are canonicalised to W-first format before UIDs are assigned, so equivalent layouts get the same HandUID.
- BoardUID is built from HandUID and the player names instead of DealUID, DealNum and TableID.
- TableID and player names are uppercased.

### Fixed
- Leader and opener views no longer fail on boards with a missing lead or opener.
- Event deduplication (`fuzzy_deduplicate_events`) returns the mapping its callers expect.
- Compatibility with newer Polars versions (derived-feature extraction; a blank direction raised an exception).

## [0.1.1] - 2026-02-20

### Fixed
- Directory traversal matches file extensions case-insensitively, so files are found on every operating system.
- Miscellaneous bug fixes and cleanup.

### Removed
- OpenerView.csv, LeaderView.csv and DeclarerView.csv are no longer written; their columns are in FullBoards.csv.

## [0.1.0] - 2025-10-22

### Added
- Multi-format file ingestion (PBN, LIN, JSON, RBN)
- Hand analysis (HCP, shapes, patterns, controls)
- Auction parsing and validation
- Contract scoring calculations
- Double-dummy analysis support (optional)
- Team game comparative analysis
- Statistical summaries
- Parallel file processing
- Data validation and quality checks
- Command-line interface
- Python API for programmatic use
- Package structure, documentation (README, CONTRIBUTING, INSTALLATION), GitHub Actions CI workflow, MIT License

### Data Outputs
- RawData.csv - All ingested records
- all.csv, events.csv, deals.csv, boards.csv, hands.csv - Normalised tables
- ProcessedDeals.csv - Deals with hand analysis
- ProcessedBoards.csv - Boards with auction analysis
- FullBoards.csv - Boards with all derived features
- FullDeals.csv - Side-by-side table comparisons
- Summary.csv - Statistical summaries
- Openings.csv - Opening bid analysis
- EarlyBids.csv - Competitive bidding analysis
- OpenerView.csv - Opener perspective
- LeaderView.csv - Opening lead analysis
- DeclarerView.csv - Declarer analysis

[Unreleased]: https://github.com/ureshvahalia/bridge-deals-ingest/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/ureshvahalia/bridge-deals-ingest/compare/v0.1.1...v0.1.4
[0.1.1]: https://github.com/ureshvahalia/bridge-deals-ingest/compare/8781dcd...v0.1.1
[0.1.0]: https://github.com/ureshvahalia/bridge-deals-ingest/tree/8781dcd
