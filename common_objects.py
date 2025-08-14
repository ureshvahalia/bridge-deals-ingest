import re
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, List, Any
from enum import Enum, IntEnum
from functools import total_ordering
from line_profiler import LineProfiler

@dataclass
class BoardRecord:
    """Represents a bridge board with all its attributes."""
    EventName: str = "UNKNOWN"
    MatchName: str = "UNKNOWN"
    EventLocation: Optional[str] = None
    MatchDate: Optional[str] = None
    ScoringForm: str = "UNKNOWN"
    FilePath: str = ""
    DealNum: int = 0
    Dealer: str = ""
    Vulnerability: str = "X"
    Hands: str = ""
    DDS: Optional[str] = None
    TableID: str = ""
    North: str = ""
    East: str = ""
    South: str = ""
    West: str = ""
    Lead: Optional[str] = None
    Contract: Optional[str] = None
    Declarer: Optional[str] = None
    TricksMade: Optional[int] = None
    RawScoreNS: Optional[int] = None
    Auction: Optional[str] = ""
    Play: str = ""
    BiddingMD: str = ""
    Commentary: str = ""

vulDict: Dict[str, str] = {
    'Z': 'Z', 
    'NONE': 'Z',
    'N': 'N',
    'NS': 'N',
    'E': 'E',
    'EW': 'E',
    'WE': 'E',
    'B': 'B',
    'BOTH': 'B',
    'ALL': 'B',
    'X': 'X'
}

vulDDS: Dict[str, int] =    {
    'Z': 0,
    'B': 1,
    'N': 2,
    'E': 3
}

def translate_vul(vulStr: str) -> str:
    return vulDict[vulStr.upper()]

vul_sides: Dict[str, Tuple[bool, bool]] =  {
    'X': (False, False),
    'Z': (False, False),
    'N': (True, False),
    'E': (False, True), 
    'B': (True, True)
}

def parse_vulnerability(vuln_str: str) -> Tuple[bool, bool]:
    return vul_sides[vulDict[vuln_str]]

dealVulnerabilities: List[str] = [
    'E',      # deal 0 has value for deal 16
    'Z',
    'N',
    'E',
    'B',
    'N',
    'E',
    'B',
    'Z',
    'E',
    'B',
    'Z',
    'N',
    'B',
    'Z',
    'N'
]

@total_ordering
class Rank(Enum):
    TWO     = (2, "2")
    THREE   = (3, "3")
    FOUR    = (4, "4")
    FIVE    = (5, "5")
    SIX     = (6, "6")
    SEVEN   = (7, "7")
    EIGHT   = (8, "8")
    NINE    = (9, "9")
    TEN     = (10, "T")
    JACK    = (11, "J")
    QUEEN   = (12, "Q")
    KING    = (13, "K")
    ACE     = 14, "A"

    __from_str_map__ = {
        "2": TWO,
        "3": THREE,
        "4": FOUR,
        "5": FIVE,
        "6": SIX,
        "7": SEVEN,
        "8": EIGHT,
        "9": NINE,
        "10": TEN,
        "T": TEN,
        "J": JACK,
        "Q": QUEEN,
        "K": KING,
        "A": ACE,
    }

    @classmethod
    def from_str(cls, rank_str: str) -> "Rank":
        return Rank(cls.__from_str_map__[rank_str.upper()])

    def __lt__(self, other) -> bool:
        return self.value[0] < other.value[0]

    def __repr__(self) -> str:
        return self.name

    def abbreviation(self) -> str:
        return self.value[1]


def get_number(s: str | None) -> Optional[int]:
    match: re.Match | None = re.search(r'-?\d+', s) if s else None
    return int(match.group()) if match else None

@total_ordering
class Direction(IntEnum):
    NORTH = 0
    EAST = 1
    SOUTH = 2
    WEST = 3

    __from_str_map__ = {"N": NORTH, "E": EAST, "S": SOUTH, "W": WEST}

    @classmethod
    def from_str(cls, direction_str) -> "Direction":
        return Direction(cls.__from_str_map__[direction_str.upper()])
    
    @classmethod
    def from_int(cls, value: int) -> "Direction":
        return Direction(value)

    def __lt__(self, other) -> bool:
        return self.value < other.value

    def __repr__(self) -> str:
        return self.name

    def offset(self, offset: int) -> "Direction":
        return Direction((self.value + offset) % 4)

    def next(self) -> "Direction":
        return self.offset(1)

    def partner(self) -> "Direction":
        return self.offset(2)

    def previous(self) -> "Direction":
        return self.offset(3)

    def abbreviation(self) -> str:
        return self.name[0]

PairSide: Dict[str, str] = {"N": "NS", "E": "EW", "S": "NS", "W": "EW"}
def str_to_side(direction_str: str) -> str:
    try:
        return PairSide[direction_str]
    except:
        return ""

def Direction_to_side(dirn: Direction) -> str:
    return "NS" if (dirn == Direction.NORTH or dirn == Direction.SOUTH) else "EW"

def validate_contract(contract: Optional[str]) -> str:
    if not contract:
        return ""
    if contract.startswith("P"):
        return "AP"
    contract = contract.upper().replace("NT", "N")
    if len(contract) > 2 and contract[2:] != "X" and contract[2:] != "XX":
        return ""
    if len(contract) < 2:
        return ""
    return contract if (contract[0] in "1234567" and contract[1] in "SHDCN") else ""

@dataclass
class BridgeEvent:
    """Represents a bridge event with all its attributes."""
    EventName: str = "UNKNOWN"
    MatchName: str = "UNKNOWN"
    EventLocation: str = "UNKNOWN"
    MatchDate: str = "UNKNOWN"
    ScoringForm: str = "UNKNOWN"
    FilePath: str = ""

@dataclass
class BridgeDeal:
    DealNum: int = 0
    Dealer: str = ""
    Vulnerability: str = ""
    Hands: str = ""

lineProf: LineProfiler = LineProfiler()

def dealNo2dealer(dno: int) -> str:
    dealer_map = {1: "N", 2: "E", 3: "S", 0: "W"}
    return dealer_map[dno % 4]

def dealNo2vul(dno: int) -> str:
    return dealVulnerabilities[dno % 16]

def guessDealNum(dlr: str, vul: str) -> int:
    dealMap: Dict[str, Dict[str, int]] = {
        "N":    {"Z": 1, "N": 5, "E": 9, "B": 13},
        "E":    {"N": 2, "E": 6, "B": 10, "Z": 14},
        "S":    {"E": 3, "B": 7, "Z": 11, "N": 15},
        "W":    {"B": 4, "Z": 8, "N": 12, "E": 16}
    }
    try:
        return(dealMap[dlr][vul])
    except:
        print(f"Cannot compute deal num for dealer {dlr}, vul {vul}")
        return 0
    
def safe_get(obj: Any, key: str, default: Any = None) -> Any:
    """Safely get value from object, handling None objects and missing keys."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key) or default
    return default

def create_matchname(file_stem: str, match: Optional[str], homeTeam: Optional[str], visitors: Optional[str], 
                     stage: Optional[str], round: Optional[str], section: Optional[str]) -> str:
    lineup = " vs ".join(filter(None, [homeTeam, visitors])) or None
    # stage = f"Stage {stage}" if stage else None
    round = f"Round {round}" if round else None
    section = f"Section {section}" if section else None
    return ": ".join(filter(None, [f"{file_stem}", match, lineup, stage, round, section]))

rank_order = "AKQJT98765432"
rank_positions = {card: i for i, card in enumerate(rank_order)}
def sort_holding(holding: str | List[str]) -> str:
    """
    Sorts cards in descending rank order. Input must be valid cards:
    Either a string (e.g. "QA39") or a list of cards
    """
    return ''.join(sorted(holding, key=lambda x: rank_positions[x]))
