import logging
import polars as pl
from typing import List, Dict, Any, Optional, Tuple, Final
from pathlib import Path
from common_objects import Direction, BoardRecord, PairSide
from common_objects import lineProf, dealNo2dealer, dealNo2vul
from common_objects import rank_order, sort_holding, str_to_side
from auction import process_auction
from scoring import convert_to_imps, compute_contract_details_and_NSscore, compute_TricksMade, process_pars
from dds_wrapper import create_dd_columns
from fuzzy import fuzzy_deduplicate_events

NCARDS_IN_HAND: Final[int] = 13
NSUITS: Final[int] = 4
NHANDS: Final[int] = 4
TABLES_IN_TEAM_GAME: Final[int] = 2
CARD_ORDER = "AKQJT98765432"
SUIT_INDICES: Final[Dict[str, int]] = { "S": 0, "H": 1, "D": 2, "C": 3 }
rank_order_set = set(CARD_ORDER)
pbn_one_hand_strlen:    Final[int] = NCARDS_IN_HAND + NSUITS - 1     # 13 cards plus 3 dots
pbn_all_hands_minlen:   Final[int] = 3 * pbn_one_hand_strlen + 4

def parse_hand_string(hand_str: str) -> Optional[Dict[str, str]]:
    """
    Parse a bridge hand string into a dictionary mapping positions to hands.
    Assumes standard PBN format with no nested parentheses.
    
    Args:
        hand_str: String in PBN format
    
    Returns:
        Dictionary mapping positions (SOUTH, WEST, etc.) to hand strings
    """
    # Check min strlen: Dealer, colon, three hands, and two hand-separator spaces
    if len(hand_str) < pbn_all_hands_minlen or hand_str[1] != ":": 
        logging.info(f"Invalid hands {hand_str}")
        return None

    position: Direction = Direction.from_str(hand_str[0])
    # Strip Direction and split into hands
    hands: List[str] = hand_str[2:].split()
    num_hands: int = len(hands)
    if num_hands < 3 or num_hands > 4:
        logging.warning(f"Found {num_hands} hands in {hand_str}")
        return None
    
    result = {}
    seen_cards: List[List[str]] = [ [], [], [], [] ]
    
    for hand in hands:
        if len(hand) != pbn_one_hand_strlen:
            logging.info(f"Invalid Hand {hand} in {hand_str}")
            return None
        result[f"{position.abbreviation()}_Hand"] = hand
        holdings: List[str] = hand.split(".")
        if len(holdings) != NSUITS:
            logging.info(f"Hand {hand} has only {len(holdings)} suits")
            return None
        for suitno, holding in enumerate(holdings):
            seen_cards[suitno].extend(holding)
        position = position.next()

    if num_hands == 4:
        for i in range(NSUITS):
            if set(seen_cards[i]) != rank_order_set:
                logging.info(f"Invalid hand {hand_str}")
                return None
    else:   # len(hands) == 3
        missing_cards: List[str] = []
        for i in range(NSUITS):
            missing_ranks: set[str] = rank_order_set - set(seen_cards[i])
            missing_cards.append(sort_holding(''.join(missing_ranks)))
        missing_hand: str = ".".join(missing_cards)
        if len(missing_hand) != pbn_one_hand_strlen:
            logging.error(f"Failed to construct missing hand for {hand_str}")
            return None
        result[f"{position.abbreviation()}_Hand"] = missing_hand
    
    # Build final result in desired order
    final_result = {}
    for position_key in ['N_Hand', 'E_Hand', 'S_Hand', 'W_Hand']:
        if position_key in result:
            final_result[position_key] = result[position_key]
    return final_result

# Points lookup
HCP_values = {'A': 4, 'K': 3, 'Q': 2, 'J': 1}

def analyze_hand(hand_str: str) -> dict:
    """
    Analyze a bridge hand string.
    
    Args:
        hand_str: String in format "AKJ62.K7.Q98.KT3"
    
    Returns:
        Dictionary containing hand analysis
    """
    # Split into suits
    suits: List = hand_str.split('.')
    
    # Initialize storage for analysis
    Suit_lengths: List[int] = [0] * NSUITS
    suit_HCP: List[int] = [0] * NSUITS
    controls = 0
    total_cards = 0
    
    # Process each suit
    for suit_ndx, suit_str in enumerate(suits):
        suit_len = len(suit_str)
        if suit_len == 0:
            continue
        
        # Count cards in suit
        Suit_lengths[suit_ndx] = suit_len
        total_cards += suit_len
        
        # Calculate HCP and controls
        suit_pts: int = 0
        for card in suit_str:
            # Add HCP
            if card in HCP_values:
                suit_pts += HCP_values[card]
                # Add controls
                if card == 'A':
                    controls += 2
                elif card == 'K':
                    controls += 1
        suit_HCP[suit_ndx] = suit_pts
    
    # Calculate shape (lengths sorted in descending order)
    shape = sorted(Suit_lengths, reverse=True)
    
    return {
        'Length_S': Suit_lengths[0],
        'Length_H': Suit_lengths[1],
        'Length_D': Suit_lengths[2],
        'Length_C': Suit_lengths[3],
        'HCP_S': suit_HCP[0],
        'HCP_H': suit_HCP[1],
        'HCP_D': suit_HCP[2],
        'HCP_C': suit_HCP[3],
        'Total_HCP': sum(suit_HCP),
        'Controls': controls,
        'Pattern': '-'.join(str(x) for x in Suit_lengths),
        'Shape': '.'.join(str(x) for x in shape)
    }

def _is_valid(col_name: str) -> pl.Expr:
    return pl.col(col_name).is_not_null() & pl.col(col_name).ne("")

def _is_invalid(col_name: str) -> pl.Expr:
    """Check if a column is null or empty."""
    return pl.col(col_name).is_null() | (pl.col(col_name) == "")

def compare_deal_at_both_tables(expandedDf: pl.DataFrame) -> pl.DataFrame:
    # Calculate derived columns - with null checks
    result1 = expandedDf.with_columns(
        pl.struct(["RawScoreNS_1", "RawScoreNS_2"])
            .map_elements(lambda x: convert_to_imps(x["RawScoreNS_1"], x["RawScoreNS_2"])
                        if (x["RawScoreNS_1"] is not None and x["RawScoreNS_2"] is not None)
                        else 0,
                        return_dtype=pl.Int32)
            .alias("Team1NS_IMPs")
    )
    result1 = result1.with_columns(
        pl.col("Team1NS_IMPs").abs().alias("SWING"),
        (pl.col("Opener_2") == pl.col("Opener_1")).alias("SameOpener")
    )
    result1 = result1.with_columns(
        (pl.col("SameOpener") & (pl.col("Opening_1") == pl.col("Opening_2"))).alias("SameOpening"),
        (pl.col("Auction_2") == pl.col("Auction_1")).alias("SameAuction"),
        (pl.col("Contract_2") == pl.col("Contract_1")).alias("SameBid"),
        ((pl.col("Contract_2") == pl.col("Contract_1")) & 
        (pl.col("Declarer_2") == pl.col("Declarer_1"))).alias("SameContract"),
        (pl.col("DeclSide_2") == pl.col("DeclSide_1")).alias("SameDeclSide")
    )
    result1 = result1.with_columns(        
        (pl.col("SameBid") & pl.col("SameDeclSide") & ~pl.col("SameContract")).alias("RightSide"),
        (pl.col("SameContract") & (pl.col("TricksMade_2") == pl.col("TricksMade_1"))).alias("SameResult"),
        (pl.col("Lead_1") == pl.col("Lead_2")).alias("SameLead")
    )
    result1 = result1.with_columns(
        (pl.when(
                (pl.col("SameContract")) & 
                (pl.col("Intervention_1") == "") & 
                (pl.col("Intervention_2") == "")
        ).then(
            pl.when(pl.col("AuctionLen_1") < pl.col("AuctionLen_2"))
            .then(pl.when(pl.col("DeclSide_1") == "NS").then(1).otherwise(-1))
            .when(pl.col("AuctionLen_1") > pl.col("AuctionLen_2"))
            .then(pl.when(pl.col("DeclSide_1") == "EW").then(1).otherwise(-1))
            .otherwise(0)
        ).otherwise(0)
        * pl.col("Team1NS_IMPs")
        ).alias("ShorterAuctionScore")
    )
    result = result1.with_columns(
        (pl.when(pl.col("OpenSeat_1") < pl.col("OpenSeat_2"))
        .then(pl.col("Opening_1"))
        .otherwise(
            pl.when(pl.col("OpenSeat_1") > pl.col("OpenSeat_2"))
            .then(pl.col("Opening_2"))
            .otherwise(pl.lit(""))
        )).alias("EarlyBid")
    )
    # Add OpenerIMPs calculations at the end, before the return statement
    result = result.with_columns([
        # OpenerIMPs_1: 
        # - If OpenSide_1 is "NS", use Team1NS_IMPs
        # - If OpenSide_1 is "EW", use -Team1NS_IMPs
        # - If blank, use 0
        pl.when(pl.col("OpenSide_1") == "NS")
        .then(pl.col("Team1NS_IMPs"))
        .when(pl.col("OpenSide_1") == "EW")
        .then(-pl.col("Team1NS_IMPs"))
        .otherwise(0)
        .alias("OpenerIMPs_1"),
        
        # OpenerIMPs_2:
        # - If OpenSide_2 is "EW", use Team1NS_IMPs
        # - If OpenSide_2 is "NS", use -Team1NS_IMPs
        # - If blank, use 0
        pl.when(pl.col("OpenSide_2") == "EW")
        .then(pl.col("Team1NS_IMPs"))
        .when(pl.col("OpenSide_2") == "NS")
        .then(-pl.col("Team1NS_IMPs"))
        .otherwise(0)
        .alias("OpenerIMPs_2")
    ])
    
    return result.with_columns(
        pl.when(pl.col("Opening_1") == pl.col("EarlyBid"))
        .then(pl.col("OpenerIMPs_1"))
        .when(pl.col("Opening_2") == pl.col("EarlyBid"))
        .then(pl.col("OpenerIMPs_2"))
        .otherwise(0)
        .alias("EBScore")
    )

def expand_matches(dealsDf: pl.DataFrame, boardsDf: pl.DataFrame) -> pl.DataFrame:
    # Remove common columns to avoid duplication
    common_columns = set(dealsDf.columns).intersection(boardsDf.columns) - {"DealUID"}
    boardsDf = boardsDf.drop(list(common_columns))
    
    # Create row numbers within each DealUID group (will be 1 and 2)
    matches = boardsDf.with_columns(pl.col("DealUID").cum_count().over("DealUID").alias("match_num"))
    
    # Split into two dataframes and rename columns
    exclude_cols: List[str] = ["DealUID", "match_num"]
    rename_cols_1 = {col: f"{col}_1" for col in matches.columns if col not in exclude_cols}
    rename_cols_2 = {col: f"{col}_2" for col in matches.columns if col not in exclude_cols}
    
    match1 = matches.filter(pl.col("match_num") == 1).drop("match_num").rename(rename_cols_1)
    match2 = matches.filter(pl.col("match_num") == 2).drop("match_num").rename(rename_cols_2)
    
    # Join deals with both matches
    result = (dealsDf
              .join(match1, on="DealUID", how="inner")
              .join(match2, on="DealUID", how="inner"))
    
    return compare_deal_at_both_tables(result)
    
def process_auction_vectorized(dealer_col: pl.Series, auction_col: pl.Series) -> pl.DataFrame:
    """Vectorized function to process multiple auctions at once."""
    
    # Parse the auction and extract info from it
    results = []
    lineProf.add_function(process_auction)
    for dealer_str, auction in zip(dealer_col, auction_col):
        result: Dict[str, str|int] = process_auction(Direction.from_str(dealer_str), auction)
        results.append(result)
    
    # Convert results to a DataFrame
    return pl.DataFrame(results)

def _create_player_column_mapping(position_col: str, column_suffix: str) -> pl.Expr:
    """Create a polars expression to map player positions to their corresponding columns"""
    when_expr = pl.when(pl.col(position_col) == "N").then(pl.col(f"N_{column_suffix}"))
    for pos in ["E", "S", "W"]:
        when_expr = when_expr.when(pl.col(position_col) == pos).then(pl.col(f"{pos}_{column_suffix}"))
    return when_expr

def _reorder_columns(boardsdf: pl.DataFrame) -> pl.DataFrame:
    # Move all validation columns to the end
    derived_cols = [col for col in boardsdf.columns if "Derived" in col]
    validation_cols = [col for col in boardsdf.columns if "Validation" in col]
    other_cols = [col for col in boardsdf.columns if "Derived" not in col and "Validation" not in col]
    boardsdf = boardsdf.select(other_cols + derived_cols + validation_cols)
    return boardsdf

def validate_and_combine_columns(df: pl.DataFrame, primary: str, secondary: str, validation_col: str) -> pl.DataFrame:
    if df[primary].dtype == pl.Utf8:
        primary_invalid = _is_invalid(primary)
        secondary_invalid = _is_invalid(secondary)
    else:
        primary_invalid = pl.col(primary).is_null()
        secondary_invalid = pl.col(secondary).is_null()

    df = df.with_columns([
        pl.when(primary_invalid)
            .then(pl.when(secondary_invalid).then(pl.lit("Missing")).otherwise(pl.lit("Derived")))
            .otherwise(pl.when(secondary_invalid)
                    .then(pl.lit("Primary"))
                    .otherwise(pl.when(pl.col(primary) == pl.col(secondary))
                                .then(pl.lit("Match"))
                                .otherwise(pl.lit("Mismatch"))))
        .alias(validation_col)
    ])
    
    return df.with_columns([
        pl.when(primary_invalid)
            .then(pl.col(secondary))
            .otherwise(pl.col(primary))
        .alias(primary)
    ])
    
def process_boards(boardsdf: pl.DataFrame, dealsdf: pl.DataFrame) -> pl.DataFrame:
    """Process all boards more efficiently using Polars operations."""
    
    # Extract required columns for processing
    process_data = boardsdf.select(['DealUID', 'Contract', 'Auction'])
    dealer_series = process_data.join(
                        dealsdf.select(['DealUID', 'Dealer']), 
                        on='DealUID', 
                        how='left'
                    )['Dealer'].fill_null("N")
    # Process auctions
    auction_results = process_auction_vectorized(dealer_series, process_data['Auction'])
    boardsdf = boardsdf.drop("Auction").hstack(auction_results).with_columns(
        pl.when(_is_invalid("Auction") & (pl.col("Contract") == "AP"))
            .then(pl.lit("AP"))
            .otherwise(pl.col("Auction"))
            .alias("Auction"),
        pl.when(pl.col("Contract") == "AP")
            .then(pl.lit("Legal"))
            .otherwise(pl.col("AuctionCheck"))
            .alias("AuctionCheck")
    )
    
    boardsdf = validate_and_combine_columns(boardsdf, "Contract", "DerivedContract", "ContractValidation")
    boardsdf = validate_and_combine_columns(boardsdf, "Declarer", "DerivedDeclarer", "DeclarerValidation")
    boardsdf = boardsdf.with_columns(pl.col("Declarer").map_elements(lambda x: str_to_side(x), return_dtype=pl.Utf8).alias("DeclSide"))
    
    boardsdf = boardsdf.join(dealsdf.select(["DealUID", "Dealer", "Vulnerability"]), on="DealUID", how="left") 
    # Compute the score and tricksMade if missing 
    boardsdf = compute_contract_details_and_NSscore(boardsdf)
    boardsdf = compute_TricksMade(boardsdf)
    boardsdf = validate_and_combine_columns(boardsdf, "RawScoreNS", "DerivedScoreNS", "ScoreValidation")
    boardsdf = validate_and_combine_columns(boardsdf, "TricksMade", "DerivedTricks", "TricksValidation")
    boardsdf = boardsdf.drop(["BiddingMD", "Commentary", "Dealer", "Vulnerability"])

    # Validate Contract, Declarer, and Lead
    boardsdf = boardsdf.with_columns(pl.col("Play").map_elements(lambda x: "" if len(x) < 2 else x[:2], return_dtype=pl.Utf8).alias("DerivedLead"))
    boardsdf = validate_and_combine_columns(boardsdf, "Lead", "DerivedLead", "LeadValidation")
    boardsdf = boardsdf.drop(["Play"])
    
    return boardsdf

def add_uids(df: pl.DataFrame) -> pl.DataFrame:
    """
    Using group_by() for UID creation - offers better performance for large datasets
    """
    
    xlations: Dict[str, str] = fuzzy_deduplicate_events(df["EventName"].to_list())
    df_with_uids = df.with_columns([pl.col("EventName").replace_strict(xlations).alias("CleanedEventName")
        ]).with_columns([
            # EventUID: dense_rank over EventName
            pl.col('CleanedEventName').rank('dense').alias('EventUID'),
            
            # MatchID: rank within each event
            pl.col('MatchName').rank('dense').over('CleanedEventName').alias('MatchID')
        ]).with_columns([
            # HandUID: rank over hand-specific fields (independent of other UIDs)
            pl.struct(['Hands', 'Dealer', 'Vulnerability']).rank('dense').alias('HandUID'),
        
            # DealUID: rank over combination of EventUID, MatchID, Hands
            # Using EventUID/MatchID instead of EventName/MatchName for efficiency
            pl.struct(['EventUID', 'MatchID', 'Hands']).rank('dense').alias('DealUID')
        ]).with_columns([
            # BoardUID: rank over all 8 fields that define a unique board
            # Leverages DealUID computation by adding the remaining 5 fields
            pl.struct(['DealUID', 'DealNum', 'TableID', 'North', 'East', 'South', 'West']).rank('dense').alias('BoardUID')
        ])
    
    # Reorder columns
    uid_cols = ['BoardUID', 'DealUID', 'EventUID', 'MatchID', 'HandUID']
    other_cols = [col for col in df_with_uids.columns if col not in uid_cols]
    return df_with_uids.select(uid_cols + other_cols)

def update_scoring_form(df):
    # Step 1: Handle direct mappings and keep IMPs/MPs as is
    df = df.with_columns(
        pl.when(pl.col("ScoringForm") == "MatchPoints")
        .then(pl.lit("MPs"))
        .otherwise(pl.col("ScoringForm"))
        .alias("ScoringForm")
    )
    
    # Step 2: Identify rows that need board count analysis
    needs_analysis = ~pl.col("ScoringForm").is_in(["IMPs", "MPs"])
    
    # Step 3: Calculate board counts per deal and find most common count per event-match
    board_counts = (
        df.group_by("DealUID")
        .agg([
            pl.count().alias("boards_per_deal"),
            pl.col("EventUID").first(),
            pl.col("MatchID").first()
        ])
        .group_by(["EventUID", "MatchID"])
        .agg(pl.col("boards_per_deal").mode().first().alias("common_board_count"))
        .with_columns([
            (pl.col("common_board_count").alias("Tables")),
            (
                # Map board count to scoring form
                pl.when(pl.col("common_board_count") == 1)
                .then(pl.lit("UNKNOWN"))
                .when(pl.col("common_board_count") == TABLES_IN_TEAM_GAME)
                .then(pl.lit("IMPs"))
                .otherwise(pl.lit("MPs"))
                .alias("new_scoring_form")
            )])
    )
    
    # Step 4: Join back and update ScoringForm
    result = (
        df.join(
            board_counts,
            on=["EventUID", "MatchID"],
            how="left"
        )
        .with_columns(
            pl.when(needs_analysis & pl.col("new_scoring_form").is_not_null())
            .then(pl.col("new_scoring_form"))
            .otherwise(pl.col("ScoringForm"))
            .alias("ScoringForm")
        )
        .drop("common_board_count", "new_scoring_form")
    )
    
    return result

output_dir: Optional[Path] = None

def df_to_csv(which: pl.DataFrame, fname: str, **kwargs) -> None:
    if output_dir and len(which) > 0:
        which.write_csv(f"{output_dir}/{fname}.csv")
        logging.warning(f"Wrote {fname}.csv")
    
def process_hands(hands: str) -> Dict[str, str]:
    hands_dict: Optional[Dict[str, str]] = parse_hand_string(hands)
    if hands_dict is None:
        return {}
    # Analyze each hand
    for direction in ['N', 'E', 'S', 'W']:
        hand_features = analyze_hand(hands_dict[f"{direction}_Hand"])
        # Add direction prefix to each feature
        for key, value in hand_features.items():
            hands_dict[f'{direction[0:1]}_{key}'] = value
    return hands_dict

def extract_derived_features(rawdf: pl.DataFrame, generateDD: bool = False) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Write the collected data to CSV files using Polars for better performance."""
    # Create DataFrames for each entity type
    events_df = (
        rawdf.select(["EventUID", "MatchID", "EventName", "MatchName", "EventLocation", "MatchDate", "ScoringForm", "Tables", "FilePath"])
        .unique(subset=["EventUID", "MatchID"], keep="first")
    )
    
    allDf = rawdf.with_columns(pl.col("FilePath").map_elements(lambda x: Path(x).suffix[1:].upper(), return_dtype=pl.Utf8).alias("SourceType"))
    
    deals_df = (
        allDf.select(["DealUID", "HandUID", "EventUID", "MatchID", "SourceType", "DealNum", "Dealer", "Vulnerability", "Hands", "DDS", "DealerValidation", "VulValidation"])
        .unique(subset=["DealUID"], keep="first")
    )
    
    boards_df = (
        allDf.select(["BoardUID", "DealUID", "TableID", "SourceType", "North", "East", "South", "West", "Declarer", 
                      "Contract", "TricksMade", "RawScoreNS", "Auction", "Lead", "Play", "BiddingMD", "Commentary"])
        .unique(subset=["BoardUID"], keep="first")
    )
    hands_df = (
        deals_df.select(["HandUID", "Hands", "Dealer", 'Vulnerability'])
        .unique(subset=["HandUID"], keep="first")
    )
    hands_df = hands_df.with_columns(
            pl.col("Hands")
            .map_elements(process_hands, return_dtype=pl.Struct)
            .alias("processed_data")
        ).unnest("processed_data")  # Expand dict to separate columns
    hands_df = hands_df.filter(pl.col("N_Hand").is_not_null()).with_columns(
        pl.format("W:{} {} {} {}", 
                pl.col("W_Hand"), pl.col("N_Hand"), pl.col("E_Hand"), pl.col("S_Hand"))
        .alias("Hands")
    )
    valid_hand_lookup = hands_df.select("HandUID")

    if generateDD:
        hands_df = create_dd_columns(hands_df)
    
    # Filter other DataFrames using efficient joins instead of is_in()
    # Filter deals_df using semi join (keeps only matching rows)
    deals_df = deals_df.join(valid_hand_lookup, on="HandUID", how="semi")
    
    # Filter boards_df using DealUID from the already filtered deals_df
    valid_deal_lookup = deals_df.select("DealUID")
    boards_df = boards_df.join(valid_deal_lookup, on="DealUID", how="semi")
    
    # Filter allDf using semi join
    allDf = allDf.join(valid_hand_lookup, on="HandUID", how="semi")    # Write individual CSV files

    return allDf, events_df, deals_df, boards_df, hands_df

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch

def generate_2d_waterfall(data: List[List[Any]], x_label: str, y_label: str, fname: str) -> None:
    # Dict must have three elements -- a string that is the label for each rectangle, and the x and y dimensions
    df = pl.DataFrame(data, schema=["Label", x_label, y_label], orient="row")
    fpath: str = f"{output_dir}/{fname}.png" if output_dir else f"{fname}.png"

    # Plot
    _, ax = plt.subplots(figsize=(8,6))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]  # get default color cycle

    prev_x, prev_y = 0.0, 0.0
    x_max: float = 0.0
    y_max: float = 0.0
    i = 0
    for row in df.iter_rows(named=True):
        # Cast to float to keep matplotlib happy
        curr_x = float(row[x_label])
        curr_y = float(row[y_label])
        x_max = max(curr_x, x_max)
        y_max = max(curr_y, y_max)
        color = colors[i % len(colors)]  # cycle through colors
        i = i + 1

        rect = Rectangle(
            (0.0, 0.0),
            curr_x,
            curr_y,
            alpha=0.6,
            fc=color,
            ec="black",
            label=row["Label"]
        )
        ax.add_patch(rect)

        prev_x, prev_y = curr_x, curr_y
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(f"{y_label} vs {x_label} by Factor (Stepwise Stacked View)")
    # Axis limits (ensure floats)
    ax.set_xlim(0, x_max * 1.1)
    ax.set_ylim(0, y_max * 1.1)
    legend_patches = [
        Patch(facecolor=colors[i % len(colors)], edgecolor="black", label=row["Label"])
        for i, row in enumerate(df.iter_rows(named=True))
    ]
    ax.legend(handles=legend_patches)

    # Save chart to file
    plt.savefig(fpath, dpi=300, bbox_inches="tight")
    plt.close()

def generate_summaries(auctionsDf: pl.DataFrame) -> None:
    def _summaryRow(desc: str, df: pl.DataFrame, totHands: int) -> tuple[str, int, float, int, float]:
        return (desc, df.height, df.height / totHands, int(df["SWING"].sum()), df["SWING"].sum()/df.height if df.height > 0 else 0.0)
    def _chartRow(desc: str, df: pl.DataFrame, totHands: int) -> tuple[str, float, float]:
        return (desc, df.height / totHands, df["SWING"].sum()/df.height if df.height > 0 else 0.0)
    
    handsWithAuctions: int = auctionsDf.height

    summaryData: List[List[Any]] = [
        list(_summaryRow("Hands with valid auctions matching contracts", auctionsDf, handsWithAuctions)),
        list(_summaryRow("Valid auction, Same Contract/Side", auctionsDf.filter(pl.col("SameBid") & pl.col("SameDeclSide")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same Contract/Declarer", auctionsDf.filter(pl.col("SameContract")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same Contract/Side, Diff Declarer", auctionsDf.filter(pl.col("RightSide")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same Contract, Diff Sides", auctionsDf.filter(pl.col("SameBid") & ~pl.col("SameDeclSide")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Different contracts, same side", auctionsDf.filter(pl.col("SameDeclSide") & ~pl.col("SameBid")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Different contracts, different sides", auctionsDf.filter(~pl.col("SameDeclSide") & ~pl.col("SameBid")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same contract, declarer, and lead", auctionsDf.filter(pl.col("SameContract") & pl.col("SameLead")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same contract and declarer, different lead", auctionsDf.filter(pl.col("SameContract") & ~pl.col("SameLead")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same Auction/Contract/Declarer", auctionsDf.filter(pl.col("SameAuction")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Diff Auction, Same Contract/Declarer", auctionsDf.filter(pl.col("SameContract") & ~pl.col("SameAuction")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Intervention at Neither Table", auctionsDf.filter(_is_invalid("Intervention_1") & _is_invalid("Intervention_2")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Intervention at One Table", auctionsDf.filter(_is_valid("Intervention_1").xor(_is_valid("Intervention_2"))), handsWithAuctions)),
        list(_summaryRow("Valid auction, Intervention at Both Tables", auctionsDf.filter(_is_valid("Intervention_1") & _is_valid("Intervention_2")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same auction and lead at both tables", auctionsDf.filter(pl.col("SameAuction") & pl.col("SameLead")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same auction, different leads", auctionsDf.filter(pl.col("SameAuction") & ~pl.col("SameLead")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same contract/declarer, Different auctions,same lead", auctionsDf.filter(pl.col("SameContract") & ~pl.col("SameAuction") & pl.col("SameLead")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same contract/declarer, Different auctions,different leads", auctionsDf.filter(pl.col("SameContract") & ~pl.col("SameAuction") & ~pl.col("SameLead")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same Opening, Intervention at Neither Table", auctionsDf.filter(pl.col("SameOpening") & _is_invalid("Intervention_1") & _is_invalid("Intervention_2")), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same Opening, Intervention at One Table", auctionsDf.filter(pl.col("SameOpening") & _is_valid("Intervention_1").xor(_is_valid("Intervention_2"))), handsWithAuctions)),
        list(_summaryRow("Valid auction, Same Opening, Intervention at Both Tables", auctionsDf.filter(pl.col("SameOpening") & _is_valid("Intervention_1") & _is_valid("Intervention_2")), handsWithAuctions))
    ]
    df_to_csv(
        pl.DataFrame(
            summaryData,
            schema=["Description", "Count", "Percentage", "Total_SWING", "Avg_SWING"],
            orient="row",
            schema_overrides={
                "Description": pl.Utf8,
                "Count": pl.Int64,
                "Percentage": pl.Float64,
                "Total_SWING": pl.Int64,
                "Avg_SWING": pl.Float64
            }
        ),
        "Summary",
        column_formats={
            "Percentage": {"num_format": "0.0%"},
            "Avg_SWING": {"num_format": "0.000"}
        },
        autofit=True
    )
    # chart_data: List[List[Any]] = [
    #     list(_chartRow("All Hands", auctionsDf, handsWithAuctions)),
    #     list(_chartRow("Same Contract/Side", auctionsDf.filter(pl.col("SameBid") & pl.col("SameDeclSide")), handsWithAuctions)),
    #     list(_chartRow("Same Contract/Declarer", auctionsDf.filter(pl.col("SameContract")), handsWithAuctions)),
    #     list(_chartRow("Same Auction/Contract/Declarer", auctionsDf.filter(pl.col("SameAuction")), handsWithAuctions)),
    #     list(_chartRow("Same Auction/Contract/Declarer/Lead", auctionsDf.filter(pl.col("SameAuction") & pl.col("SameLead")), handsWithAuctions)),
    # ]
    # generate_2d_waterfall(chart_data, "Frequency", "Ave Swing", "Swing_Chart")

def analyze_early_bids(auctionsDf: pl.DataFrame) -> None:
    # Process Early Bids
    num_deals_with_auctions: int = auctionsDf.height
    pivot_df: pl.DataFrame = (
        auctionsDf.filter(_is_valid("EarlyBid"))  # Only include rows where EarlyBid is True
        .group_by("EarlyBid")
        .agg([
            pl.col("EarlyBid").count().cast(pl.Int32).alias("Count of EarlyBid"),
            pl.col("EBScore").sum().alias("Sum of EBScore"),
            pl.col("EBScore").mean().alias("Ave of EBScore")
        ])
    ).with_columns(
        (pl.col("Count of EarlyBid")/num_deals_with_auctions).alias("Percent")
    ).sort(
        "Count of EarlyBid", descending=True
    ).select(
        ["EarlyBid", "Count of EarlyBid", "Percent", "Sum of EBScore", "Ave of EBScore"]
    )

    # For the "Grand Total" row
    totEB: int = int(pivot_df["Count of EarlyBid"].sum())
    totEBScore: int = int(pivot_df["Sum of EBScore"].sum())
    grand_total = pl.DataFrame({
        "EarlyBid": ["Grand Total"],
        "Count of EarlyBid": totEB,
        "Percent": [pivot_df["Percent"].sum()],
        "Sum of EBScore": totEBScore,
        "Ave of EBScore": totEBScore/totEB if totEB else 0.0
    })
    final_result = pl.concat([pivot_df, grand_total])

    df_to_csv(
        final_result, 
        "EarlyBids",
        column_formats={
            "Percent": {"num_format": "0.0%"},
            "Ave of EBScore": {"num_format": "0.00"}
        },
        autofit=True
    )

def analyze_openings(auctionsDf: pl.DataFrame) -> None:
    # Analyze the opening bids - optimized aggregation
    sameOpDf: pl.DataFrame = (
        auctionsDf.filter(pl.col("SameOpening"))
        .group_by("Opening_2")
        .agg([
            pl.count().alias("SameOpeningCount"),
            pl.col("SameAuction").sum().alias("SameAuctionCount"),
            pl.col("SameContract").sum().alias("SameContractCount")
        ])
        .rename({"Opening_2": "Opening"})
        .with_columns([(pl.col("SameAuctionCount")/pl.col("SameOpeningCount")).alias("SameAuctionPercent"),
                       (pl.col("SameContractCount")/pl.col("SameOpeningCount")).alias("SameContractPercent")])
    )

    openings_melted = pl.concat([
        auctionsDf.select(pl.col("Opening_1").alias("Opening"), pl.col("SWING")),
        auctionsDf.select(pl.col("Opening_2").alias("Opening"), pl.col("SWING"))
    ])

    total_auctions = TABLES_IN_TEAM_GAME * auctionsDf.height
    openingDf = (
        openings_melted.group_by("Opening")
        .agg([
                pl.count().alias("Count"),
                pl.col("SWING").sum().alias("Tot SWING")
        ])
        .with_columns([
            (pl.col("Count")).alias("Count"),
            (pl.col("Count") / total_auctions).alias("Percentage"),
            (pl.col("Tot SWING") / pl.col("Count")).alias("Ave SWING")
        ])
        .join(
            sameOpDf, 
            on="Opening",  # Explicit join key
            how="outer"
        ).with_columns(
            (pl.col("SameOpeningCount") / pl.col("Count")).alias("SameOpeningPercent")
        )
        .sort("Count", descending=True)
    ).select([
            "Opening", 
            "Count",
            "Percentage", 
            "Ave SWING",
            "SameOpeningCount",
            "SameOpeningPercent",
            "SameAuctionCount",
            "SameAuctionPercent",
            "SameContractCount",
            "SameContractPercent"
        ])

    df_to_csv(
        openingDf, 
        "Openings",
        column_formats={
            "Percentage": {"num_format": "0.0%"},
            "SameOpeningPercent": {"num_format": "0.0%"},
            "SameAuctionPercent": {"num_format": "0.0%"},
            "Ave SWING": {"num_format": "0.00"}
        },
        autofit=True
    )

def add_leader_view(boardsDf: pl.DataFrame) -> pl.DataFrame:
    # Create and write the Opening Lead Sheet
    def get_leader_holding(hand: str, lead: str) -> str:
        try:
            suit = lead[0:1]
            suitHoldings: List[str] = hand.split(".")
            holding:str = suitHoldings[SUIT_INDICES[suit]]
            return holding
        except (IndexError, KeyError, AttributeError) as e:
            logging.info(f"No lead {lead} in hand {hand}: {e}")
            return ""
    
    def lead_type(holding: str, played_card: str) -> str:
        # Strip the suit symbol from the holding and card
        played_card = played_card[1:2]
        # Make sure if played_card is actually in the holding
        if played_card not in holding:
            return "UNKNOWN"
        # Define card order for reference

        # If holding has only one card
        if len(holding) == 1:
            return "SINGLETON"

        # Get indices of cards in holding and the played card
        played_index = CARD_ORDER.index(played_card)
        holding_indices = [CARD_ORDER.index(card) for card in holding]

        # Rule 2 and 3: Check for TOUCHING or unsupported HONOR lead
        if played_card in "AKQJ":
            if (played_index > 0 and CARD_ORDER[played_index - 1] in holding) or \
            (played_index < len(CARD_ORDER) - 1 and CARD_ORDER[played_index + 1] in holding):
                return "TOUCHING"
            else:
                return "UNSUPPORTED HONOR"
        if played_card == "T" and ('J' in holding or '9' in holding):
            return "TOUCHING"
        if played_card == '9' and 'T' in holding:
            return "TOUCHING"

        # Rule 5: Check for doubleton
        if len(holding) == 2:
            return "LOW_FROM_DBLTN" if played_index == max(holding_indices) else "TOP_OF_DBLTN"
        else:
            # Rule 6: Check for nth_BEST
            sorted_holding_indices = sorted(holding_indices)
            rank = sorted_holding_indices.index(played_index) + 1
            return f"{rank}_BEST"
        
    LeaderView_columns = ["BoardUID", "DealNum", "Contract", "Declarer", "Leader", "Lead", "SuitHolding", "Lead_Type", "Led_Suit_Len"]
    boardsDf = boardsDf.with_columns(
            pl.col("Declarer").map_elements(lambda x: Direction.from_str(x).next().abbreviation(), return_dtype=pl.Utf8).alias("Leader")
        ).with_columns(
            _create_player_column_mapping("Leader", "Hand").alias("LeaderHand")
        ).with_columns(
            pl.struct("LeaderHand", "Lead")
            .map_elements(lambda combined: get_leader_holding(combined["LeaderHand"], combined["Lead"]), return_dtype=pl.Utf8)
            .alias("SuitHolding")
        ).with_columns(
            pl.struct("SuitHolding", "Lead")
            .map_elements(lambda combined: lead_type(combined["SuitHolding"], combined["Lead"]), return_dtype=pl.Utf8)
            .alias("Lead_Type"),
            pl.col("SuitHolding").map_elements(len, return_dtype=pl.Int64).alias("Led_Suit_Len")
        )
    df_to_csv(boardsDf.select(pl.col(LeaderView_columns)), "LeaderView")
    return boardsDf

# Create and write the OpenerView sheet
def relative_vulnerability(vul: str, dirn: str) -> str:
    seat: str = dirn[0:1]
    if vul == 'Z':
        return "None"
    elif vul == 'B':
        return "Both"
    elif vul == 'N':
        return "We" if (seat == 'N' or seat == 'S') else "They"
    elif vul == 'E':
        return "We" if (seat == 'E' or seat == 'W') else "They"
    else:
        return "Unknown"

# Define helper functions for map_elements
def get_lho_bid(row):
    """Get the LHO bid (next bid after opening)"""
    bids = row["_bids"] if row["_bids"] else []
    open_seat = row["OpenSeat"]
    
    # Check if the index exists (OpenSeat + 1 for next bid)
    if open_seat is not None and 0 <= open_seat < len(bids):
        return bids[open_seat]
    return ""

def get_response_bid(row):
    """Get the response bid (second bid after opening)"""
    bids = row["_bids"] if row["_bids"] else []
    open_seat = row["OpenSeat"]
    
    # Check if the index exists (OpenSeat + 2 for second bid after)
    if open_seat is not None and 0 <= open_seat + 1 < len(bids):
        return bids[open_seat + 1]
    return ""

def add_opener_view(boardsDf: pl.DataFrame) -> pl.DataFrame:
    boardsDf = boardsDf.with_columns([
            pl.col("Opener").map_elements(lambda x: Direction.from_str(x).next().abbreviation(), return_dtype=pl.Utf8).alias("LHO"),
            pl.col("Opener").map_elements(lambda x: Direction.from_str(x).previous().abbreviation(), return_dtype=pl.Utf8).alias("RHO")
        ]).with_columns([
            pl.struct("Vulnerability", "Opener")
            .map_elements(lambda combined: relative_vulnerability(combined["Vulnerability"], combined["Opener"]), return_dtype=pl.Utf8)
            .alias("OpenerVul"),
            _create_player_column_mapping("Opener", "Hand").alias("OpenerHand"),
            _create_player_column_mapping("LHO", "Hand").alias("LHOHand"),
            _create_player_column_mapping("Responder", "Hand").alias("ResponderHand"),
            _create_player_column_mapping("RHO", "Hand").alias("RHOHand"),
            _create_player_column_mapping("Opener", "Shape").alias("OpenerShape"),
            _create_player_column_mapping("Opener", "Pattern").alias("OpenerPattern"),
            _create_player_column_mapping("Opener", "Total_HCP").alias("OpenerHCP"),
            _create_player_column_mapping("LHO", "Shape").alias("LHOShape"),
            _create_player_column_mapping("LHO", "Pattern").alias("LHOPattern"),
            _create_player_column_mapping("LHO", "Total_HCP").alias("LHOHCP"),
            _create_player_column_mapping("Responder", "Shape").alias("ResponderShape"),
            _create_player_column_mapping("Responder", "Pattern").alias("ResponderPattern"),
            _create_player_column_mapping("Responder", "Total_HCP").alias("ResponderHCP"),
            _create_player_column_mapping("RHO", "Shape").alias("RHOShape"),
            _create_player_column_mapping("RHO", "Pattern").alias("RHOPattern"),
            _create_player_column_mapping("RHO", "Total_HCP").alias("RHOHCP")
        ])
    
    # Create the _bids column first
    boardsDf = boardsDf.with_columns([
        pl.col("Auction").str.split("-").alias("_bids")
    ])
    
    boardsDf = boardsDf.with_columns([
        # LHO bid (next bid after opening)
        pl.struct(["_bids", "OpenSeat"])
        .map_elements(get_lho_bid, return_dtype=pl.Utf8)
        .alias("LHOBid"),
        
        # Response bid (second bid after opening)
        pl.struct(["_bids", "OpenSeat"])
        .map_elements(get_response_bid, return_dtype=pl.Utf8)
        .alias("Response")
    ]).drop(["_bids", "Responder", "LHO", "RHO"])
    return boardsDf
    
def write_opener_view(full_deals_df: pl.DataFrame) -> None:
    """Write OpenerView.csv with OpenerIMPs from full_deals_df."""
    
    OpenerView_columns = [
        "BoardUID", "DealNum", "Dealer", "Opener", "OpenSeat", "Opening", 
        "OpenerShape", "OpenerPattern", "OpenerHCP", "OpenerVul", "OpenerIMPs"
    ]
    
    # Define the columns we want from each table
    columns_to_unpivot = [
        "BoardUID", "Opener", "OpenSeat", "Opening", 
        "OpenerShape", "OpenerPattern", "OpenerHCP", "OpenerVul", "OpenerIMPs"
    ]
    
    # Create DataFrames for each table by renaming _1 and _2 columns
    table1_cols = [pl.col("DealNum"), pl.col("Dealer")] + [pl.col(f"{col}_1").alias(col) for col in columns_to_unpivot]
    table2_cols = [pl.col("DealNum"), pl.col("Dealer")] + [pl.col(f"{col}_2").alias(col) for col in columns_to_unpivot]

    table1 = full_deals_df.select(table1_cols)
    table2 = full_deals_df.select(table2_cols)
    
    # Combine both tables vertically
    opener_view_df = pl.concat([table1, table2])
    
    df_to_csv(opener_view_df.select(pl.col(OpenerView_columns)).sort("BoardUID"), "OpenerView")

def add_declarer_view(boardsDf: pl.DataFrame) -> pl.DataFrame:
    # Create and write the DeclarerView sheet
    DeclarerView_columns = ["BoardUID", "DealUID", "Declarer", "DeclarerVul", "DeclarerScore", 
                            "DeclarerHCP", "DummyHCP", "TotalHCP", "DeclarerShape", "DummyShape", "DeclarerPattern", "DummyPattern"]
    boardsDf = boardsDf.with_columns(
            pl.col("Declarer").map_elements(lambda x: Direction.from_str(x).partner().abbreviation(), return_dtype=pl.Utf8).alias("Dummy")
        ).with_columns([
            pl.struct("Vulnerability", "Declarer")
            .map_elements(lambda combined: relative_vulnerability(combined["Vulnerability"], combined["Declarer"]), return_dtype=pl.Utf8)
            .alias("DeclarerVul"),
            _create_player_column_mapping("Declarer", "Shape").alias("DeclarerShape"),
            _create_player_column_mapping("Declarer", "Pattern").alias("DeclarerPattern"),
            _create_player_column_mapping("Declarer", "Total_HCP").alias("DeclarerHCP"),
            _create_player_column_mapping("Declarer", "Hand").alias("DeclarerHand"),
            _create_player_column_mapping("Dummy", "Shape").alias("DummyShape"),
            _create_player_column_mapping("Dummy", "Pattern").alias("DummyPattern"),
            _create_player_column_mapping("Dummy", "Total_HCP").alias("DummyHCP"),
            _create_player_column_mapping("Dummy", "Hand").alias("DummyHand"),
            (pl.col("RawScoreNS") * pl.when(pl.col("Declarer").is_in(["N", "S"])).then(1).otherwise(-1)).alias("DeclarerScore")]
        ).with_columns(
            (pl.col("DeclarerHCP") + pl.col("DummyHCP")).alias("TotalHCP")
        ).drop("Dummy")
    df_to_csv(boardsDf.select(pl.col(DeclarerView_columns)), "DeclarerView")
    return boardsDf

def _analyze_records(processed_dealsdf: pl.DataFrame, processed_boardsdf: pl.DataFrame) -> None:
    # Create an expanded table with deal info and info about each board in a single row
    # Find most common board count (choose smallest number if tied)
    commonest_board_count = (processed_boardsdf.group_by("DealUID")
                          .count()
                          .rename({"count": "group_size"})
                          .group_by("group_size")
                          .count()
                          .sort(["count", "group_size"], descending=[True, False])
                          .item(0, "group_size"))
    if commonest_board_count != TABLES_IN_TEAM_GAME:
        logging.error(f"Most common board count is {commonest_board_count}. Unexpected, exiting")
        raise ValueError

    processed_boardsdf = _reorder_columns(processed_boardsdf)
    validBoardsDf: pl.DataFrame = processed_dealsdf.join(processed_boardsdf.drop("SourceType"), on="DealUID", how="inner")
    validBoardsDf = validBoardsDf.filter(pl.col("AuctionCheck") == "Legal")
    validBoardsDf = validBoardsDf.filter((pl.col("ContractValidation") != "Mismatch") & (pl.col("ContractValidation") != "Missing"))
    validBoardsDf = validBoardsDf.filter((pl.col("DeclarerValidation") != "Mismatch") & (pl.col("DeclarerValidation") != "Missing"))
    validBoardsDf = validBoardsDf.filter((pl.col("LeadValidation") != "Mismatch") & (pl.col("LeadValidation") != "Missing"))
    validBoardsDf = validBoardsDf.filter((pl.col("ScoreValidation") != "Mismatch") & (pl.col("ScoreValidation") != "Missing"))
    deal_counts: int = validBoardsDf.group_by("DealUID").count()
    deals_to_keep = deal_counts.filter(pl.col("count") == 2).select("DealUID")
    validBoardsDf = validBoardsDf.join(deals_to_keep, on="DealUID", how="inner").sort(["DealUID", "TableID"])
    
    if "DD_W_N" in processed_dealsdf.columns: # Double-dummy analysis included
        validBoardsDf = process_pars(validBoardsDf)
    validBoardsDf = add_opener_view(validBoardsDf)
    validBoardsDf = add_leader_view(validBoardsDf)
    validBoardsDf = add_declarer_view(validBoardsDf)
    df_to_csv(validBoardsDf, "FullBoards")
    
    validDf = expand_matches(processed_dealsdf, validBoardsDf)
    df_to_csv(validDf, "FullDeals")
    
    generate_summaries(validDf)
    analyze_early_bids(validDf)
    analyze_openings(validDf)
    write_opener_view(validDf)
    
def _process_records(reclist: List[BoardRecord], generateDD: bool = False, outdir: Optional[Path] = None) -> Tuple[pl.DataFrame, pl.DataFrame]:
    logging.warning("Start process_records")
    global output_dir
    output_dir = outdir
    rawdf: pl.DataFrame = pl.from_records(reclist)
    df_to_csv(rawdf, "RawData")

    # Validate dealer and vulnerability per deal
    rawdf = rawdf.with_columns([
        # Compute expected dealer and vulnerability for all rows
        pl.col("DealNum").map_elements(dealNo2dealer, return_dtype=pl.Utf8).alias("dealer2"),
        pl.col("DealNum").map_elements(dealNo2vul, return_dtype=pl.Utf8).alias("vul2"),
    ])
    rawdf = validate_and_combine_columns(rawdf, "Dealer", "dealer2", "DealerValidation")
    rawdf = validate_and_combine_columns(rawdf, "Vulnerability", "vul2", "VulValidation")
    rawdf = rawdf.drop(["dealer2", "vul2"])
    # Add UIDs and fix scoring form
    rawdf = add_uids(rawdf)
    rawdf = update_scoring_form(rawdf)

    # Validate hands and derive hand-specific features
    lineProf.add_function(process_hands)
    # Separate into event, deals, and boards-specific dataframes
    alldf, eventsdf, dealsdf, boardsdf, handsdf = extract_derived_features(rawdf, generateDD)
    df_to_csv(alldf, "all")
    df_to_csv(eventsdf, "events")
    df_to_csv(dealsdf, "deals")
    df_to_csv(boardsdf, "boards")
    df_to_csv(handsdf, "hands")
    
    # Validate dealer and vulnerability per deal
    processed_dealsdf = dealsdf.join(handsdf.drop(["Dealer", "Vulnerability"]), on='HandUID', how='left')
    df_to_csv(processed_dealsdf, "ProcessedDeals")
    
    # Now process each board
    processed_boardsdf = process_boards(boardsdf, dealsdf)
    df_to_csv(processed_boardsdf, "ProcessedBoards")
    return processed_dealsdf, processed_boardsdf

def process_and_analyze_records(reclist: List[BoardRecord], generateDD: bool, outdir: Path) -> None:
    processed_dealsdf, processed_boardsdf = _process_records(reclist, generateDD, outdir)
    _analyze_records(processed_dealsdf, processed_boardsdf)

def process_records(reclist: List[BoardRecord], generateDD: bool, outdir: Optional[Path] = None) -> Tuple[List[Dict], List[Dict]]:
    processed_dealsdf, processed_boardsdf = _process_records(reclist, generateDD, outdir)
    return (list(processed_dealsdf.iter_rows(named=True)), list(processed_boardsdf.iter_rows(named=True)))

def analyze_records(outdir: Path) -> None:
    global output_dir
    output_dir = outdir
    processed_dealsdf = pl.read_csv(f"{output_dir}/ProcessedDeals.csv")
    processed_boardsdf = pl.read_csv(f"{output_dir}/ProcessedBoards.csv")
    _analyze_records(processed_dealsdf, processed_boardsdf)