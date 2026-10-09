import logging
import cProfile
import pstats
import sys
import faulthandler
from line_profiler import LineProfiler
from pathlib import Path
from argparse import ArgumentParser
from typing import List, Optional
from common_objects import BoardRecord, lineProf
from process_records import process_and_analyze_records, process_records, analyze_records
from ingest import ingest_files
from play_analysis import normalize_db, play_analysis_from_db, repair_plays
from dds_wrapper import load_dd_cache

def _main_impl(lp: LineProfiler) -> None:
    # Process arguments
    arg_list = ArgumentParser(description="Process bridge game files and generate analysis")
    arg_list.add_argument("db_locn", help="Database folder path for output files")
    arg_list.add_argument("files", nargs="*", help="Bridge data files or directories to process (PBN, LIN, JSON, RBN, CSV)")
    arg_list.add_argument("--profile", action="store_true", help="Enable performance profiling")
    arg_list.add_argument("-d", "--doubledummy", action="store_true", help="Generate double-dummy analysis")
    arg_list.add_argument("--reuse-dd", metavar="HANDS",
                          help="Double-dummy analysis reusing an earlier hands.csv (file or DB folder): "
                               "only hands not in it are computed. Implies -d")
    arg_list.add_argument("--play", action="store_true",
                          help="Card-by-card play analysis with PlayDD, written to <db_locn>/play/")
    arg_list.add_argument("--play-depth", choices=("line", "full"), default="full",
                          help="Play analysis depth (default full)")
    arg_list.add_argument("--play-workers", type=int, default=None,
                          help="Play analysis worker processes (default: CPU count)")
    mode_group = arg_list.add_mutually_exclusive_group()
    mode_group.add_argument("-a", "--analyzeonly", action="store_true", help="Analyze existing DB only")
    mode_group.add_argument("-p", "--processonly", action="store_true", help="Only process, do not analyze")
    mode_group.add_argument("--playonly", action="store_true",
                            help="Only run play analysis on the existing DB in db_locn")
    mode_group.add_argument("--normalizeplay", action="store_true",
                            help="Rewrite Play in the existing DB's boards.csv and all.csv in play order (in place)")
    mode_group.add_argument("--repairplay", action="store_true",
                            help="Re-read the given files and replace only Play/Claim for their boards in the "
                                 "existing DB (in place); other columns and UIDs are unchanged")
    args = arg_list.parse_intermixed_args()     # files may follow options: "DB --repairplay files..."
    if not args.files and not (args.analyzeonly or args.playonly or args.normalizeplay):
        arg_list.error("files are required unless --analyzeonly, --playonly or --normalizeplay")
    output_dir: Path = Path(args.db_locn if args.db_locn else "./output")
    # faulthandler.enable()  # Enable segfault handler for better debugging of native code issues

    try:
        # Run the ingestion
        if args.analyzeonly:
            analyze_records(output_dir)
        elif args.playonly:
            play_analysis_from_db(output_dir, args.play_depth, args.play_workers)
        elif args.normalizeplay:
            normalize_db(output_dir)
        elif args.repairplay:
            repair_plays(output_dir, [Path(f) for f in args.files])
        else:
            # Read earlier DD results before anything is written: output_dir may be the same DB
            dd_cache = load_dd_cache(Path(args.reuse_dd)) if args.reuse_dd else None
            reclist: List[BoardRecord] = ingest_files([Path(f) for f in args.files], parallelize=True)
            if len(reclist) > 0:
                output_dir.mkdir(exist_ok=True)
                play_options = {"depth": args.play_depth, "workers": args.play_workers} if args.play else None
                generate_dd = args.doubledummy or dd_cache is not None
                if args.processonly:
                    process_records(reclist, generate_dd, output_dir, play_options, dd_cache)
                else:
                    process_and_analyze_records(reclist, generate_dd, output_dir, play_options, dd_cache)
            
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
        