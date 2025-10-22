import polars as pl
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from logging import getLogger
from bridgebots import Direction
from db_comp import DBComp, BridgeDB

logger = getLogger(__name__)

@dataclass
class BridgeBoard:
    def __init__(self, bd: Dict) -> None:
        self.BoardUID:int       = 0
        self.DealUID: int       = 0
        self.TableID: str       = bd["TableID"]
        self.North: str         = bd.get("North", "")
        self.West: str          = bd.get("West", "")
        self.South: str         = bd.get("South", "")
        self.East: str          = bd.get("East", "")
        self.Declarer: Optional[str]    = bd.get("Declarer")
        self.Contract: Optional[str]    = bd.get("Contract")
        self.TricksMade: int    = bd.get("TricksMade", -1)
        self.RawScoreNS         = bd["score"] if (self.Declarer == "N" or self.Declarer == "S") else (-1 * bd["score"])
        self.Auction: str       = bd.get("Auction", "")
        self.Play: str          = bd.get("Play", "")
        self.BiddingMD: str     = bd.get("BiddingMD", "")
        self.Commentary: str    = bd.get("Commentary", "")
        
    def to_dict(self) ->Dict[str, Any]:
        return  {
            "BoardUID":     int(self.BoardUID),
            "DealUID":      int(self.DealUID),
            "TableID":      self.TableID,
            "Players":      self.Players,
            "Declarer":     self.Declarer,
            "Contract":     self.Contract,
            "TricksMade":   int(self.TricksMade),
            "RawScoreNS":   int(self.RawScoreNS) if self.RawScoreNS else None,
            "Auction":      self.Auction,
            "Play":         self.Play,
            "BiddingMD":    self.BiddingMD,
            "Commentary":   self.Commentary
       }
        
class BoardsDB(DBComp):
    """Database manager for bridge boards."""
    """A board is a deal played at one table."""
    SCHEMA = {
        "BoardUID":     pl.Int64,
        "DealUID":      pl.Int64,
        "TableID":      pl.Utf8,
        "North":        pl.Utf8,
        "East":         pl.Utf8,
        "South":        pl.Utf8,
        "West":         pl.Utf8,
        "Declarer":     pl.Utf8,
        "Contract":     pl.Utf8,
        "TricksMade":   pl.Int64,
        "RawScoreNS":   pl.Int64,
        "Auction":      pl.Utf8,
        "Play":         pl.Utf8,
        "BiddingMD":    pl.Utf8,
        "Commentary":   pl.Utf8
    }

    def __init__(self, db: BridgeDB):
        """Initialize the board database."""
        super().__init__(db=db, fileNameBase="Boards", pkey="BoardUID", schema=self.SCHEMA)

    def find(self, dealUid: int, tableId: str) -> Optional[BridgeBoard]:
        try:
            matches = self.df.filter((pl.col("DealUID") == dealUid) & (pl.col("TableID") == tableId))
            if matches.height > 1:
                error=f"Multiple matches for DealUID {dealUid}, table {tableId}"
                logger.error(error)
                raise KeyError
            else:
                return BridgeBoard(**matches.to_dicts()[0]) if matches.height == 1 else None
        except Exception as e:
            logger.error(f"Error finding boards: {str(e)}")
            raise

    def get(self, boardUid: int) -> Optional[BridgeBoard]:
        """Get a specific deal by boardUID."""
        try:
            matches = self.df.filter(pl.col("BoardUID") == boardUid)
            if matches.height == 0:
                return None
            if matches.height > 1:
                raise ValueError(f"Multiple events found for BoardUID={boardUid}")

            # Convert the row data to appropriate types
            row_dict = matches.row(0, named=True)
            row_dict["Declarer"] = Direction[row_dict["Declarer"]]  # Convert back to Direction enum
            # Do any type conversions needed [TBD]
            return BridgeBoard(**row_dict)
        except Exception as e:
            logger.error(f"Error getting event: {str(e)}")
            return None

    def add_batch(self, boards: list[BridgeBoard]) -> list[int]:
        """Add multiple board records in a batch for better performance."""
        if not boards:
            return []
        
        # Validate no preset UIDs
        for board in boards:
            if board.BoardUID != 0:
                raise ValueError("Cannot add board with preset UID")
        
        # Create lookup dataframe for duplicate checking
        check_df = pl.DataFrame({
            'DealUID': [board.DealUID for board in boards],
            'TableID': [board.TableID for board in boards]
        })
        
        # Find duplicates using join
        existing = (
            self.df
            .lazy()
            .join(
                check_df.lazy(),
                on=['DealUID', 'TableID'],
                how='inner'
            )
            .select(['DealUID', 'TableID', 'BoardUID'])
            .collect()
        )
        
        # Create lookup set for quick duplicate checking
        existing_boards = {(row['DealUID'], row['TableID']): row['BoardUID'] 
                        for row in existing.iter_rows(named=True)}
        
        # Process boards and prepare new rows
        new_rows = []
        assigned_uids = []
        
        for board in boards:
            key = (board.DealUID, board.TableID)
            if key in existing_boards:
                logger.error(f"Error processing board {board}")
                logger.error(f"Found existing match: {existing_boards[key]}. Ignoring.")
                assigned_uids.append(0)
                continue
                
            board.BoardUID = self.incrementMaxId()
            board_dict = board.to_dict()
            
            # Explicit type conversions as in original
            board_dict["Players"] = str(board_dict["Players"])
            board_dict["Auction"] = str(board_dict["Auction"])
            board_dict["Contract"] = str(board_dict["Contract"])
            board_dict["Commentary"] = str(board_dict["Commentary"])
            board_dict["Play"] = str(board_dict["Play"])
            board_dict["BiddingMD"] = str(board_dict["BiddingMD"])
            
            new_rows.append(board_dict)
            assigned_uids.append(board.BoardUID)
        
        if new_rows:
            new_df = pl.DataFrame(new_rows)
            self.df = pl.concat([self.df, new_df], how="vertical")
        
        return assigned_uids