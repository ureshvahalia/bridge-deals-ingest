import polars as pl
import numpy as np
from typing import List, Dict, Any
import endplay.config as config
from endplay.types import Deal, Denom, Player, Vul
from endplay.dds import calc_all_tables, par
import logging
from pathlib import Path

vul2dds: Dict[str, Vul] = {
    "Z": Vul.none,
    "N": Vul.ns,
    "E": Vul.ew,
    "B": Vul.both
}

player2dds: Dict[str, Player] = {
    "N": Player.north,
    "E": Player.east,
    "S": Player.south,
    "W": Player.west
}

DD_KEY = ["Hands", "Dealer", "Vulnerability"]      # par depends on dealer and vulnerability too
DD_COLUMNS = [f"DD_{p}_{d}" for p in "WNES" for d in "NSHDC"] + ["ParScoreNS", "ParContracts"]


def load_dd_cache(path: Path) -> pl.DataFrame:
    """DD and par columns from an earlier hands.csv (a file, or the DB folder holding it)."""
    path = Path(path)
    if path.is_dir():
        path = path / "hands.csv"
    if not path.exists():
        raise FileNotFoundError(f"no hands.csv to reuse DD results from: {path}")
    cached = pl.read_csv(path, columns=DD_KEY + DD_COLUMNS, infer_schema_length=0)
    missing = [c for c in DD_COLUMNS if c not in cached.columns]
    if missing:
        raise ValueError(f"{path} has no DD columns {missing}: it was built without -d")
    cached = cached.with_columns([pl.col(c).cast(pl.Int8) for c in DD_COLUMNS[:20]] +
                                 [pl.col("ParScoreNS").cast(pl.Int16), pl.col("ParContracts").fill_null("")])
    logging.warning(f"Loaded DD results for {len(cached)} hands from {path}")
    return cached.unique(DD_KEY, keep="first")


def reuse_dd_columns(df: pl.DataFrame, cache: pl.DataFrame, batch_size: int = 32) -> pl.DataFrame:
    """Add DD and par columns, copied from `cache` (load_dd_cache) where the same
    hands, dealer and vulnerability were analysed before; DDS runs only for the rest.
    Same result as create_dd_columns(df); row order is kept."""
    joined = df.with_row_index("_row").join(cache, on=DD_KEY, how="left")
    found = joined.filter(pl.col("DD_W_N").is_not_null())
    todo = joined.filter(pl.col("DD_W_N").is_null()).drop(DD_COLUMNS)
    logging.warning(f"DD results: {len(found)} reused, {len(todo)} to compute")
    if len(todo):
        computed = create_dd_columns(todo, batch_size).select(found.columns)
        same_types = [pl.col(c).cast(t) for c, t in found.select(DD_COLUMNS).schema.items()]
        found = pl.concat([found, computed.with_columns(same_types)])
    return found.sort("_row").drop("_row")


def create_dd_columns(df: pl.DataFrame, batch_size: int = 32) -> pl.DataFrame:
    """
    Process PBN hands in batches and add double dummy results and par scores as columns.
    
    :param dealsdf: Polars DataFrame with 'Hands', 'Vulnerability', and 'Dealer' columns
    :param batch_size: Number of hands to process in each batch (default 32)
    :return: DataFrame with added DD result columns, par scores, and par contracts
    """
    
    # Validate required columns
    required_columns = {'Hands', 'Vulnerability', 'Dealer'}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")
    
    # Create column names for all 20 denom-player combinations
    config.use_unicode = False
    column_names = []
    for player in ['W', 'N', 'E', 'S']:
        for denom in ['N', 'S', 'H', 'D', 'C']:
            column_names.append(f"DD_{player}_{denom}")
    
    # Initialize result arrays
    num_deals = len(df)
    dd_results = np.zeros((num_deals, 20), dtype=np.int8)
    par_scores = np.zeros(num_deals, dtype=np.int16)  # Par scores can be larger than int8
    par_contracts = [''] * num_deals  # List to store contract strings
    
    # Process in batches
    for batch_start in range(0, num_deals, batch_size):
        batch_end = min(batch_start + batch_size, num_deals)
        
        # Get batch data more efficiently
        batch_data = df.slice(batch_start, batch_end - batch_start).select(['Hands', 'Vulnerability', 'Dealer'])
        
        # print(f"Processing batch {batch_start//batch_size + 1}: deals {batch_start}-{batch_end-1}")
        
        # Convert PBN strings to Deal objects
        batch_deals = []
        for row in batch_data.iter_rows(named=True):
            try:
                deal = Deal.from_pbn(row['Hands'])
                batch_deals.append(deal)
            except (ValueError, IndexError) as e:
                logging.error(f"Error parsing PBN hand at index {batch_start + len(batch_deals)}: {row['Hands'][:50]}... Error: {e}")
                raise
        
        # Calculate DD tables for the batch
        try:
            # print(f"Processing batch starting at deal {batch_start}:", flush=True)
            # for j, row in enumerate(batch_data.iter_rows(named=True)):
            #     print(f"  [{batch_start + j}] {row['Hands']}", flush=True)
            dd_table_list = calc_all_tables(batch_deals)
            
            # Extract results and store in arrays
            for i, (table, row) in enumerate(zip(dd_table_list, batch_data.iter_rows(named=True))):
                global_idx = batch_start + i
                
                # Calculate par score and contracts
                try:
                    par_result = par(table, vul2dds[row['Vulnerability']], player2dds[row['Dealer']])
                    par_scores[global_idx] = par_result.score
                    # Convert contracts to strings and join with spaces
                    contract_strings = [str(contract) for contract in par_result]
                    par_contracts[global_idx] = ' '.join(contract_strings).replace("NT", "N")
                except Exception as e:
                    print(f"Error calculating par for deal {global_idx}: {e}")
                    par_scores[global_idx] = 0  # Default value
                    par_contracts[global_idx] = ''  # Default value
                
                # Extract DD results
                col_idx = 0
                for player in [Player.west, Player.north, Player.east, Player.south]:
                    for denom in [Denom.nt, Denom.spades, Denom.hearts, Denom.diamonds, Denom.clubs]:
                        dd_results[global_idx, col_idx] = table[denom, player]
                        col_idx += 1
                        
        except Exception as e:
            print(f"Error calculating DD tables for batch {batch_start//batch_size + 1}: {e}")
            raise
    
    # Create new columns dictionary
    new_columns = {}
    
    # Add DD columns
    for i, col_name in enumerate(column_names):
        new_columns[col_name] = dd_results[:, i]
    
    # Add par columns
    new_columns['ParScoreNS'] = par_scores
    new_columns['ParContracts'] = par_contracts
    
    # Add all new columns to the DataFrame efficiently
    result_df = df.with_columns([
            pl.lit(new_columns[col_name]).alias(col_name) 
            for col_name in column_names
        ] + [
            pl.lit(new_columns['ParScoreNS']).alias('ParScoreNS'),
        ]).with_columns(pl.Series('ParContracts', par_contracts))
    
    return result_df