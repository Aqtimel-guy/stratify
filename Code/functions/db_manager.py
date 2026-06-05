import duckdb
import streamlit as st
import logging
import time
import pandas as pd
from sqlalchemy import create_engine , text
import duckdb
import fsspec

DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'


# for LOCAL & STORAGE CONNECTION (DuckDB + Google Cloud Storage) 
def get_local_db_connection():
    """
    Initializes and returns a unified DuckDB connection inside session state,
    automatically registered with the GCS file system for remote Parquet reading.
    """
    # FIX: Standardized connection key name to 'duckdb_con' across the app
    if 'duckdb_con' not in st.session_state:
        db_path = st.secrets.get("LOCAL_DB_PATH", "stratify.db")
        con = duckdb.connect(db_path)
        
        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")
        
        try:
            con.register_filesystem(fsspec.filesystem('gcs'))
        except Exception:
            pass
            
        st.session_state.duckdb_con = con
        
    return st.session_state.duckdb_con


# for SUPABASE CONNECTION 
def get_supabase_engine():
    """
    Returns a persistent SQLAlchemy engine for cloud database operations.
    Leverages Supabase Connection Pooler to maintain stable remote connections.
    """
    if 'supabase_engine' not in st.session_state:
        db_password = st.secrets["database"]["password"]
        db_user = "postgres.nbmxcagcaftevvsplsxj"
        db_host = "aws-1-eu-central-1.pooler.supabase.com"
        db_port = 6543
        db_name = "postgres"
        connection_string = f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        
        # pool_pre_ping checks connection liveness before executing queries
        st.session_state.supabase_engine = create_engine(
            connection_string, 
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        
    return st.session_state.supabase_engine

# for data fetching
def get_data(query, params=None, use_cloud=False):
    """
    Unified data fetching interface.
    Routes queries to Supabase (PostgreSQL) if use_cloud is True, 
    otherwise routes to the local DuckDB instance.
    """
    # ---- OPTION A: Cloud Database Execution (Supabase) ----
    if use_cloud:
        engine = get_supabase_engine()
        
        # PostgreSQL syntax utilizes %s for positional parameters instead of ?
        cloud_query = query.replace('?', '%s')
        
        if params is not None:
            if isinstance(params, list):
                params = tuple(params)
            elif not isinstance(params, (tuple, dict)):
                params = (params,)
        
        # Explicitly wrap query in text() to ensure SQLAlchemy compatibility
        with engine.connect() as connection:
            return pd.read_sql(text(cloud_query), con=connection, params=params)

    # ---- OPTION B: Local Database Execution (DuckDB) ----
    # Standardized fallback checking the correct session key
    con = st.session_state.get('duckdb_con')
    
    if con:
        if params:
            return con.execute(query, params).df()
        return con.execute(query).df()
    
    # Emergency fallback if connection was not initialized in session state
    db_path = st.secrets.get("LOCAL_DB_PATH", "stratify.db")
    with duckdb.connect(db_path) as emergency_con:
        if params:
            return emergency_con.execute(query, params).df()
        return emergency_con.execute(query).df()
    

# for getting assets details 
def get_asset_snapshot(con, ticker, sim_date, use_cloud=False):
    """
    Fetches comprehensive info about a specific asset as of the simulation date.
    Optimized for remote server infrastructure to prevent massive network overhead
    by migrating from full file downloads to targeted SQL database queries.
    """
    ticker_upper = ticker.upper()
    df_asset = pd.DataFrame()
    
    # 1. Asset Metadata Layer
    if use_cloud:
        try:
            # OPTIMIZED: Querying remote Supabase directly instead of reading heavy static assets Parquet
            query_asset = "SELECT asset_id, ticker, name, sector, industry FROM assets WHERE ticker = ?"
            df_asset = get_data(query_asset, [ticker_upper], use_cloud=True)
        except Exception as cloud_err:
            st.sidebar.warning(f"Cloud assets sync failed: {cloud_err}. Shifting to local engine.")
            use_cloud = False

    # Local fallback for asset metadata
    if not use_cloud or df_asset.empty:
        try:
            table_check = con.execute("SELECT table_name FROM information_schema.tables WHERE table_name = 'assets'").df()
            if not table_check.empty:
                query_asset = "SELECT asset_id, ticker, name, sector, industry FROM assets WHERE ticker = ?"
                df_asset = con.execute(query_asset, [ticker_upper]).df()
            else:
                st.sidebar.error("Database catalog mismatch: Table 'assets' is missing locally.")
                return None
        except Exception:
            return None
        
    if df_asset.empty:
        return None

    # Extract foundational structural components
    asset_id = int(df_asset.iloc[0]['asset_id'])
    ticker_name = df_asset.iloc[0]['ticker']
    name = df_asset.iloc[0]['name']
    sector = df_asset.iloc[0]['sector']
    industry = df_asset.iloc[0]['industry']

    current_price = None
    first_trade_date = None

    # 2. Pricing Matrix Layer
    if use_cloud:
        try:
            # OPTIMIZED: Pulling only the specific asset's target price row via remote database engine
            query_price = "SELECT close FROM prices WHERE asset_id = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1"
            df_price = get_data(query_price, [asset_id, sim_date], use_cloud=True)
            current_price = df_price.iloc[0]['close'] if not df_price.empty else None

            # OPTIMIZED: Calculating aggregate min timestamp directly on cloud server
            query_first_date = "SELECT MIN(timestamp) as min_ts FROM prices WHERE asset_id = ?"
            df_first_date = get_data(query_first_date, [asset_id], use_cloud=True)
            first_trade_date = df_first_date.iloc[0]['min_ts'] if not df_first_date.empty else None
        except Exception as price_cloud_err:
            st.sidebar.error(f"Cloud pricing matrix processing dropped: {price_cloud_err}")
            use_cloud = False

    # Local fallback for pricing matrix
    if not use_cloud:
        try:
            table_check_prices = con.execute("SELECT table_name FROM information_schema.tables WHERE table_name = 'prices'").df()
            if not table_check_prices.empty:
                query_price = "SELECT close FROM prices WHERE asset_id = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1"
                df_price = con.execute(query_price, [asset_id, sim_date]).df()
                current_price = df_price.iloc[0]['close'] if not df_price.empty else None

                query_first_date = "SELECT MIN(timestamp) as min_ts FROM prices WHERE asset_id = ?"
                df_first_date = con.execute(query_first_date, [asset_id]).df()
                first_trade_date = df_first_date.iloc[0]['min_ts'] if not df_first_date.empty else None
        except Exception:
            pass

    # 3. Portfolio Holdings Layer
    portfolio_id = st.session_state.get('current_portfolio_id')
    shares_held = 0
    
    if portfolio_id:
        if use_cloud:
            try:
                # OPTIMIZED: Direct production holdings check from cloud server
                query_holdings = "SELECT quantity FROM holdings WHERE portfolio_id = ? AND asset_id = ?"
                df_holdings = get_data(query_holdings, [int(portfolio_id), asset_id], use_cloud=True)
                shares_held = df_holdings.iloc[0]['quantity'] if not df_holdings.empty else 0
            except Exception:
                shares_held = 0
        else:
            try:
                table_check_holdings = con.execute("SELECT table_name FROM information_schema.tables WHERE table_name = 'holdings'").df()
                if not table_check_holdings.empty:
                    query_holdings = "SELECT quantity FROM holdings WHERE portfolio_id = ? AND asset_id = ?"
                    df_holdings = con.execute(query_holdings, [int(portfolio_id), asset_id]).df()
                    shares_held = df_holdings.iloc[0]['quantity'] if not df_holdings.empty else 0
            except Exception:
                shares_held = 0

    return {
        "asset_id": asset_id,
        "ticker": ticker_name,
        "name": name,
        "sector": sector,
        "industry": industry,
        "current_price": current_price,
        "first_trade_date": first_trade_date,
        "shares_held": shares_held,
        "total_value_held": shares_held * current_price if current_price else 0
    }
    
    
# for getting all the data over an asset up to a sim_time
def get_asset_full_data(ticker, sim_time, portfolio_id=None):
    # 1. מידע בסיסי ותאריך התחלה
    asset_df = get_data("""
        SELECT asset_id, ticker, name, sector, industry, is_etf,
               (SELECT MIN(timestamp) FROM prices WHERE asset_id = assets.asset_id) as first_trade_date
        FROM assets WHERE ticker = ?
    """, [ticker.upper()])
    
    if asset_df.empty:
        return None

    asset_id = int(asset_df.iloc[0]['asset_id'])

    # 2. בדיקת אחזקות בתיק (אם רלוונטי)
    shares_held = 0
    if portfolio_id:
        h_df = get_data("SELECT quantity FROM holdings WHERE portfolio_id = ? AND asset_id = ?", 
                        [portfolio_id, asset_id])
        shares_held = h_df.iloc[0]['quantity'] if not h_df.empty else 0

    # 3. שליפת היסטוריית מחירים (שנה אחורה לניתוח)
    prices_df = get_data("""
        SELECT timestamp, open, high, low, close, adj_close, volume 
        FROM prices 
        WHERE asset_id = ? AND timestamp <= ? 
        ORDER BY timestamp ASC
    """, [asset_id, sim_time])

    # 4. שליפת פונדמנטלס ופיצ'רים
    fundamentals_df = get_data("SELECT * FROM fundamentals WHERE asset_id = ? AND timestamp <= ? ORDER BY timestamp ASC", [asset_id, sim_time])
    features_df = get_data("SELECT * FROM features WHERE asset_id = ? AND timestamp <= ? ORDER BY timestamp ASC", [asset_id, sim_time])

    # איסוף הכל למבנה נתונים אחד
    return {
        "info": asset_df.iloc[0].to_dict(),
        "shares_held": shares_held,
        "prices": prices_df,
        "fundamentals": fundamentals_df,
        "features": features_df,
        "latest_price": prices_df.iloc[-1]['close'] if not prices_df.empty else None
    }

# for recording snapshots of portfolios 
def capture_portfolio_snapshot(connection, portfolio_id, sim_date):
    """
    Records a portfolio valuation snapshot in history. Pre-cleans existing rows 
    for the same portfolio and date to maintain data integrity without relying on DB constraints.
    All source documentation and comments are maintained strictly in English.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 1. Calculate the real-time dynamic valuation of the portfolio assets
        total_value = portfolio_value_calculator(portfolio_id, sim_date, con=connection)
        
        # 2. Fetch the current available cash ledger balance using cloud-native parameters
        cash_res = connection.execute(
            text("SELECT available_cash FROM portfolios WHERE portfolio_id = :id"),
            {"id": portfolio_id}
        ).fetchone()
        
        available_cash = float(cash_res[0]) if cash_res else 0.0
        
        # 3. Safe Clean-up: Delete any existing historical slice for this portfolio on this exact date
        # This completely replaces the need for an 'ON CONFLICT' constraint in the cloud schema
        connection.execute(
            text("""
                DELETE FROM portfolio_history 
                WHERE portfolio_id = :portfolio_id AND timestamp = :timestamp
            """),
            {"portfolio_id": portfolio_id, "timestamp": sim_date}
        )
        
        # 4. Standard safe INSERT layout execution
        cloud_insert_query = text("""
            INSERT INTO portfolio_history (portfolio_id, timestamp, portfolio_value, available_cash)
            VALUES (:portfolio_id, :timestamp, :portfolio_value, :available_cash);
        """)
        
        connection.execute(
            cloud_insert_query,
            {
                "portfolio_id": portfolio_id,
                "timestamp": sim_date,
                "portfolio_value": total_value,
                "available_cash": available_cash
            }
        )
        
        logger.info(f"Cloud portfolio history snapshot successfully synchronized for ID {portfolio_id}.")
        return True
        
    except Exception as e:
        logger.error(f"Cloud portfolio snapshot transaction sequence failed: {e}")
        raise e


# for serching assets
def search_assets(con, search_term):
    """
    מחפשת נכסים לפי טיקר או שם ומחזירה רשימה של תוצאות.
    """
    if not search_term or len(search_term) < 1:
        return []
    
    # חיפוש גמיש (LIKE) גם בטיקר וגם בשם
    query = f"%{search_term}%"
    results = con.execute("""
        SELECT ticker, name 
        FROM assets 
        WHERE ticker LIKE ? OR name LIKE ?
        LIMIT 10
    """, [query, query]).fetchall()
    
    # עיצוב התוצאות למחרוזת קריאה: "AAPL | Apple Inc."
    return [f"{r[0]} | {r[1]}" for r in results]


# for calculating portfolio's Value at a given time 
def portfolio_value_calculator(portfolio_id, timestamp, con=None):
    """
    Computes the total financial valuation of a specific portfolio (Available Cash + Market Value of Holdings)
    at a given historical timestamp slice using cloud-native engines.
    All source documentation and comments are maintained strictly in English.
    """
    logger = logging.getLogger(__name__)
    should_close = False

    # --- DEFENSIVE REALIGNMENT ---
    # If the positional arguments are mixed up in legacy UI calls, safely swap them
    if hasattr(timestamp, 'execute'):
        con, timestamp = timestamp, con

    # If the legacy DuckDB connection leaks in, bypass it and force cloud engine connectivity
    if con is not None and ('duckdb' in str(type(con)).lower() or not hasattr(con, 'begin')):
        con = None 

    # Dynamic operational routing: Use passed active transaction context or spin up an isolated engine connection
    if con is None:
        engine = get_supabase_engine()
        con = engine.connect()
        should_close = True

    try:
        ### --- STEP 1: QUERY RELEVANT SNAPSHOT DATA FROM CLOUD DB --- ###
        
        query = text("""
            SELECT 
                h.asset_id, 
                h.quantity, 
                p.close AS price,
                (h.quantity * p.close) AS market_value
            FROM holdings h
            LEFT JOIN prices p ON h.asset_id = p.asset_id
            WHERE h.portfolio_id = :portfolio_id
            AND p.timestamp = (
                SELECT MAX(timestamp) 
                FROM prices 
                WHERE asset_id = h.asset_id 
                    AND timestamp <= :timestamp
            )
        """)
        
        result_assets = con.execute(query, {"portfolio_id": portfolio_id, "timestamp": timestamp}).fetchall()
        
        if result_assets:
            df_assets_holdings = pd.DataFrame(
                result_assets, 
                columns=['asset_id', 'quantity', 'price', 'market_value']
            )
        else:
            df_assets_holdings = pd.DataFrame(columns=['asset_id', 'quantity', 'price', 'market_value'])

        # Fetch the current unallocated cash reserves available in the target core profile
        cash_res = con.execute(
            text("""
                SELECT available_cash
                FROM portfolios
                WHERE portfolio_id = :portfolio_id
            """), 
            {"portfolio_id": portfolio_id}
        ).fetchone()
        
        portfolio_cash = float(cash_res[0]) if cash_res else 0.0
        
        ### --- STEP 2: AGGREGATE TOTAL NET VALUE --- ###
        
        total_market_value = float(df_assets_holdings['market_value'].sum()) if not df_assets_holdings.empty else 0.0
        total_portfolio_value = portfolio_cash + total_market_value
        
        logger.info(
            f"Portfolio {portfolio_id} valuation tracking at {timestamp}: "
            f"Cash: {portfolio_cash:.2f}, Assets: {total_market_value:.2f}, Total: {total_portfolio_value:.2f}"
        )
        
        return round(total_portfolio_value, 2)

    except Exception as calc_error:
        logger.error(f"Failed to execute calculation sequence context for Portfolio ID {portfolio_id}: {calc_error}")
        raise calc_error
        
    finally:
        if should_close:
            con.close()
     
            
# for making sure no dubble writing happens leading to a crash
def is_action_allowed(wait_time=2):
    """בודקת אם עבר מספיק זמן מהפעולה האחרונה"""
    now = time.time()
    last_time = st.session_state.get('last_action_time', 0)
    
    if now - last_time < wait_time:
        return False
    
    st.session_state.last_action_time = now
    return True   

# for setting initial states 
# also helps keeping track of session_state variables
def init_session_state():
    """
    Initializes system-wide default session state variables for navigation, 
    user authentication context, portfolio state tracking, and establishes
    the core persistent connection driver for the local database catalog architecture.
    """
    # -------------------------------------------------------------------------
    # CORE DATABASE CONTEXT ESTABLISHMENT
    # -------------------------------------------------------------------------
    # Ensure a single unified connection context exists across script executions
    if 'con' not in st.session_state:
        # Resolve path dynamically from session state registry (defaults to local)
        resolved_db_path = st.session_state.get('DB_PATH', 'stratify.duckdb')
        
        try:
            # Connect directly to the physical storage file containing local configurations
            # read_only=False allows mutation of user preference matrices safely
            st.session_state.con = duckdb.connect(database=resolved_db_path, read_only=False)
        except Exception as conn_error:
            st.error(f"Critical System Failure: Unable to bind data pipeline driver. Info: {conn_error}")
            st.session_state.con = None

    # -------------------------------------------------------------------------
    # APP INITIALIZATION STATE VARIABLES
    # -------------------------------------------------------------------------
    if 'initialized' not in st.session_state:
        # --- navigation ---
        st.session_state.page = "login_page"    # default target landing zone
        
        # --- user authentication context ---
        st.session_state.logged_in = False
        st.session_state.reg_success = False
        st.session_state.user_id = None
        st.session_state.first_name = None
        st.session_state.prefilled_email = ""
        st.session_state.my_portfolios = []

        # --- active backtest portfolio matrix ---
        st.session_state.my_portfolios_df = None
        st.session_state.current_portfolio_id = None
        st.session_state.current_portfolio_name = None
        st.session_state.current_sim_date = None
        st.session_state.current_portfolio_starting_at = None
        st.session_state.current_available_cash = None
        st.session_state.current_sim_date_display = None

        # --- execution lifecycle & system logging metrics ---
        st.session_state.last_action_time = 0
        st.session_state.initialized = True




