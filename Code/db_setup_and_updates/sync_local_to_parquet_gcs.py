import os
import sys
import duckdb
from google.cloud import storage

# --- ROBUST PROJECT ROOT RESOLUTION ---
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

def export_and_upload_parquet(
    tables_to_sync=[
        "assets", 
        "prices", 
        "fundamentals", 
        "features", 
        "dividends",      
        "asset_factors_normalized_final"         
    ]):
    
    """
    Connects to local DuckDB, exports financial tables to compressed Parquet format,
    and uploads them directly to Google Cloud Storage for global application access.
    """
    
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
    
    # Track execution performance statistics
    successful_syncs = 0
    failed_syncs = []
    
    for table in tables_to_sync:
        local_parquet_path = os.path.join(temp_dir, f"{table}.parquet")
        blob_name = f"data_snapshots/{table}.parquet"
        print(f"\nProcessing table: '{table}'...")
        
        try:
            # Check if table actually exists in local catalog before copying
            table_check = con.execute(f"SELECT * FROM information_schema.tables WHERE table_name = '{table}';").fetchall()
            if not table_check:
                print(f"⚠️ Warning: Table '{table}' does not exist in local database. Skipping.")
                continue

            # Export from DuckDB directly to compressed Parquet format
            print(f"-> Exporting '{table}' locally to compressed Parquet (ZSTD)...")
            con.execute(f"COPY {table} TO '{local_parquet_path}' (FORMAT 'PARQUET', COMPRESSION 'ZSTD')")
            
            # Upload to Google Cloud Storage with metadata cache handling
            blob = bucket.blob(blob_name)
            blob.cache_control = "no-cache, max-age=0" # Forces intermediate clients/CDN to fetch live file instantly
            
            print(f"-> Uploading '{table}.parquet' to GCS bucket as '{blob_name}'...")
            blob.upload_from_filename(local_parquet_path)
            print(f"✅ Table '{table}' successfully uploaded and synced.")
            successful_syncs += 1
            
        except Exception as table_error:
            print(f"❌ Error syncing table '{table}': {table_error}")
            failed_syncs.append(table)
            
        finally:
            # Clean up the local temporary file for this specific table iteration
            if os.path.exists(local_parquet_path):
                os.remove(local_parquet_path)
                
    # --- FINAL PIPELINE TELEMETRY SUMMARY ---
    print("\n" + "="*50)
    print(f"🎉 Pipeline Execution Complete. Successfully synced: {successful_syncs}/{len(tables_to_sync)} tables.")
    if failed_syncs:
        print(f"❌ The following tables failed to sync: {failed_syncs}")
    print("="*50)
    
    # Close the DuckDB connection
    con.close()

if __name__ == "__main__":
    export_and_upload_parquet()