import re
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
from dataclasses import dataclass
from common_objects import BoardRecord, lineProf, translate_vul
from common_objects import create_matchname, validate_contract, safe_get, get_number
from line_profiler import LineProfiler

@dataclass
class BidMetadata:
    """Metadata for a bid (annotations, etc.)"""
    bid_index: int
    notes: Optional[List[str]] = None
    nag: Optional[int] = None
    suffix: Optional[str] = None


@dataclass
class Commentary:
    """Commentary or notes"""
    text: str
    position: Optional[int] = None

class PBNParser:
    """Parser for PBN (Portable Bridge Notation) files"""
    
    def __init__(self):
        self.current_game_tags = {}
        self.current_auction: str = ""
        self.current_play = ""
        self.current_notes = {}
        self.commentary = ""
        
    def parse_file(self, file_path: Path) -> List[BoardRecord]:
        """Parse a PBN file and return a record for each bpoard"""
        # print(f"Reading file {file_path}, ", end = "")
        with open(file_path, 'r', encoding='iso-8859-1') as f:
            content: str = f.read()
        # print(f"Done {file_path.name}")
        file_stem: str = file_path.stem
        
        # Split into games (games are separated by semi-empty lines)
        games: List[Tuple[str, str]] = self._split_into_games(content)
        result: List[BoardRecord] = []
        
        for game_content in games:
            try:
                game_data: Optional[BoardRecord] = self._parse_game(game_content, file_stem)
                if game_data is not None:
                    result.append(game_data)
            except Exception as e:
                print(f"Warning: Failed to parse game: {e} in {file_path}")
                continue
    
        # Convert the dictionary to the required list of tuples
        if result is None:
            pass
        return result
    
    def _split_into_games(self, content: str) -> List[Tuple[str, str]]:
        """Split PBN content into individual games"""
        lines: List[str] = content.split('\n')
        games: List[Tuple[str, str]] = []
        current_game: List[str] = []
        comments: str = ""
        
        i: int = 0
        in_brace_comment: bool = False
        while i < len(lines):
            line: str = lines[i].strip()
            
            # Skip escape lines
            if line.startswith('%'):
                i += 1
                continue
            
            if in_brace_comment:
                found_at: int = line.find('}')
                if found_at >= 0:
                    comments = comments + line[0:found_at] + '\n'
                    in_brace_comment = False
                    lines[i] = line[found_at + 1:]  # strip the commentary part from the line
                    if len(lines[i]) > 0:
                        continue    # do not increment i, so we can process rest of the line
                else:   # whole line is part of the commentary
                    comments = comments + line + '\n'
            else:
                semicol_at: int = line.find(';')
                openbrace_at: int = line.find('{')
                if semicol_at >= 0 and ((semicol_at < openbrace_at) or (openbrace_at < 0)):   # Process inline commentary
                    if semicol_at > 0:
                        current_game.append(line[0:semicol_at]) # Append portion before ';' to current_game
                    comments = comments + line[semicol_at + 1:] + '\n'   # Add rest of the line to commentary
                elif openbrace_at >= 0 and ((openbrace_at < semicol_at) or (semicol_at < 0)):   # Process in-brace commentary
                    in_brace_comment = True
                    if openbrace_at > 0:
                        current_game.append(line[0:openbrace_at])   # Append portion before '{' to current_game
                    if (len(lines[i]) > openbrace_at + 1):
                        lines[i] = line[openbrace_at + 1:]  # strip data before the commentary part from the line
                        continue    # do not increment i, so we can process rest of the line
                elif line:   # Regular line, no commentary
                    current_game.append(line)
                    # Check for game separator (empty line or multiple empty lines)
                else:   # Empty line, and we are not in an in_brace_comment
                    if current_game:    # we have accumulated a game, add it
                        games.append(('\n'.join(current_game), comments))
                        current_game = []
                        comments = ""
            i += 1
        
        # Add the last game if it exists
        if current_game:
            games.append(('\n'.join(current_game), comments))
        
        return games
    
    def _parse_game(self, game_content: Tuple[str, str], file_stem: str) -> Optional[BoardRecord]:
        """Parse a single game"""
        saved_tags: Dict[str, Any] = self.current_game_tags
        self.current_game_tags = {}
        self.current_notes = {}
        self.current_auction = ""
        self.current_play = ""

        # Process commentary first, then parse the cleaned content
        cleaned_content, comments = game_content
        self.commentary = comments
        lines = cleaned_content.split('\n')
        i = 0
        
        # Parse tag pairs first
        while i < len(lines):
            line = lines[i].strip()
            # if not line or line.startswith('%'):
            #     i += 1
            #     continue
            
            if line.startswith('[') and line.endswith(']'):
                tag_match = re.match(r'\[(\w+)\s+"([^"]*)"\]', line)
                if tag_match:
                    tag_name, tag_value = tag_match.groups()
                    self.current_game_tags[tag_name] = tag_value if (tag_value != "#" and tag_value != '?') else saved_tags.get(tag_name, "")
                    if tag_name == 'Auction':
                        # Parse auction section
                        i = self._parse_auction(lines, i)
                    elif tag_name == 'Play':
                        # Parse play section
                        i = self._parse_play(lines, i)
                    elif tag_name == 'Note':
                        # Parse note
                        note_match = re.match(r'\[Note\s+"(\d+):([^"]*)"\]', line)
                        if note_match:
                            note_id, note_text = note_match.groups()
                            self.current_notes[int(note_id)] = note_text
            
            i += 1
        
        for k in ["Event", "Site", "Date", "Stage", "Round", "Section", "Scoring"]:
            if k not in self.current_game_tags.keys() and k in saved_tags.keys():
                self.current_game_tags[k] = saved_tags[k]
                # print (f"Inheriting missing key {k} as {saved_tags[k]}")
        
        # Create event, deal and board record
        return self._create_board_record(file_stem)
    
    def _parse_auction(self, lines: List[str], start_idx: int) -> int:
        """Parse auction section"""
        i = start_idx + 1
        all_calls: List[str] = []
        self.current_auction: str = ""  
        
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith('%'):
                i += 1
                continue
            
            # Check if we've reached another section
            if line.startswith('['):
                break
            
            # Parse auction calls
            calls = self._parse_auction_line(line)
            all_calls.extend(calls)
            i += 1
            
        self.current_auction = "-".join(all_calls)
        return i - 1
    
    def _parse_play(self, lines: List[str], start_idx: int) -> int:
        """Parse play section"""
        i = start_idx + 1
        all_cards: List[str] = []
        self.current_play = ""
        
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith('%'):
                i += 1
                continue
            
            # Check if we've reached another section
            if line.startswith('['):
                break
            
            # Parse played cards
            cards = self._parse_play_line(line)
            all_cards.append(cards)
            self.current_play = ", ".join(all_cards)
            i += 1
        
        return i - 1
    
    def _parse_auction_line(self, line: str) -> List[str]:
        """Parse a line of auction calls"""
        # Split on whitespace and parse each call
        tokens = line.upper().replace("NT", "N").split()
        calls = []
        
        for token in tokens:
            # Remove annotations for now (suffixes, notes, NAGs)
            call = re.sub(r'[!?]+|\$\d+|=\d+=', '', token).upper()
            if call and call not in ['+', '*']:
                if call[0] == 'P':
                    call = 'P'
                calls.append(call)
        
        return calls
    
    def _parse_play_line(self, line: str) -> str:
        """Parse a line of played cards"""
        # Remove comments
        if ';' in line:
            line = line[:line.index(';')]
        
        tokens = line.split()
        cards: List[str] = []
        
        for token in tokens:
            # Remove annotations
            card_str = re.sub(r'[!?]+|\$\d+|=\d+=', '', token)
            if card_str and card_str not in ['+', '*', '-', '^R', '^L']:
                cards.append(card_str)
        
        return "-".join(cards)
    
    def _parse_score(self, score: str) -> int | None:
        if (len(score) > 1) and score.endswith('0'):
            if (score[0:2] == "NS"):
                return int(score[2:])
            elif (score[0:2] == "EW"):
                return -1 * int(score[2:])
        return None
    
    def _create_board_record(self, file_stem: str) -> BoardRecord:
        """Create BridgeBoard from parsed data"""
        """Create BridgeEvent from parsed tags"""
        homeTeam = self.current_game_tags.get('HomeTeam')
        visitors = self.current_game_tags.get('VisitTeam') or self.current_game_tags.get('AwayTeam')
        stage = self.current_game_tags.get('Stage')
        round = self.current_game_tags.get('Round')
        section = self.current_game_tags.get('Section')
        matchName = create_matchname(file_stem, None, homeTeam, visitors, stage, round, section)
        # Get names - fix the tuple issue with North
        north_name: str = safe_get(self.current_game_tags, 'North', 'UNKNOWN')
        east_name: str  = safe_get(self.current_game_tags, 'East', 'UNKNOWN')
        south_name: str = safe_get(self.current_game_tags, 'South', 'UNKNOWN')
        west_name: str  = safe_get(self.current_game_tags, 'West', 'UNKNOWN')
        table_name: str = self.current_game_tags.get('Table', '')
        room_name: str  = self.current_game_tags.get('Room', '')
        table_name = f"{room_name}{table_name}" if table_name else f"{room_name}: {north_name}-{south_name} vs {east_name}-{west_name}"
        contractStr: Optional[str] = validate_contract(self.current_game_tags.get('Contract'))
        ntricks: Optional[int] = get_number(self.current_game_tags.get('Result'))
        if ntricks and (ntricks < 0 or ntricks > 13):
            ntricks = None
        declStr: Optional[str] = self.current_game_tags.get('Declarer') or None
        if declStr and (len(declStr) > 1) and declStr[0] == '^':
            declStr = declStr[1]
        
        return BoardRecord(
            EventName=self.current_game_tags.get('Event') or 'UNKNOWN',
            MatchName=matchName if matchName else 'UNKNOWN',  # Using Event as match name
            EventLocation=self.current_game_tags.get('Site', 'UNKNOWN'),
            MatchDate=self.current_game_tags.get('Date', 'UNKNOWN'),
            ScoringForm=self.current_game_tags.get('Scoring', 'UNKNOWN'),
            FilePath="",
            DealNum=get_number(self.current_game_tags.get('Board')) or 0,
            Dealer=self.current_game_tags.get('Dealer', ''),
            Vulnerability=translate_vul(self.current_game_tags.get('Vulnerable') or 'X'),
            Hands=self.current_game_tags.get('Deal', ''),
            TableID=table_name,
            North=north_name,
            East=east_name,
            South=south_name,
            West=west_name,
            Contract=contractStr,
            Declarer=declStr,
            TricksMade=ntricks,
            RawScoreNS=self._parse_score(str(self.current_game_tags.get('Score', '0'))),
            Auction=self.current_auction,
            Play=self.current_play,
            Lead="",
            BiddingMD="",  # TBD
            Commentary=""  # TBD
        )

def parse_pbn_file(file_path: Path) -> List[BoardRecord]:
    # Parse a PBN file and return a BoardRecord
    parser = PBNParser()
    lineProf.add_function(parser.parse_file)
    result = parser.parse_file(file_path)
    
    # Set file path in all events
    for x in result:
        x.FilePath = str(file_path)
    
    return result