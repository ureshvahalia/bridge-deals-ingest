import sys
import logging
import bridgebots
from typing import List, Iterator, Dict, Any, Tuple
from pathlib import Path
from argparse import ArgumentParser
from dataclasses import dataclass
from configparser import ConfigParser
from bridgebots import DealRecord, BoardRecord
from event import EventDB, BridgeEvent
from boards import BoardsDB, BridgeBoard
from deals import VulnerabilityType, BridgeDeal, DealsDB
from db_comp import BridgeDB, DBType
import cProfile
import pstats

logger = logging.getLogger(__name__)

@dataclass
class VuGraphConfig:
    """Configuration for VuGraph processing."""
    bridge_db_path: Path
    bridge_db_type: DBType

    @classmethod
    def from_config_file(cls, config_path: Path) -> 'VuGraphConfig':
        """Load configuration from a file."""
        config = ConfigParser()
        config.read(config_path)
        bridge_db_type_str=config.get('Type', 'bridge_db_type', fallback=DBType.CSV.value)
        return cls(
            bridge_db_path=Path(config.get('Paths', 'bridge_db_path', fallback='./DB')),
            bridge_db_type=DBType(bridge_db_type_str)
        )
# end class VuGraphConfig

class VuGraphProcessor:
    
    """Processes VuGraph files and manages event records."""
    def __init__(self, config: VuGraphConfig):
        self.config = config
        self.bridge_db = BridgeDB.create(config.bridge_db_type, config.bridge_db_path)
        self.event_db = EventDB(self.bridge_db)
        self.deals_db = DealsDB(self.bridge_db)
        self.boards_db = BoardsDB(self.bridge_db)

    def _process_file_events(self, input_file: Path, parser_func) -> List[Dict[str, Any]]:
        """
        Process multiple events from a file using the specified parser
        :param input_file: Path to the file
        :param parser_func: Function to parse the file
        :return: List of dictionaries with event, deal, and board information
        """
        events_data: List[Tuple[BridgeEvent, List[DealRecord]]] = parser_func(input_file)
        results: List[Dict[str, Any]] = []
        
        for event_obj, deals in events_data:
            # Prepare deal objects for this event
            deal_objects: List[BridgeDeal] = []
            board_objects_by_deal: List[List[BoardRecord]] = []
            
            # Process deals
            for result in deals:
                if not result.board_records:
                    continue
                # deal_number = self._extract_deal_number(result)
                deal: BridgeDeal = BridgeDeal(
                    0,  # eid will be added later
                    0,  # mid will be added later
                    result.deal.dealNum,
                    result.deal.dealer,
                    VulnerabilityType.translate_vul(result.deal.ns_vulnerable, result.deal.ew_vulnerable),
                    str(result.deal.hands)
                )
                deal_objects.append(deal)
                # Store board records for this deal
                board_objects_by_deal.append(result.board_records)
            
            # Add this event's results
            results.append({
                "file_path": input_file,
                "event_obj": event_obj,
                "deal_objects": deal_objects,
                "board_objects_by_deal": board_objects_by_deal
            })
        
        return results

    def _parse_rbn_file(self, input_file: Path) -> Dict[str, Any] | None:
        return None

    def _extract_deal_number(self, result: DealRecord) -> int:
        """Helper method to extract deal number from board record"""
        if not result.board_records:
            return 0
            
        name = result.board_records[0].board_name
        if not name:
            return 0
            
        # More efficient parsing of deal number
        try:
            if name[0] in ('o', 'c', 'O', 'C'):
                return int(name[1:])
            return int(name)
        except (ValueError, IndexError):
            return 0

    def sync_all(self) -> None:
        self.event_db.sync()
        self.deals_db.sync()
        self.boards_db.sync()
        
# end class VuGraphProcessor

logger = logging.getLogger(__name__)

def process_paths(paths: List[str]) -> Iterator[Path]:
    """
    Process a list of file/directory paths and yield Path objects for all .lin files
    
    Args:
        paths: List of file or directory paths to process
    
    Yields:
        Path objects for each .lin file found
    """
    for path_str in paths:
        path = Path(path_str)
        
        if not path.exists():
            logger.error(f"Path does not exist: {path}")
            continue
            
        if path.is_file():
            yield path
        elif path.is_dir():
            # Recursively process all .lin files in directory
            for file_path in path.rglob('*.*'):
                yield file_path
        else:
            logger.error(f"Path is neither file nor directory: {path}")

from datetime import datetime
from processDeals import process_deals, expand_matches
from parallel import parallel_process_files
from rbn_parse import parse_multi_rbn
from json_parse import parse_json_file
from pbn_parse import parse_pbn_file

from line_profiler import LineProfiler

def process_results(processor, results: List[Any], force):
    # Filter out None results or results with no event_obj
    valid_results = [r for r in results if r is not None and r["event_obj"] is not None]
    
    if not valid_results:
        return
    
    # Sort the results by event_name and then match_name
    valid_results.sort(key=lambda x: (x["event_obj"].EventName, x["event_obj"].MatchName))

    # Extract all event objects
    events = [r["event_obj"] for r in valid_results]
    
    # Process events in batch
    event_results = processor.event_db.add_batch(events, force)
    print("events added")
    
    # Collect all deals for batch processing
    all_deals = []
    deal_to_result_map = {}  # Maps deal position in all_deals to its result index and deal index
    
    # Now process deals and boards for each event
    for i, (result, (eid, mid)) in enumerate(zip(valid_results, event_results)):
        if eid > 0 and mid > 0:
            # Update deals and prepare for batch processing in one pass
            for j, deal in enumerate(result["deal_objects"]):
                deal.EventUID = eid
                deal.MatchID = mid
                all_deals.append(deal)
                deal_to_result_map[len(all_deals) - 1] = (i, j)
    
    # Process all deals in batch
    if all_deals:
        deal_uids = processor.deals_db.add_batch(all_deals)
        print("deals added")
        
        # Collect all boards for batch processing
        all_boards = []
        
        for k, uid in enumerate(deal_uids):
            if uid == 0:
                continue
                
            result_idx, deal_idx = deal_to_result_map[k]
            result = valid_results[result_idx]
            
            for board in result["board_objects_by_deal"][deal_idx]:
                board_dict = vars(board)
                board_dict["DealUID"] = uid
                all_boards.append(BridgeBoard(board_dict))
        
        print("adding boards")
        # Process all boards in batch
        if all_boards:
            processor.boards_db.add_batch(all_boards)
            
def main(lp: LineProfiler):
    """Main entry point for the VuGraph processor."""
    profiler = cProfile.Profile()
    profiler.enable()
    logging.basicConfig(level=logging.WARNING)
    
    parser = ArgumentParser(description="Process VuGraph files")
    parser.add_argument("db_locn", help="Databse folder path")
    parser.add_argument("files", nargs="+", help="LIN files or directories to process")
    parser.add_argument("--profile", action="store_true", help="LIN files or directories to process")
    parser.add_argument("-f", "--force", action="store_true", 
                       help="Force add new event even if one exists")
    args = parser.parse_args()

    try:
        logger.warning(f"Starting, time {datetime.now().time()}")
        config = VuGraphConfig.from_config_file(Path("config.ini"))
        if args.db_locn is not None:
            config.bridge_db_path = Path(args.db_locn)
        for file in config.bridge_db_path.iterdir():
            if file.is_file():
                file.unlink()
        processor = VuGraphProcessor(config)
        
        success_count = 0
        error_count = 0
        
        def process_single_file(file_path) -> List[Dict[str, Any]]:
            try:
                # Parse LIN file
                suf: str = file_path.suffix.lower()
                if (suf == '.lin'):
                    return processor._process_file_events(file_path, bridgebots.parse_multi_lin)
                elif (suf == '.rbn'):
                    return processor._process_file_events(file_path, parse_multi_rbn)
                elif (suf == ".json"):
                    return processor._process_file_events(file_path, parse_json_file)
                elif (suf == ".pbn"):
                    return processor._process_file_events(file_path, parse_pbn_file)
                else:
                    logger.warning(f"Skipping unsupported file: {file_path}")
                    return []
            except Exception as e:
                logger.error(f"Error processing {file_path}: {str(e)}")
                return []

        # lp.add_function(processor.event_db.add_batch)
        # lp.add_function(processor.boards_db.add_batch)
        # lp.add_function(expand_matches)
        lp.add_function(process_deals)
        # lp.add_function(parse_multi_rbn)
        # lp.add_function(process_single_file)
        # Get all files to process first
        in_files = list(process_paths(args.files))
        file_results: List[Any] = parallel_process_files(in_files, process_single_file)
        # file_results: List[Any] = [process_single_file(f) for f in in_files]
        logger.warning(f"Parsed files, time {datetime.now().time()}")
        # Flatten results since each file may now contain multiple events
        results = []
        for file_result in file_results:
            if file_result:  # Check if the list is not empty
                results.extend(file_result)
        logger.warning(f"Collated results, time {datetime.now().time()}")

        process_results(processor, results, args.force)
        
        # Count successes and failures
        success_count = sum(1 for r in results if r is not None)
        error_count = len(results) - success_count

        logger.info(f"Processing complete. Successfully processed {success_count} files.")
        processor.sync_all()
        process_deals(config.bridge_db_type, config.bridge_db_type, config.bridge_db_path)
        profiler.disable()
        stats = pstats.Stats(profiler)
        stats.strip_dirs().sort_stats('time').print_stats(10)  # Top 10 functions sorted by time
        logger.warning(f"Finished, time {datetime.now().time()}")
        if error_count > 0:
            logger.warning(f"Encountered errors in {error_count} files.")
            # sys.exit(1)
            
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}")
        # sys.exit(1)

if __name__ == "__main__":
    lp = LineProfiler()
    if '--profile' in sys.argv:
        
        # Add ALL target functions in one place
        lp.add_function(main)
        lp.add_function(process_results)
        
        # Profile the entire workflow
        lp.runctx('main(lp)', globals(), locals={'lp': lp})
        lp.print_stats()
    else:
        main(lp)  # Normal execution with debugger support
