import json
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
from common_objects import BoardRecord, lineProf, translate_vul
from common_objects import create_matchname, get_number, validate_contract, safe_get
from line_profiler import LineProfiler
import re

def parse_json_hand(hand: List[str]) -> str:
    handStr = ".".join(item or "" for item in hand).replace("10", "T")
    assert len(handStr) == 16   # 13 + 3 "."s
    return handStr

def from_json_deal(deal_data: dict) -> Tuple[str, str, str, str]:
    # Process dealer, vul, and hands info from JSON deal format
    # Extract dealer - convert single letter to Direction enum
    dealer: str = deal_data["Dealer"]
    
    # Extract vulnerability
    vul: str = translate_vul(deal_data["Vulnerable"])
    
    # Convert hands from JSON format to PlayerHand objects
    hands: str = f"N:" + " ".join([parse_json_hand(deal_data[h]) for h in ["N", "E", "S", "W"]])
    dds: str = str(deal_data.get("DDS", "") or "")
    return (dealer, vul, hands, dds)

def parse_names(players: Optional[Dict[str, Dict[str, str]]]) -> Dict[str, Dict[str, str]]:
    # Returns dictionary mapping directions to player names
    OR_names: Dict[str, str] = safe_get(players, "OR", {})
    CR_names: Dict[str, str] = safe_get(players, "CR", {})

    return  {
        'OR':   {
            "north_name": safe_get(OR_names, 'N', 'UNKNOWN'),
            "south_name": safe_get(OR_names, 'S', 'UNKNOWN'),
            "east_name":  safe_get(OR_names, 'E', 'UNKNOWN'),
            "west_name":  safe_get(OR_names, 'W', 'UNKNOWN')
        },
        'CR':   {
            "north_name": safe_get(CR_names, 'N', 'UNKNOWN'),
            "south_name": safe_get(CR_names, 'S', 'UNKNOWN'),
            "east_name":  safe_get(CR_names, 'E', 'UNKNOWN'),
            "west_name":  safe_get(CR_names, 'W', 'UNKNOWN')
        }
    }

def parse_json_file(file_path: Path) -> List[BoardRecord]:
    """
    Parse a single JSON file and return events and deal records.
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        List of tuples containing (BridgeEvent, List[DealRecord])
    """
    def clean_json_content(content):
        # Remove or replace invalid control characters
        # Keep only valid JSON control characters (\n, \r, \t, etc.)
        cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content)
        return cleaned
    
    board_records = []

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        cleaned_content = clean_json_content(content)
        data = json.loads(cleaned_content)
    
    # Extract basic event information
    event_name = (data.get('Tournament') or '') + ': ' + (data.get('Event') or '')
    location = data.get('Location') or 'UNKNOWN'
    start_date = data.get('Start-Date') or 'UNKNOWN'
    scoring: str = (data.get('Scoring') or data.get('Type') or 'UNKNOWN').upper()
    if scoring.startswith("IMP") or scoring.startswith("TEAM"):
        scoring = "IMPs"
    
    # Process each match
    for match_idx, match in enumerate(data.get('Matches', []), 1):
        # Create BridgeEvent
        match_name = create_matchname(file_path.stem, None, match.get('HomeTeam'), match.get('AwayTeam'), 
                                      match.get('Section'), match.get('Stage'), match.get('Round'))
        
        raw_event_data = f"{event_name},{match_name},{scoring}"
        
        # Process each session
        for session in match.get('Sessions', []):
            session_date = session.get('Date', start_date)
            session_number: Optional[int] = session.get('SessionNo')
            match_name += f": Session {session_number}" if session_number else ""
            players: Dict[str, Dict[str, str]] = parse_names(session.get('Players'))
            
            deal_records = []
            # Process each board
            for board in session.get('Boards', []):
                board_no: int = board.get('BoardNo', 0)
                deal_data = board.get('Deal')
                if deal_data is None:
                    continue
                
                # Create Deal
                dealer, vul, hands, dds = from_json_deal(deal_data)
                # Create BoardRecords for both rooms (OR and CR)
                for room_name in ['OR', 'CR']:
                    room_data = board.get(room_name)
                    if not room_data:
                        continue
                    
                    # Extract contract information
                    declarer: Optional[str] = room_data.get('Declarer') or None
                    lead = room_data.get('Lead', '')
                    contractStr: Optional[str] = validate_contract(room_data.get('Contract'))
                    raw_score_ns = 0
                    
                    # Get players for this room
                    auction: Dict = room_data.get('Auction')
                    bidList: List = auction.get('Calls', []) if auction else []
                    playStr: List[List[str]] = (room_data.get('Play') or {}).get('Tricks', [[]])
                    playCards: List[str] = []
                    try:
                        for trick in playStr:
                            for card in trick:
                                if card is not None:
                                    playCards.append(card)
                    except:
                        pass
                    if contractStr is None and len(bidList) == 0:
                        continue
                    tricksMade: Optional[int] = room_data.get('Tricks') or (0 if contractStr == 'Pass' else None)
                    board_record = BoardRecord(
                        EventName=event_name,
                        MatchName=match_name + f": Session {session_number}" if session_number else "",
                        EventLocation=location,
                        MatchDate=session_date,
                        ScoringForm=scoring,
                        FilePath=str(file_path),
                        DealNum=board_no,
                        Dealer=dealer,
                        Vulnerability=vul,
                        Hands=hands,
                        DDS=dds,
                        TableID=room_name[:1],
                        North=players[room_name]["north_name"].upper(),
                        East=players[room_name]["east_name"].upper(),
                        South=players[room_name]["south_name"].upper(),
                        West=players[room_name]["west_name"].upper(),
                        Contract=contractStr,
                        Declarer=declarer,
                        TricksMade=tricksMade,
                        RawScoreNS=None,
                        Auction="-".join(bidList).replace("R", "XX"),
                        Play="-".join(playCards),
                        Lead=lead,
                        BiddingMD="",  # TBD
                        Commentary=""  # TBD
                    )
                
                    board_records.append(board_record)
    return board_records
