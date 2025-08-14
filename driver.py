import logging
import cProfile
import pstats
import sys
from line_profiler import LineProfiler
from pathlib import Path
from argparse import ArgumentParser
from typing import List
from common_objects import BoardRecord, lineProf
from process_records import process_and_analyze_records, process_records, analyze_records
from ingest import ingest_files

def main(lp: LineProfiler) -> None:
    # Process arguments
    arg_list = ArgumentParser(description="Process VuGraph files")
    arg_list.add_argument("db_locn", help="Databse folder path")
    arg_list.add_argument("files", nargs="+", help="LIN files or directories to process")
    arg_list.add_argument("--profile", action="store_true", help="LIN files or directories to process")
    arg_list.add_argument("-d", "--doubledummy", action="store_true", help="Generate double-dummy analysis")
    mode_group = arg_list.add_mutually_exclusive_group()
    mode_group.add_argument("-a", "--analyzeonly", action="store_true", help="Analyze existing DB only")
    mode_group.add_argument("-p", "--processonly", action="store_true", help="Only process, do not analyze")
    args = arg_list.parse_args()
    output_dir: Path = Path(args.db_locn if args.db_locn else "./output")
    
    try:
        # Run the ingestion
        if args.analyzeonly:
            analyze_records(output_dir, "ProcessedDeals", "ProcessedBoards")
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

if __name__ == "__main__":
    logging.warning("Starting")
    
    # Set up profiling
    profiler = cProfile.Profile()
    profiler.enable()

    if '--profile' in sys.argv:
        lineProf.add_function(main)
        lineProf.runctx('main(lineProf)', globals(), locals={'lp': lineProf})
        lineProf.print_stats()
    else:
        main(lineProf)  # Normal execution with debugger support

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.strip_dirs().sort_stats('time').print_stats(10)  # Top 10 functions sorted by time
    logging.warning("Finished")
        