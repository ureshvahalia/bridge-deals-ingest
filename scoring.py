import bisect
import polars as pl
from typing import Dict

# Constants
DENOM_MAP = {"C": 0, "D": 1, "H": 2, "S": 3, "N": 4}
TRICK_VAL = [20, 20, 30, 30, 30]
BASE_SCORE = [0, 0, 0, 0, 10]

def parse_contract_details(df: pl.DataFrame) -> pl.DataFrame:
    """
    Common function to parse contract details from Contract, Declarer, and Vulnerability columns.
    Adds helper columns used by both scoring functions.
    """
    return df.with_columns([
        # Parse contract
        pl.col("Contract").str.extract(r"(\d)", 1).cast(pl.Int64).alias("Level"),
        pl.col("Contract").str.extract(r"([CDHSN])", 1).alias("Strain"),
        pl.col("Contract").str.extract(r"([CDHSN])", 1).map_elements(
            lambda x: DENOM_MAP.get(x), return_dtype=pl.Int64
        ).alias("_Denom"),
        # Determine premium (1 = normal, 2 = X, 4 = XX)
        pl.when(pl.col("Contract").str.contains("XX"))
          .then(4)
          .when(pl.col("Contract").str.contains("X"))
          .then(2)
          .otherwise(1)
          .alias("Premium"),
        # Declarer's side (1 for NS, -1 for EW)
        pl.when(pl.col("Declarer").is_in(["N", "S"])).then(1).otherwise(-1).alias("_SideVal"),
        # Vulnerability of declarer's side
        (
            (pl.col("Vulnerability") == "B") |
            (pl.col("Declarer").is_in(["N", "S"]) & (pl.col("Vulnerability") == "N")) |
            (pl.col("Declarer").is_in(["E", "W"]) & (pl.col("Vulnerability") == "E"))
        ).alias("_AmVul"),
        # Tricks contracted
        (pl.col("Contract").str.extract(r"(\d)", 1).cast(pl.Int64) + 6).alias("_TricksContracted")
    ])

def compute_basic_trick_score() -> pl.Expr:
    """
    Compute the basic trick score (bid level * denomination value + base score) * premium
    """
    return (
        (pl.col("Level") * pl.col("_Denom").map_elements(lambda d: TRICK_VAL[d], return_dtype=pl.Int64) +
         pl.col("_Denom").map_elements(lambda d: BASE_SCORE[d], return_dtype=pl.Int64)) *
        pl.col("Premium")
    )

def compute_game_bonus() -> pl.Expr:
    """
    Compute the game/part-game bonus
    """
    basic_trick_score = compute_basic_trick_score()
    return (
        pl.when(basic_trick_score < 100)
        .then(50)
        .otherwise(pl.when(pl.col("_AmVul")).then(500).otherwise(300))
    )

def compute_slam_bonus() -> pl.Expr:
    """
    Compute slam bonuses (small slam and grand slam)
    """
    return (
        pl.when(pl.col("Level") == 6)
        .then(pl.when(pl.col("_AmVul")).then(750).otherwise(500))
        .when(pl.col("Level") == 7)
        .then(pl.when(pl.col("_AmVul")).then(1500).otherwise(1000))
        .otherwise(0)
    )

def compute_double_bonus() -> pl.Expr:
    """
    Compute double/redouble bonus (50 for X, 100 for XX)
    """
    return (
        pl.when(pl.col("Premium") == 2).then(50)
        .when(pl.col("Premium") == 4).then(100)
        .otherwise(0)
    )

def compute_exact_contract_score() -> pl.Expr:
    """
    Compute the exact score for making the contract with no overtricks
    """
    return (
        compute_basic_trick_score() + 
        compute_game_bonus() + 
        compute_slam_bonus() + 
        compute_double_bonus()
    )

def compute_overtrick_bonus(overtricks_expr: pl.Expr) -> pl.Expr:
    """
    Compute bonus for overtricks
    """
    return (
        pl.when(pl.col("Premium") == 1)
        # Undoubled overtricks
        .then(overtricks_expr * pl.col("_Denom").map_elements(lambda d: TRICK_VAL[d], return_dtype=pl.Int64))
        # Doubled/redoubled overtricks
        .otherwise(
            overtricks_expr *
            pl.when(pl.col("_AmVul")).then(200).otherwise(100) *
            pl.when(pl.col("Premium") == 4).then(2).otherwise(1)
        )
    )

def compute_penalty_score(undertricks_expr: pl.Expr) -> pl.Expr:
    """
    Compute penalty score for undertricks (returns negative value)
    """
    return (
        pl.when(pl.col("Premium") == 1)
        # Undoubled penalties: simple multiplication by vulnerability
        .then(undertricks_expr * pl.when(pl.col("_AmVul")).then(100).otherwise(50))
        .otherwise(
            # Doubled/redoubled penalties follow standard bridge rules
            pl.when(pl.col("_AmVul"))
            # Vulnerable doubled penalties: -200, -500, -800, -1100, then -300 each
            .then(
                ((undertricks_expr * 300) + 100)
                * pl.when(pl.col("Premium") == 4).then(2).otherwise(1)  # Redoubled = 2x doubled
            )
            # Non-vulnerable doubled penalties: -100, -300, -500, -800, then -300 each
            .otherwise(
                pl.when(undertricks_expr == -1).then(-100)
                .when(undertricks_expr == -2).then(-300)
                .when(undertricks_expr == -3).then(-500)
                .otherwise(((undertricks_expr) * 300) + 400)
                * pl.when(pl.col("Premium") == 4).then(2).otherwise(1)  # Redoubled = 2x doubled
            )
        )
    )

def cleanup_helper_columns(df: pl.DataFrame) -> pl.DataFrame:
    """
    Remove helper columns added by parse_contract_details
    """
    return df.drop([
        "_Denom", "_SideVal", "_AmVul", "_TricksContracted"
    ])

def compute_contract_details_and_NSscore(df: pl.DataFrame) -> pl.DataFrame:
    """
    Compute NS score from contract details and tricks made
    """
    df = parse_contract_details(df)
    
    df = df.with_columns([
        (pl.col("TricksMade") - pl.col("_TricksContracted")).alias("_Overtricks")
    ])
    
    # Add ContractType column
    basic_trick_score = compute_basic_trick_score()
    df = df.with_columns([
        pl.when(pl.col("Contract") == "AP")
        .then(pl.lit("AllPass"))
        .when(pl.col("Level") == 7)
        .then(pl.lit("Grand"))
        .when(pl.col("Level") == 6)
        .then(pl.lit("Slam"))
        .when(basic_trick_score >= 100)
        .then(pl.lit("Game"))
        .otherwise(pl.lit("PartScore"))
        .alias("ContractType")
    ])

    # Compute the score
    made_score = (
        compute_exact_contract_score() + 
        compute_overtrick_bonus(pl.col("_Overtricks"))
    ) * pl.col("_SideVal")
    
    penalty_score = compute_penalty_score(pl.col("_Overtricks")) * pl.col("_SideVal")
    
    final_score = (
        pl.when(pl.col("Contract") == "AP").then(0)
        .when(pl.col("_Overtricks") < 0).then(penalty_score)
        .otherwise(made_score)
    )
    
    df = df.with_columns(final_score.alias("DerivedScoreNS"))
    
    return cleanup_helper_columns(df).drop("_Overtricks")

def compute_TricksMade(df: pl.DataFrame) -> pl.DataFrame:
    """
    Reverse function to compute TricksMade from RawScoreNS
    """
    df = parse_contract_details(df)
    
    exact_contract_score = compute_exact_contract_score()
    df = df.with_columns([
        # Convert RawScoreNS to declarer's perspective
        (pl.col("RawScoreNS") * pl.col("_SideVal")).alias("_DeclarerScore"),
        exact_contract_score.alias("_Contract_Score")
    ])
    
    def reverse_score_to_tricks():
        # Handle "AP" (All Pass) case
        ap_case = pl.when(pl.col("Contract") == "AP").then(0)
        
        # Determine if contract was made or failed
        contract_made = pl.col("_DeclarerScore") > 0
        
        # For made contracts, calculate overtricks
        made_case = pl.when(contract_made).then(
            pl.when(pl.col("_DeclarerScore") == pl.col("_Contract_Score"))
            .then(pl.col("_TricksContracted"))  # Exactly made
            .otherwise(
                # Has overtricks - calculate how many
                pl.col("_TricksContracted") + 
                pl.when(pl.col("Premium") == 1)
                # Undoubled overtricks
                .then(
                    (pl.col("_DeclarerScore") - pl.col("_Contract_Score")) / 
                    pl.col("_Denom").map_elements(lambda d: TRICK_VAL[d], return_dtype=pl.Int64)
                )
                # Doubled/redoubled overtricks
                .otherwise(
                    (pl.col("_DeclarerScore") - pl.col("_Contract_Score")) / 
                    (pl.when(pl.col("_AmVul")).then(200).otherwise(100) * 
                     pl.when(pl.col("Premium") == 4).then(2).otherwise(1))
                )
            )
        )
        
        # For failed contracts, calculate undertricks
        failed_case = pl.when(~contract_made).then(
            pl.when(pl.col("Premium") == 1)
            # Undoubled penalties
            .then(
                pl.col("_TricksContracted") + 
                (pl.col("_DeclarerScore") / 
                 pl.when(pl.col("_AmVul")).then(100).otherwise(50))
            )
            # Doubled/redoubled penalties - simplified calculation
            .otherwise(
                pl.when(pl.col("_AmVul"))
                # Vulnerable doubled: approximate reverse calculation
                .then(
                    pl.col("_TricksContracted") + 
                    ((pl.col("_DeclarerScore") * pl.when(pl.col("Premium") == 4).then(0.5).otherwise(1) - 100) / 300)
                )
                # Non-vulnerable doubled: approximate reverse calculation  
                .otherwise(
                    pl.col("_TricksContracted") + 
                    pl.when(pl.col("_DeclarerScore") * pl.when(pl.col("Premium") == 4).then(0.5).otherwise(1) >= -100)
                    .then(-1)
                    .when(pl.col("_DeclarerScore") * pl.when(pl.col("Premium") == 4).then(0.5).otherwise(1) >= -300)
                    .then(-2)
                    .when(pl.col("_DeclarerScore") * pl.when(pl.col("Premium") == 4).then(0.5).otherwise(1) >= -500)
                    .then(-3)
                    .otherwise(
                        ((pl.col("_DeclarerScore") * pl.when(pl.col("Premium") == 4).then(0.5).otherwise(1) + 500) / 300) - 3
                    )
                )
            )
        )
        
        return ap_case.otherwise(made_case.otherwise(failed_case))
    
    # Apply the reverse scoring logic and round to nearest integer
    df = df.with_columns(
        reverse_score_to_tricks().round().cast(pl.Int64).alias("DerivedTricks")
    )
    
    return cleanup_helper_columns(df).drop(["_DeclarerScore", "_Contract_Score"])

def convert_to_imps(myScore: int, otherScore: int) -> int:
    """
    Calculate IMPs gained by myScore relative to otherScore
    Uses the standard WBF IMP conversion table
    """
    IMP_TABLE = [
        0, 20, 50, 90, 130, 170, 220, 270, 320, 370, 
        430, 500, 600, 750, 900, 1100, 1300, 1500, 
        1750, 2000, 2250, 2500, 3000, 3500, 4000, 10000
    ]
    
    difference = myScore - otherScore
    abs_diff = abs(difference)
    
    # Find the index where abs_diff fits in IMP_TABLE
    imp_index = bisect.bisect_right(IMP_TABLE, abs_diff) - 1
    
    return imp_index if difference > 0 else -imp_index

def process_pars(df: pl.DataFrame) -> pl.DataFrame:
    # Create all DD columns as a struct, then extract the right one
    dd_cols = [col for col in df.columns if col.startswith("DD_")]
    
    df = df.with_columns([
        pl.struct(dd_cols + ["Declarer", "Strain"])
        .map_elements(
            lambda row: row[f"DD_{row['Declarer']}_{row['Strain']}"],
            return_dtype=pl.Int8
        )
        .alias("_DDTricks")
    ])
    
    dd_df: pl.DataFrame = df.with_columns([
        pl.col("_DDTricks").alias("TricksMade")  # Temporarily replace TricksMade
    ])
    # Use compute_NSscore to get DD score, then restore original TricksMade
    df_dd_scored = compute_contract_details_and_NSscore(dd_df.drop("DerivedScoreNS"))  # Remove existing score to avoid conflicts
    dd_score = df_dd_scored.select("DerivedScoreNS").to_series()
    
    # Restore original dataframe and add DD score
    df = df.with_columns([
        pl.lit(dd_score).alias("DDScoreNS")
    ])
    
    # Compute IMP differences
    df = df.with_columns([
        # NS IMPs vs DD
        pl.struct(["RawScoreNS", "DDScoreNS"]).map_elements(
            lambda x: convert_to_imps(x["RawScoreNS"], x["DDScoreNS"]), 
            return_dtype=pl.Float64
        ).alias("NSIMPsvsDD"),
        
        # NS IMPs vs Par
        pl.struct(["RawScoreNS", "ParScoreNS"]).map_elements(
            lambda x: convert_to_imps(x["RawScoreNS"], x["ParScoreNS"]), 
            return_dtype=pl.Float64
        ).alias("NSIMPsvsPar")
    ])

    # Compute declarer-perspective IMPs
    df = df.with_columns([
        # Declarer IMPs vs DD (flip sign for EW declarers)
        (pl.col("NSIMPsvsDD") * 
         pl.when(pl.col("Declarer").is_in(["N", "S"])).then(1).otherwise(-1)
        ).alias("DeclIMPsvsDD"),
        
        # Declarer IMPs vs Par (flip sign for EW declarers)
        (pl.col("NSIMPsvsPar") * 
         pl.when(pl.col("Declarer").is_in(["N", "S"])).then(1).otherwise(-1)
        ).alias("DeclIMPsvsPar")
    ])
    
    return df