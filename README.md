# Bridge Deals Ingest

A Python tool for ingesting, processing, and analyzing bridge game data from various file formats.

## Overview

Bridge Deals Ingest processes bridge game records from multiple file formats (PBN, LIN, JSON, RBN, CSV) and performs analysis including:

- Hand analysis (HCP, shape, patterns)
- Auction validation and analysis
- Contract scoring and validation
- Double-dummy analysis
- Card-by-card double-dummy analysis of the play (optional, with PlayDD)
- Comparative analysis of deals played at multiple tables
- Opening bid and lead analysis
- Statistical summaries

## Features

- **Multi-format Support**: Ingest bridge data from .pbn, .lin, .json, .rbn, and .csv files
- **Data Validation**: Validation of contracts, declarers, scores, leads, and more
- **Hand Analysis**: Automatic calculation of HCP, suit lengths, controls, shapes, and patterns
- **Auction Processing**: Parse and validate bidding sequences
- **Play Normalisation**: Every source's play converted to one encoding, in play order
- **Team Game Analysis**: Compare the same deal played at two tables
- **Statistical Analysis**: Generate summaries and opening bid statistics
- **Double-Dummy Support**: DD tables and par scores via endplay (DDS), with reuse of earlier results
- **High Performance**: Built on Polars for fast data processing
- **Parallel Processing**: Multi-threaded file ingestion for large datasets

## Bridge Deals Database

I have collected a large set of bridge deals from high-level tournament play and created a database with analytics
using this program. The raw data files as well as the results of the processing and analytics can be found in
https://github.com/ureshvahalia/bridge_deals_db

## Installation

### From Source

```bash
git clone https://github.com/ureshvahalia/bridge-deals-ingest.git
cd bridge-deals-ingest
pip install -e .
```

### Development Installation

```bash
git clone https://github.com/ureshvahalia/bridge-deals-ingest.git
cd bridge-deals-ingest
pip install -e ".[dev]"
```

See [INSTALLATION.md](INSTALLATION.md) for virtual environments and for PlayDD (optional).

## Requirements

- Python 3.10 or higher (3.11 or 3.12 recommended: endplay publishes ready-built packages for these)
- Core dependencies:
  - polars >= 1.0.0
  - matplotlib >= 3.7.0
  - numpy >= 1.24.0
  - RapidFuzz >= 3.0.0
  - line-profiler >= 4.0.0
  - endplay >= 0.5.12 (double-dummy solver)
- Optional:
  - PlayDD, for play normalisation and play analysis (available on request; see [INSTALLATION.md](INSTALLATION.md))

## Usage

### Command Line Interface

Basic usage:

```bash
bridge-ingest <output_directory> <input_files_or_directories> [options]
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
bridge-ingest ./output ./data/tournaments/ --doubledummy

# Double-dummy analysis, reusing the results in an earlier DB (only new hands are solved)
bridge-ingest ./output ./data/tournaments/ --reuse-dd ./old_output

# Add card-by-card play analysis (needs PlayDD)
bridge-ingest ./output ./data/tournaments/ --doubledummy --play

# Process only (no analysis)
bridge-ingest ./output ./data/tournament.pbn --processonly

# Analyze existing processed data
bridge-ingest ./output --analyzeonly

# Run play analysis on an existing DB
bridge-ingest ./output --playonly

# Enable profiling
bridge-ingest ./output ./data/tournament.pbn --profile
```

### Command Line Options

- `db_locn`: Directory to store output CSV files (will be created if it doesn't exist)
- `files`: One or more file paths or directories containing bridge data files
- `--doubledummy`, `-d`: Generate double-dummy analysis
- `--reuse-dd HANDS`: Double-dummy analysis that copies results from an earlier `hands.csv` (the file, or the DB
  folder holding it) for the same hands, dealer and vulnerability; only new hands are solved. Implies `-d`
- `--play`: Card-by-card play analysis with PlayDD, written to `<db_locn>/play/`
- `--play-depth {line,full}`: Play analysis depth (default `full`)
- `--play-workers N`: Play analysis worker processes (default: CPU count)
- `--profile`: Enable performance profiling

The following modes are mutually exclusive:

- `--processonly`, `-p`: Process files but skip the analysis phase
- `--analyzeonly`, `-a`: Analyze existing processed data (no files needed)
- `--playonly`: Only run play analysis on the existing DB in `db_locn` (no files needed)
- `--normalizeplay`: Rewrite Play in the existing DB's boards.csv and all.csv in play order, in place
  (no files needed)
- `--repairplay`: Re-read the given files and replace only Play and Claim for their boards in the existing DB,
  in place; other columns and UIDs are unchanged

`--normalizeplay` and `--repairplay` fix the play in a DB built by an older version without a full re-ingest.

### Python API

The modules are flat (there is no package to import from), so import them directly:

```python
from pathlib import Path
from ingest import ingest_files
from process_records import process_and_analyze_records

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
- **RawData.csv**: All ingested records with minimal processing (Play as parsed from the source)
- **all.csv**: Flat file with all data and validation flags
- **events.csv**: Unique events and matches
- **deals.csv**: Unique deals (hands + dealer + vulnerability + match)
- **boards.csv**: Individual board records (one per deal per table)
- **hands.csv**: Unique hand combinations with analysis (and double-dummy results with `-d`)

### Processed Analysis
- **ProcessedDeals.csv**: Deals with derived hand features
- **ProcessedBoards.csv**: Boards with validated and derived auction/contract data
- **FullBoards.csv**: Complete board data with all features
- **FullDeals.csv**: Side-by-side comparison of both tables for each deal

### Statistical Analysis
- **Summary.csv**: Statistical summary of swings and outcomes
- **Openings.csv**: Analysis of opening bids and their outcomes
- **EarlyBids.csv**: Analysis of competitive situations where one table opens and the other does not

### Play Analysis (with `--play` or `--playonly`)
Written to the `play/` subfolder, keyed by BoardUID:
- **play/boards.csv**, **play/positions.csv**, **play/cards.csv**, **play/summary.csv**

### Play and Claim Columns
In all.csv and boards.csv, `Play` holds the cards in play order separated by `_` (e.g. `SJ_SK_S2_S4`) for every
source. `PlayEncoding` says how the play was recorded in the source:

- `order`: already in play order (LIN, RBN, JSON, CSV)
- `pbn`: PBN seat-column tricks, reordered into play order using the deal and contract
- `pbn_raw`: PBN seat-column tricks with no contract or declarer to reorder them; Play kept as recorded
- `bad`: play could not be parsed; Play kept as recorded
- empty: no play recorded

Play normalisation needs PlayDD. Without it, Play is left as parsed and PlayEncoding is empty.

`Claim` is declarer's claimed total of tricks, from LIN (`mc|`) and EBL/WBF JSON sources. PBN, RBN and CSV
sources carry no claim.

## Data Validation

The tool validates:

- ✓ Hand completeness and validity (13 cards per player)
- ✓ Dealer and vulnerability consistency with deal number
- ✓ Auction legality
- ✓ Contract and declarer matching auction
- ✓ Score consistency with contract and tricks made
- ✓ Lead consistency with the recorded play
- ✓ Lead held by the opening leader (FullBoards `Lead_Type` is `UNKNOWN` if not; such boards are kept)
- ✓ Every card of the play legal: in the player's hand and following suit (play analysis only;
  `valid_through` in play/boards.csv is the number of legal cards from the start)
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
3. **Play Normalisation**: Convert every source's play to play order (with PlayDD)
4. **Feature Extraction**: Derive hand features (HCP, shapes, etc.) and, optionally, double-dummy tables and par,
   reusing earlier results if asked
5. **Auction Processing**: Validate auctions and extract bidding information
6. **Scoring**: Validate or compute scores and tricks made
7. **Play Analysis**: Card-by-card double-dummy analysis of the play (optional, with PlayDD)
8. **Analysis**: Compare deals played at multiple tables
9. **Statistics**: Generate summaries

### Key Components

- **driver.py**: Main entry point and CLI argument handling
- **ingest.py**: File discovery and parallel processing coordination
- **\*\_parse.py**: Format-specific parsers (PBN, LIN, JSON, RBN, CSV)
- **process_records.py**: Core processing and analysis engine
- **auction.py**: Auction parsing and validation
- **scoring.py**: Contract scoring calculations
- **common_objects.py**: Data structures and enums
- **fuzzy.py**: Event name deduplication using fuzzy matching
- **dds_wrapper.py**: Double-dummy analysis via endplay, and reuse of earlier DD results
- **play_analysis.py**: Play normalisation, play repair, and card-by-card play analysis via PlayDD

## File Format Support

### PBN (Portable Bridge Notation)
Standard format for bridge deals. Plays recorded in PBN's seat-column layout are reordered into play order.

### LIN (BBO LIN format)
Bridge Base Online's native format, used for BBO vugraph files. Results, plays and claims are read.

### JSON
EBL/WBF JSON results files, including claims.

### RBN (Richard's Bridge Notation)
Richard Pavlicek's compact notation.

### CSV
Files in the RawData.csv column layout (EventName, MatchName, ..., Auction, Play, Claim), such as the
lovebridge vugraph data, or a RawData.csv written by an earlier run.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Development

### Running Tests

```bash
pytest
```

Tests that need PlayDD are skipped if it isn't installed.

### Code Formatting

```bash
black .
ruff check .
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Bridge data formats based on community standards
- Double-dummy analysis uses DDS (Double Dummy Solver) through endplay
- Built with Polars for high-performance data processing

## Support

For issues, questions, or contributions, please visit the [GitHub Issues](https://github.com/ureshvahalia/bridge-deals-ingest/issues) page.

## Version History

See [CHANGELOG.md](CHANGELOG.md).
