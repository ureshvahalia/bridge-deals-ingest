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

### Changed
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
- Initial package structure for PyPI distribution
- Comprehensive documentation (README, CONTRIBUTING, INSTALLATION)
- GitHub Actions CI/CD workflow
- MIT License

## [0.1.0] - 2025-01-XX

### Added
- Multi-format file ingestion (PBN, LIN, JSON, RBN)
- Comprehensive hand analysis (HCP, shapes, patterns, controls)
- Auction parsing and validation
- Contract scoring calculations
- Double-dummy analysis support (optional)
- Team game comparative analysis
- Statistical summaries and visualizations
- Parallel file processing
- Data validation and quality checks
- Command-line interface
- Python API for programmatic use

### Features
- Parse and validate bridge auctions
- Analyze opening bids and leads
- Compare deals played at multiple tables
- Generate swing analysis and statistics
- Export to CSV for further analysis
- Fuzzy matching for event deduplication
- High-performance processing with Polars

### Data Outputs
- RawData.csv - All ingested records
- ProcessedDeals.csv - Deals with hand analysis
- ProcessedBoards.csv - Boards with auction analysis
- FullDeals.csv - Side-by-side table comparisons
- Summary.csv - Statistical summaries
- Openings.csv - Opening bid analysis
- EarlyBids.csv - Competitive bidding analysis
- OpenerView.csv - Opener perspective
- LeaderView.csv - Opening lead analysis
- DeclarerView.csv - Declarer analysis
- Swing_Chart.png - Visualization

### Documentation
- Comprehensive README with usage examples
- Installation guide
- Contributing guidelines
- API documentation in docstrings
- Read.me with detailed data processing explanation

## Version History

### Pre-release Development
- Initial development and testing
- Format parser implementations
- Core processing engine
- Analysis algorithms
- Validation logic

[Unreleased]: https://github.com/yourusername/bridge-deals-ingest/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/bridge-deals-ingest/releases/tag/v0.1.0




