# Quick Start Guide

Get up and running with Bridge Deals Ingest.

## 1. Installation

```bash
# Install from source (development)
git clone https://github.com/ureshvahalia/bridge-deals-ingest.git
cd bridge-deals-ingest
pip install -e .
```

Play analysis also needs PlayDD, which is available on request (see [INSTALLATION.md](INSTALLATION.md)).

## 2. Basic Usage

### Process a single file

```bash
bridge-ingest ./output ./data/tournament.pbn
```

This will:
- Parse the PBN file
- Process all boards
- Generate analysis files in `./output/` directory

### Process multiple files

```bash
bridge-ingest ./output ./data/*.pbn
```

### Process an entire directory

```bash
bridge-ingest ./output ./data/tournaments/
```

The tool will recursively find and process all supported files (.pbn, .lin, .json, .rbn, .csv).

## 3. Understanding the Output

After processing, you'll find these files in the output directory:

**Quick Reference Files:**
- `Summary.csv` - Statistical summary of all deals
- `Openings.csv` - Opening bid frequency and outcomes
- `FullDeals.csv` - Side-by-side comparison of both tables

**Detailed Analysis:**
- `FullBoards.csv` - One row per board with all derived features, including the leader's,
  opener's and declarer's view of the board
- `EarlyBids.csv` - Competitive bidding situations

**Play Analysis** (with `--play`):
- `play/` - Card-by-card double-dummy analysis of each board's play

See the [README](README.md#output-files) for the full list, including the raw and processed data files.

## 4. Common Commands

### With double-dummy analysis
```bash
bridge-ingest ./output ./data/tournament.pbn --doubledummy
```

### Process only (skip analysis)
```bash
bridge-ingest ./output ./data/tournament.pbn --processonly
```

### Analyze existing data
```bash
bridge-ingest ./output --analyzeonly
```

### With card-by-card play analysis (needs PlayDD)
```bash
bridge-ingest ./output ./data/tournament.pbn --doubledummy --play
```

### Reuse double-dummy results from an earlier run
```bash
bridge-ingest ./output ./data/tournaments/ --reuse-dd ./old_output
```

### Enable profiling
```bash
bridge-ingest ./output ./data/tournament.pbn --profile
```

## 5. Using the Python API

```python
from pathlib import Path
from ingest import ingest_files
from process_records import process_and_analyze_records

# Ingest files
files = [Path("tournament.pbn")]
records = ingest_files(files, parallelize=True)

# Process and analyze
output_dir = Path("./output")
output_dir.mkdir(exist_ok=True)
process_and_analyze_records(records, generateDD=False, outdir=output_dir)
```

## 6. Viewing Results

### In Excel or LibreOffice
Simply open any of the CSV files in your spreadsheet application.

### In Python with pandas
```python
import pandas as pd

# Load summary
summary = pd.read_csv("output/Summary.csv")
print(summary)

# Load opening analysis
openings = pd.read_csv("output/Openings.csv")
print(openings.head())
```

### In Python with polars (faster)
```python
import polars as pl

# Load full deals
deals = pl.read_csv("output/FullDeals.csv")
print(deals.describe())
```

## 7. Filtering and Analysis

### View only high-swing deals
```python
import polars as pl

deals = pl.read_csv("output/FullDeals.csv")
high_swings = deals.filter(pl.col("SWING") > 10)
print(f"Found {len(high_swings)} deals with swings > 10 IMPs")
```

### Analyze opening bid success
```python
import polars as pl

openings = pl.read_csv("output/Openings.csv")
best_openings = openings.sort("Ave SWING", descending=True).head(10)
print(best_openings)
```

## 8. Example Workflow

1. **Collect Data**: Gather .pbn, .lin, .json, .rbn, or .csv files
2. **Process**: Run `bridge-ingest ./analysis ./data/`
3. **Review Summary**: Open `analysis/Summary.csv`
4. **Deep Dive**: Explore `FullBoards.csv` and `FullDeals.csv`
5. **Custom Analysis**: Load CSVs in Python/R/Excel for custom queries

## 9. Tips

- **Large datasets**: Use `--processonly` first, then `--analyzeonly` later
- **Re-runs with double-dummy**: Use `--reuse-dd <earlier DB>` so only new hands are solved
- **Performance**: Processing uses all CPU cores by default for parallel file reading
- **Memory**: For very large datasets (>100K boards), process in batches
- **Validation**: Check validation columns (e.g., `ContractValidation`) to assess data quality

## 10. Next Steps

- Read the full [README.md](README.md) for detailed documentation
- See [INSTALLATION.md](INSTALLATION.md) for installation options
- Check [CONTRIBUTING.md](CONTRIBUTING.md) if you want to contribute
- Browse the code to understand the analysis algorithms

## Troubleshooting

**Issue**: "No supported files found"
- **Solution**: Ensure files have correct extensions (.pbn, .lin, .json, .rbn, .csv)

**Issue**: Command not found
- **Solution**: Ensure package is installed and virtual environment is activated

**Issue**: Permission denied
- **Solution**: Run with appropriate permissions or change output directory

**Issue**: Memory error on large datasets
- **Solution**: Process files in smaller batches

## Support

For issues or questions:
- Check existing issues: https://github.com/ureshvahalia/bridge-deals-ingest/issues
- Create a new issue with details of your problem
- Include sample data (without sensitive information) if possible

Happy analyzing! 🃏
