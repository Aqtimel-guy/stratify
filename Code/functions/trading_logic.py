import logging
import duckdb
import streamlit as st
import datetime
import pandas as pd
import math
from .db_manager import *
from sqlalchemy import text

DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'



# for executing cash transactions (withdrawal / deposit)
def execute_cash_transaction(con, portfolio_id, amount, transaction_type, timestamp, reference=None):
    """
    Executes a cash deposit or withdrawal, updates the central Supabase database,
    and records an updated historical portfolio timeline snapshot.
    All source documentation and comments are maintained strictly in English.
    
    transaction_type: 'deposit' or 'withdrawal'
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 1. Fetch and verify current cash balance using cloud-native parameters
        res = con.execute(
            text("SELECT available_cash FROM portfolios WHERE portfolio_id = :id"), 
            {"id": portfolio_id}
        ).fetchone()
        
        if not res:
            return False, "Portfolio not found"
        
        current_cash = float(res[0])

        # 2. Enforce structural validation rules for withdrawal pipeline executions
        if transaction_type == 'withdrawal' and amount > current_cash:
            return False, f"Insufficient funds. Available: ${current_cash:,.2f}"

        # 3. Handle Context Transaction Lifespan
        is_nested = con.in_transaction()
        tx = None if is_nested else con.begin()

        try:
            # A. Allocate sequence primary keys and log the event inside the cash_transactions ledger audit table
            max_id_res = con.execute(
                text("SELECT COALESCE(MAX(transaction_id), 0) FROM cash_transactions")
            ).fetchone()
            next_transaction_id = int(max_id_res[0]) + 1

            con.execute(
                text("""
                    INSERT INTO cash_transactions (transaction_id, portfolio_id, timestamp, amount, transaction_type, reference)
                    VALUES (:transaction_id, :portfolio_id, :timestamp, :amount, :transaction_type, :reference)
                """), 
                {
                    "transaction_id": next_transaction_id,
                    "portfolio_id": portfolio_id,
                    "timestamp": timestamp,
                    "amount": amount,
                    "transaction_type": transaction_type,
                    "reference": reference
                }
            )

            # B. Mutate and shift liquidity ledger balances inside the main portfolios table
            cash_change = amount if transaction_type == 'deposit' else -amount
            con.execute(
                text("""
                    UPDATE portfolios 
                    SET available_cash = ROUND(CAST(available_cash + :cash_change AS NUMERIC), 2)
                    WHERE portfolio_id = :portfolio_id
                """), 
                {"cash_change": cash_change, "portfolio_id": portfolio_id}
            )
            
            # C. Trigger system historical timeline layout matrix update snapshot
            capture_portfolio_snapshot(con, portfolio_id, timestamp)
            
            if tx:
                tx.commit()
            else:
                con.commit()
                
            logger.info(f"Successfully executed {transaction_type} of ${amount} for portfolio {portfolio_id}")
            return True, f"Successfully {transaction_type}ed ${amount:,.2f}"

        except Exception as inner_error:
            if tx:
                tx.rollback()
            else:
                try:
                    con.rollback()
                except Exception:
                    pass
            raise inner_error

    except Exception as e:
        logger.error(f"Cash transaction workflow pipeline failed: {e}")
        return False, str(e)


# for executing a trade
def execute_asset_trade(cloud_con, duckdb_con, portfolio_id, ticker, timestamp, quantity, side): 
    """
    Executes an asset trade (buy/sell), updates the core portfolios liquidity ledger,
    modifies asset positioning frames, and captures a historical snapshot.
    Fetches market data from GCS via DuckDB before running cloud updates on Supabase.
    All source documentation and comments are maintained strictly in English.
    
    side: 'buy' or 'sell'
    """
    logger = logging.getLogger(__name__)
    
    try:
        # --- Step 1: Query asset metadata from cloud (Supabase) ---
        asset_res = cloud_con.execute(
            text("SELECT asset_id FROM assets WHERE UPPER(TRIM(ticker)) = UPPER(TRIM(:ticker)) LIMIT 1"), 
            {"ticker": ticker}
        ).fetchone()

        if not asset_res:
            logger.warning(f"Trade failed: Ticker '{ticker}' not found in Supabase.")
            return False, f"Asset '{ticker}' not found"

        asset_id = asset_res[0]

        # --- Step 2: Query portfolio liquidity balance from cloud (Supabase) ---
        portfolio_res = cloud_con.execute(
            text("SELECT starting_at, available_cash FROM portfolios WHERE portfolio_id = :portfolio_id"), 
            {"portfolio_id": portfolio_id}
        ).fetchone()
        
        if not portfolio_res:
            logger.warning(f"Trade execution aborted: Portfolio ID {portfolio_id} not found.")
            return False, "Portfolio not found"
            
        portfolio_start_day, raw_cash = portfolio_res
        portfolio_available_cash = float(raw_cash) if raw_cash is not None else 0.0

        # --- Step 3: Evaluate Historical Asset Price from GCS (DuckDB) ---
        try:
            gcs_prices_url = "https://storage.googleapis.com/stratify-historical-data/data_snapshots/prices.parquet"
            price_res = duckdb_con.execute(f"""
                SELECT close 
                FROM read_parquet('{gcs_prices_url}') 
                WHERE asset_id = ? AND date = ? 
                LIMIT 1
            """, [asset_id, timestamp]).fetchone()
            
            if not price_res:
                return False, f"No price data available for {ticker} on {timestamp} in cloud storage."
                
            asset_price = float(price_res[0])
        except Exception as price_err:
            logger.error(f"Internal price evaluation engine error on GCS layer: {price_err}")
            return False, f"Price evaluation engine error: {price_err}"

        # --- Step 4: Structural Validations ---
        total_amount = quantity * asset_price
        
        if side == 'buy' and portfolio_available_cash < total_amount:
            return False, "Insufficient funds"

        if side == 'sell':
            holding_res = cloud_con.execute(
                text("SELECT quantity FROM holdings WHERE portfolio_id = :portfolio_id AND asset_id = :asset_id"), 
                {"portfolio_id": portfolio_id, "asset_id": asset_id}
            ).fetchone()
            
            amount_held = float(holding_res[0]) if holding_res else 0.0
            if amount_held < quantity:
                return False, f"Not enough shares (Held: {amount_held}, Request: {quantity})"

        # --- Step 5: Atomic Transaction Lifecycle Execution on Cloud (Supabase) ---
        is_nested = cloud_con.in_transaction()
        tx = None if is_nested else cloud_con.begin()

        try:
            # A. Record the event inside assets_transactions table
            max_id_res = cloud_con.execute(
                text("SELECT COALESCE(MAX(transaction_id), 0) FROM assets_transactions")
            ).fetchone()
            next_transaction_id = int(max_id_res[0]) + 1

            cloud_con.execute(
                text("""
                    INSERT INTO assets_transactions (transaction_id, portfolio_id, asset_id, timestamp, quantity, price_per_share, total_value, side)
                    VALUES (:transaction_id, :portfolio_id, :asset_id, :timestamp, :quantity, :price_per_share, :total_value, :side)
                """), 
                {
                    "transaction_id": next_transaction_id,
                    "portfolio_id": portfolio_id,
                    "asset_id": asset_id,
                    "timestamp": timestamp,
                    "quantity": quantity,
                    "price_per_share": asset_price,
                    "total_value": total_amount,
                    "side": side
                }
            )

            # B. Mutate and manage inventory allocations within the holdings table
            qty_change = quantity if side == 'buy' else -quantity
            
            existing_holding = cloud_con.execute(
                text("SELECT quantity FROM holdings WHERE portfolio_id = :portfolio_id AND asset_id = :asset_id"),
                {"portfolio_id": portfolio_id, "asset_id": asset_id}
            ).fetchone()

            if existing_holding:
                cloud_con.execute(
                    text("""
                        UPDATE holdings 
                        SET quantity = quantity + :qty_change
                        WHERE portfolio_id = :portfolio_id AND asset_id = :asset_id
                    """),
                    {"qty_change": qty_change, "portfolio_id": portfolio_id, "asset_id": asset_id}
                )
            else:
                cloud_con.execute(
                    text("""
                        INSERT INTO holdings (portfolio_id, asset_id, quantity)
                        VALUES (:portfolio_id, :asset_id, :qty_change)
                    """),
                    {"portfolio_id": portfolio_id, "asset_id": asset_id, "qty_change": qty_change}
                )

            # C. Adjust liquidity balances inside the portfolios framework
            cash_change = -total_amount if side == 'buy' else total_amount
            cloud_con.execute(
                text("""
                    UPDATE portfolios 
                    SET available_cash = ROUND(CAST(available_cash + :cash_change AS NUMERIC), 2)
                    WHERE portfolio_id = :portfolio_id
                """), 
                {"cash_change": cash_change, "portfolio_id": portfolio_id}
            )

            # D. Architectural cleanup: Purge empty zeroed inventory assets
            cloud_con.execute(
                text("DELETE FROM holdings WHERE quantity <= 0 AND portfolio_id = :portfolio_id"), 
                {"portfolio_id": portfolio_id}
            )
            
            # E. Trigger historical ledger timeline update snapshot
            capture_portfolio_snapshot(cloud_con, portfolio_id, timestamp)
            
            # Force explicit database commit depending on active transaction frame
            if tx:
                tx.commit()
            else:
                cloud_con.commit()
                
            return True, f"Successfully {side} {quantity} shares of {ticker}"

        except Exception as inner_error:
            if tx:
                tx.rollback()
            else:
                try:
                    cloud_con.rollback()
                except Exception:
                    pass
            raise inner_error

    except Exception as e:
        logger.error(f"Asset trade execution pipeline failed: {e}")
        return False, str(e)


# for easier performnce analysis
def record_portfolio_snapshot(con, portfolio_id, timestamp):
    """
    Computes the total current valuation layout of a portfolio and commits a clean 
    historical snapshot record inside the Supabase database instance.
    All source documentation and comments are maintained strictly in English.
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 1. Delegate dynamic valuation to our updated cloud-native calculator function
        total_value = portfolio_value_calculator(portfolio_id, timestamp, con=con)
        
        # 2. Extract the present cash balance frame using cloud binding parameters
        cash_res = con.execute(
            text("SELECT available_cash FROM portfolios WHERE portfolio_id = :id"),
            {"id": portfolio_id}
        ).fetchone()
        
        available_cash = float(cash_res[0]) if cash_res else 0.0
        
        # 3. Safe Clean-up: Delete any pre-existing snapshot rows for this target date 
        # to guarantee unique execution frames without relying on strict DB physical constraints
        con.execute(
            text("""
                DELETE FROM portfolio_history 
                WHERE portfolio_id = :portfolio_id AND timestamp = :timestamp
            """),
            {"portfolio_id": portfolio_id, "timestamp": timestamp}
        )
        
        # 4. Standard secure cloud INSERT execution layout
        cloud_insert_query = text("""
            INSERT INTO portfolio_history (portfolio_id, timestamp, portfolio_value, available_cash)
            VALUES (:portfolio_id, :timestamp, :portfolio_value, :available_cash);
        """)
        
        con.execute(
            cloud_insert_query,
            {
                "portfolio_id": portfolio_id,
                "timestamp": timestamp,
                "portfolio_value": total_value,
                "available_cash": available_cash
            }
        )
        
        logger.info(f"Cloud portfolio timeline snapshot successfully recorded for ID {portfolio_id} at {timestamp}.")
        return True
        
    except Exception as e:
        logger.error(f"Cloud explicit database snapshot logging workflow failed: {e}")
        raise e


# for showing the history of transactions
@st.cache_data(show_spinner=False)
def get_portfolio_cash_history(portfolio_id, sim_date):
    """
    Builds a unified portfolio cash ledger by combining cloud and analytical layers.
    Processes deposits/withdrawals and trades from Supabase, and matches historical 
    dividend allocations from the local DuckDB storage engine.
    
    Optimized with:
    - Streamlit cache layer mapping
    - Cross-engine data merging pipelines
    - Vectorized pandas ledger cleaning pipelines
    All comments and documentation are maintained strictly in English.
    """
    logger = logging.getLogger(__name__)

    # =========================================
    # 1. ESTABLISH CLOUD CONNECTION (SUPABASE)
    # =========================================
    # Fetching cloud connection context internally to preserve caching layer stability
    cloud_engine = get_supabase_engine()
    
    with cloud_engine.connect() as cloud_con:
        # --- CASH TRANSACTIONS (Cloud) ---
        cash_query = text("""
            SELECT
                timestamp,
                amount,
                transaction_type AS type,
                reference
            FROM cash_transactions
            WHERE portfolio_id = :portfolio_id
              AND timestamp <= :sim_date
        """)
        
        cash_res = cloud_con.execute(cash_query, {"portfolio_id": portfolio_id, "sim_date": sim_date}).fetchall()
        
        if cash_res:
            cash_df = pd.DataFrame(cash_res, columns=["timestamp", "amount", "type", "reference"])
            cash_df["type"] = cash_df["type"].astype(str).str.lower()
        else:
            cash_df = pd.DataFrame(columns=["timestamp", "amount", "type", "reference"])

        # --- ASSET TRANSACTIONS (Cloud) ---
        tx_query = text("""
            SELECT
                t.timestamp,
                t.asset_id,
                a.ticker,
                t.quantity,
                t.price_per_share,
                t.side
            FROM assets_transactions t
            JOIN assets a
                ON t.asset_id = a.asset_id
            WHERE t.portfolio_id = :portfolio_id
              AND t.timestamp <= :sim_date
            ORDER BY t.timestamp ASC
        """)
        
        tx_res = cloud_con.execute(tx_query, {"portfolio_id": portfolio_id, "sim_date": sim_date}).fetchall()
        
        if tx_res:
            tx_df = pd.DataFrame(tx_res, columns=["timestamp", "asset_id", "ticker", "quantity", "price_per_share", "side"])
        else:
            tx_df = pd.DataFrame(columns=["timestamp", "asset_id", "ticker", "quantity", "price_per_share", "side"])

    # =========================================
    # 2. LOCAL ANALYTICAL LAYER (DUCKDB)
    # =========================================
    # Historical large-scale dividend datasets are executed exclusively via local memory engines
    div_query = """
        SELECT
            d.asset_id,
            d.timestamp,
            d.dividend_amount,
            a.ticker
        FROM 'https://storage.googleapis.com/stratify-historical-data/data_snapshots/dividends.parquet' d
        JOIN assets a
            ON d.asset_id = a.asset_id
        WHERE d.timestamp <= $sim_date
        ORDER BY d.timestamp ASC
    """
    
    try:
        # Executes directly against the local duckdb instance/file infrastructure
        div_res_df = duckdb.execute(div_query, {"sim_date": sim_date}).df()
        if not div_res_df.empty:
            div_df = div_res_df
        else:
            div_df = pd.DataFrame(columns=["asset_id", "timestamp", "dividend_amount", "ticker"])
    except Exception as e:
        logger.error(f"Failed to fetch dividends from local DuckDB storage layer: {e}")
        div_df = pd.DataFrame(columns=["asset_id", "timestamp", "dividend_amount", "ticker"])

    # =========================================
    # EMPTY CASE FALLBACK
    # =========================================
    if cash_df.empty and tx_df.empty and div_df.empty:
        return pd.DataFrame(columns=["timestamp", "amount", "type", "reference"])

    # =========================================
    # STRUCTURAL DATA CLEANING
    # =========================================
    if not tx_df.empty:
        tx_df["timestamp"] = pd.to_datetime(tx_df["timestamp"])
        tx_df["side"] = tx_df["side"].astype(str).str.strip().str.lower()
        tx_df["quantity"] = pd.to_numeric(tx_df["quantity"], errors="coerce").fillna(0.0)
        tx_df["price_per_share"] = pd.to_numeric(tx_df["price_per_share"], errors="coerce").fillna(0.0)

    if not div_df.empty:
        div_df["timestamp"] = pd.to_datetime(div_df["timestamp"])

    if not cash_df.empty:
        cash_df["timestamp"] = pd.to_datetime(cash_df["timestamp"])

    # =========================================
    # BUILD BUY / SELL LEDGER FRAME
    # =========================================
    trade_records = []

    if not tx_df.empty:
        for _, tx in tx_df.iterrows():
            trade_value = float(tx["quantity"] * tx["price_per_share"])
            
            if tx["side"] == "buy":
                signed_amount = -trade_value
                trade_type = "buy"
            else:
                signed_amount = trade_value
                trade_type = "sell"

            trade_records.append({
                "timestamp": tx["timestamp"],
                "amount": signed_amount,
                "type": trade_type,
                "reference": tx["ticker"]
            })

    trades_df = pd.DataFrame(trade_records) if trade_records else pd.DataFrame(columns=["timestamp", "amount", "type", "reference"])

    # =========================================
    # BUILD DIVIDEND HISTORICAL LEDGER
    # =========================================
    dividend_records = []

    if not tx_df.empty and not div_df.empty:
        tx_events = tx_df.copy()
        tx_events["event_type"] = "transaction"

        div_events = div_df.copy()
        div_events["event_type"] = "dividend"

        events = pd.concat([tx_events, div_events], ignore_index=True)

        # Critical prioritizing map: process execution transactions BEFORE tracking dividends on matching days
        events["priority"] = events["event_type"].map({"transaction": 0, "dividend": 1})
        events = events.sort_values(["timestamp", "priority"])

        holdings = {}

        # Executing single state machine simulation pass
        for _, event in events.iterrows():
            asset_id = event["asset_id"]

            if event["event_type"] == "transaction":
                qty = float(event["quantity"])
                if event["side"] == "buy":
                    holdings[asset_id] = holdings.get(asset_id, 0.0) + qty
                elif event["side"] == "sell":
                    holdings[asset_id] = holdings.get(asset_id, 0.0) - qty
                continue

            # Process dividend calculations based on current historical ownership state
            current_qty = holdings.get(asset_id, 0.0)
            if current_qty > 0:
                dividend_records.append({
                    "timestamp": event["timestamp"],
                    "amount": float(current_qty * event["dividend_amount"]),
                    "type": "dividend",
                    "reference": event["ticker"]
                })

    dividend_df = pd.DataFrame(dividend_records) if dividend_records else pd.DataFrame(columns=["timestamp", "amount", "type", "reference"])

    # =========================================
    # FINAL CONSOLIDATED MERGE
    # =========================================
    frames = []

    if not cash_df.empty:
        frames.append(cash_df)

    if not trades_df.empty:
        frames.append(trades_df)

    if not dividend_df.empty:
        frames.append(dividend_df)

    if len(frames) == 0:
        return pd.DataFrame(columns=["timestamp", "amount", "type", "reference"])

    unified = pd.concat(frames, ignore_index=True)

    # Cast output formats cleanly into static date layout objects
    unified["timestamp"] = pd.to_datetime(unified["timestamp"]).dt.date
    unified["amount"] = pd.to_numeric(unified["amount"], errors="coerce").fillna(0.0)
    unified["reference"] = unified["reference"].fillna("-").astype(str)
    unified["type"] = unified["type"].fillna("unknown").astype(str).str.lower()

    # Sort chronology: newest operational actions bubble to the top interface view
    unified = unified.sort_values("timestamp", ascending=False).reset_index(drop=True)

    return unified




# for simulating time
def handle_time_jump(new_date, p_id):
    """
    Advances the operational simulation clock, calculates and distributes interim dividends 
    via local DuckDB analytical layer reading from cloud Parquet snapshots, and bulk backfills 
    daily historical performance metrics directly within the cloud database.
    All source documentation and comments are maintained strictly in English.
    """
    logger = logging.getLogger(__name__)
    
    # 1. Enforce structural timeline ceiling boundaries (Yesterday constraint)
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    yesterday_dt = datetime.datetime.combine(yesterday.date(), datetime.time.max)

    if new_date > yesterday_dt:
        st.error("Cannot travel to the future!")
        return False

    engine = get_supabase_engine()
    
    try:
        # =====================================================================
        # STEP 1: FETCH STATE FRAME FROM CLOUD (SUPABASE)
        # =====================================================================
        with engine.begin() as con:
            res = con.execute(
                text("SELECT current_sim_date, available_cash FROM portfolios WHERE portfolio_id = :p_id"),
                {"p_id": p_id}
            ).fetchone()
            
            if not res:
                return False
                
            start_date = res[0]
            current_cash = float(res[1])
            
            # Bypass execution if no forward progression is requested
            if start_date >= new_date:
                return True

            # Extract holding matrix metadata to feed local analytical query scopes
            holdings_res = con.execute(
                text("SELECT asset_id, quantity FROM holdings WHERE portfolio_id = :p_id AND quantity > 0"),
                {"p_id": p_id}
            ).fetchall()
            
            df_holdings = pd.DataFrame(holdings_res, columns=["asset_id", "quantity"])

        # =====================================================================
        # STEP 2: HEAVY LIFTING INSIDE LOCAL LAYER (DUCKDB + PARQUET URL)
        # =====================================================================
        total_dividends = 0.0
        df_history_backfill = pd.DataFrame(columns=["portfolio_id", "timestamp", "portfolio_value", "available_cash"])

        if not df_holdings.empty:
            asset_ids = df_holdings["asset_id"].tolist()
            
            # Direct optimization routing pointing straight to the Google Cloud Storage Parquet file
            div_parquet_url = "https://storage.googleapis.com/stratify-historical-data/data_snapshots/dividends.parquet"
            
            # Vectorized dividend query mapping matching historical holding states
            div_calc_query = f"""
                SELECT d.asset_id, SUM(d.dividend_amount) as total_rate
                FROM '{div_parquet_url}' d
                WHERE d.asset_id IN $asset_list
                  AND d.timestamp > $start_date
                  AND d.timestamp <= $new_date
                GROUP BY d.asset_id
            """
            
            # Ensure DuckDB reads from network endpoints seamlessly
            duckdb.execute("INSTALL httpfs; LOAD httpfs;")
            
            df_div_rates = duckdb.execute(div_calc_query, {
                "asset_list": asset_ids,
                "start_date": start_date,
                "new_date": new_date
            }).df()

            if not df_div_rates.empty:
                df_div_merge = pd.merge(df_holdings, df_div_rates, on="asset_id", how="inner")
                total_dividends = float((df_div_merge["quantity"] * df_div_merge["total_rate"]).sum())

            # Generate dynamic daily time-series performance tracking matrices inside local core
            backfill_matrix_query = """
                WITH date_series AS (
                    SELECT CAST(day_raw AS TIMESTAMP) as day_ts
                    FROM generate_series(
                        CAST($start_date AS TIMESTAMP) + INTERVAL '1 day', 
                        CAST($new_date AS TIMESTAMP), 
                        INTERVAL '1 day'
                    ) AS day_raw
                ),
                daily_prices AS (
                    SELECT 
                        ds.day_ts,
                        h.asset_id,
                        h.quantity,
                        p.close,
                        ROW_NUMBER() OVER (PARTITION BY ds.day_ts, h.asset_id ORDER BY p.timestamp DESC) as rn
                    FROM date_series ds
                    CROSS JOIN df_holdings h
                    JOIN prices p ON p.asset_id = h.asset_id AND p.timestamp <= ds.day_ts
                ),
                daily_valuation AS (
                    SELECT day_ts, SUM(quantity * close) as assets_value
                    FROM daily_prices
                    WHERE rn = 1
                    GROUP BY day_ts
                )
                SELECT 
                    $p_id as portfolio_id,
                    day_ts as timestamp,
                    assets_value + $final_cash as portfolio_value,
                    $final_cash as available_cash
                FROM daily_valuation
            """
            
            final_cash_projection = current_cash + total_dividends
            df_history_backfill = duckdb.execute(backfill_matrix_query, {
                "start_date": start_date,
                "new_date": new_date,
                "p_id": p_id,
                "final_cash": final_cash_projection
            }).df()

        # =====================================================================
        # STEP 3: RE-ENGAGE CLOUD LAYER FOR FINAL WRITE ACTIONS (SUPABASE)
        # =====================================================================
        with engine.begin() as con:
            # Inject calculated global dividend yields into core profile state
            if total_dividends > 0:
                con.execute(
                    text("""
                        UPDATE portfolios 
                        SET available_cash = available_cash + :total_dividends 
                        WHERE portfolio_id = :p_id
                    """),
                    {"total_dividends": total_dividends, "p_id": p_id}
                )

            # Clear overlapping historical record slices to ensure operational idempotency
            con.execute(
                text("""
                    DELETE FROM portfolio_history 
                    WHERE portfolio_id = :portfolio_id 
                      AND timestamp > CAST(:start_date AS TIMESTAMP)
                      AND timestamp <= CAST(:new_date AS TIMESTAMP)
                """),
                {"portfolio_id": p_id, "start_date": start_date, "new_date": new_date}
            )

            # Bulk safe write operations using highly optimized pandas backend to_sql framework
            if not df_history_backfill.empty:
                df_history_backfill["timestamp"] = pd.to_datetime(df_history_backfill["timestamp"])
                df_history_backfill.to_sql(
                    name="portfolio_history",
                    con=con,
                    if_exists="append",
                    index=False,
                    method="multi"
                )

            # Finalize core milestone timeline metrics anchoring step
            con.execute(
                text("UPDATE portfolios SET current_sim_date = :new_date WHERE portfolio_id = :p_id"),
                {"new_date": new_date, "p_id": p_id}
            )

        # Update core Streamlit reactive application state variables layout framework
        st.session_state.current_sim_date = new_date
        st.session_state.current_sim_date_display = new_date.strftime('%d/%m/%Y')
        if 'perf_data' in st.session_state:
            del st.session_state.perf_data
            
        return True

    except Exception as e:
        logger.error(f"Global time jump processing pipeline sequence crashed safely: {e}")
        st.error(f"Time Jump Failed: {e}")
        return False



# for getting recomendations to buy/sell



