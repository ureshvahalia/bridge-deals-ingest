"""
bridge-deals-ingest
===================
A comprehensive tool for ingesting, processing, and analyzing bridge game data.

This package provides functionality to:
- Ingest bridge data from multiple file formats (PBN, LIN, JSON, RBN)
- Validate and process board records
- Analyze hands, auctions, and contracts
- Generate statistical summaries and comparisons
- Export to CSV for further analysis
"""

__version__ = "0.1.0"

# Note: With a flat module structure, imports should be done directly:
# Example:
#   from ingest import ingest_files
#   from process_records import process_and_analyze_records
#   from common_objects import BoardRecord, Direction
