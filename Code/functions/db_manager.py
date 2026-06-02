import duckdb
import streamlit as st
import logging
import time
import pandas as pd
from sqlalchemy import create_engine

DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'



# for easy querying 
# Ensure you have your SQLAlchemy engine ready (either globally or imported from your db_manager)
def get_supabase_engine():
    db_password = st.secrets["database"]["password"]
    db_user = "postgres.nbmxcagcaftevvsplsxj"
    db_host = "aws-1-eu-central-1.pooler.supabase.com"
    db_port = 6543
    db_name = "postgres"
    connection_string = f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_engine(connection_string)

# for getting assets details 
def get_data(query, params=None, use_cloud=False):
    """
    Unified data fetching function.
    If use_cloud=True, queries the external Supabase database with safe parameter casting.
    If use_cloud=False (default), queries the local DuckDB database using active session state if available.
    """
    import pandas as pd

    # ---- OPTION A: Querying the Cloud Database (Supabase) ----
    if use_cloud:
        engine = get_supabase_engine()
        
        # PostgreSQL uses %s for parameters instead of ?
        cloud_query = query.replace('?', '%s')
        
        # Convert list/single params to a tuple that Pandas/SQLAlchemy expects
        if params is not None:
            if isinstance(params, list):
                params = tuple(params)
            elif not isinstance(params, (tuple, dict)):
                params = (params,)
        
        return pd.read_sql(cloud_query, con=engine, params=params)

    # ---- OPTION B: Querying the Local Database (DuckDB) ----
    # 1. Check if an active connection exists in Streamlit session state
    if 'con' in st.session_state:
        con = st.session_state.con
        if params:
            return con.execute(query, params).df()
        return con.execute(query).df()
    
    # 2. Fallback if no active session connection exists (e.g., initial startup)
    import duckdb
    with duckdb.connect(DB_PATH) as con:
        if params:
            return con.execute(query, params).df()
        return con.execute(query).df()

# for getting assets details 
def get_asset_snapshot(con, ticker, sim_date, use_cloud=False):
    """
    Fetches comprehensive info about a specific asset as of the simulation date,
    including inception date if the asset did not trade yet on the requested date.
    """
    ASSETS_SOURCE = "assets_cloud" if use_cloud else "assets"
    PRICES_SOURCE = "prices_cloud" if use_cloud else "prices"
    
    # 1. Fetch core metadata from assets catalog using unified get_data
    query_asset = f"SELECT asset_id, ticker, name, sector, industry FROM {ASSETS_SOURCE} WHERE ticker = ?"
    df_asset = get_data(query_asset, [ticker.upper()], use_cloud=use_cloud)
    
    if df_asset.empty:
        return None

    # Extract first row values from DataFrame
    asset_id = df_asset.iloc[0]['asset_id']
    ticker_name = df_asset.iloc[0]['ticker']
    name = df_asset.iloc[0]['name']
    sector = df_asset.iloc[0]['sector']
    industry = df_asset.iloc[0]['industry']

    # 2. Fetch the latest available price up to the current simulation date
    query_price = f"""
        SELECT close, timestamp 
        FROM {PRICES_SOURCE} 
        WHERE asset_id = ? AND timestamp <= ? 
        ORDER BY timestamp DESC 
        LIMIT 1
    """
    df_price = get_data(query_price, [int(asset_id), sim_date], use_cloud=use_cloud)
    current_price = df_price.iloc[0]['close'] if not df_price.empty else None

    # 3. Fetch the first historical trading date
    query_first_date = f"SELECT MIN(timestamp) as min_ts FROM {PRICES_SOURCE} WHERE asset_id = ?"
    df_first_date = get_data(query_first_date, [int(asset_id)], use_cloud=use_cloud)
    first_trade_date = df_first_date.iloc[0]['min_ts'] if not df_first_date.empty else None

    # 4. Check for existing holdings within the active portfolio context
    portfolio_id = st.session_state.get('current_portfolio_id')
    shares_held = 0
    if portfolio_id:
        use_cloud_portfolio = st.session_state.get('use_cloud', False)
        HOLDINGS_SOURCE = "holdings_cloud" if use_cloud_portfolio else "holdings"
        
        query_holdings = f"SELECT quantity FROM {HOLDINGS_SOURCE} WHERE portfolio_id = ? AND asset_id = ?"
        df_holdings = get_data(query_holdings, [int(portfolio_id), int(asset_id)], use_cloud=use_cloud_portfolio)
        shares_held = df_holdings.iloc[0]['quantity'] if not df_holdings.empty else 0

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
def capture_portfolio_snapshot(con, portfolio_id, sim_date):
    """
    Calculates total portfolio value and records a snapshot in history.
    Saves to both local DuckDB and external Supabase (Dual-Write).
    """
    # 1. Calculate portfolio value (Runs locally on DuckDB)
    total_value = portfolio_value_calculator(portfolio_id, sim_date)
    
    # 2. Fetch available cash from local DuckDB
    cash_res = con.execute("SELECT available_cash FROM portfolios WHERE portfolio_id = ?", [portfolio_id]).fetchone()
    available_cash = cash_res[0] if cash_res else 0
    
    # ---- STEP A: LOCAL WRITE (DuckDB) ----
    con.execute("""
        INSERT INTO portfolio_history (portfolio_id, timestamp, portfolio_value, available_cash)
        VALUES (?, ?, ?, ?)
    """, [portfolio_id, sim_date, total_value, available_cash])

    # ---- STEP B: CLOUD WRITE (Supabase) ----
    try:
        # Optimized: Reusing the existing global engine generator function
        engine = get_supabase_engine()
        
        # Explicit PostgreSQL UPSERT syntax to prevent duplicate primary key crashes
        cloud_upsert_query = """
            INSERT INTO portfolio_history (portfolio_id, timestamp, portfolio_value, available_cash)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (portfolio_id, timestamp) 
            DO UPDATE SET 
                portfolio_value = EXCLUDED.portfolio_value,
                available_cash = EXCLUDED.available_cash;
        """
        
        # Execute the write directly to the cloud
        with engine.begin() as cloud_con:
            cloud_con.execute(cloud_upsert_query, (portfolio_id, sim_date, total_value, available_cash))
            
    except Exception as e:
        # We log the error but don't crash the app, ensuring the local user experience remains unaffected
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Cloud portfolio snapshot sync failed: {e}")


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
def portfolio_value_calculator(portfolio_id , timestamp , con=None):
    
    """
    this function will calculate the value of a portfolio
    
    tables:
    1. portfolios
    2. holdings
    3. prices
    
    """
    
     # connecting to DB and loggin
    if con is None:
        con = duckdb.connect(DB_PATH)
        should_close = True
    else:
        should_close = False
        
    logger = logging.getLogger(__name__)
    
    ### --- step 1: query ther relevant data from DB --- ###
    
    # get table of relevant prices
    query = """
        SELECT 
            h.asset_id, 
            h.quantity, 
            p.close AS price,
            (h.quantity * p.close) AS market_value
        FROM holdings h
        LEFT JOIN prices p ON h.asset_id = p.asset_id
        WHERE h.portfolio_id = ?
        AND p.timestamp = (
            SELECT MAX(timestamp) 
            FROM prices 
            WHERE asset_id = h.asset_id 
                AND timestamp <= ?
        )
    """
    df_assets_holdings = con.execute(query, [portfolio_id, timestamp]).df()
    
    # get the current balance in the portfolio
    portfolio_cash_df = con.execute("""
                                 select available_cash
                                 FROM portfolios
                                 WHERE
                                 portfolio_id = ?
                                 """ , [portfolio_id]).fetchone()
    portfolio_cash = portfolio_cash_df[0]
    
    ### --- step 2: calculate total value --- ###
    
    # calculating total asset value at given timestamp
    total_market_value = df_assets_holdings['market_value'].sum()
    
    # calculating total value
    total_portfolio_value = portfolio_cash + total_market_value
    
    # logging and closing connection
    logger.info(f"Portfolio {portfolio_id} valuation at {timestamp}: "
                f"Cash: {portfolio_cash:.2f}, Assets: {total_market_value:.2f}, Total: {total_portfolio_value:.2f}")

    if should_close:
        con.close()
    
    return round(total_portfolio_value , 2)
    
    
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
# also helps keeping track of sessio_state variables

def init_session_state():
    """מגדירה את כל ערכי ברירת המחדל של האפליקציה"""
    if 'initialized' not in st.session_state:
        # --- navigation ---
        st.session_state.page = "login_page"    # defult page
        
        # --- user ---
        st.session_state.logged_in = False
        st.session_state.reg_success = False
        st.session_state.user_id = None
        st.session_state.first_name = None
        st.session_state.prefilled_email = ""
        st.session_state.my_portfolios = []

        # ---portfolio ---
        st.session_state.my_portfolios_df = None
        st.session_state.current_portfolio_id = None
        st.session_state.current_portfolio_name = None
        st.session_state.current_sim_date = None
        st.session_state.current_portfolio_starting_at = None
        st.session_state.current_available_cash = None
        st.session_state.current_sim_date_display = None

        ### initializing
        st.session_state.last_action_time = 0
        st.session_state.initialized = True
