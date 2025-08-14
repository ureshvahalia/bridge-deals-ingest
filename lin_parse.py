import logging
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Final
from common_objects import BoardRecord, BridgeDeal, BridgeEvent, lineProf, Direction
from common_objects import create_matchname, sort_holding
from line_profiler import LineProfiler
import re

_LIN_DIRECTION_MAP: Final[List[str]] = ["S", "W", "N", "E"]
_VUL_MAP: Final[Dict[str, str]] = {"o": "Z", "b": "B", "n": "N", "e": "E"}
_HOLDING_SUIT_IDENTIFIERS = ["S", "H", "D", "C"]

def parse_lin_holding(holding: str) -> List[List[str]]:
    """
    :param holding: A LIN style holding like SAKQ952HK65DQ6CKT
    :return:
    """
    holding = holding.replace("10", "T")
    suit_holdings = []
    holding_index = 0
    for id in _HOLDING_SUIT_IDENTIFIERS:
        suit_holding = []
        while holding_index < len(holding):
            c = holding[holding_index]
            if c == id:
                holding_index += 1
                continue
            if c in _HOLDING_SUIT_IDENTIFIERS:
                break
            suit_holding.append(c)
            holding_index += 1
        suit_holdings.append(suit_holding)
    return suit_holdings

def from_lin_deal(dealNum: int, lin_dealer_str: str, vulnerability_str: str, holdings_str: str) -> BridgeDeal:
    """
    Convert LIN deal nodes into a bridgebots deal
    :param lin_dealer_str: Numbers map to directions starting with 1=South
    :param vulnerability_str: LIN vulnerability. One of b,o,n,e
    :param holdings_str: Holding like "1S98643HAJT54DCJT4,SQJTH98DKT7542C76,S5HKQ3DJ93CAKQ832,"
    :return: bridgebots deal representation
    """
    deal: BridgeDeal = BridgeDeal()
    deal.DealNum = dealNum
    deal.Dealer = _LIN_DIRECTION_MAP[int(lin_dealer_str) - 1] if lin_dealer_str else ""
    deal.Vulnerability = _VUL_MAP[vulnerability_str.lower()] if vulnerability_str else ""
    holdings = holdings_str.strip(",").split(",")
    # Convert a holding string like SA63HJ8642DK53CKJ into a PlayerHand
    players_suit_holdings: List[List[List[str]]] = [parse_lin_holding(holding) for holding in holdings]
    player_hands: List[str] = []
    suit_holdings: List[List[str]]
    for suit_holdings in players_suit_holdings:
        suit_holdings_lists: List[List[str]] = [list(suit_holding) for suit_holding in suit_holdings]
        player_hands.append(".".join([sort_holding(s) for s in suit_holdings_lists]))

    deal.Hands = "S:" + " ".join(player_hands)
    return deal

def _parse_lin_nodes(lin_str: str) -> Dict[str, List[str]]:
    """
    Accumulate all the LIN node contents. The node name becomes a key in the returned dict, and all the observed values
     for that key are stored in a list as the dictionary value
    :param lin_str: A LIN board record as a single line
    :return: A dictionary containing parsed LIN nodes
    """
    lin_dict = defaultdict(list)
    while not (lin_str.isspace() or lin_str == ""):
        key, value, lin_str = lin_str.split("|", maxsplit=2)
        if key == "an":  # Bid explanation node
            lin_dict[key].append((len(lin_dict["mb"]) - 1, value))  # Track which bid this announcement applies to
        elif key == "nt":  # Commentary node
            bid_index = None
            play_index = None
            if "pc" in lin_dict:
                play_index = len(lin_dict["pc"]) - 1
            else:
                bid_index = len(lin_dict["mb"]) - 1
            # lin_dict[key].append(Commentary(bid_index, play_index, value))    # TBD
        else:
            lin_dict[key].append(value)
    return lin_dict

def extract_board_number(text: str) -> int:
    match = re.search(r'\d+', text)
    return int(match.group()) if match else 0

def _parse_deal(lin_dict: Dict[str, List[str]], board_name: str) -> Optional[BridgeDeal]:
    """
    Parse the hands, vulnerability, and dealer from the LIN file and create a Deal object
    :return: a Deal representation of the parsed LIN file
    """
    md: List[str] = lin_dict.get("md", [])
    if (len(md) == 0) or (len(md[0]) < 3):  # md[0] must have dealer plus at least one suit and rank character
        logging.info(f"No deal or cards provided: {lin_dict}")
        return None
    deal_info: str = md[0]
    lin_dealer_str = deal_info[0]
    holding_str = deal_info[1:]
    sv: List[str] = lin_dict.get("sv", [])
    vulnerability_str = sv[0] if len(sv) > 0 else ""
    return from_lin_deal(extract_board_number(board_name), lin_dealer_str, vulnerability_str, holding_str)

def canonicalize_bid(bid: str) -> Optional[str]:
    bid = bid.upper().strip("!")
    if bid in ["DBL", "D"]:
        return "X"
    if bid in ["REDBL", "R"]:
        return "XX"
    return bid if ((bid == "P") or ((len(bid) == 2) and (bid[0] in "1234567") and (bid[1] in "SHDCN"))) else None

def _parse_bidding_record(raw_bidding_record: List[str], lin_dict: Dict):  # -> Tuple[List[str], List[BidMetadata]:
    """
    Convert LIN bids to their bridgebots representation. Create BiddingMetadata to capture alerts and bid explanations.
    :return: A pair of the parsed bidding record and the list of BiddingMetadata associated with the auction
    """
    bidding_record = []
    bidding_metadata = []
    # bid_announcements = {bid_index: announcement for (bid_index, announcement) in lin_dict.get("an", [])}
    for bid_index, bid in enumerate(raw_bidding_record):
        canonical_bid = canonicalize_bid(bid)
        if canonical_bid is None:
            raise ValueError(f"encountered unknown bid:{bid}")
        bidding_record.append(canonical_bid)
        # alerted = "!" in bid
        # TBD: Reincorporate BiddingMD processing
        # if alerted or bid_index in bid_announcements:
        #     bidding_metadata.append(BidMetadata(bid_index, canonical_bid, alerted, bid_announcements.get(bid_index)))

    return bidding_record, bidding_metadata


# def _determine_declarer(play_record: List[Card], bidding_record: List[str], deal: Deal) -> Direction:
#     """
#     Use the play or bidding to determine which Direction declared the Board
#     :return: the Direction that declared the Board
#     """
#     if bidding_record == _PASS_OUT_AUCTION:
#         return deal.dealer

#     if len(play_record) == 0:
#         raise ValueError(f"Missing play record")

#     first_card = play_record[0]
#     leader = next(direction for direction in Direction if first_card in deal.player_cards[direction])
#     return leader.previous()


# def _parse_tricks(
#     lin_dict: dict,
#     declarer: Direction,
#     contract: str,
#     play_record: List[Card],
# ) -> int:
#     """
#     Use the play record and claim record to determine how many tricks were taken by declarer
#     :return: the number of tricks taken by declarer
#     """
#     if contract == "PASS":
#         return 0

#     if len(play_record) != 52:
#         raise ValueError(f"Not enough cards played: {len(play_record)}")

#     trump_suit = BiddingSuit.from_str(contract[1:2])
#     tricks = [play_record[i : i + 4] for i in range(0, 52, 4)]
#     lead_direction = declarer.next()
#     offense_directions = [declarer, declarer.partner()]
#     offense_tricks = 0
#     for trick in tricks:
#         evaluator = trick_evaluator(trump_suit, trick[0].suit)
#         winning_index, winning_card = max(enumerate(trick), key=lambda c: evaluator(c[1]))
#         lead_direction = Direction((lead_direction.value + winning_index) % 4)
#         if lead_direction in offense_directions:
#             offense_tricks += 1
#     return offense_tricks


def _parse_player_names(lin_dict: Dict) -> Dict[Direction, str]:
    """
    :return: A mapping from Direction to the name of the player sitting that direction
    """
    if "pn" in lin_dict:
        player_names = lin_dict["pn"][0].split(",")
        if "qx" in lin_dict and len(player_names) > 4:  # True if LIN file is from a multi-board match
            if ["South", "West", "North", "East"] == player_names[4:8]:
                player_names = player_names[0:4]
            elif lin_dict["qx"][0].startswith("o"):  # Open and Closed rooms start with o or c
                player_names = player_names[0:4]
            else:
                player_names = player_names[4:8]
    else:
        player_names = ["SOUTH", "WEST", "NORTH", "EAST"]
    direction = Direction.SOUTH
    name_dict = {}
    for i in range(4):
        name_dict[direction] = player_names[i]
        direction = direction.next()
    return name_dict


def _parse_board_name(lin_dict: Dict) -> str:
    if "qx" in lin_dict:
        return lin_dict["qx"][0]
    if "ah" in lin_dict:
        return lin_dict["ah"][0]
    return "x0" # default


def _parse_board_record(lin_dict: Dict[str, List[str]], board_name: str, event: BridgeEvent, file_path: Path, deal: BridgeDeal, resultStr: str) -> BoardRecord | None:
    """
    Construct a BoardRecord object from the parsed lin_dict and deal
    """
    player_names = _parse_player_names(lin_dict)
    raw_bidding_record = lin_dict["mb"]
    bidding_record, bidding_metadata = _parse_bidding_record(raw_bidding_record, lin_dict)
    play_record = [cs.upper() for cs in lin_dict["pc"]]
    declarer: Optional[str] = None
    contract: Optional[str] = None
    tricks: Optional[int] = None
    resultStr = resultStr.strip().upper()
    if resultStr and resultStr != ",":
        if resultStr == "P":
            contract = "AP"
        else:
            match = re.match(r"^(\d)([SHDNTC])([NESW])(X{0,2})([-+=]\d*|=)$", resultStr)
            if match:
                level, suit, declarer, doubling, result = match.groups()
                contract = level + suit + doubling
                tricks = 6 + int(level)
                ot_or_down = int(result[1:]) if len(result) > 1 else 0
                if result.startswith("+"):
                    # Made with overtricks
                    tricks += ot_or_down
                elif result.startswith("-"):
                    # Went down
                    tricks -= ot_or_down
    claim: Optional[int] = None
    if "mc" in lin_dict:
        mc_val: List[str] = lin_dict["mc"]
        if len(mc_val) > 0:
            claim_str: str = lin_dict["mc"][0]
            if isinstance(claim_str, int):
                claim = int(claim_str)
    if tricks is not None and claim is not None and tricks != claim:
        print (f"claim of {claim} tricks does not match result of {tricks} tricks")
    elif tricks is None and claim is not None:
        tricks = claim
        
    return BoardRecord(
        EventName=event.EventName,
        MatchName=event.MatchName,
        ScoringForm=event.ScoringForm,
        FilePath=str(file_path),
        DealNum=deal.DealNum,
        Dealer=deal.Dealer,
        Vulnerability=deal.Vulnerability,
        Hands=deal.Hands,
        TableID=board_name[:1],
        North=player_names[Direction.NORTH],
        East=player_names[Direction.EAST],
        South=player_names[Direction.SOUTH],
        West=player_names[Direction.WEST],
        Contract=contract,
        Declarer=declarer,
        TricksMade=tricks,
        RawScoreNS=None,
        Auction="-".join(bidding_record),
        Play="_".join(play_record),
        Lead="",
        BiddingMD="",  # TBD
        Commentary=""  # TBD
    )

def _combine_header(file) -> str:
    """
    :returns: The combined header lines of a multi-board LIN.
    """
    combined = ""
    line = file.readline()
    while line:
        combined += line.replace("\n", "")
        if combined.endswith("|pg||"):
            return combined
        line = file.readline()
    raise ValueError(f"Invalid multi-lin header in file: {file}")

# def parse_lin_str(lin_str: str) -> List[DealRecord]:
#     """
#     Parse a board-per-lin lin str
#     :param lin_str: lin data
#     :return: Collected list of DealRecords each of which has a BoardRecord for each occurrence of a deal
#     """
#     # Maintain a mapping from deal to board records to create a single deal record per deal
#     records = defaultdict(list)
#     for line in lin_str.splitlines():
#         lin_dict = _parse_lin_nodes(line)
#         board_name: str = _parse_board_name(lin_dict)
#         deal:Deal = _parse_deal(lin_dict, board_name)
#         board_record = _parse_board_record(lin_dict, board_name, deal, "")
#         if board_record is not None:
#             records[deal].append(board_record)
#     return [DealRecord(deal, board_records) for deal, board_records in records.items()]

# def parse_single_lin(file_path: Path) -> List[DealRecord]:
#     """
#     Parse a board-per-line LIN file
#     :param file_path: path to single-board LIN file
#     :return: A list of parsed DealRecords, one for each line of the LIN file
#     """
#     with open(file_path) as lin_file:
#         return parse_lin_str(lin_file.read())
    
# from event import BridgeEvent

def parse_event(input_file: Path, header: Dict[str, List[str]]) -> BridgeEvent:
    # Prepare event data - do everything except the actual database add
    if "vg" in header:
        if len(header["vg"]) != 1:
            print(f"Multiple vg entries found: {header['vg']}") # TBD: Eliminate or redo
        
        vg_data = header["vg"][0].split(",")
        header_keys = [
            "Event", "Match", "MatchType", "StartBoard",
            "EndBoard", "Team1", "Carry1", "Team2", "Carry2"
        ]
        header_dict = dict(zip(header_keys, vg_data))
        
        return BridgeEvent(
            EventName=header_dict.get("Event") or "UNKNOWN",
            MatchName=create_matchname(input_file.stem, header_dict.get("Match"), header_dict.get("Team1"), 
                                       header_dict.get("Team2"), None, None, None),
            ScoringForm=header_dict.get("MatchType") or "UNKNOWN",
            FilePath=str(input_file)
        )
    else:
        return BridgeEvent(FilePath=str(input_file))

def parse_lin_file(file_path: Path) -> List[BoardRecord]:
    """
    Parse a multi-board session LIN file
    :param file_path: path to multi-board LIN file
    :return: A list of parsed DealRecords corresponding to the session in the LIN file
    """
    board_records: List[BoardRecord] = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as lin_file:
        # Read the first line of the file to get the header
        header_line: str = _combine_header(lin_file)
        header: Dict[str, List[str]] = _parse_lin_nodes(header_line)
        event_obj = parse_event(file_path, header)
        rs: List[str] = header.get("rs", [])
        board_strings: List[str] = []
        board_index: int = -1
        resultList: List[str] = rs[0].split(",")
        nresults: int = len(resultList)
        for line in lin_file:
            if line.isspace() or line == "":
                continue
            # Boards are split with a qx node
            if line.startswith("qx"):
                board_index += 1
                board_strings.append("")
            board_strings[board_index] += line
        # if nresults != len(board_strings):
        #     print(f"Mismatched results")
        # Create single-line LIN for each record
        board_single_strings = [board_string.replace("\n", "") for board_string in board_strings]
        # Maintain a mapping from deal to board records to create a single deal record per deal
        records = defaultdict(list)
        bno: int = 0
        for board_single_string in board_single_strings:
            try:
                lin_dict: Dict[str, List[str]] = _parse_lin_nodes(board_single_string)
                lin_dict["pn"] = header.get("pn", [])
                board_name: str = _parse_board_name(lin_dict)
                deal: Optional[BridgeDeal] = _parse_deal(lin_dict, board_name)
                if deal:
                    board_record: Optional[BoardRecord] = _parse_board_record(lin_dict, board_name, event_obj, file_path, deal, 
                                                                            resultList[bno] if bno < nresults else "")
                    if board_record:
                        board_records.append(board_record)
            except (ValueError, AssertionError, KeyError) as e:
                logging.warning(f"Malformed record {board_single_string[:80]}: {e}")
            bno = bno + 1
        lin_file.close()
    return board_records

class LinType(Enum):
    SINGLE = 0
    MULTI = 1
