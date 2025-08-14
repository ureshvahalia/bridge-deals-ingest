from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path
from functools import total_ordering
from collections import defaultdict
from common_objects import BoardRecord, BridgeEvent, BridgeDeal, lineProf, Direction
from common_objects import create_matchname, translate_vul  , validate_contract, safe_get, get_number
from line_profiler import LineProfiler
import re

@dataclass
class BidMetadata:
    """Metadata for a particular bid"""
    bid_index: int
    note: str = ""
    
    
@dataclass
class Commentary:
    """Commentary related to a deal"""
    text: str
    position: int = 0  # Position in the auction/play where this commentary applies
    
def parse_hands(hands_str: str) -> str:
    """
    Parse hands string from H label and convert it to standard PBN format
    RBN hands are very similar to PBN, so here we do only minimal checking
    of the RBN-specific differences. Other checks done in common code
    """
    # Format: H D:hand1:hand2:hand3:hand4
    result: str = hands_str.replace(";", ":")
    hands: List[str] = result[2:].split(":")
    for h in hands:
        suits: List[str] = h.split(".")
        while len(suits) < 4:
            suits.append("")
            h += "."
    return result[:2] + " ".join(hands)

def parse_auction(auction_str: str) -> str:
    # Parse bidding
    bidding: List[str] = []
    auctionRounds: List[str] = auction_str.split(":")[1:]
    ndx: int = 0
    auctionStrLen: int = len(auction_str)
    while (ndx < auctionStrLen):
        level: str = auction_str[ndx]
        ndx = ndx + 1
        if not level:
            continue
        if level in "1234567":    # regular bid
            strain: str = auction_str[ndx]
            if strain and strain in "SHDCN":
                bidding.append(f"{level}{strain}")
                ndx = ndx + 1
        elif level == "P":
            bidding.append("P")
        elif level == "X":
            bidding.append("X")
        elif level == "R":
            bidding.append("XX")
        elif level == "A":      # All Pass -- end of auction
            break
        elif level == "^":      # Bidding Note, ignore
            ndx = ndx + 1
        else:                   # Exclamation or unexpected character, ignore
            continue
        
    return "-".join(bidding)


def parse_result(result_str: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse result string from R label
    Returns tricks taken and score (if available)
    """
    parts = result_str.split(":")

    if parts[0]:
        match = re.search(r'(\d+)(?:.*?([+-]\d+))?', parts[0])
        if match:
            tricks = int(match.group(1))
            score = match.group(2)
            return tricks, int(score) if score else None
    return None, None

def parse_play(play_str: str) -> List[str]:
    """
    Parse play string from P label
    Returns list of cards played
    """
    parts = play_str.split(":")
    cards = []
    current_suit: Optional[str] = None
    
    for part in parts:
        for i in range(0, len(part)):
            if part[i] in "CDHS":
                current_suit = part[i]
            elif part[i] in "AKQJT98765432":
                if current_suit:
                    cards.append(current_suit+part[i])
                else:
                    break
    
    return cards


def parse_names(names_str: str) -> Dict[Direction, str]:
    """
    Parse names string from N label
    Returns dictionary mapping directions to player names
    """
    parts = names_str.split(":")
    
    names = {}
    
    if len(parts) >= 1:
        ns_parts = parts[0].split("+")
        if len(ns_parts) >= 1 and ns_parts[0]:
            names["N"] = ns_parts[0]
        if len(ns_parts) >= 2 and ns_parts[1]:
            names["S"] = ns_parts[1]
    
    if len(parts) >= 2:
        ew_parts = parts[1].split("+")
        if len(ew_parts) >= 1 and ew_parts[0]:
            names["W"] = ew_parts[0]
        if len(ew_parts) >= 2 and ew_parts[1]:
            names["E"] = ew_parts[1]
    
    return names


def parse_date(date_str: str) -> str:
    """Parse date string from D label"""
    # Just return as is for now - could be expanded to parse more thoroughly
    return date_str

def parse_record(lines: List[str]) -> Optional[Tuple[Dict[str, str], List[str]]]:
    """
    Parse a single RBN record from lines
    Returns dictionary of labels and their content, and a list of free text
    """
    if not lines:
        return None
    
    # Skip lines starting with % (comments)
    if lines[0].startswith("%"):
        lines = lines[1:]
        if not lines:
            return None
    
    labels: Dict[str, str] = {}
    free_text: List[str] = []
    in_comment: bool = False
    
    for line in lines:
        if in_comment:
            if line.endswith("}"):
                in_comment = False
                free_text.append(line[:-1])
            else:
                free_text.append(line)
        elif line.startswith("{"):
            # Free text
            if line.endswith("}"):
                free_text.append(line[1:-1])
            else:
                free_text.append(line[1:])
                in_comment = True
        elif len(line) >= 2 and line[1] == " " and line[0] in "DTLEFKSNBHACPRMI0123456789":
            # Label
            label = line[0]
            content = line[2:].strip()
            labels[label] = content
    
    return labels, free_text

def parse_match_info(fpath: Path, session_str: Optional[str], teams: Optional[str]) -> str:
    # Split the string into parts (handling tabs/spaces)
    stage: Optional[str] = None
    round: Optional[str] = None
    session: Optional[str] = None
    homeTeam: Optional[str] = None
    visitors: Optional[str] = None
    match: Optional[str] = None
    if session_str:
        parts = session_str.strip().split(':')
        main_part = parts[0]
        
        # Initialize description components
        
        # Parse the main part
        if main_part.isdigit():
            # Case: Just a number (e.g., "2")
            session = main_part
        # Handle R## cases (e.g., R16, R32)
        elif main_part.startswith('R') and main_part[1:].isdigit():
            round = f"Of {main_part[1:]}"
        else:
            # Check for known abbreviations
            abbrev_map = {
                'F': 'Finals',
                'P': 'Playoffs',
                'S': 'Semifinal',
                'Q': 'Quarterfinal',
                'I': 'Qualifying'
            }
            
            if main_part in abbrev_map:
                stage = abbrev_map[main_part]
            else:
                # If no abbreviation matches, treat as a subheading
                match = main_part
        
        # Parse the segment/round part if it exists
        if len(parts) > 1:
            if parts[1].isdigit():
                    round = " ".join(filter(None, [parts[1], round]))
            else:
                # If not a number, treat as additional subheading info
                match = " - ".join(filter(None, [match, parts[1]]))
    if teams:
        teamNames: List[str] = teams.split(':')
        homeTeam = teamNames[0]
        if len(teamNames) > 1:
            visitors = teamNames[1]

    return create_matchname(fpath.stem, match, homeTeam, visitors, stage, round, session)

def create_bridge_event(labels: Dict[str, str], fpath: Path) -> BridgeEvent:
    """Create BridgeEvent from labels"""
    event = BridgeEvent()
    
    EName: str = labels.get("E", "")
    TName: str = labels.get("T", "").split(":")[0]
    if EName != "" and TName != "":
        event.EventName = f"{EName} - {TName}"
    else:
        event.EventName = EName or TName or "UNKNOWN"
    
    event.EventLocation = labels.get("L", "UNKNOWN")    
    event.MatchDate = labels.get("D", "UNKNOWN")
    event.ScoringForm = labels.get("F", "UNKNOWN")
    if "S" in labels:
        event.MatchName = parse_match_info(fpath, labels["S"], labels["K"])
    event.FilePath = fpath.as_posix()

    return event

def create_board_record(labels: Dict[str, str], event: BridgeEvent, hands: str, tableID: str, file_path: Path) -> Optional[BoardRecord]:
    """Create BoardRecord from labels without creating a new deal"""
    # Set defaults
    auction: str = ""
    contract: str = ""
    declarer: str = ""
    dealer: str = ""
    vul: str = ""
    
    # Extract contract and declarer
    if "C" in labels:
        parts = labels["C"].split(":")
        if len(parts) == 2:
            contract = parts[0].replace("R", "XX")
            declarer = parts[1]

    # Parse the auction    
    bidding: str = labels.get("A") or ""
    if bidding and bidding[:1] in "NSEW":
        dealer = bidding[0]
        vul = bidding[1:2]
        bidding = bidding[3:].strip(":")
    auction = parse_auction(bidding)
    
    # Extract result
    tricks = 0
    score = None
    
    if "R" in labels:
        tricks, score = parse_result(labels["R"])
    
    # Extract play
    cards_played = []
    
    if "P" in labels:
        cards_played = parse_play(labels["P"])
    
    # Extract names
    names = None
    if "N" in labels:
        names = parse_names(labels["N"])
    
    try:
        dealNum = int(labels.get("B", 0))
    except (ValueError, TypeError):
        dealNum = 0

    # Create board record
    return BoardRecord(
        EventName=event.EventName,
        MatchName=event.MatchName,
        EventLocation=event.EventLocation,
        MatchDate=event.MatchDate,
        ScoringForm=labels.get("F", "UNKNOWN"),
        FilePath=str(file_path),
        DealNum=dealNum,
        Dealer=dealer,
        Vulnerability=vul,
        Hands=hands,
        TableID=tableID,
        North=safe_get(names, "N", ""),
        East=safe_get(names, "E", ""),
        South=safe_get(names, "S", ""),
        West=safe_get(names, "W", ""),
        Contract=contract,
        Declarer=declarer,
        TricksMade=tricks,
        RawScoreNS=score,
        Auction=auction,
        Play="-".join(cards_played),
        Lead="",
        BiddingMD="",  # TBD
        Commentary=""  # TBD
    )

def parse_rbn_file(file_path: Path) -> List[BoardRecord]:
    """
    Parse an RBN file into a list of BridgeEvent and DealRecord pairs
    Handles team matches with open/closed room designations
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by double line feeds
    record_texts = content.split("\n\n")
    
    # Parse each record
    records: List = []
    # Store repeating labels
    repeating_labels: Dict[str, str] = {}
    # Track table ID for team matches (open or closed room)
    open_names: str = ":"
    closed_names: str = ":"
    event: BridgeEvent = BridgeEvent()
    hands: str = ""

    for record_text in record_texts:
        if not record_text.strip():
            continue
        
        # Parse record
        lines = record_text.split("\n")
        parsed: Optional[Tuple[Dict[str, str], List[str]]] = parse_record(lines)
        if not parsed:
            continue
        
        labels, _ = parsed
        event_changed: bool = False
        
        # Check if we need to create a new deal
        newHand: bool = "H" in labels
        
        # Create or update event - check BEFORE applying repeating labels
        for label in "DEFKLST":
            if label in labels:
                if (label not in repeating_labels or labels[label] != repeating_labels[label]):
                    event_changed = True
                    repeating_labels[label] = labels[label]
            elif label in repeating_labels:
                labels[label] = repeating_labels[label]
        
        # Check if we need to create a new event
        if event_changed:
            event = create_bridge_event(labels, file_path)
        
        # Process player names (N label)
        names_value: str = labels.get("N", "")
        numParts: int = 0
        if names_value:
            parts: List[str] = names_value.split(":")
            numParts = len(parts)
            if numParts == 1:
                open_names = parts[0] + ":"
            elif numParts == 2:
                open_names = parts[0] + ":" + parts[1]
            elif numParts == 3:
                is_team_match = True
                if parts[2] == "O":
                    open_names = parts[0] + ":" + parts[1]
                elif parts[2] == "C":
                    closed_names = parts[0] + ":" + parts[1]
                else: # Only 3 pairs named, add a blank pair
                    parts[3] = ""
                    open_names = parts[0] + ":" + parts[1]
                    closed_names = parts[2] + ":" + parts[3]
            elif numParts == 4:
                is_team_match = True
                open_names = parts[0] + ":" + parts[1]
                closed_names = parts[2] + ":" + parts[3]
        
        # Sync repeating_labels with current labels
        for key in "KNBH":
            if key  in labels:
                repeating_labels[key] = labels[key]
            else:
                labels[key] = repeating_labels.get(key, "")

        if newHand: # New hands means new deal
            hands = parse_hands(labels["H"]) if "H" in labels else ""
            labels["N"] = open_names
        else:
            labels["N"] = closed_names
        # Extract board details without creating a new deal
        board_record = create_board_record(labels, event, hands, "O" if newHand else "C", file_path)
        if board_record:
            records.append(board_record)

    return records

# Example usage
if __name__ == "__main__":
    file_path = Path("example.rbn")
    result = parse_rbn_file(file_path)
    print(f"Parsed {len(result)} boards")