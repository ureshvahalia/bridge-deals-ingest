from __future__ import annotations
from enum import IntEnum
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from functools import total_ordering
from common_objects import Direction, Direction_to_side
import re

# Regular expression for valid bids
BID_PATTERN = re.compile(r'^(?:[1-7][CDHSN]|P|X|XX|AP)$')
STRAIN_ORDER = {'C': 0, 'D': 1, 'H': 2, 'S': 3, 'N': 4}

def is_legal_bid(last_reg_bid: str, curbid: str):
    # Assumes input is a regular bid, not P/AP/X/XX
    return  (last_reg_bid == "") or (curbid[0] > last_reg_bid[0]) or \
            ((curbid[0] == last_reg_bid[0]) and (STRAIN_ORDER[curbid[1]] > STRAIN_ORDER[last_reg_bid[1]]))

def process_auction(dealer: Direction, auction: str) -> Dict[str, str|int]:
    """Process a bridge auction and return comprehensive analysis."""
    # Validate input types
    if not isinstance(dealer, Direction):
        raise TypeError(f"dealer must be Direction, got {type(dealer)}")
    if not isinstance(auction, str):
        raise TypeError(f"auction must be str, got {type(auction)}")

    # Initialize tracking variables
    current_dir = dealer
    opener: Optional[Direction] = None
    intervener: Optional[Direction] = None
    advancer: Optional[Direction] = None
    opening_bid: str = ""
    intervention_bid: str = ""
    contract: str = "AP"
    declarer: Optional[Direction] = None
    cur_contract: str = ""
    cur_contract_side: str = ""
    auctionType: str = "Missing"
    premium: str = "Undoubled"
    open_side: str = ""
    
    # Bid tracking structures
    bids: List[Tuple[Direction, str]] = []
    first_bidder_of_strain: Dict[str, Dict[str, Direction]] = {
        "NS": {},
        "EW": {}
    }
    consecutive_passes = 0
    auction_len: int = 0 # Does not include the final passes
    auction_complete = False
    open_seat: int = 0

    # Process each bid
    if auction:
        for bid in auction.split("-"):
            bids.append((current_dir, bid))
            if auction_complete:
                break
            
            # Validate bid format
            if not BID_PATTERN.match(bid):
                auctionType = "Corrupt"
                break

            # Check for auction termination conditions
            if bid == "AP":
                auction_complete = True
                break
            
            if bid == "P":
                consecutive_passes += 1
                if consecutive_passes >= 3 and len(bids) > 3:
                    auction_complete = True
                    break
            else:
                consecutive_passes = 0
            
                # Track first bidder for each strain by side
                side: str = Direction_to_side(current_dir)
                if bid == "XX":
                    if (premium != "Doubled") or (side != cur_contract_side):
                        auctionType = "Illegal"
                        break
                    premium = "Redoubled"
                elif bid == "X":
                    if (premium == "Undoubled") and (side != cur_contract_side):
                        premium = "Doubled"
                    elif premium == "Doubled":  # check for redouble entered as "X"
                        if side == cur_contract_side:
                            bid = "XX"  # Fix the bid. This is a hack for some json files
                            bids[-1] = (current_dir, "XX")
                            premium = "Redoubled"
                        else:
                            auctionType = "Illegal" # Can only redouble own side's bid
                    else:
                        auctionType = "Illegal" # Can't double your own side's bid
                        break
                elif len(bid) == 2 and bid[1] in "CDHSN": # Regular bid
                    if not is_legal_bid(cur_contract, bid):
                        auctionType = "Illegal"
                        break
                    cur_contract = bid
                    cur_contract_side = side
                    premium = "Undoubled"
                    strain = bid[1]
                    if strain not in first_bidder_of_strain[side]:
                        first_bidder_of_strain[side][strain] = current_dir
                    # Identify opener
                    if opener is None:
                        opener = current_dir
                        open_side = side
                        opening_bid = bid
                        open_seat = len(bids)
                    
                # Identify intervener and advancer
                if intervener is None and opener is not None and side != open_side:
                    intervener = current_dir
                    advancer = current_dir.partner()
                    intervention_bid = bid
            
            current_dir = current_dir.next()

        # Determine contract and declarer
        if bids and auctionType not in ["Corrupt", "Illegal"]:
            # Find the last non-pass, non-double bid
            if auctionType == "Missing":
                auctionType = "Legal"
            contract_bid = None
            contract_side: Optional[str] = None
            doubled: bool = False
            redoubled: bool = False
            auction_len = len(bids) - consecutive_passes
            for bidder, bid in reversed(bids):
                if bid in ["P", "AP"]:
                    continue
                elif bid == "X":
                    doubled = True
                elif bid == "XX":
                    redoubled = True
                else:
                    contract_bid = bid
                    contract_side = Direction_to_side(bidder)
                    break
            
            if contract_bid and contract_side:
                contract = contract_bid + ("XX" if redoubled else ("X" if doubled else ""))
                # Find first player on contract side who bid this strain
                strain = contract_bid[1] if len(contract_bid) > 1 else ""
                declarer = first_bidder_of_strain[contract_side].get(strain)
        
    # Prepare result dictionary
    result: Dict[str, str|int] = {
        "Auction": "-".join(bid[1] for bid in bids[:auction_len]) if (auction_len > 0) else ("AP" if bids else ""),
        "AuctionLen": auction_len,
        "AuctionCheck": auctionType,
        "Opener": opener.abbreviation() if opener is not None else "",
        "OpenSide": open_side,
        "Responder": opener.partner().abbreviation() if opener is not None else "",
        "Intervener": intervener.abbreviation() if intervener is not None else "",
        "Advancer": advancer.abbreviation() if advancer is not None else "",
        "Opening": opening_bid,
        "OpenSeat": open_seat,
        "Intervention": intervention_bid,
        "DerivedContract": contract if auctionType == "Legal" else "",
        "DerivedDeclarer": declarer.abbreviation() if declarer is not None else ""
    }

    return result

# Example usage and testing
if __name__ == "__main__":
    # Test cases
    test_cases = [
        (Direction.NORTH, "1N-P-1F-P-P-P"),
        (Direction.NORTH, "1N-P-1S-P-P-P"),
        (Direction.NORTH, "1N-P-X-P-P-P"),
        (Direction.NORTH, "1N-X-P-XX-P-P-P"),
        (Direction.NORTH, "1N-P-1N-P-P-P"),
        (Direction.NORTH, "1N-P-3N-P-P-P"),  # Simple 1NT-3NT
        (Direction.EAST, "P-1C-1S-2C-2S-P-P-P"),  # With intervention
        (Direction.SOUTH, "1C-X-XX-P-P-P"),  # Double and redouble
        (Direction.WEST, "P-P-P-P"),  # All pass
        (Direction.NORTH, "1H-P-1S-P-1N-P-3N-AP"),  # With AP termination
    ]
    
    for dealer, auction in test_cases:
        print(f"\nDealer: {dealer}, Auction: {auction}")
        try:
            result = process_auction(dealer, auction)
            print(f"{result}")
            pass
        except Exception as e:
            print(f"  Error: {e}")