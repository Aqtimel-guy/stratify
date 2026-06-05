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
from sync_local_to_parquet_gcs import export_and_upload_parquet

# Get the absolute path of the 'Code' directory (one level up from this file)
code_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if code_dir not in sys.path:
    sys.path.insert(0, code_dir)

# Now Python can find 'strategy_builder' easily without any dots
from strategy_builder.factor_formulas_raw import *
from strategy_builder.normelizing_factors import *


DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'
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


# Global logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# =========================================================================
# PIPELINE COMPONENT 1: ASSETS INGESTION
# =========================================================================

def fill_assets_table():
    """
    Fetches S&P 500 companies data from GitHub, cleans it, 
    and inserts it along with manual ETFs into the local 'assets' table.
    """
    logger = logging.getLogger(__name__)

    # --- Step 1: Scrape S&P 500 companies data from GitHub ---
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    try:
        df = pd.read_csv(url)
    except Exception as e:
        logger.error(f"Error fetching data from GitHub: {e}")
        return

    # --- Step 2: Clean and rename columns to match DB schema ---
    df_clean = df[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
    df_clean.rename(columns={
        "Symbol": "ticker", 
        "Security": "name",
        "GICS Sector": "sector", 
        "GICS Sub-Industry": "industry"
    }, inplace=True)

    # --- Step 3: Connect to DuckDB via dynamic path catalog handle ---
    print(f"Connecting to local DuckDB instance at: {DB_PATH}")
    con = duckdb.connect(DB_PATH)
    
    try:
        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")

        # Safeguard sequence management: fetch absolute max ID before inserting anything
        max_id = con.execute("SELECT COALESCE(MAX(asset_id), 0) FROM assets").fetchone()[0]
        con.execute("DROP SEQUENCE IF EXISTS asset_id_seq")
        con.execute(f"CREATE SEQUENCE asset_id_seq START WITH {max_id + 1}")
        
        # Get baseline row count
        count_before = con.execute("SELECT count(*) FROM assets").fetchone()[0]

        # --- Step 4: Register S&P 500 Equities DataFrame ---
        con.register('temp_assets_df', df_clean)

        # --- Step 5: Execute Equities Insert Query ---
        con.execute("""
            INSERT INTO assets (asset_id, ticker, name, sector, industry, is_etf)
            SELECT 
                nextval('asset_id_seq'), 
                ticker, 
                name, 
                sector, 
                industry,
                FALSE AS is_etf
            FROM temp_assets_df
            WHERE ticker NOT IN (SELECT ticker FROM assets)
        """)
        
        # --- Step 5.1: Define Specific ETFs Portfolio Framework ---
        etfs = [
            # --- Broad Market ---
            {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "sector": "Benchmark", "industry": "Broad Market"},
            {"ticker": "QQQ", "name": "Invesco QQQ Trust (Nasdaq 100)", "sector": "Benchmark", "industry": "Technology Index"},
            {"ticker": "IWM", "name": "iShares Russell 2000 ETF", "sector": "Benchmark", "industry": "Small Cap"},
            {"ticker": "DIA", "name": "SPDR Dow Jones Industrial Average", "sector": "Benchmark", "industry": "Blue Chip"},
            {"ticker": "VTI", "name": "Vanguard Total Stock Market", "sector": "Benchmark", "industry": "Total Market"},

            # --- S&P 500 Select Sector SPDRs ---
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

            # --- Thematic Tech ---
            {"ticker": "SMH", "name": "VanEck Semiconductor ETF", "sector": "Technology", "industry": "Semiconductors"},
            {"ticker": "CIBR", "name": "First Trust NASDAQ Cybersecurity", "sector": "Technology", "industry": "Cybersecurity"},
            {"ticker": "BOTZ", "name": "Global X Robotics & AI ETF", "sector": "Technology", "industry": "AI & Robotics"},
            {"ticker": "SKYY", "name": "First Trust Cloud Computing", "sector": "Technology", "industry": "Cloud Computing"},
            {"ticker": "ARKK", "name": "ARK Innovation ETF", "sector": "Technology", "industry": "Disruptive Tech"},

            # --- Digital Assets (Crypto) ---
            {"ticker": "IBIT", "name": "iShares Bitcoin Trust", "sector": "Crypto", "industry": "Bitcoin"},
            {"ticker": "ETHA", "name": "iShares Ethereum Trust", "sector": "Crypto", "industry": "Ethereum"},
            {"ticker": "BITO", "name": "ProShares Bitcoin Strategy ETF", "sector": "Crypto", "industry": "Bitcoin Futures"},
            {"ticker": "WGMI", "name": "Valkyrie Bitcoin Miners ETF", "sector": "Crypto", "industry": "Crypto Mining"},

            # --- Energy and Commodities ---
            {"ticker": "GLD", "name": "SPDR Gold Shares", "sector": "Commodities", "industry": "Gold"},
            {"ticker": "SLV", "name": "iShares Silver Trust", "sector": "Commodities", "industry": "Silver"},
            {"ticker": "USO", "name": "United States Oil Fund", "sector": "Commodities", "industry": "Crude Oil"},
            {"ticker": "UNG", "name": "United States Natural Gas Fund", "sector": "Commodities", "industry": "Natural Gas"},
            {"ticker": "ICLN", "name": "iShares Global Clean Energy", "sector": "Energy", "industry": "Renewable Energy"},
            {"ticker": "URA", "name": "Global X Uranium ETF", "sector": "Energy", "industry": "Uranium"},
            {"ticker": "COPX", "name": "Global X Copper Miners ETF", "sector": "Commodities", "industry": "Copper"},
            {"ticker": "DBA", "name": "Invesco Agriculture Fund", "sector": "Commodities", "industry": "Agriculture"},

            # --- Macro & Bonds ---
            {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond", "sector": "Bonds", "industry": "Long Term Treasuries"},
            {"ticker": "IEF", "name": "iShares 7-10 Year Treasury Bond", "sector": "Bonds", "industry": "Mid Term Treasuries"},
            {"ticker": "SHY", "name": "iShares 1-3 Year Treasury Bond", "sector": "Bonds", "industry": "Short Term Treasuries"},
            {"ticker": "TIP", "name": "iShares TIPS Bond ETF", "sector": "Bonds", "industry": "Inflation Protected"},
            {"ticker": "LQD", "name": "iShares Investment Grade Corp Bond", "sector": "Bonds", "industry": "Corporate Bonds"},

            # --- Investment Styles (Factor ETFs) ---
            {"ticker": "VUG", "name": "Vanguard Growth ETF", "sector": "Style", "industry": "Growth"},
            {"ticker": "VTV", "name": "Vanguard Value ETF", "sector": "Style", "industry": "Value"},
            {"ticker": "MTUM", "name": "iShares MSCI USA Momentum", "sector": "Style", "industry": "Momentum"},
            {"ticker": "QUAL", "name": "iShares MSCI USA Quality", "sector": "Style", "industry": "Quality"},
            {"ticker": "NOBL", "name": "ProShares Dividend Aristocrats", "sector": "Style", "industry": "Dividends"},

            # --- Worldwide Markets (Global) ---
            {"ticker": "EEM", "name": "iShares MSCI Emerging Markets", "sector": "Global", "industry": "Emerging Markets"},
            {"ticker": "VGK", "name": "Vanguard FTSE Europe ETF", "sector": "Global", "industry": "Europe"},
            {"ticker": "EWJ", "name": "iShares MSCI Japan ETF", "sector": "Global", "industry": "Japan"},
            {"ticker": "FXI", "name": "iShares China Large-Cap ETF", "sector": "Global", "industry": "China"},

            # --- Fear and Hedging (Sentiment/Inverse) ---
            {"ticker": "VIXY", "name": "ProShares VIX Short-Term Futures", "sector": "Volatility", "industry": "VIX Factor"},
            {"ticker": "SQQQ", "name": "ProShares Short QQQ (3x)", "sector": "Inverse", "industry": "Inverse Tech"},
            {"ticker": "SH", "name": "ProShares Short S&P 500", "sector": "Inverse", "industry": "Inverse Market"}
        ]

        temp_etf_df = pd.DataFrame(etfs)

        # Explicitly register ETF dataframe into connection context
        con.register('temp_etf_df', temp_etf_df)

        # Insert ETFs into assets catalog ensuring absolute uniqueness
        con.execute("""
            INSERT INTO assets (asset_id, ticker, name, sector, industry, is_etf)
            SELECT 
                nextval('asset_id_seq'), 
                ticker, 
                name, 
                sector, 
                industry,
                TRUE AS is_etf
            FROM temp_etf_df
            WHERE ticker NOT IN (SELECT ticker FROM assets)
        """)

        # --- Step 6: Telemetry Analysis ---
        count_after = con.execute("SELECT count(*) FROM assets").fetchone()[0]
        added_rows = count_after - count_before
        
        logger.info("-" * 30)
        logger.info("Database Synchronization Status:")
        logger.info(f"New structural assets added: {added_rows}")
        logger.info(f"Total functional entities in database: {count_after}")
        logger.info("-" * 30)
        
    except Exception as query_error:
        logger.error(f"Critical execution error within query block: {query_error}")
        
    finally:
        # --- Step 8: Safe Handle Closure ---
        con.close()


def fill_prices_table():
    """
    Advanced ETL for Price Data:
    - Incremental loading per asset group to optimize network traffic
    - Dynamic MultiIndex flattening safely handling yfinance structure variations
    - Ingests clean records via transactional chunk streaming
    """
    logger = logging.getLogger(__name__)
    print(f"Connecting to local DuckDB instance at: {DB_PATH}")
    con = duckdb.connect(DB_PATH)
    
    try:
        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")

        # --- Step 1: Load assets baseline data ---
        tickers_df = con.execute("""
            SELECT asset_id, ticker
            FROM assets
        """).fetchdf()

        if tickers_df.empty:
            logger.warning("No assets found in 'assets' table. Aborting price pipeline.")
            return

        tickers_df['ticker_yf'] = tickers_df['ticker'].str.strip().str.replace(".", "-", regex=False)

        # --- Step 2: Extract latest stored telemetry dates per asset ---
        last_dates = con.execute("""
            SELECT asset_id, MAX(timestamp) AS last_timestamp
            FROM prices
            GROUP BY asset_id
        """).fetchdf()

        tickers_df = tickers_df.merge(last_dates, on="asset_id", how="left")
        
        # Explicitly fallback missing data assets to benchmark epoch (year 2000)
        default_start = pd.Timestamp("2000-01-01")
        tickers_df['last_timestamp'] = tickers_df['last_timestamp'].fillna(default_start)
        tickers_df['last_timestamp'] = pd.to_datetime(tickers_df['last_timestamp']).dt.date

        # CRITICAL FIX: Segment tickers to prevent single outdated ticker from forcing 
        # a massive global re-download of the entire S&P 500 matrix history.
        today_date = datetime.utcnow().date()
        tickers_df['days_outdated'] = tickers_df['last_timestamp'].apply(lambda x: (today_date - x).days)
        
        # Filter assets that actually require data refresh processing
        active_targets = tickers_df[tickers_df['days_outdated'] > 1].copy()
        
        if active_targets.empty:
            logger.info("All local market asset vector price tracks are already up to date.")
            return

        # Determine the boundaries based on target assets requirements
        overall_min_date = active_targets['last_timestamp'].min()
        fetch_start = (overall_min_date + timedelta(days=1)).strftime('%Y-%m-%d')
        end_date = (today_date + timedelta(days=1)).strftime('%Y-%m-%d')

        ticker_list = active_targets['ticker_yf'].tolist()
        logger.info(f"Downloading data snapshot for {len(ticker_list)} assets from {fetch_start} to {end_date}")

        # --- Step 3: Executing Network Batch Download Handling Retries ---
        raw_data = None
        for attempt in range(3):
            try:
                raw_data = yf.download(
                    ticker_list,
                    start=fetch_start,
                    end=end_date,
                    interval="1d",
                    group_by='ticker',
                    auto_adjust=False,
                    threads=True
                )
                if not raw_data.empty:
                    break
            except Exception as download_error:
                logger.warning(f"Network processing failed (Attempt {attempt+1}/3): {download_error}")
                time.sleep(3)

        if raw_data is None or raw_data.empty:
            logger.warning("Zero records received from structural data vendor API.")
            return

        # --- Step 4: Robust DataFrame MultiIndex Flattening Engine ---
        if isinstance(raw_data.columns, pd.MultiIndex):
            # Stack structural layers shifting tickers back to regular rows representation safely
            data = raw_data.stack(level=0, future_stack=True).reset_index()
            
            # Map structural columns variations applied dynamically by vendor engine
            possible_ticker_cols = ['level_1', 'Ticker', 'ticker', 'tickers']
            found_col = next((c for c in possible_ticker_cols if c in data.columns), None)
            
            if found_col:
                data.rename(columns={found_col: 'ticker_yf'}, inplace=True)
            else:
                # If column hidden within current index state, reset structure manually
                if data.index.name in possible_ticker_cols:
                    data = data.reset_index()
                    data.rename(columns={data.columns[0]: 'ticker_yf'}, inplace=True)
                else:
                    logger.error(f"Structural layout mismatch: Unable to identify ticker column mapping out of: {data.columns}")
                    return
        else:
            # Handle isolated fallback single element data structures
            data = raw_data.reset_index()
            data['ticker_yf'] = ticker_list[0]

        # --- Step 5: Normalize Schema Layout ---
        data.rename(columns={
            'Date': 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Adj Close': 'adj_close',
            'Volume': 'volume'
        }, inplace=True)

        data['timestamp'] = pd.to_datetime(data['timestamp']).dt.date

        # --- Step 6: Map to Relational Primary Key System ---
        data = data.merge(
            active_targets[['asset_id', 'ticker_yf', 'last_timestamp']],
            on='ticker_yf',
            how='inner'
        )

        # --- Step 7: Incremental Isolation Filter Guard ---
        data = data[data['timestamp'] > data['last_timestamp']]

        if data.empty:
            logger.info("Zero incremental delta changes detected following frame filtering operations.")
            return

        # --- Step 8: Cleanse Ingested Assets ---
        data.dropna(subset=['close'], inplace=True)
        data.drop_duplicates(subset=['asset_id', 'timestamp'], inplace=True)

        final_cols = ['asset_id', 'timestamp', 'open', 'high', 'low', 'close', 'adj_close', 'volume']
        data = data[final_cols]

        logger.info(f"Streaming {len(data)} normalized market matrix records to local architecture...")

        # --- Step 9: Transactional Chunk Isolation Stream Ingestion ---
        chunk_size = 100_000
        for i in range(0, len(data), chunk_size):
            chunk = data.iloc[i:i+chunk_size]
            con.register("temp_chunk", chunk)

            con.execute("""
                INSERT INTO prices (asset_id, timestamp, open, high, low, close, adj_close, volume)
                SELECT asset_id, timestamp, open, high, low, close, adj_close, volume FROM temp_chunk
                ON CONFLICT (asset_id, timestamp) DO NOTHING
            """)

        logger.info("✅ Prices catalog tracking sequence updated successfully.")

    except Exception as pipeline_failure:
        logger.error(f"Critical execution error tracking within active historical data processor: {pipeline_failure}")
        
    finally:
        con.close()
### fill fundamentals table (3)

def fill_fundamentals_table(test_only=False, force_refresh=False):
    
    
    db_path = r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb"
    con = duckdb.connect(db_path)
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    # 1. Identify assets
    # If force_refresh is True, we take ALL assets. 
    # If False, only those older than 90 days.
    if force_refresh:
        query = "SELECT asset_id, ticker, NULL as last_fund FROM assets"
    else:
        threshold_date = (datetime.today() - timedelta(days=90)).date()
        query = f"""
            SELECT a.asset_id, a.ticker, MAX(f.timestamp) as last_fund
            FROM assets a
            LEFT JOIN fundamentals f ON a.asset_id = f.asset_id
            GROUP BY a.asset_id, a.ticker
            HAVING last_fund IS NULL OR last_fund < '{threshold_date}'
        """
    
    assets_to_update = con.execute(query).fetchdf()

    # 2. Test Mode Override
    if test_only:
        logging.info("🛠️ TEST MODE: Focusing on AAPL.")
        assets_to_update = assets_to_update[assets_to_update['ticker'] == 'AAPL']

    if assets_to_update.empty:
        logging.info("No assets to update.")
        con.close()
        return

    logging.info(f"Fundamentals: Processing {len(assets_to_update)} tickers...")

    for row in assets_to_update.itertuples(index=False):
        asset_id, ticker_str = row.asset_id, row.ticker.strip().replace(".", "-")
        # If we are in test mode OR force_refresh, we ignore the last_fund filter
        last_fund = row.last_fund if not (test_only or force_refresh) else None
        
        yt = yf.Ticker(ticker_str)
        q_fin = pd.DataFrame()
        
        for attempt in range(3):
            try:
                q_fin = yt.quarterly_financials.T
                f_info = yt.fast_info
                shares = getattr(f_info, 'shares_outstanding', None)
                if not shares:
                    shares = yt.info.get('sharesOutstanding')
                mkt_cap = getattr(f_info, 'market_cap', None)
                
                if not q_fin.empty: break
            except Exception as e:
                logging.warning(f"{ticker_str} attempt {attempt+1} failed: {e}")
                time.sleep(0.5)

        if q_fin.empty:
            continue

        try:
            # Step 3: Transformation
            q_fin = q_fin.reset_index().rename(columns={'index': 'timestamp'})
            q_fin['timestamp'] = pd.to_datetime(q_fin['timestamp']).dt.date
            q_fin['asset_id'] = asset_id

            # Mapping Revenue & Income
            revenue_names = ['Total Revenue', 'TotalRevenue', 'Operating Revenue', 'Revenue']
            q_fin['revenue'] = None
            for name in revenue_names:
                if name in q_fin.columns:
                    q_fin['revenue'] = q_fin[name]
                    break

            income_names = ['Net Income', 'NetIncome', 'Net Income Common Stockholders', 'Net Income From Continuing Operation Net Minority Interest']
            net_income = None
            for name in income_names:
                if name in q_fin.columns:
                    net_income = q_fin[name]
                    break

            # EPS Calculation
            if net_income is not None and shares:
                q_fin['eps'] = net_income / shares
            else:
                q_fin['eps'] = q_fin.get('Basic EPS', q_fin.get('Diluted EPS', None))
            
            q_fin['shares_outstanding'] = shares
            q_fin['market_cap'] = mkt_cap
            q_fin['pe_ratio'] = None 

            # Step 4: Incremental Filter
            if last_fund:
                last_date = pd.to_datetime(last_fund).date()
                q_fin = q_fin[q_fin['timestamp'] > last_date]

            if q_fin.empty:
                # הוספתי לוג קטן כדי שנבין למה הוא מדלג
                logging.info(f"ℹ️ {ticker_str}: All fetched quarters already exist in DB.")
                continue

            # Step 5: Clean and Cast
            final_cols = ['asset_id', 'timestamp', 'pe_ratio', 'market_cap', 'revenue', 'eps', 'shares_outstanding']
            for col in final_cols:
                if col not in q_fin.columns: q_fin[col] = None
            
            final_df = q_fin[final_cols].copy()
            numeric_cols = ['pe_ratio', 'market_cap', 'revenue', 'eps', 'shares_outstanding']
            for col in numeric_cols:
                final_df[col] = pd.to_numeric(final_df[col], errors='coerce')

            # Step 6: Ingestion
            con.register("temp_df", final_df)
            con.execute("INSERT INTO fundamentals SELECT * FROM temp_df ON CONFLICT DO NOTHING")
            con.unregister("temp_df")
            
            logging.info(f"✅ {ticker_str}: Inserted {len(final_df)} rows.")

        except Exception as e:
            logging.error(f"💥 Error processing {ticker_str}: {e}")

    con.close()
    logging.info("🏁 Task Finished.")

### fill features table (4)
def fill_features_table(test_only=False, force_refresh=False):
    """
    This function will compute and fill the 'features' table based on the 'prices' and 'fundamentals' tables.
    The implementation will depend on the specific features we want to calculate
    """
    # connect to duckdb
    con = duckdb.connect(r"C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb")
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    logger = logging.getLogger(__name__)

    ### --- step 1:setting the date range ---
    last_date = con.execute("SELECT MAX(timestamp) FROM features").fetchone()[0]
    
    if force_refresh or last_date is None:
        # if it's the first run or we want to refresh everything, we start from the earliest date possible
        logger.info("Starting full features refresh...")
        con.execute("DELETE FROM features") # if forced refresh, we clear the table first to avoid duplicates
        insert_start_date = "1900-01-01"
        fetch_start_date = "1900-01-01"
    else:
        # otherwise, we only calculate features for new data since the last date in the features table
        insert_start_date = last_date
        # we need 1y of price data to calculate features, so we fetch from 1 year before the last date in features
        fetch_start_date = (last_date - pd.Timedelta(days=365)).strftime('%Y-%m-%d')
        logger.info(f"Updating features since {insert_start_date} (fetching data from {fetch_start_date})")
        
        
### --- step 2: Fetching SPY data ---
    spy_id = con.execute("SELECT asset_id FROM assets WHERE ticker = 'SPY'").fetchone()[0]
    spy_df = con.execute(f"""
        SELECT timestamp, close 
        FROM prices 
        WHERE asset_id = {spy_id} AND timestamp >= '{fetch_start_date}'
        ORDER BY timestamp
    """).df().rename(columns={'close': 'spy_close'})
    
    # Calculate returns for SPY
    spy_df['spy_ret_1y'] = spy_df['spy_close'].pct_change(252)
    spy_df['spy_ret_1d'] = spy_df['spy_close'].pct_change(1) # Important for Beta
    
    # Keep only what we need for the merge
    spy_df = spy_df[['timestamp', 'spy_ret_1y', 'spy_ret_1d']] 
    
    
    ### --- step 3: Fetching assets to process ---

    assets = con.execute("SELECT asset_id, ticker FROM assets").fetchall()
    if test_only:
        assets = [(2 , 'AAPL')] # testing only over AAPL
        logger.info(f"Test mode: processing only AAPL (asset_id=2)")
        
    # counters for logging    
    total_rows_inserted = 0
    assets_processed = 0
    assets_skipped = 0
    assets_failed = 0

    for asset_id, ticker in assets:
        try:
            # fetch data for the asset starting from fetch_start_date
            df = con.execute(f"""
                SELECT 
                    p.asset_id, 
                    p.timestamp, 
                    p.open, p.high, p.low, p.close, p.volume,
                    f.pe_ratio, 
                    f.market_cap, 
                    f.revenue, 
                    f.eps, 
                    f.shares_outstanding
                FROM prices p
                ASOF LEFT JOIN fundamentals f 
                -- ASOF JOIN to get the most recent fundamental data for each price date
                    ON p.asset_id = f.asset_id 
                    AND p.timestamp >= f.timestamp
                WHERE p.asset_id = {asset_id} 
                AND p.timestamp >= '{fetch_start_date}'
                ORDER BY p.timestamp
            """).df()


            if df.empty or len(df) < 21: # we need at least 21 days of data to calculate the 1m return and SMA50, so if we have less than that, we skip this asset for now
                logger.warning(f"Not enough price data for {ticker} (asset_id={asset_id}) to calculate features. Skipping.")
                continue

    ### --- step 4: calculate features ---
            
            # 1. Basic Returns
            df['return_1d'] = df['close'].pct_change(1)
            df['return_7d'] = df['close'].pct_change(7)
            df['return_1m'] = df['close'].pct_change(21)
            df['return_3m'] = df['close'].pct_change(63)
            df['return_6m'] = df['close'].pct_change(126)
            df['return_1y'] = df['close'].pct_change(252)
            df['return_3y'] = df['close'].pct_change(252 * 3)
            df['return_max'] = (df['close'] / df['close'].iloc[0]) - 1

            # 2. Moving Averages & Distances
            df['sma50'] = df['close'].rolling(50).mean()
            df['sma200'] = df['close'].rolling(200).mean()
            df['dist_sma50'] = (df['close'] - df['sma50']) / df['sma50']
            df['dist_sma200'] = (df['close'] - df['sma200']) / df['sma200']

            # 3. Volatility & Volume
            df['volatility'] = df['return_1d'].rolling(21).std() * (252**0.5)
            df['avg_volume'] = df['volume'].rolling(20).mean()
            df['volume_spike'] = df['volume'] / df['avg_volume']

            # 4. Technical Indicators (Manual)
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
            df['rsi_14'] = 100 - (100 / (1 + (gain / loss)))
            
            tr = pd.concat([
                (df['high'] - df['low']),
                (df['high'] - df['close'].shift()).abs(),
                (df['low'] - df['close'].shift()).abs()
            ], axis=1).max(axis=1)
            df['atr_14'] = tr.rolling(window=14).mean()

            # 5. Risk & Market Metrics
            # Max Drawdown (90d)
            rolling_max = df['close'].rolling(window=90, min_periods=1).max()
            df['max_drawdown_90d'] = (df['close'] / rolling_max) - 1.0
            
            # Sharpe Ratio (90d)
            r_mean = df['return_1d'].rolling(90).mean()
            r_std = df['return_1d'].rolling(90).std()
            df['sharpe_ratio_90d'] = (r_mean / r_std) * (252**0.5)

            # SPY Relative Momentum & Beta
            if 'spy_ret_1d' not in spy_df.columns:
                spy_df['spy_ret_1d'] = spy_df['spy_close'].pct_change(1)
            
            df = df.merge(spy_df, on='timestamp', how='left')
            df['momentum_relative_sp_1y'] = df['return_1y'] - df['spy_ret_1y']
            
            # Beta 90d
            cov_90 = df['return_1d'].rolling(90).cov(df['spy_ret_1d'])
            var_90 = df['spy_ret_1d'].rolling(90).var()
            df['beta_90d'] = cov_90 / var_90

            # 6. Fundamental Derived Features
            # Fill gaps in fundamental data (reports are quarterly)
            df[['revenue', 'eps']] = df[['revenue', 'eps']].ffill()
            df['revenue_growth_yoy'] = df['revenue'].pct_change(252)
            df['eps_growth_yoy'] = df['eps'].pct_change(252)

            # 7. Final Clean-up for Database
            df = df.replace([float('inf'), float('-inf')], pd.NA)
            
            

    ### --- step 5: data injection ---
            
            # 1. Exact column list to match your CREATE TABLE schema
            features_columns = [
                'asset_id', 'timestamp', 'volatility', 'momentum_relative_sp_1y',
                'avg_volume', 'rsi_14', 'beta_90d', 'dist_sma50', 'dist_sma200',
                'sharpe_ratio_90d', 'max_drawdown_90d', 'volume_spike', 'atr_14',
                'revenue_growth_yoy', 'eps_growth_yoy',
                'return_1d', 'return_7d', 'return_1m', 'return_3m', 
                'return_6m', 'return_1y', 'return_3y', 'return_max'
            ]

            # 2. Filter for new data rows only
            insert_mask = df['timestamp'] > pd.Timestamp(insert_start_date)
            df_to_save = df.loc[insert_mask, features_columns].copy()

            if not df_to_save.empty:
                # 3. Final drop of rows with missing IDs or Timestamps
                df_to_save = df_to_save.dropna(subset=['asset_id', 'timestamp'])
                
                # 4. Inject into DuckDB
                con.execute("INSERT INTO features SELECT * FROM df_to_save")
                
                # 5. Update global counters for the final log
                rows_count = len(df_to_save)
                total_rows_inserted += rows_count
                assets_processed += 1
                
                logger.info(f"Successfully injected {rows_count} new features for {ticker}")
            else:
                assets_skipped += 1
                logger.info(f"No new records to add for {ticker}")

        except Exception as e:
            logger.error(f"Error processing {ticker}: {str(e)}")
            assets_failed += 1
            continue
    ### --- step 6: process summary  and closing connection ---
    
    logger.info("="*40)
    logger.info("FEATURE CALCULATION SUMMARY")
    logger.info(f"Total Assets Processed:  {assets_processed}")
    logger.info(f"Total Assets Skipped:    {assets_skipped}")
    logger.info(f"Total Assets Failed:     {assets_failed}")
    logger.info(f"Total New Rows Inserted: {total_rows_inserted}")
    logger.info("="*40)
    logger.info(f"\n🚀 Process Finished!")
    logger.info(f"Added {total_rows_inserted} records to 'features' table.")
    logger.info(f"Check logs for details on {assets_failed} failed assets.")
    
    con.close()

### fill dividends table (11)
def fill_dividends_table():
    """
    This function will fill the 'dividends' table by downloading dividend data from Yahoo Finance for all assets in the 'assets' table.
    It will use a smart mapping of tickers to asset IDs, batch downloading for efficiency, and robust processing to handle different - 
    data formats and potential issues with the Yahoo Finance API.

    """
    # Set up logging and database connection
    
    logger = logging.getLogger(__name__)
    con = duckdb.connect(r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb")
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    try:
        # --- first step: build a smart mapping of tickers to asset IDs ---

        asset_list = con.execute("SELECT asset_id, ticker FROM assets").fetchall()
        
        ticker_to_id = {}
        expanded_tickers = set() # a list to hold all the ticker variations we want to download from Yahoo (with dots, with dashes, etc.)
        for aid, ticker in asset_list:
            # 1. for processing the data after download, we want to have a mapping of all possible ticker variations to the correct asset_id, so we can easily assign dividends to the right asset
            ticker_to_id[ticker] = aid
            ticker_to_id[ticker.replace('.', '-')] = aid
            ticker_to_id[ticker.replace('-', '.')] = aid
            
            # 2. add to the download list (for Yahoo)
            expanded_tickers.add(ticker)
            expanded_tickers.add(ticker.replace('.', '-'))
            expanded_tickers.add(ticker.replace('-', '.'))
            
        tickers_list = list(expanded_tickers)
        
        if not tickers_list:
            logger.debug("No tickers found in assets table.")
            return
        
        # --- second step: batch download dividends data for all tickers ---

        logger.info(f" Downloading dividends for {len(tickers_list)} assets...")
        # actions=True to get dividends and splits, group_by='ticker' to get a MultiIndex DataFrame with tickers as the top level of columns
        data = yf.download(tickers_list, start="2000-01-01", actions=True, group_by='ticker', progress=True)

        if data.empty:
            logger.error("No data downloaded from Yahoo Finance.")
            return

        all_divs = []
    
        
        # --- third step: process data for each ticker ---
        for ticker in tickers_list:
            try:
                # failsafe to get the correct DataFrame for the ticker, whether it's a MultiIndex (batch) or single ticker download
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker not in data.columns.levels[0]:
                        logger.warning(f"Ticker {ticker} not found in downloaded data columns. Skipping.")
                        continue
                    ticker_df = data.xs(ticker, axis=1, level=0)
                else:
                    ticker_df = data 
                
                # making sure we have a 'Dividends' column to work with, if not, we skip this ticker
                if 'Dividends' not in ticker_df.columns:
                    logger.warning(f"No 'Dividends' column for {ticker}. Skipping.")
                    continue
                
                # filtering only the dividend rows where the amount is greater than 0, and resetting index to get 'timestamp' as a column
                ticker_divs = ticker_df['Dividends'].dropna()
                ticker_divs = ticker_divs[ticker_divs > 0].reset_index()
                
                if not ticker_divs.empty:
                    ticker_divs.columns = ['timestamp', 'dividend_amount']
                    
                    # Yahoo Finance sometimes returns timestamps with timezone info, we need to remove it to match our DB schema (which is timezone-naive)
                    ticker_divs['timestamp'] = pd.to_datetime(ticker_divs['timestamp']).dt.tz_localize(None)
                    
                    # getting the asset_id for the current ticker using our mapping, if it's not found, we skip this ticker
                    current_id = ticker_to_id.get(ticker)
                    
                    if current_id is not None:
                        ticker_divs['asset_id'] = current_id
                        # arranging columns in the order of the DB table
                        all_divs.append(ticker_divs[['asset_id', 'timestamp', 'dividend_amount']])
                    
            except Exception as e:
                logger.debug(f"Skipping {ticker} due to processing error: {e}")

        # --- 4th step: bulk insert ---
        if all_divs:
            final_df = pd.concat(all_divs).dropna(subset=['asset_id', 'timestamp', 'dividend_amount'])
            final_df = final_df.drop_duplicates(subset=['asset_id', 'timestamp'])
            con.execute("INSERT OR IGNORE INTO dividends SELECT * FROM final_df")
            logger.info(f"✅ Successfully synced {len(final_df)} dividend records to the database.")
        else:
            logger.info("No new dividend data to insert.")

    except Exception as e:
        logger.error(f"Critical error in fill_dividends_table: {e}")
    finally:
        con.close()





##############################################################################
def fill_fundamentals_table_v2(test_only=False, force_refresh=False):
    """
    Robust Fundamentals ETL (Production Grade)

    Features:
    - Incremental loading
    - Reporting lag (no lookahead bias)
    - Retry logic for API
    - Robust column mapping
    - Partial data tolerance
    """

    db_path = r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb"
    logger = logging.getLogger(__name__)

    REPORTING_LAG_DAYS = 2
    EPSILON = 1e-6

    with duckdb.connect(db_path) as con:

        # -----------------------
        # 1. Select assets
        # -----------------------
        if force_refresh:
            query = "SELECT asset_id, ticker, NULL as last_fund FROM assets WHERE is_etf = FALSE"
        else:
            threshold_date = (datetime.today() - timedelta(days=60)).date()

            query = f"""
                SELECT a.asset_id, a.ticker, MAX(f.timestamp) as last_fund
                FROM assets a
                LEFT JOIN fundamentals f ON a.asset_id = f.asset_id
                WHERE a.is_etf = FALSE
                GROUP BY a.asset_id, a.ticker
                HAVING last_fund IS NULL OR last_fund < '{threshold_date}'
            """

        assets = con.execute(query).fetchdf()

        if test_only:
            assets = assets[assets["ticker"] == "AAPL"]
            logger.info("TEST MODE: AAPL only")

        if assets.empty:
            logger.info("No assets to update.")
            return

        # -----------------------
        # 2. Loop assets
        # -----------------------
        for row in assets.itertuples(index=False):

            asset_id = row.asset_id
            ticker = row.ticker.replace(".", "-")
            last_fund = row.last_fund

            yt = yf.Ticker(ticker)

            q_fin = pd.DataFrame()
            shares = None

            # -----------------------
            # Retry logic
            # -----------------------
            for attempt in range(3):
                try:
                    q_fin = yt.quarterly_financials.T

                    # Shares outstanding
                    shares = getattr(yt.fast_info, "shares_outstanding", None)
                    if not shares:
                        shares = yt.info.get("sharesOutstanding")

                    if not q_fin.empty:
                        break

                except Exception as e:
                    logger.warning(f"{ticker} attempt {attempt+1} failed: {e}")
                    time.sleep(1)

            if q_fin.empty:
                logger.warning(f"No data for {ticker}")
                continue

            try:
                # -----------------------
                # 3. Transform
                # -----------------------
                q_fin = q_fin.reset_index().rename(columns={"index": "timestamp"})
                q_fin["timestamp"] = pd.to_datetime(q_fin["timestamp"])

                # Reporting lag
                q_fin["timestamp"] = (
                    q_fin["timestamp"] + pd.Timedelta(days=REPORTING_LAG_DAYS)
                ).dt.date

                q_fin["asset_id"] = asset_id

                # -----------------------
                # Revenue mapping
                # -----------------------
                revenue_cols = [
                    "Total Revenue",
                    "TotalRevenue",
                    "Operating Revenue",
                    "Revenue"
                ]

                q_fin["revenue"] = None
                for col in revenue_cols:
                    if col in q_fin.columns:
                        q_fin["revenue"] = q_fin[col]
                        break

                # -----------------------
                # Net income mapping
                # -----------------------
                income_cols = [
                    "Net Income",
                    "NetIncome",
                    "Net Income Common Stockholders"
                ]

                net_income = None
                for col in income_cols:
                    if col in q_fin.columns:
                        net_income = q_fin[col]
                        break

                # -----------------------
                # EPS calculation
                # -----------------------
                if "Diluted EPS" in q_fin.columns:
                    q_fin["eps"] = q_fin["Diluted EPS"]
                elif "Basic EPS" in q_fin.columns:
                    q_fin["eps"] = q_fin["Basic EPS"]
                elif net_income is not None and shares:
                    q_fin["eps"] = net_income / shares
                else:
                    q_fin["eps"] = None

                q_fin["shares_outstanding"] = shares

                # -----------------------
                # 4. Incremental filtering
                # -----------------------
                if last_fund and not force_refresh:
                    last_date = pd.to_datetime(last_fund).date()
                    q_fin = q_fin[q_fin["timestamp"] > last_date]

                if q_fin.empty:
                    continue

                # -----------------------
                # 5. Cleaning
                # -----------------------
                final_cols = [
                    "asset_id",
                    "timestamp",
                    "revenue",
                    "eps",
                    "shares_outstanding"
                ]

                final_df = q_fin[final_cols].copy()

                # numeric cast
                for col in ["revenue", "eps", "shares_outstanding"]:
                    final_df[col] = pd.to_numeric(final_df[col], errors="coerce")

                # clean invalid values
                final_df["revenue"] = final_df["revenue"].clip(lower=EPSILON)
                final_df.loc[~np.isfinite(final_df["eps"]), "eps"] = np.nan

                final_df = final_df.dropna(subset=["timestamp"])

                final_df = final_df.sort_values("timestamp").drop_duplicates(
                    subset=["asset_id", "timestamp"], keep="last"
                )

                if final_df.empty:
                    continue

                # -----------------------
                # 6. Insert
                # -----------------------
                con.register("temp_fund", final_df)

                con.execute("""
                    INSERT INTO fundamentals
                    SELECT * FROM temp_fund
                    ON CONFLICT (asset_id, timestamp) DO NOTHING
                """)

                logger.info(f"✅ {ticker}: {len(final_df)} rows inserted")

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"{ticker} processing failed: {e}")

    logger.info("🏁 Fundamentals ETL completed.")
    



########### Exectute the functions ############

def daily_update_data(test_only=False, force_refresh=False):
    '''This function will execute all the necessary steps to update the database on a daily basis.'''
    fill_assets_table() # first we make sure the assets table is up to date with all the tickers we want to track.
    fill_prices_table() # then we update the prices table with the latest price data for all assets.
    fill_dividends_table() # then we update the dividends table with the latest dividend data for all assets.
    # fill_fundamentals_table(test_only=test_only, force_refresh=True) # then we update the fundamentals table with the latest financial data for all assets. 
    fill_features_table(test_only=test_only, force_refresh=force_refresh) # then we calculate the features based on the updated prices and fundamentals data, and fill the features table.
    
def daily_update_strategy():
    '''This function will execute all the necessary steps to update the strategy related tables on a daily '''
    update_asset_factors_raw_v1() # then we update the raw factor table with the latest calculations.
    update_factors_percentile() # then we update the factors percentile table with the latest percentiles based on the updated raw factors.
    update_factors_zscore() # then we update the factors zscore table with the latest z-scores based on the updated percentiles.
    update_asset_factors_normelized_final() # then we update the final normalized factors table with the latest data from the raw, percentile, and zscore tables.
    
    
    logging.info("Data is up to date")



def master_daily_update(test_only=False, force_refresh=False):
    '''This function will execute the entire daily update process, including data updates and cloud uploads.'''
    daily_update_data(test_only=test_only, force_refresh=force_refresh)
    daily_update_strategy()
    export_and_upload_parquet() # then we export the updated tables to parquet files and upload them to S3 for use in the backtesting and live trading environments."
    
###########################

master_daily_update(test_only=False, force_refresh=False)
