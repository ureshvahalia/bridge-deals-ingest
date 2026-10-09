import csv
import logging
from pathlib import Path
from typing import List, Optional
from common_objects import BoardRecord


def _to_int(value: str) -> Optional[int]:
    return int(value) if value.strip() else None


def parse_csv_file(file_path: Path) -> List[BoardRecord]:
    """
    Parse a RawData.csv file into BoardRecords.
    :param file_path: path to a CSV file with RawData.csv column layout
    :return: A list of BoardRecords parsed from the file
    """
    board_records: List[BoardRecord] = []
    with open(file_path, "r", encoding="utf-8", errors="replace", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            try:
                board_records.append(BoardRecord(
                    EventName=row.get("EventName", "UNKNOWN"),
                    MatchName=row.get("MatchName", "UNKNOWN"),
                    EventLocation=row.get("EventLocation") or None,
                    MatchDate=row.get("MatchDate") or None,
                    ScoringForm=row.get("ScoringForm", "UNKNOWN"),
                    FilePath=row.get("FilePath", ""),
                    DealNum=_to_int(row.get("DealNum", "")) or 0,
                    Dealer=row.get("Dealer", ""),
                    Vulnerability=row.get("Vulnerability", "X"),
                    Hands=row.get("Hands", ""),
                    DDS=row.get("DDS") or None,
                    TableID=row.get("TableID", "").upper(),
                    North=row.get("North", ""),
                    East=row.get("East", ""),
                    South=row.get("South", ""),
                    West=row.get("West", ""),
                    Lead=row.get("Lead") or None,
                    Contract=row.get("Contract") or None,
                    Declarer=row.get("Declarer") or None,
                    TricksMade=_to_int(row.get("TricksMade", "")),
                    RawScoreNS=_to_int(row.get("RawScoreNS", "")),
                    Auction=row.get("Auction", ""),
                    Play=row.get("Play", ""),
                    BiddingMD=row.get("BiddingMD", ""),
                    Commentary=row.get("Commentary", ""),
                    Claim=_to_int(row.get("Claim") or ""),
                ))
            except (ValueError, KeyError) as e:
                logging.warning(f"Malformed CSV row in {file_path}: {e}")
    return board_records
