import os
import sys
import time
import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import yfinance as yf
import duckdb
import os
import sys
from sqlalchemy import text
from functions.db_manager import get_supabase_engine
DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'



def sync_assets_duckdb_to_supabase(duckdb_con, cloud_engine):
    """
    Daily Sync Pipeline: Extracts the current asset universe via SELECT * from local DuckDB,
    dynamically cleans all VARCHAR columns (ticker, sector, industry, name),
    and pushes/updates them in the Supabase cloud ledger.
    All source documentation and comments are maintained strictly in English.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # --- Step 1: Extract ALL columns from the local DuckDB asset matrix ---
        logger.info("Extracting latest asset universe via SELECT * from local DuckDB...")
        duck_df = duckdb_con.execute("SELECT * FROM assets").df()

        if duck_df.empty:
            logger.warning("Local asset data frame is empty. Sync aborted.")
            return False, "No local assets found to sync."

        # --- Step 2: Dynamic Cleaning Framework ---
        # Identify object/string columns dynamically to trim whitespace
        # Automatically ignores asset_id (INTEGER) and is_etf (BOOLEAN)
        text_cols = duck_df.select_dtypes(include=['object', 'string']).columns
        
        for col in text_cols:
            duck_df[col] = duck_df[col].astype(str).str.strip()
            
        logger.info(f"Cleaned whitespaces for text columns: {list(text_cols)}")

        # --- Step 3: Map Columns & Build Dynamic PostgreSQL Upsert Statement ---
        columns_list = list(duck_df.columns)
        insert_cols = ", ".join(columns_list)
        values_placeholders = ", ".join([f":{col}" for col in columns_list])
        
        # Exclude the primary key (asset_id) from the update clause to protect relational constraints
        update_cols = ", ".join([f"{col} = EXCLUDED.{col}" for col in columns_list if col != 'asset_id'])

        upsert_query = text(f"""
            INSERT INTO assets ({insert_cols})
            VALUES ({values_placeholders})
            ON CONFLICT (asset_id) 
            DO UPDATE SET {update_cols};
        """)

        # --- Step 4: Open Cloud Connection & Execute Atomic Bulk Upsert Payload ---
        logger.info(f"Syncing {len(duck_df)} assets into Supabase cloud ledger...")
        
        with cloud_engine.connect() as cloud_con:
            with cloud_con.begin():
                # Convert DataFrame rows into a clean dictionary list for SQLAlchemy mapping
                payload = duck_df.to_dict(orient="records")
                cloud_con.execute(upsert_query, payload)
                
        logger.info("Database sync pipeline completed successfully.")
        return True, f"Successfully synced {len(duck_df)} assets to Supabase (All attributes aligned)."

    except Exception as e:
        logger.error(f"Failed to sync asset matrix to cloud: {e}")
        return False, str(e)
    
    
# 1. Obtain the local DuckDB connection context (assuming 'con' is your active local instance)
local_duckdb_conn = duckdb.connect(DB_PATH)

# 2. Instantiate or retrieve the global cloud engine context
cloud_db_engine = get_supabase_engine()

# 3. Trigger the synchronization pipeline boundary
success, message = sync_assets_duckdb_to_supabase(
    duckdb_con=local_duckdb_conn,
    cloud_engine=cloud_db_engine
)

# 4. Handle downstream flow results
if success:
    print(success(message))
else:
    print(f"Sync failed: {message}")