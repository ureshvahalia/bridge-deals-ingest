# Bridge Deals Ingest

A comprehensive Python tool for ingesting, processing, and analyzing bridge game data from various file formats.

## Overview

Bridge Deals Ingest processes bridge game records from multiple file formats (PBN, LIN, JSON, RBN) and performs comprehensive analysis including:

- Hand analysis (HCP, shape, patterns)
- Auction validation and analysis
- Contract scoring and validation
- Double-dummy analysis support
- Comparative analysis of deals played at multiple tables
- Opening bid and lead analysis
- Statistical summaries and visualizations

## Features

- **Multi-format Support**: Ingest bridge data from .pbn, .lin, .json, and .rbn files
- **Data Validation**: Comprehensive validation of contracts, declarers, scores, and more
- **Hand Analysis**: Automatic calculation of HCP, suit lengths, controls, shapes, and patterns
- **Auction Processing**: Parse and validate bidding sequences
- **Team Game Analysis**: Compare the same deal played at two tables
- **Statistical Analysis**: Generate summaries, opening bid statistics, and swing charts
- **Double-Dummy Support**: Optional integration with DDS (Double Dummy Solver)
- **High Performance**: Built on Polars for fast data processing
- **Parallel Processing**: Multi-threaded file ingestion for large datasets

## Bridge Deals Database

I have collected a large set of bridge deals from high-level tournament play and created a database with analytics
using this program. The raw data files as well as the results of the processing and analytics can be found in
https://github.com/ureshvahalia/bridge_deals_db/releases/edit/untagged-a523b3c9b8bd0632c394

## Installation

### From PyPI (once published)

```bash
pip install bridge-deals-ingest
```

### From Source

```bash
git clone https://github.com/yourusername/bridge-deals-ingest.git
cd bridge-deals-ingest
pip install -e .
```

### Development Installation

```bash
git clone https://github.com/yourusername/bridge-deals-ingest.git
cd bridge-deals-ingest
pip install -e ".[dev]"
```

## Requirements

- Python 3.9 or higher
- Core dependencies:
  - polars >= 1.0.0
  - matplotlib >= 3.7.0
  - numpy >= 1.24.0
  - RapidFuzz >= 3.0.0

## Usage

### Command Line Interface

Basic usage:

```bash
bridge-ingest <output_directory> <input_files_or_directories>
```

Examples:

```bash
# Process a single PBN file
bridge-ingest ./output ./data/tournament.pbn

# Process multiple files
bridge-ingest ./output ./data/file1.pbn ./data/file2.lin

# Process entire directory (recursively)
bridge-ingest ./output ./data/tournaments/

# Generate double-dummy analysis
bridge-ingest ./output ./data/tournament.pbn --doubledummy

# Process only (no analysis)
bridge-ingest ./output ./data/tournament.pbn --processonly

# Analyze existing processed data
bridge-ingest ./output --analyzeonly

# Enable profiling
bridge-ingest ./output ./data/tournament.pbn --profile
```

### Command Line Options

- `db_locn`: Directory to store output CSV files (will be created if it doesn't exist)
- `files`: One or more file paths or directories containing bridge data files
- `--doubledummy`, `-d`: Generate double-dummy analysis (requires DDS DLL)
- `--processonly`, `-p`: Process files but skip analysis phase
- `--analyzeonly`, `-a`: Analyze existing processed data (skip ingestion)
- `--profile`: Enable performance profiling

### Python API

```python
from pathlib import Path
from bridge_ingest.ingest import ingest_files
from bridge_ingest.process_records import process_and_analyze_records

# Ingest files
files_to_process = [Path("tournament.pbn"), Path("data_directory")]
records = ingest_files(files_to_process, parallelize=True)

# Process and analyze
output_dir = Path("./output")
output_dir.mkdir(exist_ok=True)
process_and_analyze_records(records, generateDD=False, outdir=output_dir)
```

## Output Files

The tool generates several CSV files in the output directory:

### Raw and Processed Data
- **RawData.csv**: All ingested records with minimal processing
- **all.csv**: Flat file with all data and validation flags
- **events.csv**: Unique events and matches
- **deals.csv**: Unique deals (hands + dealer + vulnerability + match)
- **boards.csv**: Individual board records (one per deal per table)
- **hands.csv**: Unique hand combinations with analysis

### Processed Analysis
- **ProcessedDeals.csv**: Deals with derived hand features
- **ProcessedBoards.csv**: Boards with validated and derived auction/contract data
- **FullBoards.csv**: Complete board data with all features
- **FullDeals.csv**: Side-by-side comparison of both tables for each deal

### Statistical Analysis
- **Summary.csv**: Statistical summary of swings and outcomes
- **Openings.csv**: Analysis of opening bids and their outcomes
- **EarlyBids.csv**: Analysis of competitive situations where one table opens

## Data Validation

The tool performs comprehensive validation:

- ✓ Hand completeness and validity (13 cards per player)
- ✓ Dealer and vulnerability consistency with deal number
- ✓ Auction legality
- ✓ Contract and declarer matching auction
- ✓ Score consistency with contract and tricks made
- ✓ Lead consistency with opening leader's hand
- ✓ Board count per deal (for team games)

Each field has a validation status:
- **Match**: Primary and derived values agree
- **Mismatch**: Primary and derived values conflict
- **Primary**: Primary value present, derived not computable
- **Derived**: Primary missing, derived value used
- **Missing**: No value available

## Architecture

### Processing Pipeline

1. **Ingestion**: Parse multiple file formats into standardized BoardRecord objects
2. **Validation**: Check dealer, vulnerability, and data consistency
3. **Feature Extraction**: Derive hand features (HCP, shapes, etc.)
4. **Auction Processing**: Validate auctions and extract bidding information
5. **Scoring**: Validate or compute scores and tricks made
6. **Analysis**: Compare deals played at multiple tables
7. **Statistics**: Generate summaries and visualizations

### Key Components

- **driver.py**: Main entry point and CLI argument handling
- **ingest.py**: File discovery and parallel processing coordination
- **\*\_parse.py**: Format-specific parsers (PBN, LIN, JSON, RBN)
- **process_records.py**: Core processing and analysis engine
- **auction.py**: Auction parsing and validation
- **scoring.py**: Contract scoring calculations
- **common_objects.py**: Data structures and enums
- **fuzzy.py**: Event name deduplication using fuzzy matching
- **dds_wrapper.py**: Optional double-dummy solver integration

## File Format Support

### PBN (Portable Bridge Notation)
Standard format for bridge deals with full support for all tags.

### LIN (BBO LIN format)
Bridge Base Online's native format.

### JSON
JSON-formatted bridge data.

### RBN (Richard's Bridge Notation)
Alternative bridge notation format.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black .
ruff check .
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Bridge data formats based on community standards
- Double-dummy analysis uses DDS (Double Dummy Solver)
- Built with Polars for high-performance data processing

## Support

For issues, questions, or contributions, please visit the [GitHub Issues](https://github.com/yourusername/bridge-deals-ingest/issues) page.

## Version History

### 0.1.0 (Initial Release)
- Multi-format file ingestion (PBN, LIN, JSON, RBN)
- Comprehensive hand and auction analysis
- Team game comparative analysis
- Statistical summaries and visualizations
- Parallel processing support
- Data validation and quality checks


