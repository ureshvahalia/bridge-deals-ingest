import threading
import logging
from pbn_parse import parse_pbn_file
from lin_parse import parse_lin_file
from json_parse import parse_json_file
from rbn_parse import parse_rbn_file
from pathlib import Path
from typing import List, Dict, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from common_objects import BoardRecord
from process_records import process_records

class DataCollector:
    """Thread-safe collector for processed data."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.boards: List[BoardRecord] = []
        self.success: int = 0
    
    def add_batch(self, batch: List[BoardRecord]):
        """Add a batch of records in a thread-safe manner."""
        with self._lock:
            self.boards.extend(batch)
            self.success = self.success + 1
            
# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

def get_file_extension(file_path: Path) -> str:
    """Get file extension in lowercase."""
    return file_path.suffix.upper()

parsers: Dict[str, Callable[[Path], List[BoardRecord]]] = {}

def register_parser(ext: str, parser_func: Callable[[Path], List[BoardRecord]]):
    parsers[ext.upper()] = parser_func

def get_parser_for_file(file_path: Path) -> Callable[[Path], List[BoardRecord]]:
    """Return the appropriate parser function for the file type."""
    return parsers[get_file_extension(file_path)]

# Register parsers
register_parser(".PBN", parse_pbn_file)
register_parser(".JSON", parse_json_file)
register_parser(".RBN", parse_rbn_file)
register_parser(".LIN", parse_lin_file)

def process_file(file_path: Path, collector: DataCollector) -> None:
    """Process a single file and add results to collector."""
    try:
        parser: Callable[[Path], List[BoardRecord]] = get_parser_for_file(file_path)
        raw_data: List[BoardRecord] = parser(file_path)
        collector.add_batch(raw_data)
        
    except Exception as e:
        logging.error(f"Error processing file {file_path}: {str(e)}")

def collect_files(paths: List[Path]) -> List[Path]:
    """Collect all supported files from the given paths."""
    files = []
    
    for path in paths:
        if path.is_file():
            if get_file_extension(path) in parsers.keys():
                files.append(path)
        elif path.is_dir():
            # Recursively find all supported files
            for ext in parsers.keys():
                files.extend(path.rglob(f"*{ext}"))
    
    return files

def ingest_files(paths: List[Path], parallelize: bool = True, output_dir: Path = Path(".")) -> List[BoardRecord]:
    """
    Main driver function to ingest bridge files and generate CSV outputs.
    
    Args:
        paths: List of file or directory paths to process
        parallelize: Maximum number of threads for parallel processing
        output_dir: Directory to write output CSV files
    """
    # Collect all files to process
    files_to_process = collect_files(paths)
    
    if not files_to_process:
        logging.warning("No supported files found to process")
        return []
    
    logging.info(f"Found {len(files_to_process)} files to process")
    
    # Initialize thread-safe components
    collector = DataCollector()
    
    # Process files (serial or parallel based on parallelize)
    if parallelize: # Parallel processing
        with ThreadPoolExecutor() as executor:
            # Submit all files for processing
            future_to_file = {
                executor.submit(process_file, file_path, collector): file_path
                for file_path in files_to_process
            }
            
            # Wait for completion and handle any errors
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Failed to process {file_path}: {str(e)}")
    else:   # Serial processing
        for file_path in files_to_process:
            try:
                process_file(file_path, collector)
            except Exception as e:
                logging.error(f"Failed to process {file_path}: {str(e)}")
                    
    logging.info(f"Successfully processed {collector.success} files")
    logging.info(f"Processing complete. Generated {len(collector.boards)} total records")
    
    return collector.boards
