import logging
import cProfile
import pstats
import sys
from line_profiler import LineProfiler
from pathlib import Path
from argparse import ArgumentParser
from typing import List, Optional
from common_objects import BoardRecord, lineProf
from process_records import process_and_analyze_records, process_records, analyze_records
from ingest import ingest_files

def _main_impl(lp: LineProfiler) -> None:
    # Process arguments
    arg_list = ArgumentParser(description="Process bridge game files and generate analysis")
    arg_list.add_argument("db_locn", help="Database folder path for output files")
    arg_list.add_argument("files", nargs="+", help="Bridge data files or directories to process (PBN, LIN, JSON, RBN)")
    arg_list.add_argument("--profile", action="store_true", help="Enable performance profiling")
    arg_list.add_argument("-d", "--doubledummy", action="store_true", help="Generate double-dummy analysis")
    mode_group = arg_list.add_mutually_exclusive_group()
    mode_group.add_argument("-a", "--analyzeonly", action="store_true", help="Analyze existing DB only")
    mode_group.add_argument("-p", "--processonly", action="store_true", help="Only process, do not analyze")
    args = arg_list.parse_args()
    output_dir: Path = Path(args.db_locn if args.db_locn else "./output")
    
    try:
        # Run the ingestion
        if args.analyzeonly:
            analyze_records(output_dir)
        else:
            reclist: List[BoardRecord] = ingest_files([Path(f) for f in args.files], parallelize=True)
            if len(reclist) > 0:
                output_dir.mkdir(exist_ok=True)
                if args.processonly:
                    process_records(reclist, args.doubledummy, output_dir)
                else:
                    process_and_analyze_records(reclist, args.doubledummy, output_dir)
            
    except Exception as e:
        logging.error(f"Error during processing: {str(e)}")

def main() -> None:
    """Entry point for the bridge-ingest console script."""
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.warning("Starting")
    if '--profile' in sys.argv:
        # Set up profiling
        profiler = cProfile.Profile()
        profiler.enable()
        lineProf.add_function(_main_impl)
        lineProf.runctx('_main_impl(lineProf)', globals(), {'lineProf': lineProf})
        lineProf.print_stats()
        profiler.disable()
        stats = pstats.Stats(profiler)
        stats.strip_dirs().sort_stats('time').print_stats(10)  # Top 10 functions sorted by time
    else:
        _main_impl(lineProf)  # Normal execution with debugger support
    logging.warning("Finished")

if __name__ == "__main__":
    main()
        