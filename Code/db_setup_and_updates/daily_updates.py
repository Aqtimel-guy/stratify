import yfinance as yf
import duckdb
import pandas as pd
from datetime import datetime, timedelta
import logging
import time
import sys
import os
import numpy as np
import random
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from strategy_builder.factor_formulas_raw import *
from strategy_builder.normelizing_factors import *
DB_PATH = r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb"




# Global logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

### fill asset table (1)

def fill_assets_table():
    """
    Fetches US assets from:
    1. S&P 500 constituents
    2. Ate329/top-us-stock-tickers full US stock list
    3. Manual ETF list

    Then inserts them into the assets table in DuckDB.
    Existing tickers are not duplicated.
    """

    logger = logging.getLogger(__name__)

    db_path = r'C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb'
    con = duckdb.connect(db_path)

    def reset_asset_sequence():
        max_id = con.execute("""
            SELECT COALESCE(MAX(asset_id), 0)
            FROM assets
        """).fetchone()[0]

        con.execute("DROP SEQUENCE IF EXISTS asset_id_seq")
        con.execute(f"CREATE SEQUENCE asset_id_seq START WITH {max_id + 1}")

    def clean_assets_df(df):
        df = df.copy()

        df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
        df["name"] = df["name"].astype(str).str.strip()
        # Remove preferred shares / special tickers that break yfinance
        df = df[~df["ticker"].str.contains(r"\^", regex=True, na=False)]

        df["sector"] = df["sector"].fillna("Unknown").astype(str).str.strip()
        df["industry"] = df["industry"].fillna("Unknown").astype(str).str.strip()
        
        # Normalize sector names across different data sources
        sector_mapping = {
            "Finance": "Financials",
            "Financial": "Financials",
            "Information Technology": "Technology",
            "Basic Materials": "Materials",
            "Telecommunications": "Communication Services",
            "Consumer": "Consumer Discretionary",
            "Uncategorized": "Unrecognized",
            "Miscellaneous": "Unrecognized",
        }

        df["sector"] = df["sector"].replace(sector_mapping)

        df.loc[df["sector"].isin(["", "nan", "None", "NaN"]), "sector"] = "Unknown"
        df.loc[df["industry"].isin(["", "nan", "None", "NaN"]), "industry"] = "Unknown"

        df = df[df["ticker"] != ""]
        df = df[df["ticker"] != "NAN"]
        df = df[df["name"] != ""]
        df = df[df["name"].str.lower() != "nan"]

        df = df.drop_duplicates(subset=["ticker"], keep="first")

        return df

    def insert_assets_df(df, source_name, is_etf=False):
        if df is None or df.empty:
            logger.warning(f"{source_name}: empty dataframe, skipped.")
            return 0

        df = clean_assets_df(df)
        df["is_etf"] = is_etf

        if df.empty:
            logger.warning(f"{source_name}: dataframe empty after cleaning, skipped.")
            return 0

        reset_asset_sequence()

        temp_table_name = f"temp_assets_{source_name.lower().replace(' ', '_').replace('-', '_')}"
        con.register(temp_table_name, df)

        count_before_insert = con.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

        try:
            con.execute(f"""
                INSERT INTO assets (asset_id, ticker, name, sector, industry, is_etf)
                SELECT
                    nextval('asset_id_seq'),
                    ticker,
                    name,
                    sector,
                    industry,
                    is_etf
                FROM {temp_table_name}
                WHERE ticker NOT IN (
                    SELECT ticker
                    FROM assets
                )
            """)
        finally:
            try:
                con.unregister(temp_table_name)
            except Exception:
                pass

        count_after_insert = con.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        added = count_after_insert - count_before_insert

        logger.info(f"{source_name}: processed {len(df)} rows, added {added} new assets.")
        return added

    try:
        con.execute("CREATE SEQUENCE IF NOT EXISTS asset_id_seq START 1")

        count_before = con.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

        # ======================================================
        # 1. S&P 500
        # ======================================================
        sp500_url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

        try:
            sp500_df = pd.read_csv(sp500_url)

            sp500_clean = sp500_df[[
                "Symbol",
                "Security",
                "GICS Sector",
                "GICS Sub-Industry"
            ]].copy()

            sp500_clean.rename(columns={
                "Symbol": "ticker",
                "Security": "name",
                "GICS Sector": "sector",
                "GICS Sub-Industry": "industry"
            }, inplace=True)

            insert_assets_df(sp500_clean, "S&P 500", is_etf=False)

        except Exception as e:
            logger.error(f"Error fetching S&P 500 data: {e}")

        # ======================================================
        # 2. Full US stock list from Ate329/top-us-stock-tickers
        # ======================================================
        ate329_url = "https://raw.githubusercontent.com/Ate329/top-us-stock-tickers/main/tickers/all.csv"

        try:
            ate329_df = pd.read_csv(ate329_url)

            ate329_clean = ate329_df.copy()

            ate329_clean.rename(columns={
                "symbol": "ticker",
                "name": "name",
                "industry": "industry"
            }, inplace=True)

            ate329_clean = ate329_clean[[
                "ticker",
                "name",
                "industry"
            ]].copy()

            # This source gives industry, but not a clean separate sector.
            # For now, we use industry as sector too, to avoid losing classification.
            ate329_clean["sector"] = ate329_clean["industry"]

            ate329_clean = ate329_clean[[
                "ticker",
                "name",
                "sector",
                "industry"
            ]]

            insert_assets_df(ate329_clean, "Ate329 US stocks", is_etf=False)

        except Exception as e:
            logger.error(f"Error fetching Ate329 US stocks data: {e}")

        # ======================================================
        # 3. Manual ETFs
        # ======================================================
        etfs = [
            {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "sector": "Benchmark", "industry": "Broad Market"},
            {"ticker": "QQQ", "name": "Invesco QQQ Trust (Nasdaq 100)", "sector": "Benchmark", "industry": "Technology Index"},
            {"ticker": "IWM", "name": "iShares Russell 2000 ETF", "sector": "Benchmark", "industry": "Small Cap"},
            {"ticker": "DIA", "name": "SPDR Dow Jones Industrial Average", "sector": "Benchmark", "industry": "Blue Chip"},
            {"ticker": "VTI", "name": "Vanguard Total Stock Market", "sector": "Benchmark", "industry": "Total Market"},

            {"ticker": "XLK", "name": "Technology Select Sector SPDR", "sector": "Technology", "industry": "Sector ETF"},
            {"ticker": "XLF", "name": "Financial Select Sector SPDR", "sector": "Financials", "industry": "Sector ETF"},
            {"ticker": "XLV", "name": "Health Care Select Sector SPDR", "sector": "Health Care", "industry": "Sector ETF"},
            {"ticker": "XLY", "name": "Consumer Discretionary SPDR", "sector": "Consumer", "industry": "Sector ETF"},
            {"ticker": "XLP", "name": "Consumer Staples Select Sector SPDR", "sector": "Consumer", "industry": "Defensive ETF"},
            {"ticker": "XLI", "name": "Industrial Select Sector SPDR", "sector": "Industrials", "industry": "Sector ETF"},
            {"ticker": "XLE", "name": "Energy Select Sector SPDR", "sector": "Energy", "industry": "Sector ETF"},
            {"ticker": "XLRE", "name": "Real Estate Select Sector SPDR", "sector": "Real Estate", "industry": "Sector ETF"},
            {"ticker": "XLU", "name": "Utilities Select Sector SPDR", "sector": "Utilities", "industry": "Sector ETF"},
            {"ticker": "XLB", "name": "Materials Select Sector SPDR", "sector": "Materials", "industry": "Sector ETF"},

            {"ticker": "SMH", "name": "VanEck Semiconductor ETF", "sector": "Technology", "industry": "Semiconductors"},
            {"ticker": "CIBR", "name": "First Trust NASDAQ Cybersecurity", "sector": "Technology", "industry": "Cybersecurity"},
            {"ticker": "BOTZ", "name": "Global X Robotics & AI ETF", "sector": "Technology", "industry": "AI & Robotics"},
            {"ticker": "SKYY", "name": "First Trust Cloud Computing", "sector": "Technology", "industry": "Cloud Computing"},
            {"ticker": "ARKK", "name": "ARK Innovation ETF", "sector": "Technology", "industry": "Disruptive Tech"},

            {"ticker": "IBIT", "name": "iShares Bitcoin Trust", "sector": "Crypto", "industry": "Bitcoin"},
            {"ticker": "ETHA", "name": "iShares Ethereum Trust", "sector": "Crypto", "industry": "Ethereum"},
            {"ticker": "BITO", "name": "ProShares Bitcoin Strategy ETF", "sector": "Crypto", "industry": "Bitcoin Futures"},
            {"ticker": "WGMI", "name": "Valkyrie Bitcoin Miners ETF", "sector": "Crypto", "industry": "Crypto Mining"},

            {"ticker": "GLD", "name": "SPDR Gold Shares", "sector": "Commodities", "industry": "Gold"},
            {"ticker": "SLV", "name": "iShares Silver Trust", "sector": "Commodities", "industry": "Silver"},
            {"ticker": "USO", "name": "United States Oil Fund", "sector": "Commodities", "industry": "Crude Oil"},
            {"ticker": "UNG", "name": "United States Natural Gas Fund", "sector": "Commodities", "industry": "Natural Gas"},
            {"ticker": "ICLN", "name": "iShares Global Clean Energy", "sector": "Energy", "industry": "Renewable Energy"},
            {"ticker": "URA", "name": "Global X Uranium ETF", "sector": "Energy", "industry": "Uranium"},
            {"ticker": "COPX", "name": "Global X Copper Miners ETF", "sector": "Commodities", "industry": "Copper"},
            {"ticker": "DBA", "name": "Invesco Agriculture Fund", "sector": "Commodities", "industry": "Agriculture"},

            {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond", "sector": "Bonds", "industry": "Long Term Treasuries"},
            {"ticker": "IEF", "name": "iShares 7-10 Year Treasury Bond", "sector": "Bonds", "industry": "Mid Term Treasuries"},
            {"ticker": "SHY", "name": "iShares 1-3 Year Treasury Bond", "sector": "Bonds", "industry": "Short Term Treasuries"},
            {"ticker": "TIP", "name": "iShares TIPS Bond ETF", "sector": "Bonds", "industry": "Inflation Protected"},
            {"ticker": "LQD", "name": "iShares Investment Grade Corp Bond", "sector": "Bonds", "industry": "Corporate Bonds"},

            {"ticker": "VUG", "name": "Vanguard Growth ETF", "sector": "Style", "industry": "Growth"},
            {"ticker": "VTV", "name": "Vanguard Value ETF", "sector": "Style", "industry": "Value"},
            {"ticker": "MTUM", "name": "iShares MSCI USA Momentum", "sector": "Style", "industry": "Momentum"},
            {"ticker": "QUAL", "name": "iShares MSCI USA Quality", "sector": "Style", "industry": "Quality"},
            {"ticker": "NOBL", "name": "ProShares Dividend Aristocrats", "sector": "Style", "industry": "Dividends"},

            {"ticker": "EEM", "name": "iShares MSCI Emerging Markets", "sector": "Global", "industry": "Emerging Markets"},
            {"ticker": "VGK", "name": "Vanguard FTSE Europe ETF", "sector": "Global", "industry": "Europe"},
            {"ticker": "EWJ", "name": "iShares MSCI Japan ETF", "sector": "Global", "industry": "Japan"},
            {"ticker": "FXI", "name": "iShares China Large-Cap ETF", "sector": "Global", "industry": "China"},

            {"ticker": "VIXY", "name": "ProShares VIX Short-Term Futures", "sector": "Volatility", "industry": "VIX Factor"},
            {"ticker": "SQQQ", "name": "ProShares Short QQQ (3x)", "sector": "Inverse", "industry": "Inverse Tech"},
            {"ticker": "SH", "name": "ProShares Short S&P 500", "sector": "Inverse", "industry": "Inverse Market"}
        ]

        etf_df = pd.DataFrame(etfs)
        insert_assets_df(etf_df, "Manual ETFs", is_etf=True)

        count_after = con.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        added_rows = count_after - count_before

        unknown_count = con.execute("""
            SELECT COUNT(*)
            FROM assets
            WHERE sector IS NULL
               OR TRIM(sector) = ''
               OR LOWER(TRIM(sector)) = 'unknown'
        """).fetchone()[0]

        logger.info("-" * 30)
        logger.info("Database Update Status:")
        logger.info(f"New assets added: {added_rows}")
        logger.info(f"Total assets in database: {count_after}")
        logger.info(f"Assets with Unknown sector: {unknown_count}")
        logger.info("-" * 30)

    finally:
        con.close()
        
### fill prices table (2)

def fill_prices_table():
    """
    Updates the prices table using yfinance.

    Main logic:
    - Loads all assets from the assets table
    - Converts tickers to yfinance format
    - Checks the latest saved price date per asset
    - Downloads prices in batches
    - Filters only new rows per asset
    - Inserts safely into prices without duplicates
    """

    db_path = r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb"

    con = duckdb.connect(db_path)
    logger = logging.getLogger(__name__)

    try:
        # ======================================================
        # 1. Load assets
        # ======================================================
        tickers_df = con.execute("""
            SELECT asset_id, ticker
            FROM assets
            WHERE ticker IS NOT NULL
              AND TRIM(ticker) <> ''
        """).fetchdf()

        if tickers_df.empty:
            logger.warning("No assets found in assets table.")
            return

        tickers_df["ticker"] = tickers_df["ticker"].astype(str).str.strip().str.upper()

        # yfinance uses '-' instead of '.' for tickers like BRK.B -> BRK-B
        tickers_df["ticker_yf"] = (
        tickers_df["ticker"]
        .str.replace(".", "-", regex=False)
        .str.replace("/", "-", regex=False)
        )

        # ======================================================
        # 2. Get last saved price date per asset
        # ======================================================
        last_dates = con.execute("""
            SELECT
                asset_id,
                MAX(timestamp) AS last_timestamp
            FROM prices
            GROUP BY asset_id
        """).fetchdf()

        tickers_df = tickers_df.merge(last_dates, on="asset_id", how="left")

        default_start = pd.Timestamp("2000-01-01").date()

        tickers_df["last_timestamp"] = pd.to_datetime(
            tickers_df["last_timestamp"],
            errors="coerce"
        ).dt.date

        tickers_df["last_timestamp"] = tickers_df["last_timestamp"].fillna(default_start)

        end_date = datetime.today().strftime("%Y-%m-%d")

        # ======================================================
        # 3. Batch download settings
        # ======================================================
        batch_size = 100
        insert_chunk_size = 100_000
        total_inserted = 0
        failed_batches = []

        logger.info(f"Starting price update for {len(tickers_df)} assets.")

        # ======================================================
        # 4. Download and insert batch by batch
        # ======================================================
        for start_idx in range(0, len(tickers_df), batch_size):
            batch_num = start_idx // batch_size + 1
            batch_df = tickers_df.iloc[start_idx:start_idx + batch_size].copy()

            
            batch_min_date = batch_df["last_timestamp"].min()
            fetch_start = (batch_min_date + timedelta(days=1)).strftime("%Y-%m-%d")

            ticker_list = batch_df["ticker_yf"].dropna().unique().tolist()

            print(f"Starting batch {batch_num} | tickers: {len(ticker_list)} | from {fetch_start}")

            if fetch_start >= end_date:
                logger.info(f"Batch {batch_num}: already up to date.")
                continue

            ticker_list = batch_df["ticker_yf"].dropna().unique().tolist()

            if not ticker_list:
                logger.warning(f"Batch {batch_num}: no valid tickers.")
                continue

            logger.info(
                f"Batch {batch_num}: downloading {len(ticker_list)} tickers "
                f"from {fetch_start} to {end_date}"
            )

            raw_data = None

            for attempt in range(3):
                try:
                    raw_data = yf.download(
                        ticker_list,
                        start=fetch_start,
                        end=end_date,
                        interval="1d",
                        group_by="ticker",
                        auto_adjust=False,
                        threads=True,
                        progress=False
                    )
                    break

                except Exception as e:
                    logger.warning(
                        f"Batch {batch_num}: download failed "
                        f"(attempt {attempt + 1}/3): {e}"
                    )
                    time.sleep(2)

            if raw_data is None or raw_data.empty:
                logger.warning(f"Batch {batch_num}: no data downloaded.")
                failed_batches.append(batch_num)
                continue

            # ======================================================
            # 5. Flatten yfinance output
            # ======================================================
            try:
                if isinstance(raw_data.columns, pd.MultiIndex):
                    data = raw_data.stack(level=0, future_stack=True).reset_index()

                    possible_ticker_cols = ["level_1", "Ticker", "ticker"]
                    found_col = next(
                        (c for c in possible_ticker_cols if c in data.columns),
                        None
                    )

                    if found_col is None:
                        logger.error(
                            f"Batch {batch_num}: could not find ticker column. "
                            f"Columns: {list(data.columns)}"
                        )
                        failed_batches.append(batch_num)
                        continue

                    data.rename(columns={found_col: "ticker_yf"}, inplace=True)

                else:
                    data = raw_data.reset_index()
                    data["ticker_yf"] = ticker_list[0]

            except Exception as e:
                logger.error(f"Batch {batch_num}: failed to flatten data: {e}")
                failed_batches.append(batch_num)
                continue

            # ======================================================
            # 6. Standardize columns
            # ======================================================
            data.rename(columns={
                "Date": "timestamp",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume"
            }, inplace=True)

            required_cols = [
                "timestamp",
                "ticker_yf",
                "open",
                "high",
                "low",
                "close",
                "adj_close",
                "volume"
            ]

            missing_cols = [col for col in required_cols if col not in data.columns]

            if missing_cols:
                logger.error(
                    f"Batch {batch_num}: missing required columns: {missing_cols}"
                )
                failed_batches.append(batch_num)
                continue

            data["timestamp"] = pd.to_datetime(
                data["timestamp"],
                errors="coerce"
            ).dt.date

            data = data.dropna(subset=["timestamp"])

            # ======================================================
            # 7. Merge asset_id and filter only new rows
            # ======================================================
            data = data.merge(
                batch_df[["asset_id", "ticker_yf", "last_timestamp"]],
                on="ticker_yf",
                how="inner"
            )

            data = data[data["timestamp"] > data["last_timestamp"]]

            if data.empty:
                logger.info(f"Batch {batch_num}: no new rows after filtering.")
                continue

            # ======================================================
            # 8. Clean rows
            # ======================================================
            data.dropna(subset=["close"], inplace=True)

            data = data.drop_duplicates(
                subset=["asset_id", "timestamp"],
                keep="last"
            )

            final_cols = [
                "asset_id",
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "adj_close",
                "volume"
            ]

            data = data[final_cols]

            if data.empty:
                logger.info(f"Batch {batch_num}: no valid rows after cleaning.")
                continue

            # ======================================================
            # 9. Insert safely in chunks
            # ======================================================
            inserted_this_batch = 0

            for i in range(0, len(data), insert_chunk_size):
                chunk = data.iloc[i:i + insert_chunk_size]

                con.register("temp_price_chunk", chunk)

                try:
                    con.execute("""
                        INSERT INTO prices (
                            asset_id,
                            timestamp,
                            open,
                            high,
                            low,
                            close,
                            adj_close,
                            volume
                        )
                        SELECT
                            asset_id,
                            timestamp,
                            open,
                            high,
                            low,
                            close,
                            adj_close,
                            volume
                        FROM temp_price_chunk
                        ON CONFLICT (asset_id, timestamp) DO NOTHING
                    """)
                finally:
                    try:
                        con.unregister("temp_price_chunk")
                    except Exception:
                        pass

                inserted_this_batch += len(chunk)

            total_inserted += inserted_this_batch

            logger.info(
                f"Batch {batch_num}: inserted up to {inserted_this_batch} rows."
            )

        logger.info("-" * 50)
        logger.info("Prices table update completed.")
        logger.info(f"Total rows attempted/inserted: {total_inserted}")

        if failed_batches:
            logger.warning(f"Failed batches: {failed_batches}")

        logger.info("-" * 50)

    finally:
        con.close()


### fill fundamentals table (3)

def fill_fundamentals_table(
    force_refresh=False,
    refresh_days=30,
    retry_failed_days=7,
    batch_size=100,
    max_batches=None,
    max_fail_count=10,
    pause_between_tickers=(0.5, 1.5),
    pause_between_batches=60,
    include_etfs=False,
    allow_slow_info_fallback=False
):
    
    
    ##########################
    ## sub_functions
    ##########################
    
    def normalize_yahoo_ticker(ticker: str) -> str:
        return (
            str(ticker)
            .strip()
            .replace(".", "-")
            .replace("/", "-")
        )


    def safe_date(value):
        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        try:
            return pd.to_datetime(value).date()
        except Exception:
            return None


    def safe_fast_info_get(fast_info, keys):
        if fast_info is None:
            return None

        for key in keys:
            try:
                value = fast_info.get(key)
                if value is not None:
                    return value
            except Exception:
                pass

            try:
                value = getattr(fast_info, key)
                if value is not None:
                    return value
            except Exception:
                pass

        return None


    def ensure_fundamentals_pipeline_tables(con):
        con.execute("""
            CREATE TABLE IF NOT EXISTS fundamentals_update_status (
                asset_id INTEGER PRIMARY KEY,
                ticker VARCHAR,
                yahoo_ticker VARCHAR,
                last_attempt_at TIMESTAMP,
                last_success_at TIMESTAMP,
                last_fundamental_date DATE,
                status VARCHAR,
                fail_count INTEGER,
                error_message VARCHAR
            )
        """)


    def update_fundamentals_status(
        con,
        asset_id,
        ticker,
        yahoo_ticker,
        status,
        last_fundamental_date=None,
        error_message=None
    ):
        now = datetime.now()
        last_fundamental_date = safe_date(last_fundamental_date)

        existing = con.execute("""
            SELECT
                fail_count,
                last_success_at
            FROM fundamentals_update_status
            WHERE asset_id = ?
        """, [asset_id]).fetchone()

        previous_fail_count = existing[0] if existing else 0
        previous_last_success_at = existing[1] if existing else None

        if previous_fail_count is None:
            previous_fail_count = 0

        if status in ("success", "no_new_rows"):
            fail_count = 0
            last_success_at = now
        elif status in ("failed", "no_data"):
            fail_count = previous_fail_count + 1
            last_success_at = previous_last_success_at
        else:
            fail_count = previous_fail_count
            last_success_at = previous_last_success_at

        con.execute("""
            DELETE FROM fundamentals_update_status
            WHERE asset_id = ?
        """, [asset_id])

        con.execute("""
            INSERT INTO fundamentals_update_status (
                asset_id,
                ticker,
                yahoo_ticker,
                last_attempt_at,
                last_success_at,
                last_fundamental_date,
                status,
                fail_count,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            asset_id,
            ticker,
            yahoo_ticker,
            now,
            last_success_at,
            last_fundamental_date,
            status,
            fail_count,
            error_message
        ])


    def get_assets_for_fundamentals_update(
        con,
        force_refresh=False,
        refresh_days=30,
        retry_failed_days=7,
        batch_size=100,
        max_fail_count=10,
        include_etfs=False
    ):
        batch_size = int(batch_size)

        etf_filter = ""
        if not include_etfs:
            etf_filter = "AND COALESCE(a.is_etf, FALSE) = FALSE"

        if force_refresh:
            query = f"""
                SELECT
                    a.asset_id,
                    a.ticker,
                    MAX(f.timestamp) AS last_fund
                FROM assets a
                LEFT JOIN fundamentals f
                    ON a.asset_id = f.asset_id
                WHERE
                    a.ticker IS NOT NULL
                    AND TRIM(a.ticker) <> ''
                    {etf_filter}
                GROUP BY
                    a.asset_id,
                    a.ticker
                ORDER BY
                    a.ticker
                LIMIT {batch_size}
            """

            return con.execute(query).fetchdf()

        refresh_cutoff = datetime.now() - timedelta(days=refresh_days)
        retry_cutoff = datetime.now() - timedelta(days=retry_failed_days)

        query = f"""
            WITH latest_fund AS (
                SELECT
                    asset_id,
                    MAX(timestamp) AS last_fund
                FROM fundamentals
                GROUP BY asset_id
            )

            SELECT
                a.asset_id,
                a.ticker,
                lf.last_fund,
                s.last_attempt_at,
                s.status,
                s.fail_count
            FROM assets a
            LEFT JOIN latest_fund lf
                ON a.asset_id = lf.asset_id
            LEFT JOIN fundamentals_update_status s
                ON a.asset_id = s.asset_id
            WHERE
                a.ticker IS NOT NULL
                AND TRIM(a.ticker) <> ''
                {etf_filter}
                AND (
                    s.asset_id IS NULL

                    OR (
                        s.status IN ('success', 'no_new_rows', 'no_data')
                        AND (
                            s.last_attempt_at IS NULL
                            OR s.last_attempt_at < ?
                        )
                    )

                    OR (
                        s.status = 'failed'
                        AND COALESCE(s.fail_count, 0) < ?
                        AND (
                            s.last_attempt_at IS NULL
                            OR s.last_attempt_at < ?
                        )
                    )
                )
            ORDER BY
                COALESCE(s.fail_count, 0) ASC,
                COALESCE(s.last_attempt_at, TIMESTAMP '1900-01-01') ASC,
                a.ticker
            LIMIT {batch_size}
        """

        return con.execute(query, [
            refresh_cutoff,
            max_fail_count,
            retry_cutoff
        ]).fetchdf()


    def fetch_quarterly_fundamentals_from_yahoo(
        yahoo_ticker,
        max_attempts=3,
        allow_slow_info_fallback=False
    ):
        last_error = None

        for attempt in range(max_attempts):
            try:
                yt = yf.Ticker(yahoo_ticker)

                q_fin = pd.DataFrame()
                source_used = None

                # Try the most explicit modern yfinance method first
                fetch_methods = [
                    ("get_income_stmt_quarterly", lambda: yt.get_income_stmt(freq="quarterly")),
                    ("quarterly_income_stmt", lambda: yt.quarterly_income_stmt),
                    ("quarterly_financials", lambda: yt.quarterly_financials),
                ]

                for source_name, fetch_func in fetch_methods:
                    try:
                        temp_df = fetch_func()

                        if temp_df is not None and not temp_df.empty:
                            q_fin = temp_df.T.copy()
                            source_used = source_name
                            break

                    except Exception as inner_error:
                        last_error = f"{source_name}: {str(inner_error)}"

                if q_fin is None or q_fin.empty:
                    return (
                        pd.DataFrame(),
                        None,
                        None,
                        f"No quarterly fundamentals returned from Yahoo. Last error: {last_error}"
                    )

                shares = None
                market_cap = None

                try:
                    fast_info = yt.fast_info

                    shares = safe_fast_info_get(
                        fast_info,
                        ["shares_outstanding", "shares"]
                    )

                    market_cap = safe_fast_info_get(
                        fast_info,
                        ["market_cap", "marketCap"]
                    )

                except Exception:
                    pass

                if allow_slow_info_fallback:
                    if shares is None or market_cap is None:
                        try:
                            info = yt.info

                            if shares is None:
                                shares = info.get("sharesOutstanding")

                            if market_cap is None:
                                market_cap = info.get("marketCap")

                        except Exception:
                            pass

                logging.info(
                    f"{yahoo_ticker}: fundamentals fetched successfully using {source_used}. "
                    f"Rows: {len(q_fin)}, Columns: {list(q_fin.columns)[:8]}"
                )

                return q_fin, shares, market_cap, None

            except Exception as e:
                last_error = str(e)

                sleep_seconds = (2 ** attempt) + random.uniform(0.25, 1.25)

                logging.warning(
                    f"{yahoo_ticker}: attempt {attempt + 1} failed. "
                    f"Error: {last_error}. Sleeping {sleep_seconds:.2f}s"
                )

                time.sleep(sleep_seconds)

        return pd.DataFrame(), None, None, last_error


    def transform_quarterly_fundamentals(q_fin, asset_id, shares, market_cap):
        if q_fin is None or q_fin.empty:
            return pd.DataFrame()

        q_fin = q_fin.copy()

        # Normalize column names to strings
        q_fin.columns = [str(col).strip() for col in q_fin.columns]

        # Reset index safely
        q_fin = q_fin.reset_index()

        # The first column after reset_index should be the quarter/date column
        first_col = q_fin.columns[0]
        q_fin = q_fin.rename(columns={first_col: "timestamp"})

        q_fin["timestamp"] = pd.to_datetime(
            q_fin["timestamp"],
            errors="coerce"
        ).dt.date

        q_fin = q_fin.dropna(subset=["timestamp"])

        if q_fin.empty:
            return pd.DataFrame()

        q_fin["asset_id"] = asset_id

        revenue_names = [
            "Total Revenue",
            "TotalRevenue",
            "Operating Revenue",
            "OperatingRevenue",
            "Revenue"
        ]

        q_fin["revenue"] = None

        for name in revenue_names:
            if name in q_fin.columns:
                q_fin["revenue"] = q_fin[name]
                break

        eps_names = [
            "Diluted EPS",
            "DilutedEPS",
            "Basic EPS",
            "BasicEPS"
        ]

        q_fin["eps"] = None

        for name in eps_names:
            if name in q_fin.columns:
                q_fin["eps"] = q_fin[name]
                break

        # Fallback: calculate EPS from net income / shares
        if q_fin["eps"].isna().all():
            income_names = [
                "Net Income",
                "NetIncome",
                "Net Income Common Stockholders",
                "NetIncomeCommonStockholders",
                "Net Income From Continuing Operation Net Minority Interest",
                "NetIncomeFromContinuingOperationNetMinorityInterest"
            ]

            net_income = None

            for name in income_names:
                if name in q_fin.columns:
                    net_income = q_fin[name]
                    break

            if net_income is not None and shares is not None and shares != 0:
                q_fin["eps"] = pd.to_numeric(net_income, errors="coerce") / shares

        q_fin["shares_outstanding"] = shares
        q_fin["market_cap"] = market_cap

        # Important:
        # This is not a real historical PE ratio.
        # It is only a rough current approximation based on current market cap.

        if shares is not None and shares != 0:
            eps_numeric = pd.to_numeric(q_fin["eps"], errors="coerce")

            annualized_eps = eps_numeric * 4


        final_cols = [
            "asset_id",
            "timestamp",
            "market_cap",
            "revenue",
            "eps",
            "shares_outstanding"
        ]

        for col in final_cols:
            if col not in q_fin.columns:
                q_fin[col] = None

        final_df = q_fin[final_cols].copy()

        numeric_cols = [
            "market_cap",
            "revenue",
            "eps",
            "shares_outstanding"
        ]

        for col in numeric_cols:
            final_df[col] = pd.to_numeric(final_df[col], errors="coerce")

        final_df = final_df.drop_duplicates(
            subset=["asset_id", "timestamp"],
            keep="last"
        )

        final_df = final_df.sort_values("timestamp").reset_index(drop=True)

        return final_df


    def insert_new_fundamentals_rows(con, final_df):
        if final_df is None or final_df.empty:
            return 0

        con.register("temp_fundamentals_df", final_df)

        try:
            rows_to_insert = con.execute("""
                SELECT
                    COUNT(*)
                FROM temp_fundamentals_df t
                LEFT JOIN fundamentals f
                    ON t.asset_id = f.asset_id
                AND t.timestamp = f.timestamp
                WHERE f.asset_id IS NULL
            """).fetchone()[0]

            if rows_to_insert == 0:
                return 0

            con.execute("""
                INSERT INTO fundamentals (
                    asset_id,
                    timestamp,
                    market_cap,
                    revenue,
                    eps,
                    shares_outstanding
                )
                SELECT
                    t.asset_id,
                    t.timestamp,
                    t.market_cap,
                    t.revenue,
                    t.eps,
                    t.shares_outstanding
                FROM temp_fundamentals_df t
                LEFT JOIN fundamentals f
                    ON t.asset_id = f.asset_id
                AND t.timestamp = f.timestamp
                WHERE f.asset_id IS NULL
            """)

            return rows_to_insert

        finally:
            con.unregister("temp_fundamentals_df")
    
    
    
    ##########################
    ## the function
    ##########################
    
    
    con = duckdb.connect(DB_PATH)

    total_batches = 0
    total_processed_count = 0
    total_success_count = 0
    total_no_new_rows_count = 0
    total_no_data_count = 0
    total_failed_count = 0
    total_inserted_rows = 0

    try:
        ensure_fundamentals_pipeline_tables(con)

        while True:
            if max_batches is not None and total_batches >= max_batches:
                logging.info(
                    f"Reached max_batches limit: {max_batches}. Stopping fundamentals run."
                )
                break

            assets_to_update = get_assets_for_fundamentals_update(
                con=con,
                force_refresh=force_refresh,
                refresh_days=refresh_days,
                retry_failed_days=retry_failed_days,
                batch_size=batch_size,
                max_fail_count=max_fail_count,
                include_etfs=include_etfs
            )

            if assets_to_update.empty:
                logging.info("No more fundamentals assets to update. Full run finished.")
                break

            total_batches += 1

            batch_processed_count = 0
            batch_success_count = 0
            batch_no_new_rows_count = 0
            batch_no_data_count = 0
            batch_failed_count = 0
            batch_inserted_rows = 0

            logging.info(
                f"Starting fundamentals batch {total_batches}. "
                f"Assets in batch: {len(assets_to_update)}"
            )

            for row in assets_to_update.itertuples(index=False):
                asset_id = int(row.asset_id)
                ticker = str(row.ticker).strip()
                yahoo_ticker = normalize_yahoo_ticker(ticker)
                last_fund = safe_date(getattr(row, "last_fund", None))

                batch_processed_count += 1
                total_processed_count += 1

                try:
                    q_fin, shares, market_cap, fetch_error = fetch_quarterly_fundamentals_from_yahoo(
                        yahoo_ticker=yahoo_ticker,
                        max_attempts=3,
                        allow_slow_info_fallback=allow_slow_info_fallback
                    )

                    if q_fin is None or q_fin.empty:
                        status = "failed" if fetch_error else "no_data"

                        update_fundamentals_status(
                            con=con,
                            asset_id=asset_id,
                            ticker=ticker,
                            yahoo_ticker=yahoo_ticker,
                            status=status,
                            last_fundamental_date=last_fund,
                            error_message=fetch_error
                        )

                        if status == "failed":
                            batch_failed_count += 1
                            total_failed_count += 1
                        else:
                            batch_no_data_count += 1
                            total_no_data_count += 1

                        logging.warning(
                            f"Batch {total_batches} | "
                            f"{batch_processed_count}/{len(assets_to_update)} | "
                            f"{yahoo_ticker}: no fundamentals data."
                        )

                        time.sleep(random.uniform(*pause_between_tickers))
                        continue

                    final_df = transform_quarterly_fundamentals(
                        q_fin=q_fin,
                        asset_id=asset_id,
                        shares=shares,
                        market_cap=market_cap
                    )

                    if final_df.empty:
                        update_fundamentals_status(
                            con=con,
                            asset_id=asset_id,
                            ticker=ticker,
                            yahoo_ticker=yahoo_ticker,
                            status="no_data",
                            last_fundamental_date=last_fund,
                            error_message=None
                        )

                        batch_no_data_count += 1
                        total_no_data_count += 1

                        logging.warning(
                            f"Batch {total_batches} | "
                            f"{batch_processed_count}/{len(assets_to_update)} | "
                            f"{yahoo_ticker}: transformed data is empty."
                        )

                        time.sleep(random.uniform(*pause_between_tickers))
                        continue

                    if last_fund is not None and not force_refresh:
                        final_df = final_df[final_df["timestamp"] > last_fund]

                    if final_df.empty:
                        update_fundamentals_status(
                            con=con,
                            asset_id=asset_id,
                            ticker=ticker,
                            yahoo_ticker=yahoo_ticker,
                            status="no_new_rows",
                            last_fundamental_date=last_fund,
                            error_message=None
                        )

                        batch_no_new_rows_count += 1
                        total_no_new_rows_count += 1

                        logging.info(
                            f"Batch {total_batches} | "
                            f"{batch_processed_count}/{len(assets_to_update)} | "
                            f"{yahoo_ticker}: no new rows."
                        )

                        time.sleep(random.uniform(*pause_between_tickers))
                        continue

                    inserted_rows = insert_new_fundamentals_rows(con, final_df)
                    latest_fundamental_date = final_df["timestamp"].max()

                    batch_inserted_rows += inserted_rows
                    total_inserted_rows += inserted_rows

                    if inserted_rows > 0:
                        status = "success"

                        batch_success_count += 1
                        total_success_count += 1
                    else:
                        status = "no_new_rows"

                        batch_no_new_rows_count += 1
                        total_no_new_rows_count += 1

                    update_fundamentals_status(
                        con=con,
                        asset_id=asset_id,
                        ticker=ticker,
                        yahoo_ticker=yahoo_ticker,
                        status=status,
                        last_fundamental_date=latest_fundamental_date,
                        error_message=None
                    )

                    logging.info(
                        f"Batch {total_batches} | "
                        f"{batch_processed_count}/{len(assets_to_update)} | "
                        f"{yahoo_ticker}: inserted {inserted_rows} rows. "
                        f"Latest quarter: {latest_fundamental_date}"
                    )

                    time.sleep(random.uniform(*pause_between_tickers))

                except Exception as e:
                    error_message = str(e)

                    update_fundamentals_status(
                        con=con,
                        asset_id=asset_id,
                        ticker=ticker,
                        yahoo_ticker=yahoo_ticker,
                        status="failed",
                        last_fundamental_date=last_fund,
                        error_message=error_message
                    )

                    batch_failed_count += 1
                    total_failed_count += 1

                    logging.error(
                        f"Batch {total_batches} | "
                        f"{batch_processed_count}/{len(assets_to_update)} | "
                        f"{yahoo_ticker}: failed. Error: {error_message}"
                    )

                    time.sleep(random.uniform(*pause_between_tickers))

            logging.info(
                f"Finished fundamentals batch {total_batches}. "
                f"Processed: {batch_processed_count}, "
                f"Success: {batch_success_count}, "
                f"No new rows: {batch_no_new_rows_count}, "
                f"No data: {batch_no_data_count}, "
                f"Failed: {batch_failed_count}, "
                f"Inserted rows: {batch_inserted_rows}"
            )

            if len(assets_to_update) < batch_size:
                logging.info(
                    "Last batch was smaller than batch_size. "
                    "No more assets are expected in this run."
                )
                break

            logging.info(
                f"Sleeping {pause_between_batches} seconds before next fundamentals batch."
            )

            time.sleep(pause_between_batches)

        logging.info(
            "Full fundamentals update finished. "
            f"Batches: {total_batches}, "
            f"Processed: {total_processed_count}, "
            f"Success: {total_success_count}, "
            f"No new rows: {total_no_new_rows_count}, "
            f"No data: {total_no_data_count}, "
            f"Failed: {total_failed_count}, "
            f"Inserted rows: {total_inserted_rows}"
        )

    finally:
        con.close()
        
 

def fill_fundamentals_table_from_sec():
    DB_PATH = r'C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb'
    con = duckdb.connect(DB_PATH)
    SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    SEC_COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"


    REVENUE_TAGS = [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "OperatingRevenues",
        "InterestAndDividendIncomeOperating",
    ]

    EPS_TAGS = [
        "EarningsPerShareDiluted",
        "EarningsPerShareBasic",
    ]

    SHARES_TAGS = [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "EntityCommonStockSharesOutstanding",
    ]


    def build_sec_headers(user_agent_email):
        return {
            "User-Agent": f"StratifySECBackfill/1.0 ({user_agent_email})",
            "Accept-Encoding": "gzip, deflate",
        }


    def fetch_sec_ticker_cik_mapping(user_agent_email):
        response = requests.get(
            SEC_TICKERS_URL,
            headers=build_sec_headers(user_agent_email),
            timeout=30,
        )
        response.raise_for_status()

        raw_data = response.json()

        rows = []
        for _, item in raw_data.items():
            rows.append({
                "ticker": str(item["ticker"]).upper().replace(".", "-"),
                "cik": int(item["cik_str"]),
                "cik_padded": str(item["cik_str"]).zfill(10),
                "sec_title": item.get("title"),
            })

        return pd.DataFrame(rows)


    def get_cik_for_ticker(ticker, sec_mapping_df):
        ticker_normalized = str(ticker).upper().replace(".", "-")

        match = sec_mapping_df[
            sec_mapping_df["ticker"] == ticker_normalized
        ]

        if match.empty:
            return None

        return str(match.iloc[0]["cik_padded"]).zfill(10)


    def fetch_company_facts_from_sec(cik_padded, user_agent_email, sleep_seconds=0.15):
        if cik_padded is None:
            return None

        url = SEC_COMPANY_FACTS_URL_TEMPLATE.format(
            cik_padded=str(cik_padded).zfill(10)
        )

        try:
            response = requests.get(
                url,
                headers=build_sec_headers(user_agent_email),
                timeout=30,
            )

            if response.status_code == 404:
                return None

            if response.status_code == 429:
                time.sleep(3)
                response = requests.get(
                    url,
                    headers=build_sec_headers(user_agent_email),
                    timeout=30,
                )

            response.raise_for_status()
            time.sleep(sleep_seconds)

            return response.json()

        except Exception:
            return None


    def extract_sec_fact_rows(company_facts_json, tag_candidates, preferred_units):
        """
        Extracts rows from all matching SEC tag/unit combinations.

        Important:
        This does not stop at the first available tag.
        It collects all possible tags so older revenue history is not missed.
        """

        if not company_facts_json:
            return pd.DataFrame()

        facts = company_facts_json.get("facts", {})
        us_gaap = facts.get("us-gaap", {})

        rows = []

        for tag_priority, tag in enumerate(tag_candidates):
            tag_data = us_gaap.get(tag)

            if not tag_data:
                continue

            units = tag_data.get("units", {})

            for unit_priority, unit in enumerate(preferred_units):
                if unit not in units:
                    continue

                for item in units[unit]:
                    rows.append({
                        "timestamp": item.get("end"),
                        "start": item.get("start"),
                        "value": item.get("val"),
                        "fy": item.get("fy"),
                        "fp": item.get("fp"),
                        "form": item.get("form"),
                        "filed": item.get("filed"),
                        "frame": item.get("frame"),
                        "tag": tag,
                        "unit": unit,
                        "tag_priority": tag_priority,
                        "unit_priority": unit_priority,
                    })

        return pd.DataFrame(rows)


    def clean_sec_quarterly_fact(raw_df, output_column, start_year=2000, is_duration_metric=True):
        """
        Cleans SEC fact rows into quarterly timestamp/value rows.

        For duration metrics such as revenue and EPS:
        - Uses true quarterly values when available.
        - Uses YTD/FY cumulative values only to derive missing quarter values.
        - Converts FY value into Q4 value using: FY - Q1 - Q2 - Q3.

        For non-duration metrics:
        - Uses the latest filed value per timestamp.
        """
        def empty_clean_df():
            return pd.DataFrame({
                "timestamp": pd.Series(dtype="datetime64[ns]"),
                output_column: pd.Series(dtype="float64"),
            })


        if raw_df is None or raw_df.empty:
            return pd.DataFrame({
                "timestamp": pd.Series(dtype="datetime64[ns]"),
                output_column: pd.Series(dtype="float64"),
            })
        df = raw_df.copy()

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["start"] = pd.to_datetime(df["start"], errors="coerce")
        df["filed"] = pd.to_datetime(df["filed"], errors="coerce")
        df[output_column] = pd.to_numeric(df["value"], errors="coerce")

        df = df.dropna(subset=["timestamp", output_column])
        df = df[df["timestamp"] >= pd.Timestamp(f"{int(start_year)}-01-01")]
        df = df[df["form"].isin(["10-Q", "10-K"])]

        if "fp" in df.columns:
            df = df[df["fp"].isin(["Q1", "Q2", "Q3", "Q4", "FY"])]

        if df.empty:
            return pd.DataFrame({
                "timestamp": pd.Series(dtype="datetime64[ns]"),
                output_column: pd.Series(dtype="float64"),
            })
        df["period_days"] = (df["timestamp"] - df["start"]).dt.days

        df["tag_priority"] = pd.to_numeric(
            df.get("tag_priority", 999),
            errors="coerce"
        ).fillna(999)

        df["unit_priority"] = pd.to_numeric(
            df.get("unit_priority", 999),
            errors="coerce"
        ).fillna(999)

        df["fy"] = pd.to_numeric(df["fy"], errors="coerce")

        if not is_duration_metric:
            df = df.sort_values(
                ["timestamp", "tag_priority", "unit_priority", "filed"],
                ascending=[True, True, True, False],
            )

            df = df.drop_duplicates(subset=["timestamp"], keep="first")

            return df[["timestamp", output_column]]

        quarterly_df = df[
            df["period_days"].between(60, 130)
        ].copy()

        quarterly_df = quarterly_df.sort_values(
            ["timestamp", "tag_priority", "unit_priority", "filed"],
            ascending=[True, True, True, False],
        )

        quarterly_df = quarterly_df.drop_duplicates(
            subset=["timestamp"],
            keep="first",
        )

        cumulative_df = df[
            df["period_days"].between(131, 420)
        ].copy()

        cumulative_df = cumulative_df.sort_values(
            ["fy", "timestamp", "tag_priority", "unit_priority", "filed"],
            ascending=[True, True, True, True, False],
        )

        cumulative_df = cumulative_df.drop_duplicates(
            subset=["fy", "timestamp"],
            keep="first",
        )

        derived_rows = []

        for fy, group in cumulative_df.groupby("fy"):
            if pd.isna(fy):
                continue

            group = group.sort_values("timestamp").copy()

            previous_value = None

            for _, row in group.iterrows():
                current_value = row[output_column]

                if previous_value is None:
                    quarter_value = current_value
                else:
                    quarter_value = current_value - previous_value

                previous_value = current_value

                derived_rows.append({
                    "timestamp": row["timestamp"],
                    output_column: quarter_value,
                    "source_type": "derived_from_cumulative",
                })

        derived_df = pd.DataFrame(derived_rows)

        if derived_df.empty:
            combined_df = quarterly_df[["timestamp", output_column]].copy()
        else:
            quarterly_clean_df = quarterly_df[["timestamp", output_column]].copy()
            quarterly_clean_df["source_type"] = "reported_quarterly"

            combined_df = pd.concat(
                [quarterly_clean_df, derived_df],
                ignore_index=True,
            )

            combined_df["source_priority"] = combined_df["source_type"].map({
                "reported_quarterly": 1,
                "derived_from_cumulative": 2,
            }).fillna(9)

            combined_df = combined_df.sort_values(
                ["timestamp", "source_priority"],
                ascending=[True, True],
            )

            combined_df = combined_df.drop_duplicates(
                subset=["timestamp"],
                keep="first",
            )

            combined_df = combined_df[["timestamp", output_column]]

        combined_df[output_column] = pd.to_numeric(
            combined_df[output_column],
            errors="coerce",
        )

        combined_df = combined_df.dropna(subset=[output_column])

        return combined_df.sort_values("timestamp")

    def transform_company_facts_to_fundamentals_df(company_facts_json, asset_id, start_year=2000):
        revenue_raw = extract_sec_fact_rows(
            company_facts_json=company_facts_json,
            tag_candidates=REVENUE_TAGS,
            preferred_units=["USD"],
        )

        eps_raw = extract_sec_fact_rows(
            company_facts_json=company_facts_json,
            tag_candidates=EPS_TAGS,
            preferred_units=["USD/shares", "USD/share"],
        )

        shares_raw = extract_sec_fact_rows(
            company_facts_json=company_facts_json,
            tag_candidates=SHARES_TAGS,
            preferred_units=["shares"],
        )

        revenue_df = clean_sec_quarterly_fact(
            raw_df=revenue_raw,
            output_column="revenue",
            start_year=start_year,
            is_duration_metric=True,
        )

        eps_df = clean_sec_quarterly_fact(
            raw_df=eps_raw,
            output_column="eps",
            start_year=start_year,
            is_duration_metric=True,
        )

        shares_df = clean_sec_quarterly_fact(
            raw_df=shares_raw,
            output_column="shares_outstanding",
            start_year=start_year,
            is_duration_metric=False,
        )

        for df in [revenue_df, eps_df, shares_df]:
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

        revenue_df = revenue_df.dropna(subset=["timestamp"])
        eps_df = eps_df.dropna(subset=["timestamp"])
        shares_df = shares_df.dropna(subset=["timestamp"])

        merged = revenue_df.merge(eps_df, on="timestamp", how="outer")
        merged = merged.merge(shares_df, on="timestamp", how="outer")

        if merged.empty:
            return pd.DataFrame(columns=[
                "asset_id",
                "timestamp",
                "market_cap",
                "revenue",
                "eps",
                "shares_outstanding",
            ])

        merged["asset_id"] = int(asset_id)
        merged["market_cap"] = None

        merged = merged[[
            "asset_id",
            "timestamp",
            "market_cap",
            "revenue",
            "eps",
            "shares_outstanding",
        ]]

        merged = merged.sort_values("timestamp")

        return merged

    def fill_missing_market_cap_from_prices(con, start_year=2000):
        """
        Fills missing market_cap values using shares_outstanding * latest available close price
        at or before the fundamentals timestamp.

        This only fills NULL market_cap values.
        Existing market_cap values are not overwritten.
        """

        con.sql(f"""
            UPDATE fundamentals AS f
            SET market_cap = f.shares_outstanding * p.close
            FROM (
                SELECT
                    f2.asset_id,
                    f2.timestamp,
                    p2.close,
                    ROW_NUMBER() OVER (
                        PARTITION BY f2.asset_id, f2.timestamp
                        ORDER BY p2.timestamp DESC
                    ) AS rn
                FROM fundamentals f2
                JOIN prices p2
                    ON p2.asset_id = f2.asset_id
                AND p2.timestamp <= f2.timestamp
                WHERE f2.timestamp >= DATE '{int(start_year)}-01-01'
                AND f2.market_cap IS NULL
                AND f2.shares_outstanding IS NOT NULL
                AND p2.close IS NOT NULL
            ) p
            WHERE f.asset_id = p.asset_id
            AND f.timestamp = p.timestamp
            AND p.rn = 1
            AND f.market_cap IS NULL
        """)


    def get_assets_with_missing_fundamental_values(con, start_year=2000, limit=None):
        """
        Returns candidate assets for SEC fundamentals fill.

        Candidate logic:
        1. Existing fundamentals rows have missing revenue / eps / shares_outstanding.
        2. Asset has fundamentals, but history starts after start_year.
        Example: AAPL has data only from 2025, so it must be sent to SEC.
        3. Skip assets already attempted with NO_CHANGES_WRITTEN.

        This returns asset-level candidates, not only missing rows.
        """

        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""

        query = f"""
            WITH filtered_assets AS (
                SELECT *
                FROM assets
                WHERE COALESCE(is_etf, FALSE) = FALSE

                -- Ticker-based filters
                AND ticker NOT LIKE '%W'
                AND ticker NOT LIKE '%U'
                AND ticker NOT LIKE '%R'
                AND ticker NOT LIKE '%P'
                AND ticker NOT LIKE '%+'
                AND ticker NOT LIKE '%='

                -- Security-type filters by name
                AND LOWER(name) NOT LIKE '%warrant%'
                AND LOWER(name) NOT LIKE '%warrants%'
                AND LOWER(name) NOT LIKE '%unit%'
                AND LOWER(name) NOT LIKE '%units%'
                AND LOWER(name) NOT LIKE '%right%'
                AND LOWER(name) NOT LIKE '%rights%'

                -- Preferred / debt-like securities
                AND LOWER(name) NOT LIKE '%preferred%'
                AND LOWER(name) NOT LIKE '%preference%'
                AND LOWER(name) NOT LIKE '%depositary%'
                AND LOWER(name) NOT LIKE '%note%'
                AND LOWER(name) NOT LIKE '%notes%'
                AND LOWER(name) NOT LIKE '%bond%'
                AND LOWER(name) NOT LIKE '%bonds%'
                AND LOWER(name) NOT LIKE '%debenture%'
                AND LOWER(name) NOT LIKE '%fixed-to-float%'
                AND LOWER(name) NOT LIKE '%fixed to float%'
                AND LOWER(name) NOT LIKE '%fixed rate%'
                AND LOWER(name) NOT LIKE '%floating rate%'
                AND LOWER(name) NOT LIKE '%mandatory convertible%'
                AND LOWER(name) NOT LIKE '%cumulative redeemable%'
                AND LOWER(name) NOT LIKE '%senior%'
                AND LOWER(name) NOT LIKE '%subordinated%'

                -- Funds / trusts / wrappers
                AND LOWER(name) NOT LIKE '%fund%'
                AND LOWER(name) NOT LIKE '%trust%'
                AND LOWER(name) NOT LIKE '%etf%'
                AND LOWER(name) NOT LIKE '%beneficial interest%'
                AND LOWER(name) NOT LIKE '%income company%'
                AND LOWER(name) NOT LIKE '%investment company%'
                AND LOWER(name) NOT LIKE '%closed-end%'
                AND LOWER(name) NOT LIKE '%closed end%'

                -- SPAC / acquisition wrappers
                AND LOWER(name) NOT LIKE '%acquisition corp%'
                AND LOWER(name) NOT LIKE '%acquisition corporation%'
                AND LOWER(name) NOT LIKE '%acquisition inc%'
                AND LOWER(name) NOT LIKE '%acquisition company%'
                AND LOWER(name) NOT LIKE '%blank check%'
                AND LOWER(name) NOT LIKE '%spac%'
            ),

            asset_fundamentals_quality AS (
                SELECT
                    a.asset_id,
                    a.ticker,
                    a.name,
                    a.sector,
                    a.industry,

                    COUNT(f.timestamp) AS total_rows,

                    COUNT(*) FILTER (
                        WHERE f.revenue IS NULL
                    ) AS missing_revenue_rows,

                    COUNT(*) FILTER (
                        WHERE f.eps IS NULL
                    ) AS missing_eps_rows,

                    COUNT(*) FILTER (
                        WHERE f.shares_outstanding IS NULL
                    ) AS missing_shares_rows,

                    MIN(f.timestamp) AS first_fundamental_date,
                    MAX(f.timestamp) AS last_fundamental_date

                FROM filtered_assets a
                JOIN fundamentals f
                    ON f.asset_id = a.asset_id

                GROUP BY
                    a.asset_id,
                    a.ticker,
                    a.name,
                    a.sector,
                    a.industry
            )

            SELECT
                asset_id,
                ticker,
                name,
                sector,
                industry,
                total_rows,
                missing_revenue_rows,
                missing_eps_rows,
                missing_shares_rows,
                first_fundamental_date,
                last_fundamental_date,

                CASE
                    WHEN first_fundamental_date > DATE '{int(start_year)}-01-01'
                        THEN 1
                    ELSE 0
                END AS missing_historical_backfill,

                CASE
                    WHEN first_fundamental_date > DATE '{int(start_year)}-01-01'
                        THEN 'NEEDS_HISTORICAL_BACKFILL'
                    WHEN missing_revenue_rows > 0
                        THEN 'MISSING_REVENUE'
                    WHEN missing_eps_rows > 0
                        THEN 'MISSING_EPS'
                    WHEN missing_shares_rows > 0
                        THEN 'MISSING_SHARES'
                    ELSE 'UNKNOWN'
                END AS candidate_reason

            FROM asset_fundamentals_quality afq

            WHERE (
                    first_fundamental_date > DATE '{int(start_year)}-01-01'
                    OR missing_revenue_rows > 0
                    OR missing_eps_rows > 0
                    OR missing_shares_rows > 0
            )

            AND NOT EXISTS (
                SELECT 1
                FROM sec_fundamentals_backfill_status s
                WHERE s.asset_id = afq.asset_id
                    AND s.last_status IN (
                                        'NO_CHANGES_WRITTEN',
                                        'NO_CIK',
                                        'NO_SEC_FACTS',
                                        'NO_USABLE_SEC_ROWS'
                                    )
            )

            ORDER BY
                missing_historical_backfill DESC,
                ticker ASC

            {limit_clause}
        """

        return con.sql(query).df()

    def fill_fundamentals_with_sec(
        con,
        user_agent_email,
        start_year=2000,
        limit_assets=None,
        dry_run=True,
        sleep_seconds=0.15,
        progress_every=10
    ):
        """
        Fills fundamentals from SEC from start_year onward.

        Behavior:
        - Goes asset by asset.
        - Uses SEC only.
        - Inserts missing historical rows from start_year onward.
        - Updates only NULL values in existing rows.
        - Never overwrites existing non-NULL Yahoo values.
        """

        logger = logging.getLogger(__name__)

        missing_rows_df = get_assets_with_missing_fundamental_values(
            con=con,
            start_year=start_year,
            limit=None,
        )

        if missing_rows_df.empty:
            return pd.DataFrame([{
                "asset_id": None,
                "ticker": None,
                "status": "NO_MISSING_ROWS",
                "sec_rows": 0,
                "written_rows": 0,
            }])

        candidate_assets_df = (
            missing_rows_df[["asset_id", "ticker", "name"]]
            .drop_duplicates()
            .sort_values("ticker")
            .copy()
        )

        if limit_assets is not None:
            candidate_assets_df = candidate_assets_df.head(int(limit_assets))
            
        total_candidates = len(candidate_assets_df)

        print("-" * 80)
        print(f"SEC batch asset count: {total_candidates}")
        print("-" * 80)

        sec_mapping_df = fetch_sec_ticker_cik_mapping(
            user_agent_email=user_agent_email
        )

        results = []

        for asset_index, (_, asset_row) in enumerate(candidate_assets_df.iterrows(), start=1):
            asset_id = int(asset_row["asset_id"])
            ticker = asset_row["ticker"]
            name = asset_row["name"]

            if asset_index == 1 or asset_index % progress_every == 0 or asset_index == total_candidates:
                print(
                    f"Processing SEC asset {asset_index}/{total_candidates} | "
                    f"asset_id={asset_id} | ticker={ticker}"
                )

            logger.info(f"SEC fundamentals fill | asset_id={asset_id} | ticker={ticker}")

            cik_padded = get_cik_for_ticker(
                ticker=ticker,
                sec_mapping_df=sec_mapping_df,
            )

            if cik_padded is None:
                status = "NO_CIK"

                if not dry_run:
                    update_sec_backfill_status(
                        con=con,
                        asset_id=asset_id,
                        ticker=ticker,
                        status=status,
                        sec_rows=0,
                        inserted_rows=0,
                        filled_values=0,
                        written_rows=0,
                    )

                results.append({
                    "asset_id": asset_id,
                    "ticker": ticker,
                    "name": name,
                    "status": status,
                    "sec_rows": 0,
                    "inserted_rows": 0,
                    "filled_values": 0,
                    "written_rows": 0,
                })
                continue

            company_facts_json = fetch_company_facts_from_sec(
                cik_padded=cik_padded,
                user_agent_email=user_agent_email,
                sleep_seconds=sleep_seconds,
            )
            if not company_facts_json:
                status = "NO_SEC_FACTS"

                if not dry_run:
                    update_sec_backfill_status(
                        con=con,
                        asset_id=asset_id,
                        ticker=ticker,
                        status=status,
                        sec_rows=0,
                        inserted_rows=0,
                        filled_values=0,
                        written_rows=0,
                    )

                results.append({
                    "asset_id": asset_id,
                    "ticker": ticker,
                    "name": name,
                    "status": status,
                    "sec_rows": 0,
                    "inserted_rows": 0,
                    "filled_values": 0,
                    "written_rows": 0,
                })
                continue

            sec_fundamentals_df = transform_company_facts_to_fundamentals_df(
                company_facts_json=company_facts_json,
                asset_id=asset_id,
                start_year=start_year,
            )

            if sec_fundamentals_df.empty:
                status = "NO_USABLE_SEC_ROWS"

                if not dry_run:
                    update_sec_backfill_status(
                        con=con,
                        asset_id=asset_id,
                        ticker=ticker,
                        status=status,
                        sec_rows=0,
                        inserted_rows=0,
                        filled_values=0,
                        written_rows=0,
                    )

                results.append({
                    "asset_id": asset_id,
                    "ticker": ticker,
                    "name": name,
                    "status": status,
                    "sec_rows": 0,
                    "inserted_rows": 0,
                    "filled_values": 0,
                    "written_rows": 0,
                })
                continue

            if dry_run:
                results.append({
                    "asset_id": asset_id,
                    "ticker": ticker,
                    "name": name,
                    "status": "DRY_RUN_READY",
                    "sec_rows": len(sec_fundamentals_df),
                    "written_rows": 0,
                })
                continue

            write_result = upsert_fundamentals_from_sec_safely(
                con=con,
                sec_fundamentals_df=sec_fundamentals_df,
            )

            inserted_rows = write_result["inserted_rows"]
            filled_values = write_result["filled_values"]
            total_written = write_result["total_written"]

            if total_written == 0:
                status = "NO_CHANGES_WRITTEN"
            elif inserted_rows > 0 and filled_values > 0:
                status = "INSERTED_AND_FILLED"
            elif inserted_rows > 0:
                status = "INSERTED_HISTORICAL_ROWS"
            elif filled_values > 0:
                status = "FILLED_LOCAL_NULLS"
            else:
                status = "UPDATED"
                
            if not dry_run:
                update_sec_backfill_status(
                    con=con,
                    asset_id=asset_id,
                    ticker=ticker,
                    status=status,
                    sec_rows=len(sec_fundamentals_df),
                    inserted_rows=inserted_rows,
                    filled_values=filled_values,
                    written_rows=total_written,
                )

            results.append({
                "asset_id": asset_id,
                "ticker": ticker,
                "name": name,
                "status": status,
                "sec_rows": len(sec_fundamentals_df),
                "inserted_rows": inserted_rows,
                "filled_values": filled_values,
                "written_rows": total_written,
            })
            
            if total_written > 0:
                print(
                    f"  Updated {ticker}: "
                    f"status={status}, "
                    f"inserted_rows={inserted_rows}, "
                    f"filled_values={filled_values}, "
                    f"total_written={total_written}"
                )

        return pd.DataFrame(results)

    def update_sec_backfill_status(
        con,
        asset_id,
        ticker,
        status,
        sec_rows,
        inserted_rows,
        filled_values,
        written_rows,
    ):
        """
        Saves the last SEC backfill result for an asset.
        """

        status_df = pd.DataFrame([{
            "asset_id": int(asset_id),
            "ticker": ticker,
            "last_attempt_at": datetime.now(),
            "last_status": status,
            "sec_rows": int(sec_rows),
            "inserted_rows": int(inserted_rows),
            "filled_values": int(filled_values),
            "written_rows": int(written_rows),
        }])

        con.register("sec_status_update", status_df)

        con.sql("""
            INSERT INTO sec_fundamentals_backfill_status (
                asset_id,
                ticker,
                last_attempt_at,
                last_status,
                sec_rows,
                inserted_rows,
                filled_values,
                written_rows
            )
            SELECT
                asset_id,
                ticker,
                last_attempt_at,
                last_status,
                sec_rows,
                inserted_rows,
                filled_values,
                written_rows
            FROM sec_status_update

            ON CONFLICT (asset_id)
            DO UPDATE SET
                ticker = excluded.ticker,
                last_attempt_at = excluded.last_attempt_at,
                last_status = excluded.last_status,
                sec_rows = excluded.sec_rows,
                inserted_rows = excluded.inserted_rows,
                filled_values = excluded.filled_values,
                written_rows = excluded.written_rows
        """)

        con.unregister("sec_status_update")


    def upsert_fundamentals_from_sec_safely(con, sec_fundamentals_df):
        """
        Inserts SEC fundamentals rows and updates only NULL values.

        Existing non-NULL values are never overwritten.

        Returns:
        - inserted_rows: new historical rows inserted
        - filled_values: existing NULL field values filled
        - total_written: inserted_rows + filled_values
        """

        if sec_fundamentals_df is None or sec_fundamentals_df.empty:
            return {
                "inserted_rows": 0,
                "filled_values": 0,
                "total_written": 0,
            }

        df = sec_fundamentals_df.copy()

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["asset_id", "timestamp"])

        if df.empty:
            return {
                "inserted_rows": 0,
                "filled_values": 0,
                "total_written": 0,
            }

        df["asset_id"] = df["asset_id"].astype(int)

        for col in ["market_cap", "revenue", "eps", "shares_outstanding"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        con.register("sec_fundamentals_to_upsert", df)

        before_df = con.sql("""
            SELECT
                COUNT(*) FILTER (
                    WHERE f.asset_id IS NULL
                ) AS insertable_rows,

                COUNT(*) FILTER (
                    WHERE f.asset_id IS NOT NULL
                    AND f.revenue IS NULL
                    AND s.revenue IS NOT NULL
                ) AS fillable_revenue,

                COUNT(*) FILTER (
                    WHERE f.asset_id IS NOT NULL
                    AND f.eps IS NULL
                    AND s.eps IS NOT NULL
                ) AS fillable_eps,

                COUNT(*) FILTER (
                    WHERE f.asset_id IS NOT NULL
                    AND f.shares_outstanding IS NULL
                    AND s.shares_outstanding IS NOT NULL
                ) AS fillable_shares

            FROM sec_fundamentals_to_upsert s
            LEFT JOIN fundamentals f
                ON f.asset_id = s.asset_id
            AND f.timestamp = s.timestamp
        """).df()

        inserted_rows = int(before_df["insertable_rows"].iloc[0])

        filled_values = int(
            before_df["fillable_revenue"].iloc[0]
            + before_df["fillable_eps"].iloc[0]
            + before_df["fillable_shares"].iloc[0]
        )

        con.sql("""
            INSERT INTO fundamentals (
                asset_id,
                timestamp,
                market_cap,
                revenue,
                eps,
                shares_outstanding
            )
            SELECT
                asset_id,
                timestamp,
                market_cap,
                revenue,
                eps,
                shares_outstanding
            FROM sec_fundamentals_to_upsert

            ON CONFLICT (asset_id, timestamp)
            DO UPDATE SET
                market_cap = COALESCE(fundamentals.market_cap, excluded.market_cap),
                revenue = COALESCE(fundamentals.revenue, excluded.revenue),
                eps = COALESCE(fundamentals.eps, excluded.eps),
                shares_outstanding = COALESCE(fundamentals.shares_outstanding, excluded.shares_outstanding)
        """)

        con.unregister("sec_fundamentals_to_upsert")

        return {
            "inserted_rows": inserted_rows,
            "filled_values": filled_values,
            "total_written": inserted_rows + filled_values,
        }

    def run_sec_fundamentals_fill_in_batches(
        con,
        user_agent_email,
        start_year=2000,
        batch_size=50,
        max_batches=None,
        sleep_seconds=0.15,
        dry_run=False,
        progress_every=10
    ):
        """
        Runs SEC fundamentals fill in controlled batches.

        Important:
        - Each batch recalculates current missing rows.
        - This means already-fixed assets naturally disappear from the next batch.
        - Existing non-NULL values are never overwritten.
        """

        all_results = []
        batch_number = 1

        while True:
            if max_batches is not None and batch_number > max_batches:
                break

            print("=" * 80)
            print(f"SEC fundamentals batch {batch_number}")
            print("=" * 80)

            missing_rows_df = get_assets_with_missing_fundamental_values(
                con=con,
                start_year=start_year,
                limit=None,
            )

            if missing_rows_df.empty:
                print("No missing fundamentals left.")
                break

            remaining_assets = missing_rows_df["asset_id"].nunique()
            print(f"Remaining assets with missing values: {remaining_assets}")
            print(f"Remaining missing rows: {len(missing_rows_df)}")

            results_df = fill_fundamentals_with_sec(
                con=con,
                user_agent_email=user_agent_email,
                start_year=start_year,
                limit_assets=batch_size,
                dry_run=dry_run,
                sleep_seconds=sleep_seconds,
                progress_every=progress_every,
            )

            if not dry_run:
                fill_missing_market_cap_from_prices(
                    con=con,
                    start_year=start_year,
                )

                con.sql("CHECKPOINT")

            print(results_df)
            print(results_df["status"].value_counts(dropna=False))
            
            if not results_df.empty and "written_rows" in results_df.columns:
                inserted_total = results_df.get("inserted_rows", pd.Series(dtype="float")).sum()
                filled_total = results_df.get("filled_values", pd.Series(dtype="float")).sum()
                written_total = results_df["written_rows"].sum()

                print("-" * 80)
                print(f"Batch {batch_number} summary:")
                print(f"Inserted historical rows: {int(inserted_total)}")
                print(f"Filled existing NULL values: {int(filled_total)}")
                print(f"Total written: {int(written_total)}")
                print("-" * 80)

            all_results.append(results_df)

            if results_df.empty:
                break

            if dry_run:
                print("Dry run enabled. Stopping after one batch.")
                break

            batch_number += 1

        if all_results:
            return pd.concat(all_results, ignore_index=True)

        return pd.DataFrame()

    run_sec_fundamentals_fill_in_batches(
        con=con,
        user_agent_email="lavie.koren.ams@gmail.com",
        start_year=2000,
        batch_size=50,
        max_batches=None,
        sleep_seconds=0.15,
        dry_run=False,
        progress_every=10
    )

    fill_missing_market_cap_from_prices(
        con=con,
        start_year=2000,
    )

    con.sql("CHECKPOINT")
    con.close()


 
 
### fill features table (4)


def fill_features_table(
    fundamental_lag_days=60,
    lookback_days=1200,
    min_price_rows=21,
    max_assets=None,
    only_ticker=None,
    force_rebuild=False,
    rebuild_from_date=None
):
    
    """
    Computes and fills the features table from prices and fundamentals.

    Core rules:
    - No lookahead from fundamentals.
    - Missing values stay NULL.
    - No fake zero filling.
    - No full table delete.
    - Only missing (asset_id, timestamp) rows are inserted.
    """

    con = duckdb.connect(DB_PATH)
    logger = logging.getLogger(__name__)
    logger.info("fill_features_table function was called.")

    features_columns = [
        "asset_id",
        "timestamp",
        "volatility",
        "momentum_relative_sp_1y",
        "avg_volume",
        "volume_spike",
        "pe_ratio",
        "rsi_14",
        "atr_14",
        "dist_sma50",
        "dist_sma200",
        "beta_90d",
        "sharpe_ratio_90d",
        "max_drawdown_90d",
        "revenue_growth_yoy",
        "eps_growth_yoy",
        "return_1d",
        "return_7d",
        "return_1m",
        "return_3m",
        "return_6m",
        "return_1y",
        "return_3y",
        "return_max"
    ]

    total_rows_inserted = 0
    assets_processed = 0
    assets_skipped = 0
    assets_failed = 0

    try:
        logger.info("Starting features calculation...")

        # ======================================================
        # 1. LOAD SPY ID
        # ======================================================

        spy_row = con.execute("""
            SELECT asset_id
            FROM assets
            WHERE ticker = 'SPY'
            LIMIT 1
        """).fetchone()

        if spy_row is None:
            raise ValueError("SPY was not found in assets table.")

        spy_id = int(spy_row[0])

        # ======================================================
        # 2. SELECT ASSETS THAT NEED FEATURE UPDATES
        # ======================================================

        ticker_filter = ""
        params = [int(min_price_rows)]

        if only_ticker is not None:
            ticker_filter = "AND a.ticker = ?"
            params.append(str(only_ticker).strip())

        limit_clause = ""
        if max_assets is not None:
            limit_clause = f"LIMIT {int(max_assets)}"

        force_rebuild_sql = ""
        if force_rebuild:
            force_rebuild_sql = """
                OR fs.fundamentals_rows >= 1
            """

        assets_df = con.execute(f"""
            WITH last_features AS (
                SELECT
                    asset_id,
                    MAX(timestamp) AS last_feature_date
                FROM features
                GROUP BY asset_id
            ),

            price_summary AS (
                SELECT
                    asset_id,
                    COUNT(*) AS price_rows,
                    MIN(timestamp) AS first_price_date,
                    MAX(timestamp) AS last_price_date
                FROM prices
                GROUP BY asset_id
            ),

            fundamentals_summary AS (
                SELECT
                    asset_id,
                    COUNT(*) AS fundamentals_rows,
                    MAX(timestamp) + (CAST(? AS INTEGER) * INTERVAL '1 day') AS latest_available_fundamental_date
                FROM fundamentals
                GROUP BY asset_id
            ),

            latest_feature_row AS (
                SELECT
                    f.asset_id,
                    f.timestamp,
                    f.pe_ratio,
                    f.revenue_growth_yoy,
                    f.eps_growth_yoy
                FROM features f
                JOIN last_features lf
                    ON f.asset_id = lf.asset_id
                AND f.timestamp = lf.last_feature_date
            )

            SELECT
                a.asset_id,
                a.ticker,
                lf.last_feature_date,
                ps.first_price_date,
                ps.last_price_date,
                ps.price_rows
            FROM assets a
            JOIN price_summary ps
                ON a.asset_id = ps.asset_id
            LEFT JOIN last_features lf
                ON a.asset_id = lf.asset_id
            LEFT JOIN fundamentals_summary fs
                ON a.asset_id = fs.asset_id
            LEFT JOIN latest_feature_row lfr
                ON a.asset_id = lfr.asset_id
            WHERE
                a.ticker IS NOT NULL
                AND TRIM(a.ticker) <> ''
                AND ps.price_rows >= ?
                AND (
                    lf.last_feature_date IS NULL
                    OR ps.last_price_date > lf.last_feature_date

                    -- Reprocess assets whose latest row is missing fundamental-based features.
                    OR (
                        fs.fundamentals_rows >= 4
                        AND ps.last_price_date >= fs.latest_available_fundamental_date
                        AND (
                            lfr.pe_ratio IS NULL
                            OR lfr.revenue_growth_yoy IS NULL
                            OR lfr.eps_growth_yoy IS NULL
                        )
                    )

                    -- Historical rebuild mode.
                    {force_rebuild_sql}
                )
                {ticker_filter}
            ORDER BY
                COALESCE(lf.last_feature_date, DATE '1900-01-01') ASC,
                a.ticker
            {limit_clause}
        """, [int(fundamental_lag_days)] + params).df()

        if assets_df.empty:
            logger.info("No assets require feature updates.")
            return

        # ======================================================
        # 3. LOAD SPY DATA FOR THE REQUIRED RANGE
        # ======================================================

        min_spy_fetch_date = None

        for row in assets_df.itertuples(index=False):
            if pd.isna(row.last_feature_date):
                candidate = pd.Timestamp("1900-01-01")
            else:
                candidate = pd.to_datetime(row.last_feature_date) - pd.Timedelta(days=lookback_days)

            if min_spy_fetch_date is None or candidate < min_spy_fetch_date:
                min_spy_fetch_date = candidate

        spy_df = con.execute("""
            SELECT
                timestamp,
                COALESCE(adj_close, close) AS spy_close
            FROM prices
            WHERE
                asset_id = ?
                AND timestamp >= ?
            ORDER BY timestamp
        """, [
            spy_id,
            min_spy_fetch_date.strftime("%Y-%m-%d")
        ]).df()

        if spy_df.empty:
            raise ValueError("No SPY price data found for the required date range.")

        spy_df["timestamp"] = pd.to_datetime(spy_df["timestamp"])
        spy_df["spy_ret_1d"] = spy_df["spy_close"].pct_change(1)
        spy_df["spy_ret_1y"] = spy_df["spy_close"].pct_change(252)
        spy_df = spy_df[["timestamp", "spy_ret_1d", "spy_ret_1y"]].copy()

        total_assets = len(assets_df)
        logger.info(f"Assets to process: {total_assets}")

        # ======================================================
        # 4. PROCESS ASSETS ONE BY ONE
        # ======================================================

        for asset_index, row in enumerate(assets_df.itertuples(index=False), start=1):
            asset_id = int(row.asset_id)
            ticker = str(row.ticker).strip()

            try:
                # ======================================================
                # 4.1 DETERMINE FETCH AND INSERT DATES PER ASSET
                # ======================================================

                if force_rebuild:
                    if rebuild_from_date is None:
                        insert_start_date = pd.Timestamp("1900-01-01")
                        fetch_start_date = pd.Timestamp("1900-01-01")
                    else:
                        insert_start_date = pd.to_datetime(rebuild_from_date)

                        # Fetch extra history before the rebuild date so rolling indicators
                        # such as SMA200, beta, volatility, and returns can be calculated correctly.
                        fetch_start_date = insert_start_date - pd.Timedelta(days=lookback_days)

                        if fetch_start_date < pd.Timestamp("1900-01-01"):
                            fetch_start_date = pd.Timestamp("1900-01-01")

                else:
                    if pd.isna(row.last_feature_date):
                        insert_start_date = pd.Timestamp("1900-01-01")
                        fetch_start_date = pd.Timestamp("1900-01-01")
                    else:
                        insert_start_date = pd.to_datetime(row.last_feature_date)
                        fetch_start_date = insert_start_date - pd.Timedelta(days=lookback_days)

                first_close_row = con.execute("""
                    SELECT
                        COALESCE(adj_close, close) AS first_close
                    FROM prices
                    WHERE
                        asset_id = ?
                        AND COALESCE(adj_close, close) IS NOT NULL
                        AND COALESCE(adj_close, close) > 0
                    ORDER BY timestamp
                    LIMIT 1
                """, [asset_id]).fetchone()

                first_close = first_close_row[0] if first_close_row is not None else None

                # ======================================================
                # 4.2 FETCH PRICES + LAGGED FUNDAMENTALS
                # ======================================================
                # Fundamentals are not available on the quarter end date.
                # We delay them by fundamental_lag_days to reduce lookahead risk.

                df = con.execute("""
                    WITH fundamentals_base AS (
                        SELECT
                            asset_id,
                            timestamp,
                            revenue,
                            eps,
                            shares_outstanding,

                            LAG(revenue, 4) OVER (
                                PARTITION BY asset_id
                                ORDER BY timestamp
                            ) AS previous_year_revenue,

                            LAG(eps, 4) OVER (
                                PARTITION BY asset_id
                                ORDER BY timestamp
                            ) AS previous_year_eps,

                            SUM(eps) OVER (
                                PARTITION BY asset_id
                                ORDER BY timestamp
                                ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                            ) AS eps_ttm_raw,

                            COUNT(eps) OVER (
                                PARTITION BY asset_id
                                ORDER BY timestamp
                                ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                            ) AS eps_ttm_count

                        FROM fundamentals
                        WHERE asset_id = ?
                    ),

                    fundamentals_enriched AS (
                        SELECT
                            asset_id,

                            timestamp + (CAST(? AS INTEGER) * INTERVAL '1 day') AS available_timestamp,

                            CASE
                                WHEN revenue IS NOT NULL
                                    AND previous_year_revenue IS NOT NULL
                                    AND previous_year_revenue > 0
                                THEN revenue / previous_year_revenue - 1
                                ELSE NULL
                            END AS revenue_growth_yoy,

                            CASE
                                WHEN eps IS NOT NULL
                                    AND previous_year_eps IS NOT NULL
                                    AND previous_year_eps != 0
                                THEN (eps - previous_year_eps) / ABS(previous_year_eps)
                                ELSE NULL
                            END AS eps_growth_yoy,

                            CASE
                                WHEN eps_ttm_count = 4
                                    AND eps_ttm_raw IS NOT NULL
                                    AND eps_ttm_raw != 0
                                THEN eps_ttm_raw
                                ELSE NULL
                            END AS eps_ttm

                        FROM fundamentals_base
                    ),

                    prices_adjusted AS (
                        SELECT
                            p.asset_id,
                            p.timestamp,

                            CASE
                                WHEN p.adj_close IS NOT NULL
                                    AND p.close IS NOT NULL
                                    AND p.close > 0
                                    AND p.open IS NOT NULL
                                THEN p.open * (p.adj_close / p.close)
                                ELSE p.open
                            END AS open,

                            CASE
                                WHEN p.adj_close IS NOT NULL
                                    AND p.close IS NOT NULL
                                    AND p.close > 0
                                    AND p.high IS NOT NULL
                                THEN p.high * (p.adj_close / p.close)
                                ELSE p.high
                            END AS high,

                            CASE
                                WHEN p.adj_close IS NOT NULL
                                    AND p.close IS NOT NULL
                                    AND p.close > 0
                                    AND p.low IS NOT NULL
                                THEN p.low * (p.adj_close / p.close)
                                ELSE p.low
                            END AS low,

                            COALESCE(p.adj_close, p.close) AS close,

                            p.close AS raw_close,

                            p.volume

                        FROM prices p
                        WHERE
                            p.asset_id = ?
                            AND p.timestamp >= ?
                    )

                    SELECT
                        p.asset_id,
                        p.timestamp,
                        p.open,
                        p.high,
                        p.low,
                        p.close,
                        p.raw_close,
                        p.volume,

                        f.revenue_growth_yoy,
                        f.eps_growth_yoy,
                        f.eps_ttm

                    FROM prices_adjusted p
                    ASOF LEFT JOIN fundamentals_enriched f
                        ON p.asset_id = f.asset_id
                    AND p.timestamp >= f.available_timestamp
                    ORDER BY p.timestamp
                """, [
                    asset_id,
                    int(fundamental_lag_days),
                    asset_id,
                    fetch_start_date.strftime("%Y-%m-%d")
                ]).df()

                if df.empty or len(df) < min_price_rows:
                    assets_skipped += 1
                    logger.info(
                        f"{asset_index}/{total_assets} | {ticker}: skipped, not enough price rows."
                    )
                    continue

                df["timestamp"] = pd.to_datetime(df["timestamp"])

                # ======================================================
                # 4.3 RETURNS
                # ======================================================

                df["return_1d"] = df["close"].pct_change(1, fill_method=None)
                df["return_7d"] = df["close"].pct_change(7, fill_method=None)
                df["return_1m"] = df["close"].pct_change(21, fill_method=None)
                df["return_3m"] = df["close"].pct_change(63, fill_method=None)
                df["return_6m"] = df["close"].pct_change(126, fill_method=None)
                df["return_1y"] = df["close"].pct_change(252, fill_method=None)
                df["return_3y"] = df["close"].pct_change(252 * 3, fill_method=None)

                if first_close is not None and first_close > 0:
                    df["return_max"] = (df["close"] / first_close) - 1
                else:
                    df["return_max"] = pd.NA

                # ======================================================
                # 4.4 MOVING AVERAGES
                # ======================================================

                df["sma50"] = df["close"].rolling(
                    window=50,
                    min_periods=50
                ).mean()

                df["sma200"] = df["close"].rolling(
                    window=200,
                    min_periods=200
                ).mean()

                df["dist_sma50"] = (df["close"] - df["sma50"]) / df["sma50"]
                df["dist_sma200"] = (df["close"] - df["sma200"]) / df["sma200"]

                df.loc[df["sma50"].isna(), "dist_sma50"] = pd.NA
                df.loc[df["sma200"].isna(), "dist_sma200"] = pd.NA
                df.loc[df["sma50"] <= 0, "dist_sma50"] = pd.NA
                df.loc[df["sma200"] <= 0, "dist_sma200"] = pd.NA

                # ======================================================
                # 4.5 VOLATILITY AND VOLUME
                # ======================================================

                df["volatility"] = (
                    df["return_1d"]
                    .rolling(window=21, min_periods=21)
                    .std()
                    * (252 ** 0.5)
                )

                df["avg_volume"] = df["volume"].rolling(
                    window=20,
                    min_periods=20
                ).mean()

                df["volume_spike"] = df["volume"] / df["avg_volume"]

                df.loc[df["avg_volume"].isna(), "volume_spike"] = pd.NA
                df.loc[df["avg_volume"] <= 0, "volume_spike"] = pd.NA

                # ======================================================
                # 4.6 RSI 14
                # ======================================================

                delta = df["close"].diff()

                gain = (
                    delta
                    .where(delta > 0, 0)
                    .rolling(window=14, min_periods=14)
                    .mean()
                )

                loss = (
                    -delta
                    .where(delta < 0, 0)
                    .rolling(window=14, min_periods=14)
                    .mean()
                )

                rs = gain / loss
                df["rsi_14"] = 100 - (100 / (1 + rs))

                df.loc[(loss == 0) & (gain > 0), "rsi_14"] = 100
                df.loc[(loss == 0) & (gain == 0), "rsi_14"] = pd.NA

                # ======================================================
                # 4.7 ATR 14
                # ======================================================

                true_range = pd.concat(
                    [
                        df["high"] - df["low"],
                        (df["high"] - df["close"].shift()).abs(),
                        (df["low"] - df["close"].shift()).abs()
                    ],
                    axis=1
                ).max(axis=1)

                df["atr_14"] = true_range.rolling(
                    window=14,
                    min_periods=14
                ).mean()

                # ======================================================
                # 4.8 MAX DRAWDOWN 90D
                # ======================================================

                rolling_max_90 = df["close"].rolling(
                    window=90,
                    min_periods=90
                ).max()

                df["max_drawdown_90d"] = (df["close"] / rolling_max_90) - 1

                df.loc[rolling_max_90.isna(), "max_drawdown_90d"] = pd.NA
                df.loc[rolling_max_90 <= 0, "max_drawdown_90d"] = pd.NA

                # ======================================================
                # 4.9 SHARPE RATIO 90D
                # ======================================================

                rolling_return_mean_90 = df["return_1d"].rolling(
                    window=90,
                    min_periods=90
                ).mean()

                rolling_return_std_90 = df["return_1d"].rolling(
                    window=90,
                    min_periods=90
                ).std()

                df["sharpe_ratio_90d"] = (
                    rolling_return_mean_90 / rolling_return_std_90
                ) * (252 ** 0.5)

                df.loc[rolling_return_std_90.isna(), "sharpe_ratio_90d"] = pd.NA
                df.loc[rolling_return_std_90 <= 0, "sharpe_ratio_90d"] = pd.NA

                # ======================================================
                # 4.10 SPY RELATIVE MOMENTUM AND BETA
                # ======================================================

                df = df.merge(
                    spy_df,
                    on="timestamp",
                    how="left"
                )

                df["momentum_relative_sp_1y"] = df["return_1y"] - df["spy_ret_1y"]

                cov_90 = df["return_1d"].rolling(
                    window=90,
                    min_periods=90
                ).cov(df["spy_ret_1d"])

                var_90 = df["spy_ret_1d"].rolling(
                    window=90,
                    min_periods=90
                ).var()

                df["beta_90d"] = cov_90 / var_90

                df.loc[var_90.isna(), "beta_90d"] = pd.NA
                df.loc[var_90 <= 0, "beta_90d"] = pd.NA

                # ======================================================
                # 4.11 PE RATIO
                # ======================================================


                df["pe_ratio"] = df["raw_close"] / df["eps_ttm"]

                df.loc[df["raw_close"].isna(), "pe_ratio"] = pd.NA
                df.loc[df["raw_close"] <= 0, "pe_ratio"] = pd.NA
                df.loc[df["eps_ttm"].isna(), "pe_ratio"] = pd.NA
                df.loc[df["eps_ttm"] == 0, "pe_ratio"] = pd.NA

                # ======================================================
                # 4.12 FINAL CLEANUP
                # ======================================================

                df = df.replace([float("inf"), float("-inf")], pd.NA)

                for col in features_columns:
                    if col not in df.columns:
                        df[col] = pd.NA

                save_start_date = insert_start_date if force_rebuild else fetch_start_date

                df_to_save = df.loc[
                        df["timestamp"] >= save_start_date,
                        features_columns
                    ].copy()

                df_to_save = df_to_save.dropna(
                    subset=["asset_id", "timestamp"]
                )

                df_to_save = df_to_save.drop_duplicates(
                    subset=["asset_id", "timestamp"],
                    keep="last"
                )

                if df_to_save.empty:
                    assets_skipped += 1
                    logger.info(
                        f"{asset_index}/{total_assets} | {ticker}: no new feature rows."
                    )
                    continue

                # ======================================================
                # 4.13 INSERT ONLY MISSING ROWS
                # ======================================================

                con.register("df_to_save", df_to_save)

                try:
                    rows_to_save = len(df_to_save)

                    con.execute("""
                        INSERT INTO features (
                            asset_id,
                            timestamp,
                            volatility,
                            momentum_relative_sp_1y,
                            avg_volume,
                            volume_spike,
                            pe_ratio,
                            rsi_14,
                            atr_14,
                            dist_sma50,
                            dist_sma200,
                            beta_90d,
                            sharpe_ratio_90d,
                            max_drawdown_90d,
                            revenue_growth_yoy,
                            eps_growth_yoy,
                            return_1d,
                            return_7d,
                            return_1m,
                            return_3m,
                            return_6m,
                            return_1y,
                            return_3y,
                            return_max
                        )
                        SELECT
                            asset_id,
                            timestamp,
                            volatility,
                            momentum_relative_sp_1y,
                            avg_volume,
                            volume_spike,
                            pe_ratio,
                            rsi_14,
                            atr_14,
                            dist_sma50,
                            dist_sma200,
                            beta_90d,
                            sharpe_ratio_90d,
                            max_drawdown_90d,
                            revenue_growth_yoy,
                            eps_growth_yoy,
                            return_1d,
                            return_7d,
                            return_1m,
                            return_3m,
                            return_6m,
                            return_1y,
                            return_3y,
                            return_max
                        FROM df_to_save
                        ON CONFLICT (asset_id, timestamp) DO UPDATE SET
                            volatility = COALESCE(EXCLUDED.volatility, features.volatility),
                            momentum_relative_sp_1y = COALESCE(EXCLUDED.momentum_relative_sp_1y, features.momentum_relative_sp_1y),
                            avg_volume = COALESCE(EXCLUDED.avg_volume, features.avg_volume),
                            volume_spike = COALESCE(EXCLUDED.volume_spike, features.volume_spike),
                            pe_ratio = EXCLUDED.pe_ratio,
                            rsi_14 = COALESCE(EXCLUDED.rsi_14, features.rsi_14),
                            atr_14 = COALESCE(EXCLUDED.atr_14, features.atr_14),
                            dist_sma50 = COALESCE(EXCLUDED.dist_sma50, features.dist_sma50),
                            dist_sma200 = COALESCE(EXCLUDED.dist_sma200, features.dist_sma200),
                            beta_90d = COALESCE(EXCLUDED.beta_90d, features.beta_90d),
                            sharpe_ratio_90d = COALESCE(EXCLUDED.sharpe_ratio_90d, features.sharpe_ratio_90d),
                            max_drawdown_90d = COALESCE(EXCLUDED.max_drawdown_90d, features.max_drawdown_90d),
                            revenue_growth_yoy = EXCLUDED.revenue_growth_yoy,
                            eps_growth_yoy = EXCLUDED.eps_growth_yoy,
                            return_1d = COALESCE(EXCLUDED.return_1d, features.return_1d),
                            return_7d = COALESCE(EXCLUDED.return_7d, features.return_7d),
                            return_1m = COALESCE(EXCLUDED.return_1m, features.return_1m),
                            return_3m = COALESCE(EXCLUDED.return_3m, features.return_3m),
                            return_6m = COALESCE(EXCLUDED.return_6m, features.return_6m),
                            return_1y = COALESCE(EXCLUDED.return_1y, features.return_1y),
                            return_3y = COALESCE(EXCLUDED.return_3y, features.return_3y),
                            return_max = COALESCE(EXCLUDED.return_max, features.return_max)
                    """)

                    rows_to_insert = rows_to_save

                    total_rows_inserted += rows_to_insert
                    assets_processed += 1

                    logger.info(
                        f"{asset_index}/{total_assets} | "
                        f"{ticker}: inserted/updated {rows_to_insert} feature rows."
                    )

                finally:
                    con.unregister("df_to_save")

            except Exception as e:
                assets_failed += 1
                logger.error(
                    f"{asset_index}/{total_assets} | {ticker}: failed. Error: {str(e)}"
                )
                continue

        # ======================================================
        # 5. SUMMARY
        # ======================================================

        logger.info("=" * 50)
        logger.info("FEATURE CALCULATION SUMMARY")
        logger.info(f"Assets checked:       {total_assets}")
        logger.info(f"Assets processed:     {assets_processed}")
        logger.info(f"Assets skipped:       {assets_skipped}")
        logger.info(f"Assets failed:        {assets_failed}")
        logger.info(f"Rows inserted:        {total_rows_inserted}")
        logger.info("=" * 50)

    finally:
        con.close()



### fill dividends table (11)
def fill_dividends_table(
    start_date="2000-01-01",
    batch_size=100,
    max_assets=None,
    only_ticker=None,
    progress_every=5
):
    """
    Fills the dividends table using Yahoo Finance dividend data.

    Rules:
    - Uses asset_id as the main key.
    - Uses Yahoo-compatible tickers only for download.
    - Runs in batches to support thousands of assets.
    - Incremental per asset based on the latest dividend timestamp.
    - Inserts only missing rows.
    - Does not overwrite existing rows.
    - Does not print logs per asset.
    """

    logger = logging.getLogger(__name__)
    logger.info("fill_dividends_table function was called.")

    con = duckdb.connect(
        r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb"
    )

    total_rows_inserted = 0
    batches_processed = 0
    batches_failed = 0

    try:
        logger.info("Starting dividends sync...")

        # ======================================================
        # 1. ENSURE TABLE EXISTS
        # ======================================================

        con.execute("""
            CREATE TABLE IF NOT EXISTS dividends (
                asset_id INTEGER,
                timestamp TIMESTAMP,
                dividend_amount DOUBLE,
                PRIMARY KEY (asset_id, timestamp)
            );
        """)

        # ======================================================
        # 2. LOAD ASSETS + LAST DIVIDEND DATE
        # ======================================================

        ticker_filter = ""
        params = []

        if only_ticker is not None:
            ticker_filter = "AND UPPER(a.ticker) = UPPER(?)"
            params.append(str(only_ticker).strip())

        limit_clause = ""
        if max_assets is not None:
            limit_clause = f"LIMIT {int(max_assets)}"

        assets_df = con.execute(f"""
            WITH last_dividends AS (
                SELECT
                    asset_id,
                    MAX(timestamp) AS last_dividend_date
                FROM dividends
                GROUP BY asset_id
            )

            SELECT
                a.asset_id,
                a.ticker,
                ld.last_dividend_date
            FROM assets a
            LEFT JOIN last_dividends ld
                ON a.asset_id = ld.asset_id
            WHERE
                a.ticker IS NOT NULL
                AND TRIM(a.ticker) <> ''
                {ticker_filter}
            ORDER BY a.ticker
            {limit_clause}
        """, params).df()

        if assets_df.empty:
            logger.info("No assets found for dividend sync.")
            return

        # ======================================================
        # 3. BUILD YAHOO TICKER MAPPING
        # ======================================================

        def to_yahoo_ticker(ticker):
            """
            Converts internal ticker format to Yahoo Finance ticker format.
            """
            return (
                str(ticker)
                .strip()
                .replace(".", "-")
                .replace("/", "-")
            )

        assets_df["yahoo_ticker"] = assets_df["ticker"].apply(to_yahoo_ticker)

        # Remove empty Yahoo tickers after normalization
        assets_df = assets_df[
            assets_df["yahoo_ticker"].notna()
            & (assets_df["yahoo_ticker"].str.strip() != "")
        ].copy()

        if assets_df.empty:
            logger.info("No valid Yahoo tickers found for dividend sync.")
            return

        # Handle rare duplicate Yahoo ticker mappings
        duplicate_yahoo_tickers = (
            assets_df.groupby("yahoo_ticker")["asset_id"]
            .nunique()
            .reset_index(name="asset_count")
        )

        duplicate_yahoo_tickers = duplicate_yahoo_tickers[
            duplicate_yahoo_tickers["asset_count"] > 1
        ]

        if not duplicate_yahoo_tickers.empty:
            logger.warning(
                f"Found {len(duplicate_yahoo_tickers)} duplicated Yahoo ticker mappings. "
                "Keeping the first asset_id for each Yahoo ticker."
            )

        assets_df = assets_df.drop_duplicates(
            subset=["yahoo_ticker"],
            keep="first"
        ).copy()

        total_assets = len(assets_df)
        logger.info(f"Assets to check for dividends: {total_assets}")

        # ======================================================
        # 4. PROCESS IN BATCHES
        # ======================================================

        for batch_start in range(0, total_assets, batch_size):
            batch_df = assets_df.iloc[
                batch_start: batch_start + batch_size
            ].copy()

            batch_number = (batch_start // batch_size) + 1
            total_batches = (total_assets + batch_size - 1) // batch_size

            try:
                tickers_list = batch_df["yahoo_ticker"].tolist()

                # For batch download, use the earliest needed date in the batch.
                # Later we filter per asset using its own last_dividend_date.
                batch_dates = []

                for last_date in batch_df["last_dividend_date"]:
                    if pd.isna(last_date):
                        batch_dates.append(pd.Timestamp(start_date))
                    else:
                        batch_dates.append(pd.to_datetime(last_date) + pd.Timedelta(days=1))

                batch_download_start = min(batch_dates).strftime("%Y-%m-%d")

                data = yf.download(
                    tickers=tickers_list,
                    start=batch_download_start,
                    actions=True,
                    group_by="ticker",
                    auto_adjust=False,
                    progress=False,
                    threads=True
                )

                if data.empty:
                    batches_processed += 1

                    if batch_number % progress_every == 0 or batch_number == total_batches:
                        logger.info(
                            f"Progress {batch_number}/{total_batches} batches | "
                            f"inserted={total_rows_inserted}, failed_batches={batches_failed}"
                        )

                    continue

                all_divs = []

                # ======================================================
                # 5. PROCESS EACH TICKER IN THE BATCH
                # ======================================================

                for row in batch_df.itertuples(index=False):
                    asset_id = int(row.asset_id)
                    internal_ticker = str(row.ticker).strip()
                    yahoo_ticker = str(row.yahoo_ticker).strip()
                    last_dividend_date = row.last_dividend_date

                    try:
                        if isinstance(data.columns, pd.MultiIndex):
                            available_tickers = data.columns.get_level_values(0).unique()

                            if yahoo_ticker not in available_tickers:
                                continue

                            ticker_df = data.xs(
                                yahoo_ticker,
                                axis=1,
                                level=0
                            ).copy()
                        else:
                            # This happens mostly when the batch has a single ticker.
                            ticker_df = data.copy()

                        if "Dividends" not in ticker_df.columns:
                            continue

                        ticker_divs = ticker_df["Dividends"].dropna()
                        ticker_divs = ticker_divs[ticker_divs > 0]

                        if ticker_divs.empty:
                            continue

                        ticker_divs = ticker_divs.reset_index()
                        ticker_divs.columns = ["timestamp", "dividend_amount"]

                        ticker_divs["timestamp"] = (
                            pd.to_datetime(
                                ticker_divs["timestamp"],
                                utc=True,
                                errors="coerce"
                            )
                            .dt.tz_localize(None)
                        )

                        ticker_divs["dividend_amount"] = pd.to_numeric(
                            ticker_divs["dividend_amount"],
                            errors="coerce"
                        )

                        ticker_divs = ticker_divs.dropna(
                            subset=["timestamp", "dividend_amount"]
                        )

                        ticker_divs = ticker_divs[
                            ticker_divs["dividend_amount"] > 0
                        ].copy()

                        if not pd.isna(last_dividend_date):
                            ticker_divs = ticker_divs[
                                ticker_divs["timestamp"] > pd.to_datetime(last_dividend_date)
                            ].copy()

                        if ticker_divs.empty:
                            continue

                        ticker_divs["asset_id"] = asset_id

                        all_divs.append(
                            ticker_divs[
                                ["asset_id", "timestamp", "dividend_amount"]
                            ]
                        )

                    except Exception as ticker_error:
                        logger.warning(
                            f"Skipping {internal_ticker} ({yahoo_ticker}) due to processing error: {ticker_error}"
                        )
                        continue

                # ======================================================
                # 6. INSERT ONLY MISSING ROWS
                # ======================================================

                if all_divs:
                    final_df = pd.concat(
                        all_divs,
                        ignore_index=True
                    )

                    final_df = final_df.dropna(
                        subset=["asset_id", "timestamp", "dividend_amount"]
                    )

                    final_df["asset_id"] = final_df["asset_id"].astype(int)

                    final_df = final_df.drop_duplicates(
                        subset=["asset_id", "timestamp"],
                        keep="last"
                    )

                    con.register("final_dividends_df", final_df)

                    try:
                        rows_to_insert = con.execute("""
                            SELECT COUNT(*)
                            FROM final_dividends_df s
                            LEFT JOIN dividends d
                                ON s.asset_id = d.asset_id
                               AND s.timestamp = d.timestamp
                            WHERE d.asset_id IS NULL
                        """).fetchone()[0]

                        if rows_to_insert > 0:
                            con.execute("""
                                INSERT INTO dividends (
                                    asset_id,
                                    timestamp,
                                    dividend_amount
                                )
                                SELECT
                                    s.asset_id,
                                    s.timestamp,
                                    s.dividend_amount
                                FROM final_dividends_df s
                                LEFT JOIN dividends d
                                    ON s.asset_id = d.asset_id
                                   AND s.timestamp = d.timestamp
                                WHERE d.asset_id IS NULL
                            """)

                        total_rows_inserted += rows_to_insert

                    finally:
                        con.unregister("final_dividends_df")

                batches_processed += 1

                if batch_number % progress_every == 0 or batch_number == total_batches:
                    logger.info(
                        f"Progress {batch_number}/{total_batches} batches | "
                        f"inserted={total_rows_inserted}, failed_batches={batches_failed}"
                    )

            except Exception as batch_error:
                batches_failed += 1
                logger.error(
                    f"Batch {batch_number}/{total_batches} failed. Error: {batch_error}"
                )
                continue

        # ======================================================
        # 7. SUMMARY
        # ======================================================

        logger.info("=" * 50)
        logger.info("DIVIDENDS SYNC SUMMARY")
        logger.info(f"Assets checked:      {total_assets}")
        logger.info(f"Batches processed:   {batches_processed}")
        logger.info(f"Batches failed:      {batches_failed}")
        logger.info(f"Rows inserted:       {total_rows_inserted}")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"Critical error in fill_dividends_table: {e}")

    finally:
        con.close()

def clean_suspicious_dividends(
    max_dividend_amount=100.0,
    max_dividend_to_price=0.5
):
    """
    Removes suspicious dividend rows from the dividends table.

    A dividend row is considered suspicious if:
    - dividend_amount is extremely large
    - dividend_amount is too large relative to the latest available price

    This function does not delete assets.
    It only removes suspicious dividend records.
    """

    logger = logging.getLogger(__name__)
    con = duckdb.connect(
        r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb"
    )

    logger.info("Starting suspicious dividends cleanup...")

    suspicious_count = con.execute("""
        WITH suspicious AS (
            SELECT
                d.asset_id,
                d.timestamp
            FROM dividends d
            ASOF LEFT JOIN prices p
                ON d.asset_id = p.asset_id
               AND d.timestamp >= p.timestamp
            WHERE
                   d.dividend_amount > ?
                OR (
                    p.close IS NOT NULL
                    AND p.close > 0
                    AND d.dividend_amount / p.close > ?
                )
        )

        SELECT COUNT(*)
        FROM suspicious;
    """, [
        float(max_dividend_amount),
        float(max_dividend_to_price)
    ]).fetchone()[0]

    if suspicious_count == 0:
        logger.info("No suspicious dividend rows found.")
        con.close()
        return 0

    con.execute("""
        WITH suspicious AS (
            SELECT
                d.asset_id,
                d.timestamp
            FROM dividends d
            ASOF LEFT JOIN prices p
                ON d.asset_id = p.asset_id
               AND d.timestamp >= p.timestamp
            WHERE
                   d.dividend_amount > ?
                OR (
                    p.close IS NOT NULL
                    AND p.close > 0
                    AND d.dividend_amount / p.close > ?
                )
        )

        DELETE FROM dividends
        WHERE (asset_id, timestamp) IN (
            SELECT asset_id, timestamp
            FROM suspicious
        );
    """, [
        float(max_dividend_amount),
        float(max_dividend_to_price)
    ])

    logger.warning(
        f"Removed {suspicious_count} suspicious dividend rows from dividends table."
    )
    
    con.close()

    return suspicious_count




### checking quality of data

def db_quality_check():
    con = duckdb.connect(DB_PATH)
    
    tables = [
        "assets",
        "prices",
        "fundamentals",
        "features",
        "asset_factors_raw_v1",
        "asset_factors_normalized_percentile",
        "asset_factors_normalized_zscore",
        "asset_factors_normalized_final"
    ]

    results = []

    for table in tables:

        print(f"Scanning {table}...")

        total_rows = con.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

        schema = con.execute(f"""
            SELECT
                column_name,
                data_type
            FROM information_schema.columns
            WHERE table_name = '{table}'
            ORDER BY ordinal_position
        """).fetchdf()

        for _, row in schema.iterrows():

            column = row["column_name"]
            dtype = str(row["data_type"]).upper()

            null_count = con.execute(f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE "{column}" IS NULL
            """).fetchone()[0]

            nan_count = 0

            numeric_types = [
                "DOUBLE",
                "FLOAT",
                "REAL",
                "DECIMAL"
            ]

            if any(t in dtype for t in numeric_types):

                nan_count = con.execute(f"""
                    SELECT COUNT(*)
                    FROM {table}
                    WHERE isnan("{column}")
                """).fetchone()[0]

            missing_count = null_count + nan_count

            missing_pct = (
                100 * missing_count / total_rows
                if total_rows > 0
                else 0
            )

            results.append({
                "table_name": table,
                "column_name": column,
                "data_type": dtype,
                "total_rows": total_rows,
                "null_count": null_count,
                "nan_count": nan_count,
                "missing_count": missing_count,
                "missing_pct": round(missing_pct, 4)
            })

    report_df = pd.DataFrame(results)
        
    duplicate_checks = {
    "assets": ["asset_id"],
    "prices": ["asset_id", "timestamp"],
    "fundamentals": ["asset_id", "timestamp"],
    "features": ["asset_id", "timestamp"],
    "asset_factors_raw_v1": ["asset_id", "timestamp"],
    "asset_factors_normalized_percentile": ["asset_id", "timestamp"],
    "asset_factors_normalized_zscore": ["asset_id", "timestamp"],
    "asset_factors_normalized_final": ["asset_id", "timestamp"],
    }

    duplicate_results = []

    for table, key_cols in duplicate_checks.items():
        key_expr = ", ".join([f'"{col}"' for col in key_cols])

        duplicate_count = con.execute(f"""
            SELECT COUNT(*)
            FROM (
                SELECT {key_expr}, COUNT(*) AS cnt
                FROM {table}
                GROUP BY {key_expr}
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        duplicate_results.append({
            "table_name": table,
            "key_columns": ", ".join(key_cols),
            "duplicate_key_count": duplicate_count
        })

    duplicates_df = pd.DataFrame(duplicate_results)

    report_df = report_df.sort_values(
        ["missing_pct", "table_name"],
        ascending=[False, True]
    )
    
    
    
    print("duplicated rows")
    print(duplicates_df.head(20))
    
    print("general quality")
    print(report_df.head(20))
    con.close()
    
    return report_df , duplicates_df





########### Exectute the functions ############
def daily_updates(data=True , factor=True):

    def daily_update_data():
        '''This function will execute all the necessary steps to update the database on a daily basis.'''
        fill_assets_table() # first we make sure the assets table is up to date with all the tickers we want to track.
        fill_prices_table() # then we update the prices table with the latest price data for all assets.
        fill_dividends_table() # then we update the dividends table with the latest dividend data for all assets.
        clean_suspicious_dividends() # then clean irrelevant YFINANCE buggy dividents
        fill_fundamentals_table() # then we update the fundamentals table with the latest financial data for all assets. 
        fill_fundamentals_table_from_sec() # than we compleate missing fundamentals that yahoo doesnt do well
        fill_features_table() # then we calculate the features based on the updated prices and fundamentals data, and fill the features table.
        
    def daily_update_strategy():
        '''This function will execute all the necessary steps to update the strategy related tables on a daily '''
        update_asset_factors_raw_v1() # then we update the raw factor table with the latest calculations.
        update_factors_percentile() # then we update the factors percentile table with the latest percentiles based on the updated raw factors.
        update_factors_zscore() # then we update the factors zscore table with the latest z-scores based on the updated percentiles.
        update_asset_factors_normalized_final() # then we update the final normalized factors table with the latest data from the raw, percentile, and zscore tables.
        
        
        logging.info("Data is up to date")
    if data:
        daily_update_data()
    if factor:
        daily_update_strategy()
        
    db_quality_check()


###########################
### RUN UPDATES
###########################

# daily_updates()
# db_quality_check()
# update_asset_factors_raw_v1() # then we update the raw factor table with the latest calculations.
# update_factors_percentile() # then we update the factors percentile table with the latest percentiles based on the updated raw factors.
# update_factors_zscore() # then we update the factors zscore table with the latest z-scores based on the updated percentiles.
# update_asset_factors_normalized_final() # then we update the final normalized factors table with the latest data from the raw, percentile, and zscore tables.

fill_features_table(
    fundamental_lag_days=60,
    lookback_days=1200,
    force_rebuild=True,
    rebuild_from_date="2000-01-01"
)


