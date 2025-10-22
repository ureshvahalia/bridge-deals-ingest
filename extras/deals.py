import polars as pl
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from enum import IntEnum
from dataclasses import dataclass
from logging import getLogger
from bridgebots import Direction
from db_comp import DBComp, BridgeDB

logger = getLogger(__name__)

NUM_PLAYERS = 4

class VulnerabilityType(IntEnum):
    NONE    = 0
    NS      = 1
    EW      = 2
    BOTH    = 3
    WE      = 4
    THEY    = 5
    ANY     = 6
    
    def __repr__(self) -> str:
        return self.name
    
    @classmethod
    def translate_vul(cls, ns: bool, ew: bool) -> "VulnerabilityType":
        if ns:
            return cls.BOTH if ew else cls.NS
        else:
            return cls.EW if ew else cls.NONE
        
    @classmethod
    def from_dealNum(cls, dealNum: int) -> "VulnerabilityType":
        return dealVulnerabilities[dealNum % 16]
    
    @classmethod
    def from_str(cls, vul_str: str) -> "VulnerabilityType":
        vul_map: dict[str, "VulnerabilityType"]= {
            'Z': cls.NONE, 
            'NONE': cls.NONE,
            'N': cls.NS, 
            'NS': cls.NS,
            'E': cls.EW, 
            'EW': cls.EW,
            'B': cls.BOTH,
            'BOTH': cls.BOTH, 
            'X': cls.ANY
        }
        return vul_map.get(vul_str.upper(), cls.ANY)
    
    def parse(self) -> Tuple[bool, bool]:
        vul_sides: List[Tuple[bool, bool]] =  [
            (False, False),
            (True, False),
            (False, True), 
            (True, True)
        ]
        return vul_sides[self.value]
    
def is_ns_vul(dealNum: int) -> bool:
    v: VulnerabilityType = VulnerabilityType.from_dealNum(dealNum)
    return v == VulnerabilityType.NS or v == VulnerabilityType.BOTH

def is_ew_vul(dealNum: int) -> bool:
    v: VulnerabilityType = VulnerabilityType.from_dealNum(dealNum)
    return v == VulnerabilityType.EW or v == VulnerabilityType.BOTH

# To Be Fixed
def parse_vulnerability(vuln_str: str) -> Tuple[bool, bool]:
    return VulnerabilityType.parse(VulnerabilityType.from_str(vuln_str))

dealVulnerabilities: List[VulnerabilityType] = [
                                VulnerabilityType.EW,      # deal 0 has value for deal 16
                                VulnerabilityType.NONE,
                                VulnerabilityType.NS,
                                VulnerabilityType.EW,
                                VulnerabilityType.BOTH,
                                VulnerabilityType.NS,
                                VulnerabilityType.EW,
                                VulnerabilityType.BOTH,
                                VulnerabilityType.NONE,
                                VulnerabilityType.EW,
                                VulnerabilityType.BOTH,
                                VulnerabilityType.NONE,
                                VulnerabilityType.NS,
                                VulnerabilityType.BOTH,
                                VulnerabilityType.NONE,
                                VulnerabilityType.NS
                                ]

@dataclass
class BridgeDeal:
    def __init__(self, EventUID: int = 0, MatchID: int = 0, dealNum: int = 0, Dealer: str = "", 
                 Vul: str = "", hands: str = ",,,") -> None:
        self.DealUID: int = 0
        self.EventUID: int = EventUID
        self.MatchID: int = MatchID
        self.DealNum: int = dealNum
        self.Dealer: str = Dealer
        self.Vulnerability: str = Vul
        self.Deals: str = hands if hands is not None else ",,,"
        
    def to_dict(self) ->Dict[str, Any]:
        return  {
            "DealUID":int(self.DealUID),
            "EventUID":int(self.EventUID),
            "MatchID":int(self.MatchID),
            "DealNum":int(self.DealNum),
            "Dealer":self.Dealer.name,
            "Vulnerability":self.Vulnerability.name,
            "Deals":self.Deals
        }
        
class DealsDB(DBComp):
    """Database manager for bridge events."""
    SCHEMA = {
        "DealUID":  pl.Int64,
        "EventUID":      pl.Int64,
        "MatchID":      pl.Int64,
        "DealNum":  pl.Int64,
        "Dealer":   pl.Utf8,
        "Vulnerability":    pl.Utf8,
        "Deals":    pl.Utf8
    }

    def __init__(self, db: BridgeDB):
        """Initialize the event database."""
        super().__init__(db=db, fileNameBase="Deals", pkey="DealUID", schema=self.SCHEMA)

    def find(self, EventUID: int, MatchID: int, dealNum: int) -> Optional[BridgeDeal]:
        try:
            matches = self.df.filter((pl.col("EventUID") == EventUID) & (pl.col("MatchID") == MatchID) & (pl.col("DealNum") == dealNum))
            if matches.height > 1:
                error=f"Multiple matches for EventUid {EventUID}, Match {MatchID}, deal {dealNum}"
                logger.error(error)
                raise KeyError
            else:
             return BridgeDeal(**matches.to_dicts()[0]) if matches.height == 1 else None
        except Exception as e:
            logger.error(f"Error finding events: {str(e)}")
            return None


    def get(self, dealUid: int) -> Optional[BridgeDeal]:
        """Get a specific deal by EventUID and MatchID."""
        try:
            matches = self.df.filter(pl.col("DealUID") == dealUid)
            if matches.height == 0:
                return None
            if matches.height > 1:
                raise ValueError(f"Multiple events found for DealUID={dealUid}")

            # Convert the row data to appropriate types
            row_dict = matches.row(0, named=True)
            row_dict["Dealer"] = Direction[row_dict["Dealer"]]  # Convert back to Direction enum
            row_dict["Vulnerability"] = VulnerabilityType[row_dict["Vulnerability"]]  # Convert back to VulnerabilityType enum
            return BridgeDeal(**row_dict)
        except Exception as e:
            logger.error(f"Error getting event: {str(e)}")
            return None

    def add_batch(self, deals: list[BridgeDeal]) -> list[int]:
        """Add multiple deals in a batch for better performance."""
        if not deals:
            return []
        
        # with self._id_lock:
        # Create lookup dataframe of new deals for duplicate checking
        check_df = pl.DataFrame({
            'EventUID': [deal.EventUID for deal in deals],
            'MatchID': [deal.MatchID for deal in deals],
            'DealNum': [deal.DealNum for deal in deals]
        })
        
        # Find duplicates using join
        existing = (
            self.df
            .lazy()
            .join(check_df.lazy(), on=['EventUID', 'MatchID', 'DealNum'], how='inner')
            .select(['EventUID', 'MatchID', 'DealNum', 'DealUID'])
            .collect()
        )
        
        # Create lookup set for quick duplicate checking
        existing_deals = {(row['EventUID'], row['MatchID'], row['DealNum']): row['DealUID'] 
                        for row in existing.iter_rows(named=True)}
        
        # Process deals and prepare new rows
        new_rows = []
        assigned_uids = []
        
        for deal in deals:
            key = (deal.EventUID, deal.MatchID, deal.DealNum)
            if key in existing_deals:
                logger.error(f"Error processing deal {deal}")
                logger.error(f"Found existing match: {existing_deals[key]}. Ignoring.")
                assigned_uids.append(0)
                continue
                
            deal.DealUID = self.incrementMaxId()
            new_rows.append(deal.to_dict())
            assigned_uids.append(deal.DealUID)
        
        if new_rows:
            new_df = pl.DataFrame(new_rows)
            self.df = pl.concat([self.df, new_df], how="vertical")
        
        return assigned_uids