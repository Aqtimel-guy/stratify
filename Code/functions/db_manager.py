import duckdb
import streamlit as st
import logging
import time
import datetime
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
    Optimized for SQLAlchemy 2.0+ and Python 3.14 parameter binding compatibility.
    """
    import pandas as pd
    from sqlalchemy import text
    import streamlit as st
    import duckdb

    # ---- OPTION A: Cloud Database Execution (Supabase) ----
    if use_cloud:
        engine = get_supabase_engine()
        
        cloud_query = query
        cloud_params = {}
        
        if params is not None:
            if isinstance(params, dict):
                cloud_params = params
                # Handle legacy '?' placeholders if passed alongside a dictionary mapping
                if '?' in cloud_query:
                    for key in params.keys():
                        cloud_query = cloud_query.replace('?', f":{key}", 1)
            else:
                if not isinstance(params, (list, tuple)):
                    params = [params]
                
                # Convert positional markers '?' to named placeholders (:param_0, :param_1...)
                if '?' in cloud_query:
                    for i, param in enumerate(params):
                        placeholder = f"param_{i}"
                        cloud_query = cloud_query.replace('?', f":{placeholder}", 1)
                        cloud_params[placeholder] = param

        try:
            # OPTIMIZED: Execute via connection directly to resolve Pandas/SQLAlchemy 2.0 parameter conflicts
            with engine.connect() as connection:
                result_proxy = connection.execute(text(cloud_query), cloud_params)
                
                # Fetch rows and safely construct DataFrame with correct database column mappings
                extracted_rows = result_proxy.fetchall()
                if extracted_rows:
                    return pd.DataFrame(extracted_rows, columns=result_proxy.keys())
                else:
                    # Return empty DataFrame with appropriate column structural headers if no rows match
                    return pd.DataFrame(columns=result_proxy.keys())
                    
        except Exception as db_err:
            print(f"[CLOUD ENGINE CRITICAL ERROR]: {str(db_err)}")
            raise db_err

    # ---- OPTION B: Local Database Execution (DuckDB) ----
    con = st.session_state.get('duckdb_con')
    
    if con:
        if params:
            return con.execute(query, params).df()
        return con.execute(query).df()
    
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
    """
    Returns full asset dataset up to a simulation timestamp.
    Data sources:
    - Supabase: assets, holdings
    - GCS / DuckDB layer: prices, fundamentals, features (via get_data abstraction)
    """

    # 1. Asset metadata + first trade date (split to avoid correlated subquery issues)
    asset_df = get_data("""
        SELECT asset_id, ticker, name, sector, industry, is_etf
        FROM assets
        WHERE ticker = ?
    """, [ticker.upper()])

    if asset_df.empty:
        return None

    asset_id = int(asset_df.iloc[0]["asset_id"])

    # separate query for first trade date (better for Supabase performance)
    first_trade_df = get_data("""
        SELECT MIN(timestamp) AS first_trade_date
        FROM prices
        WHERE asset_id = ?
    """, [asset_id])

    first_trade_date = (
        first_trade_df.iloc[0]["first_trade_date"]
        if not first_trade_df.empty
        else None
    )

    # attach info
    info = asset_df.iloc[0].to_dict()
    info["first_trade_date"] = first_trade_date

    # 2. Holdings (Supabase)
    shares_held = 0
    if portfolio_id:
        h_df = get_data("""
            SELECT quantity
            FROM holdings
            WHERE portfolio_id = ? AND asset_id = ?
        """, [portfolio_id, asset_id])

        if not h_df.empty:
            shares_held = float(h_df.iloc[0]["quantity"])

    # 3. Price history (GCS / Parquet layer via abstraction)
    prices_df = get_data("""
        SELECT timestamp, open, high, low, close, adj_close, volume
        FROM prices
        WHERE asset_id = ? AND timestamp <= ?
        ORDER BY timestamp ASC
    """, [asset_id, sim_time])

    # 4. Fundamentals
    fundamentals_df = get_data("""
        SELECT *
        FROM fundamentals
        WHERE asset_id = ? AND timestamp <= ?
        ORDER BY timestamp ASC
    """, [asset_id, sim_time])

    # 5. Features
    features_df = get_data("""
        SELECT *
        FROM features
        WHERE asset_id = ? AND timestamp <= ?
        ORDER BY timestamp ASC
    """, [asset_id, sim_time])

    # 6. Latest price (safe handling)
    latest_price = None
    if not prices_df.empty:
        latest_price = prices_df.iloc[-1]["close"]

    return {
        "info": info,
        "shares_held": shares_held,
        "prices": prices_df,
        "fundamentals": fundamentals_df,
        "features": features_df,
        "latest_price": latest_price
    }

# for recording snapshots of portfolios 
def capture_portfolio_snapshot(connection, portfolio_id, sim_date):
    """
    Records a portfolio valuation snapshot in portfolio_history.

    Data sources:
    - Supabase: portfolios, portfolio_history, holdings (indirect via calculator)
    - GCS/DuckDB: market data via portfolio_value_calculator

    This function assumes the provided connection is a SQLAlchemy connection.
    """

    logger = logging.getLogger(__name__)

    try:
        # ---------------------------------------------------------------------
        # 1. Portfolio total value (market value + cash)
        # ---------------------------------------------------------------------
        total_value = portfolio_value_calculator(
            duckdb_con=connection,
            portfolio_id=portfolio_id,
            timestamp=sim_date
            )

        # ---------------------------------------------------------------------
        # 2. Cash balance (Supabase)
        # ---------------------------------------------------------------------
        cash_res = connection.execute(
            text("""
                SELECT available_cash
                FROM portfolios
                WHERE portfolio_id = :portfolio_id
            """),
            {"portfolio_id": portfolio_id}
        ).fetchone()

        available_cash = float(cash_res[0]) if cash_res and cash_res[0] is not None else 0.0

        # ---------------------------------------------------------------------
        # 3. Idempotent write strategy (DELETE + INSERT)
        # ---------------------------------------------------------------------
        # NOTE: kept as-is for compatibility, but logically represents UPSERT behavior

        connection.execute(
            text("""
                DELETE FROM portfolio_history
                WHERE portfolio_id = :portfolio_id
                  AND timestamp = :timestamp
            """),
            {
                "portfolio_id": portfolio_id,
                "timestamp": sim_date
            }
        )

        connection.execute(
            text("""
                INSERT INTO portfolio_history (
                    portfolio_id,
                    timestamp,
                    portfolio_value,
                    available_cash
                )
                VALUES (
                    :portfolio_id,
                    :timestamp,
                    :portfolio_value,
                    :available_cash
                )
            """),
            {
                "portfolio_id": portfolio_id,
                "timestamp": sim_date,
                "portfolio_value": float(total_value),
                "available_cash": available_cash
            }
        )

        logger.info(
            f"Portfolio snapshot stored: "
            f"portfolio_id={portfolio_id}, "
            f"date={sim_date}, "
            f"value={total_value:.2f}"
        )

        return True

    except Exception as e:
        logger.error(
            f"Failed to capture portfolio snapshot "
            f"(portfolio_id={portfolio_id}, sim_date={sim_date}): {e}"
        )
        raise

# for serching assets
def search_assets(con, search_term):
    """
    Searches assets by ticker or name and returns formatted results.
    Data source: Supabase (production) or DuckDB (local/dev) via provided connection.
    """

    if not search_term or not search_term.strip():
        return []

    search_term = search_term.strip()
    query = f"%{search_term}%"

    # Use ILIKE for PostgreSQL compatibility (Supabase)
    results = con.execute("""
        SELECT ticker, name
        FROM assets
        WHERE ticker ILIKE :q OR name ILIKE :q
        LIMIT 10
    """, {"q": query}).fetchall()

    return [f"{r[0]} | {r[1]}" for r in results]

# for calculating portfolio's Value at a given time 
def portfolio_value_calculator(duckdb_con, portfolio_id, timestamp):
    """
    Computes total portfolio value at a given timestamp:
    cash + market value of holdings.

    Data sources:
    - Supabase (Cloud): holdings, portfolios
    - DuckDB (Local Context -> GCS): prices parquet
    All source documentation and comments are maintained strictly in English.
    """
    logger = logging.getLogger(__name__)
    should_close_cloud = False

    # 1. Establish Cloud Connection for Metadata (Portfolios & Holdings)
    cloud_engine = get_supabase_engine()
    cloud_con = cloud_engine.connect()
    should_close_cloud = True

    try:
        # A. Fetch Available Cash From Cloud
        cash_res = cloud_con.execute(
            text("""
                SELECT available_cash
                FROM portfolios
                WHERE portfolio_id = :portfolio_id
            """),
            {"portfolio_id": portfolio_id}
        ).fetchone()

        portfolio_cash = float(cash_res[0]) if cash_res and cash_res[0] is not None else 0.0

        # B. Fetch Raw Asset Holdings Quantities From Cloud
        holdings_res = cloud_con.execute(
            text("""
                SELECT asset_id, quantity
                FROM holdings
                WHERE portfolio_id = :portfolio_id AND quantity > 0
            """),
            {"portfolio_id": portfolio_id}
        ).fetchall()

        df_holdings = pd.DataFrame(holdings_res, columns=["asset_id", "quantity"])

        # 2. Compute Market Value Using Local Pricing Layer (DuckDB)
        total_market_value = 0.0

        if not df_holdings.empty:
            asset_ids = df_holdings["asset_id"].tolist()
            
            # Create a temporary table to handle asset list safely in DuckDB
            duckdb_con.execute("CREATE OR REPLACE TEMPORARY TABLE target_assets AS SELECT unnest(?) as asset_id", [asset_ids])
            
            gcs_prices_url = "https://storage.googleapis.com/stratify-historical-data/data_snapshots/prices.parquet"
            
            # Simplified query: Filter Parquet directly using JOIN
            # We defer the 'as-of' logic (latest timestamp) to Pandas to ensure stability
            prices_query = f"""
                SELECT p.asset_id, p.timestamp, p.close
                FROM read_parquet('{gcs_prices_url}') p
                INNER JOIN target_assets ta ON p.asset_id = ta.asset_id
                WHERE p.timestamp <= :target_time
            """
            
            df_prices = duckdb_con.execute(prices_query, {"target_time": timestamp}).df()
            
            if not df_prices.empty:
                # Keep only the latest price per asset (as-of logic)
                df_prices = df_prices.sort_values(by='timestamp').groupby('asset_id').tail(1)
                
                # Merge holdings data with fetched localized historical prices
                df_valuation = pd.merge(df_holdings, df_prices, on="asset_id", how="inner")
                df_valuation["market_value"] = df_valuation["quantity"] * df_valuation["price"]
                total_market_value = float(df_valuation["market_value"].sum())
            else:
                logger.warning(f"No asset historical prices found in DuckDB for portfolio={portfolio_id} at timestamp={timestamp}")

        # 3. Final Evaluation Matrix Aggregation
        total_value = portfolio_cash + total_market_value

        logger.info(
            f"Portfolio valuation computed: "
            f"id={portfolio_id}, "
            f"timestamp={timestamp}, "
            f"cash={portfolio_cash:.2f}, "
            f"market={total_market_value:.2f}, "
            f"total={total_value:.2f}"
        )

        return round(total_value, 2)

    except Exception as e:
        logger.error(
            f"Portfolio valuation failed safely: portfolio_id={portfolio_id}, error={e}"
        )
        raise

    finally:
        if should_close_cloud:
            cloud_con.close()

# for getting portfolio card data (precomputed for performance)    
def get_portfolio_card_data(user_id):
    """
    Returns precomputed portfolio card data.
    UI should NOT compute anything.
    """

    df = get_data("""
        SELECT 
            portfolio_id,
            portfolio_name,
            available_cash,
            starting_at,
            current_sim_date
        FROM portfolios
        WHERE user_id = :user_id
        ORDER BY created_at DESC
    """, {"user_id": user_id}, use_cloud=True)

    if df.empty:
        return df

    results = []

    for _, row in df.iterrows():
        p_id = row["portfolio_id"]

        try:
            sim_date = pd.to_datetime(row["current_sim_date"]).to_pydatetime()
            duckdb_con = duckdb.connect(database=":memory:")

            value = portfolio_value_calculator(
                duckdb_con=duckdb_con,
                portfolio_id=p_id,
                timestamp=sim_date
            )

        except Exception:
            value = None

        results.append({
            "portfolio_id": p_id,
            "portfolio_name": row["portfolio_name"],
            "start_date": pd.to_datetime(row["starting_at"]).date() if row["starting_at"] else None,
            "sim_date": pd.to_datetime(row["current_sim_date"]).date() if row["current_sim_date"] else None,
            "value": value
        })

    return pd.DataFrame(results)
          

# for making sure no dubble writing happens leading to a crash
def is_action_allowed(wait_time=2):
    """
    Prevents rapid repeated actions (basic debounce mechanism).
    Uses Streamlit session state to track last execution time.
    """

    now = time.time()
    last_time = st.session_state.get("last_action_time", 0)

    if now - last_time < wait_time:
        return False

    st.session_state["last_action_time"] = now
    return True


# for setting initial states and to help keeping track of session_state variables
def init_session_state():
    """
    Initializes system-wide Streamlit session state variables for:
    - Navigation
    - Authentication context
    - Portfolio state tracking
    - Core database connection
    """

    # ---------------------------------------------------------------------
    # CORE DATABASE CONNECTION (LOCAL DEV ONLY)
    # ---------------------------------------------------------------------
    # DuckDB is used only for local development / analytics purposes
    if "con" not in st.session_state:
        resolved_db_path = st.session_state.get("DB_PATH", "stratify.duckdb")

        try:
            st.session_state["con"] = duckdb.connect(
                database=resolved_db_path,
                read_only=False
            )
        except Exception as conn_error:
            st.error(
                f"Failed to initialize local DuckDB connection: {conn_error}"
            )
            st.session_state["con"] = None

    # ---------------------------------------------------------------------
    # INITIALIZATION FLAG
    # ---------------------------------------------------------------------
    if "initialized" not in st.session_state:
        # Navigation
        st.session_state["page"] = "login_page"

        # Authentication context
        st.session_state["logged_in"] = False
        st.session_state["reg_success"] = False
        st.session_state["user_id"] = None
        st.session_state["first_name"] = None
        st.session_state["prefilled_email"] = ""
        st.session_state["my_portfolios"] = []

        # Portfolio state
        st.session_state["my_portfolios_df"] = None
        st.session_state["current_portfolio_id"] = None
        st.session_state["current_portfolio_name"] = None
        st.session_state["current_sim_date"] = None
        st.session_state["current_portfolio_starting_at"] = None
        st.session_state["current_available_cash"] = None
        st.session_state["current_sim_date_display"] = None

        # UI / rate limiting
        st.session_state["last_action_time"] = 0

        # Mark system initialized
        st.session_state["initialized"] = True


