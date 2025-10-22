import polars as pl
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from enum import IntEnum
from dataclasses import dataclass
from logging import getLogger
from db_comp import DBComp, BridgeDB

logger = getLogger(__name__)

class MatchType(IntEnum):
    """Enum representing different types of bridge matches."""
    UNSPECIFIED = 0
    IMPS = 1
    MPS = 2
    BAM = 3
    VPS = 4
    RUBBER = 5
    IMP_PAIRS = 6

@dataclass
class BridgeEvent:
    """Represents a bridge event with all its attributes."""
    EventUID: int = 0
    MatchID: int = 0
    EventName: str = "UNKNOWN"
    MatchName: str = "UNKNOWN"
    EventLocation: str = "UNKNOWN"
    MatchDate: str = "UNKNOWN"
    ScoringForm: str = "UNKNOWN"
    FilePath: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert the event to a dictionary with proper types for DataFrame."""
        return {
            'EventUID': int(self.EventUID),
            'MatchID': int(self.MatchID),
            'EventName': self.EventName,
            'MatchName': self.MatchName,
            'EventLocation': self.EventLocation,
            'MatchDate': self.MatchDate,
            'ScoringForm': self.ScoringForm,
            'FilePath': self.FilePath
        }
        
class EventDB(DBComp):
    """Database manager for bridge events."""
    SCHEMA: Dict[str, type] = {
        "EventUID": pl.Int64,
        "MatchID": pl.Int64,
        "EventName": str,
        "MatchName": str,
        "EventLocation": str,
        "MatchDate": str,
        "ScoringForm": str,
        "FilePath": str
    }

    def __init__(self, db: BridgeDB):
        """Initialize the event database."""
        super().__init__(db=db, fileNameBase="Event", pkey="EventUID", schema=self.SCHEMA)

    def find(self, EventName: str, MatchName: str) -> List[BridgeEvent]:
        """Find events by EventName and MatchName."""
        try:
            matches = self.df.filter((pl.col("EventName") == EventName) & (pl.col("MatchName") == MatchName))
            return [BridgeEvent(**row) for row in matches.to_dicts()]
        except Exception as e:
            logger.error(f"Error finding events: {str(e)}")
            return []

    def get(self, EventUID: int, MatchID: int) -> Optional[BridgeEvent]:
        """Get a specific event by EventUID and MatchID."""
        try:
            matches = self.df.filter((pl.col("EventUID") == EventUID) & (pl.col("MatchID") == MatchID))
            if matches.height == 0:
                return None
            if matches.height > 1:
                raise ValueError(f"Multiple events found for EventUID={EventUID}, MatchID={MatchID}")
            return BridgeEvent(**matches.row(0, named=True))
        except Exception as e:
            logger.error(f"Error getting event: {str(e)}")
            return None

    def add(self, event: BridgeEvent, force: bool) -> Tuple[int, int]:
        """Add a new event to the database."""
        try:
            if event.EventUID > 0 or event.MatchID > 0:
                raise ValueError("Cannot add event with preset ID")

            """Store the event in the database."""
            event_matches = self.df.filter(pl.col("EventName") == event.EventName)
            
            if event_matches.height == 0:
                event.EventUID = self.incrementMaxId()
                event.MatchID = 1
            else:
                match_matches = event_matches.filter(pl.col("MatchName") == event.MatchName)
                if match_matches.height > 0:
                    if not force:
                        logger.error(f"Error processing event {event}")
                        logger.error(f"Found existing matches: {match_matches}. Use -f to force add a new instance.")
                        return 0, 0
                event.EventUID = event_matches["EventUID"][0]
                event.MatchID = event_matches["MatchID"].max() + 1  # type: ignore

            new_row = pl.DataFrame([event.to_dict()])
            self.df.vstack(new_row, in_place=True)
            # self.sync()
            return event.EventUID, event.MatchID
        except Exception as e:
            logger.error(f"Error adding event: {str(e)}")
            raise

    def add_batch(self, events: List[BridgeEvent], force: bool) -> List[Tuple[int, int]]:
        """Add multiple events to the database at once.
        
        Assumes events are already sorted by EventName. Maintains input order in results.
        """
        try:
            results: List[Tuple[int,int]] = []
            current_event_name: str = ""
            current_event_id: int = 0
            current_max_match_id:int = 0
            current_event_matches: pl.DataFrame = pl.DataFrame()
            new_rows = []
            
            # Process events sequentially, maintaining their order
            for event in events:
                if event.EventUID > 0 or event.MatchID > 0:
                    raise ValueError("Cannot add event with preset ID")
                
                # If we encounter a new event name, lookup information
                if current_event_name != event.EventName:
                    # Set the current event name
                    current_event_name = event.EventName
                    
                    # Check if we have existing events with this name
                    current_event_matches = self.df.filter(pl.col("EventName") == event.EventName)
                    
                    if current_event_matches.height == 0:
                        # No existing events with this name
                        current_event_id = self.incrementMaxId()
                        current_max_match_id = 0
                    else:
                        # Events with this name exist
                        current_event_id = current_event_matches["EventUID"][0]
                        current_max_match_id = current_event_matches["MatchID"].max()   # type: ignore
                
                # Check if we already have this match name
                if current_max_match_id > 0:
                    match_matches = current_event_matches.filter(pl.col("MatchName") == event.MatchName)
                    
                    if match_matches.height > 0 and not force:
                        # Skip this event if it already exists and force is False
                        logger.error(f"Error processing event {event}")
                        logger.error(f"Found existing matches: {match_matches}. Use -f to force add a new instance.")
                        results.append((0, 0))
                        continue
                
                # Assign next match ID
                current_max_match_id += 1
                event.EventUID = current_event_id
                event.MatchID = current_max_match_id
                new_rows.append(event.to_dict())
                results.append((event.EventUID, event.MatchID))
            
            # Add all rows at once
            if new_rows:
                new_df = pl.DataFrame(new_rows)
                self.df.vstack(new_df, in_place=True)
            
            return results
        except Exception as e:
            logger.error(f"Error batch adding events: {str(e)}")
            raise
    