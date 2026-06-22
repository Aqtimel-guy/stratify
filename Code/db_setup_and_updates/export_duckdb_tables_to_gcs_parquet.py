import os
import shutil
import subprocess
from pathlib import Path

import duckdb


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DUCKDB_PATH = PROJECT_ROOT / "Data_Storage" / "stratify.duckdb"

LOCAL_EXPORT_ROOT = PROJECT_ROOT / "temp_parquet_outputs" / "gcs_market_export"

GCS_BUCKET_NAME = "stratify-historical-data"

GCS_ROOT = f"gs://{GCS_BUCKET_NAME}"


# Tables that should be exported as one Parquet file
SINGLE_FILE_TABLES = {
    "assets": {
        "gcs_path": "assets/assets.parquet",
        "order_by": "asset_id",
    },
}

# Tables that should be partitioned by year because they are time-series / large
PARTITIONED_TABLES = {
    "prices": {
        "gcs_path": "prices",
        "timestamp_column": "timestamp",
        "order_by": "asset_id, timestamp",
    },
    "fundamentals": {
        "gcs_path": "fundamentals",
        "timestamp_column": "timestamp",
        "order_by": "asset_id, timestamp",
    },
    "features": {
        "gcs_path": "features",
        "timestamp_column": "timestamp",
        "order_by": "asset_id, timestamp",
    },
    "dividends": {
        "gcs_path": "dividends",
        "timestamp_column": "timestamp",
        "order_by": "asset_id, timestamp",
    },
    "asset_factors_raw_v1": {
        "gcs_path": "factors/raw_v1",
        "timestamp_column": "timestamp",
        "order_by": "asset_id, timestamp",
    },
    "asset_factors_normalized_percentile": {
        "gcs_path": "factors/percentile",
        "timestamp_column": "timestamp",
        "order_by": "asset_id, timestamp",
    },
    "asset_factors_normalized_zscore": {
        "gcs_path": "factors/zscore",
        "timestamp_column": "timestamp",
        "order_by": "asset_id, timestamp",
    },
    "asset_factors_normalized_final": {
        "gcs_path": "factors/final",
        "timestamp_column": "timestamp",
        "order_by": "asset_id, timestamp",
    },
}


# ============================================================
# HELPERS
# ============================================================

def run_shell_command(command: list[str]) -> None:
    # Run a shell command and raise a clear error if it fails
    print(f"\nRunning command:\n{' '.join(command)}")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=False,
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        )


def ensure_gcloud_available() -> None:
    # Verify that Google Cloud CLI is installed and available
    try:
        run_shell_command(["gcloud", "--version"])
    except Exception as e:
        raise RuntimeError(
            "gcloud CLI is not available. Install Google Cloud CLI first."
        ) from e


def reset_local_export_folder() -> None:
    # Delete previous local export output and create a clean folder
    if LOCAL_EXPORT_ROOT.exists():
        shutil.rmtree(LOCAL_EXPORT_ROOT)

    LOCAL_EXPORT_ROOT.mkdir(parents=True, exist_ok=True)


def connect_to_duckdb() -> duckdb.DuckDBPyConnection:
    # Connect to the local DuckDB database
    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(f"DuckDB file not found: {DUCKDB_PATH}")

    print(f"Connecting to DuckDB: {DUCKDB_PATH}")
    return duckdb.connect(str(DUCKDB_PATH))


def table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    # Check whether a table exists in DuckDB
    result = con.execute(
        """
        SELECT COUNT(*) AS table_count
        FROM information_schema.tables
        WHERE table_name = ?
        """,
        [table_name],
    ).fetchone()

    return result[0] > 0


def get_table_row_count(con: duckdb.DuckDBPyConnection, table_name: str) -> int:
    # Count rows in a DuckDB table
    result = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(result[0])


def export_single_file_table(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    config: dict,
) -> Path:
    # Export a small/static table to one Parquet file
    output_path = LOCAL_EXPORT_ROOT / config["gcs_path"]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    order_by = config["order_by"]

    print(f"\nExporting single-file table: {table_name}")
    print(f"Output: {output_path}")

    con.execute(f"""
        COPY (
            SELECT *
            FROM {table_name}
            ORDER BY {order_by}
        )
        TO '{output_path.as_posix()}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD
        );
    """)

    return output_path


def export_partitioned_table(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    config: dict,
) -> Path:
    # Export a time-series table as partitioned Parquet by year
    output_dir = LOCAL_EXPORT_ROOT / config["gcs_path"]
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp_column = config["timestamp_column"]
    order_by = config["order_by"]

    print(f"\nExporting partitioned table: {table_name}")
    print(f"Output folder: {output_dir}")

    con.execute(f"""
        COPY (
            SELECT
                *,
                EXTRACT(YEAR FROM {timestamp_column})::INTEGER AS year
            FROM {table_name}
            WHERE {timestamp_column} IS NOT NULL
            ORDER BY {order_by}
        )
        TO '{output_dir.as_posix()}'
        (
            FORMAT PARQUET,
            COMPRESSION ZSTD,
            PARTITION_BY (year),
            OVERWRITE_OR_IGNORE TRUE
        );
    """)

    return output_dir


def upload_path_to_gcs(local_path: Path, gcs_relative_path: str) -> None:
    # Upload a local file/folder to GCS using gcloud CLI
    target_path = f"{GCS_ROOT}/{gcs_relative_path}"

    if local_path.is_file():
        run_shell_command([
            "gcloud",
            "storage",
            "cp",
            str(local_path),
            target_path,
        ])

    elif local_path.is_dir():
        run_shell_command([
            "gcloud",
            "storage",
            "cp",
            "-r",
            str(local_path),
            target_path.rsplit("/", 1)[0],
        ])

    else:
        raise FileNotFoundError(f"Local path does not exist: {local_path}")


def print_export_summary(con: duckdb.DuckDBPyConnection) -> None:
    # Print row counts before export
    print("\n" + "=" * 80)
    print("EXPORT SUMMARY")
    print("=" * 80)

    all_tables = list(SINGLE_FILE_TABLES.keys()) + list(PARTITIONED_TABLES.keys())

    for table_name in all_tables:
        if table_exists(con, table_name):
            row_count = get_table_row_count(con, table_name)
            print(f"{table_name}: {row_count:,} rows")
        else:
            print(f"{table_name}: MISSING")


# ============================================================
# MAIN
# ============================================================

def export_and_upload_market_tables_to_gcs() -> None:
    # Export selected DuckDB tables to Parquet and upload them to GCS
    ensure_gcloud_available()
    reset_local_export_folder()

    con = connect_to_duckdb()

    try:
        print_export_summary(con)

        print("\n" + "=" * 80)
        print("STARTING EXPORT")
        print("=" * 80)

        exported_paths = []

        for table_name, config in SINGLE_FILE_TABLES.items():
            if not table_exists(con, table_name):
                print(f"Skipping missing table: {table_name}")
                continue

            row_count = get_table_row_count(con, table_name)

            if row_count == 0:
                print(f"Skipping empty table: {table_name}")
                continue

            output_path = export_single_file_table(con, table_name, config)
            exported_paths.append((output_path, config["gcs_path"]))

        for table_name, config in PARTITIONED_TABLES.items():
            if not table_exists(con, table_name):
                print(f"Skipping missing table: {table_name}")
                continue

            row_count = get_table_row_count(con, table_name)

            if row_count == 0:
                print(f"Skipping empty table: {table_name}")
                continue

            output_path = export_partitioned_table(con, table_name, config)
            exported_paths.append((output_path, config["gcs_path"]))

        print("\n" + "=" * 80)
        print("STARTING GCS UPLOAD")
        print("=" * 80)

        for local_path, gcs_relative_path in exported_paths:
            print(f"\nUploading: {local_path}")
            print(f"To: {GCS_ROOT}/{gcs_relative_path}")
            upload_path_to_gcs(local_path, gcs_relative_path)

        print("\n" + "=" * 80)
        print("DONE")
        print("=" * 80)
        print(f"Local export folder: {LOCAL_EXPORT_ROOT}")
        print(f"GCS bucket: {GCS_ROOT}")

    finally:
        con.close()


if __name__ == "__main__":
    export_and_upload_market_tables_to_gcs()