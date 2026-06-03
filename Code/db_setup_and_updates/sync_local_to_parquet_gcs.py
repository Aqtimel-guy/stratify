import os
import sys
import duckdb
from google.cloud import storage

# --- ROBUST PROJECT ROOT RESOLUTION ---
# Iteratively climbs up until it finds the directory containing 'functions'
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = current_dir

while project_root and project_root != os.path.dirname(project_root):
    if os.path.isdir(os.path.join(project_root, "functions")):
        break
    project_root = os.path.dirname(project_root)

if project_root not in sys.path:
    sys.path.append(project_root)

from functions.db_manager import DB_PATH
# --------------------------------------

# Configuration
BUCKET_NAME = "stratify-historical-data"

def export_and_upload_parquet():
    """
    Connects to local DuckDB, exports financial tables to compressed Parquet format,
    and uploads them directly to Google Cloud Storage for global application access.
    """
    # List of tables to sync from your local DuckDB setup
    tables_to_sync = [
        "assets", 
        "prices", 
        "fundamentals", 
        "features", 
        "dividends", 
        "asset_factors_normalized_final"
    ]
    
    # 1. Establish local DuckDB connection in read-only mode to prevent locking issues
    print("Connecting to local DuckDB instance (Read-Only)...")
    con = duckdb.connect(DB_PATH, read_only=True)
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
   # 2. Initialize Google Cloud Storage Client via Application Default Credentials
    print("Initializing Google Cloud Storage client via Application Default Credentials...")
    storage_client = storage.Client(project="project-bc960e7b-085a-4566-9a7")
    bucket = storage_client.bucket(BUCKET_NAME)
    
    # Temporary directory to hold Parquet files before upload
    temp_dir = "temp_parquet_outputs"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        for table in tables_to_sync:
            local_parquet_path = os.path.join(temp_dir, f"{table}.parquet")
            print(f"\nProcessing table: '{table}'...")
            
            # Export from DuckDB directly to compressed Parquet format
            print(f"-> Exporting '{table}' locally to compressed Parquet...")
            con.execute(f"COPY {table} TO '{local_parquet_path}' (FORMAT 'PARQUET', COMPRESSION 'ZSTD')")
            
            # Upload to Google Cloud Storage
            blob_name = f"data_snapshots/{table}.parquet"
            blob = bucket.blob(blob_name)
            
            print(f"-> Uploading '{table}.parquet' to GCS bucket as '{blob_name}'...")
            blob.upload_from_filename(local_parquet_path)
            print(f"✅ Table '{table}' successfully uploaded and synced.")
            
            # Clean up the local temporary file
            os.remove(local_parquet_path)
            
        print("\n🎉 Sync Complete! All data snapshots are live on Google Cloud Storage.")
        
    except Exception as e:
        print(f"\n❌ Critical error occurred during sync pipeline: {e}")
        
    finally:
        # Clean up environment and database handles safely
        con.close()
        if os.path.exists(temp_dir) and not os.listdir(temp_dir):
            os.rmdir(temp_dir)

if __name__ == "__main__":
    export_and_upload_parquet()