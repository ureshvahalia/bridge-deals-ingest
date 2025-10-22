# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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




