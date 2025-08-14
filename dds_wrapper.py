import polars as pl
import numpy as np
from typing import List, Dict, Any
import endplay.config as config
from endplay.types import Deal, Denom, Player, Vul
from endplay.dds import calc_all_tables, par

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
            except Exception as e:
                print(f"Error parsing PBN hand at index {batch_start + len(batch_deals)}: {row['Hands'][:50]}... Error: {e}")
                raise
        
        # Calculate DD tables for the batch
        try:
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