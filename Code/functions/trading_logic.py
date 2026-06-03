import logging
import duckdb
import streamlit as st
import datetime
import pandas as pd
import math
from .db_manager import *
from sqlalchemy import text

DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'



# for executing cash transactions (withdrawl \ depost)
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
        # SQLAlchemy manages transactions via contexts. If the connection isn't already 
        # in a transaction block, we initialize an explicit transaction checkpoint wrapper.
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
            # Routed to use our updated safe clean-up snapshot module function
            capture_portfolio_snapshot(con, portfolio_id, timestamp)
            
            # CRITICAL FIX: Explicitly commit connection mutations if operating 
            # within a pre-existing transaction block to ensure data persists in Supabase.
            if tx:
                tx.commit()
            else:
                con.commit()
                
            logger.info(f"Successfully executed {transaction_type} of ${amount} for portfolio {portfolio_id}")
            return True, f"Successfully {transaction_type}ed ${amount:,.2f}"

        except Exception as inner_error:
            # Safely rollback mutations if this process instance owns the context block
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
def execute_asset_trade(con, portfolio_id, ticker, timestamp, quantity, side='buy'):
    """
    Executes an asset trade (buy/sell), updates the core portfolios liquidity ledger,
    modifies asset positioning frames, and captures a historical snapshot.
    All source documentation and comments are maintained strictly in English.
    
    side: 'buy' or 'sell'
    """
    logger = logging.getLogger(__name__)
    
    try:
        # --- Step 1: Query relevant data using cloud-native parameters ---
        asset_res = con.execute(
            text("SELECT asset_id FROM assets WHERE ticker = :ticker LIMIT 1"), 
            {"ticker": ticker}
        ).fetchone()
        
        if not asset_res:
            return False, f"Asset {ticker} not found"
        asset_id = asset_res[0]

        price_res = con.execute(
            text("""
                SELECT close FROM prices 
                WHERE asset_id = :asset_id AND timestamp <= :timestamp 
                ORDER BY timestamp DESC LIMIT 1
            """), 
            {"asset_id": asset_id, "timestamp": timestamp}
        ).fetchone()
        
        if not price_res:
            return False, f"Price for {ticker} not found"
        asset_price = float(price_res[0])

        portfolio_res = con.execute(
            text("SELECT starting_at, available_cash FROM portfolios WHERE portfolio_id = :portfolio_id"), 
            {"portfolio_id": portfolio_id}
        ).fetchone()
        
        if not portfolio_res:
            return False, "Portfolio not found"
            
        portfolio_start_day, portfolio_available_cash = portfolio_res
        portfolio_available_cash = float(portfolio_available_cash)

        # --- Step 2: Structural Validations ---
        total_amount = quantity * asset_price
        
        if side == 'buy' and portfolio_available_cash < total_amount:
            return False, "Insufficient funds"

        if side == 'sell':
            holding_res = con.execute(
                text("SELECT quantity FROM holdings WHERE portfolio_id = :portfolio_id AND asset_id = :asset_id"), 
                {"portfolio_id": portfolio_id, "asset_id": asset_id}
            ).fetchone()
            
            amount_held = float(holding_res[0]) if holding_res else 0.0
            if amount_held < quantity:
                return False, f"Not enough shares (Held: {amount_held}, Request: {quantity})"

        # --- Step 3: Atomic Transaction Lifecycle Execution ---
        is_nested = con.in_transaction()
        tx = None if is_nested else con.begin()

        try:
            # A. Record the operational ledger event inside the assets_transactions audit table
            # Primary key serial sequencing handling for cloud transactional environments
            max_id_res = con.execute(
                text("SELECT COALESCE(MAX(transaction_id), 0) FROM assets_transactions")
            ).fetchone()
            next_transaction_id = int(max_id_res[0]) + 1

            con.execute(
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
            
            # Safe checking routine to bypass constraint mismatches across engine instances
            existing_holding = con.execute(
                text("SELECT quantity FROM holdings WHERE portfolio_id = :portfolio_id AND asset_id = :asset_id"),
                {"portfolio_id": portfolio_id, "asset_id": asset_id}
            ).fetchone()

            if existing_holding:
                con.execute(
                    text("""
                        UPDATE holdings 
                        SET quantity = quantity + :qty_change
                        WHERE portfolio_id = :portfolio_id AND asset_id = :asset_id
                    """),
                    {"qty_change": qty_change, "portfolio_id": portfolio_id, "asset_id": asset_id}
                )
            else:
                con.execute(
                    text("""
                        INSERT INTO holdings (portfolio_id, asset_id, quantity)
                        VALUES (:portfolio_id, :asset_id, :qty_change)
                    """),
                    {"portfolio_id": portfolio_id, "asset_id": asset_id, "qty_change": qty_change}
                )

            # C. Adjust liquidity balances inside the portfolios framework
            cash_change = -total_amount if side == 'buy' else total_amount
            con.execute(
                text("""
                    UPDATE portfolios 
                    SET available_cash = ROUND(CAST(available_cash + :cash_change AS NUMERIC), 2)
                    WHERE portfolio_id = :portfolio_id
                """), 
                {"cash_change": cash_change, "portfolio_id": portfolio_id}
            )

            # D. Architectural cleanup: Purge empty zeroed inventory assets
            con.execute(
                text("DELETE FROM holdings WHERE quantity <= 0 AND portfolio_id = :portfolio_id"), 
                {"portfolio_id": portfolio_id}
            )
            
            # E. Trigger historical ledger timeline update snapshot
            capture_portfolio_snapshot(con, portfolio_id, timestamp)
            
            # Finalize operational cycle commit if owned by current invocation frame
            if tx:
                tx.commit()
                
            return True, f"Successfully {side} {quantity} shares of {ticker}"

        except Exception as inner_error:
            if tx:
                tx.rollback()
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
def get_portfolio_cash_history(_con, portfolio_id, sim_date):
    """
    Builds a unified portfolio cash ledger directly from the Supabase cloud instance.
    Processes deposits/withdrawals, trade impacts, and historical dividend allocations.
    
    Optimized with:
    - Streamlit cache layer mapping
    - Single-pass dynamic portfolio state simulation
    - Vectorized pandas ledger cleaning pipelines
    All comments and documentation are maintained strictly in English.
    """
    logger = logging.getLogger(__name__)

    # =========================================
    # CASH TRANSACTIONS
    # =========================================
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
    
    cash_res = _con.execute(cash_query, {"portfolio_id": portfolio_id, "sim_date": sim_date}).fetchall()
    
    if cash_res:
        cash_df = pd.DataFrame(cash_res, columns=["timestamp", "amount", "type", "reference"])
        cash_df["type"] = cash_df["type"].astype(str).str.lower()
    else:
        cash_df = pd.DataFrame(columns=["timestamp", "amount", "type", "reference"])

    # =========================================
    # ASSET TRANSACTIONS
    # =========================================
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
    
    tx_res = _con.execute(tx_query, {"portfolio_id": portfolio_id, "sim_date": sim_date}).fetchall()
    
    if tx_res:
        tx_df = pd.DataFrame(tx_res, columns=["timestamp", "asset_id", "ticker", "quantity", "price_per_share", "side"])
    else:
        tx_df = pd.DataFrame(columns=["timestamp", "asset_id", "ticker", "quantity", "price_per_share", "side"])

    # =========================================
    # DIVIDEND EVENTS
    # =========================================
    div_query = text("""
        SELECT
            d.asset_id,
            d.timestamp,
            d.dividend_amount,
            a.ticker
        FROM dividends d
        JOIN assets a
            ON d.asset_id = a.asset_id
        WHERE d.timestamp <= :sim_date
        ORDER BY d.timestamp ASC
    """)
    
    div_res = _con.execute(div_query, {"sim_date": sim_date}).fetchall()
    
    if div_res:
        div_df = pd.DataFrame(div_res, columns=["asset_id", "timestamp", "dividend_amount", "ticker"])
    else:
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
        # Construct unified chronological event framework flow
        tx_events = tx_df.copy()
        tx_events["event_type"] = "transaction"

        div_events = div_df.copy()
        div_events["event_type"] = "dividend"

        events = pd.concat([tx_events, div_events], ignore_index=True)

        # Critical prioritizing map: process execution transactions BEFORE tracking dividends on matching days
        events["priority"] = events["event_type"].map({"transaction": 0, "dividend": 1})
        events = events.sort_values(["timestamp", "priority"])

        # Track holdings inventory states across the time horizon
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
    Advances the operational simulation clock, calculates and distributes interim dividends,
    and bulk backfills daily historical performance metrics directly within the cloud database.
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
        # CRITICAL FIX: Use engine.begin() directly to manage both connection 
        # lifespan and transaction atomicity in a single non-overlapping scope.
        with engine.begin() as con:
            # Fetch current chronological simulation state anchor point
            res = con.execute(
                text("SELECT current_sim_date FROM portfolios WHERE portfolio_id = :p_id"),
                {"p_id": p_id}
            ).fetchone()
            
            if not res:
                return False
                
            start_date = res[0]
            
            # Bypass execution block if no forward progression is requested
            if start_date >= new_date:
                return True

            # --- CALCULATE AND UPDATE DIVIDENDS DURING TIME JUMP ---
            # Aggregate total dividends earned for current holdings within the time jump window
            dividend_calc_query = text("""
                SELECT COALESCE(SUM(h.quantity * d.dividend_amount), 0) as total_div
                FROM holdings h
                JOIN dividends d ON h.asset_id = d.asset_id
                WHERE h.portfolio_id = :p_id
                  AND h.quantity > 0
                  AND d.timestamp > CAST(:start_date AS DATE)
                  AND d.timestamp <= CAST(:new_date AS DATE)
            """)
            
            total_dividends = float(
                con.execute(
                    dividend_calc_query, 
                    {"p_id": p_id, "start_date": start_date, "new_date": new_date}
                ).fetchone()[0]
            )

            # If dividend earnings are captured, inject capital liquidity back into the ledger profile
            if total_dividends > 0:
                con.execute(
                    text("""
                        UPDATE portfolios 
                        SET available_cash = available_cash + :total_dividends 
                        WHERE portfolio_id = :p_id
                    """),
                    {"total_dividends": total_dividends, "p_id": p_id}
                )

            # --- HISTORICAL LEDGER SLICE TIME-SERIES BACKFILL ---
            # Pre-clean target time horizon slices to secure idempotent transaction commits
            con.execute(
                text("""
                    DELETE FROM portfolio_history 
                    WHERE portfolio_id = :portfolio_id 
                      AND timestamp > CAST(:start_date AS TIMESTAMP)
                      AND timestamp <= CAST(:new_date AS TIMESTAMP)
                """),
                {"portfolio_id": p_id, "start_date": start_date, "new_date": new_date}
            )

            # Standardized cloud-optimized daily time-series backfill calculation matrix layout
            backfill_query = text("""
                INSERT INTO portfolio_history (portfolio_id, timestamp, portfolio_value, available_cash)
                WITH date_series AS (
                    SELECT CAST(day_raw AS TIMESTAMP) as day_ts
                    FROM generate_series(
                        CAST(:start_date AS TIMESTAMP) + INTERVAL '1 day', 
                        CAST(:new_date AS TIMESTAMP), 
                        INTERVAL '1 day'
                    ) AS day_raw
                ),
                daily_valuation AS (
                    SELECT 
                        ds.day_ts,
                        COALESCE(SUM(h.quantity * (
                            SELECT p.close FROM prices p 
                            WHERE p.asset_id = h.asset_id 
                              AND p.timestamp <= ds.day_ts 
                            ORDER BY p.timestamp DESC LIMIT 1
                        )), 0) as assets_value
                    FROM date_series ds
                    CROSS JOIN holdings h
                    WHERE h.portfolio_id = :p_id
                    GROUP BY ds.day_ts
                )
                SELECT 
                    :p_id, 
                    dv.day_ts, 
                    dv.assets_value + p.available_cash, 
                    p.available_cash
                FROM daily_valuation dv
                JOIN portfolios p ON p.portfolio_id = :p_id
            """)
            
            con.execute(
                backfill_query, 
                {"start_date": start_date, "new_date": new_date, "p_id": p_id}
            )

            # Update master simulation timeline timestamp index inside the profiles table
            con.execute(
                text("UPDATE portfolios SET current_sim_date = :new_date WHERE portfolio_id = :p_id"),
                {"new_date": new_date, "p_id": p_id}
            )
            
            # The engine context manager will automatically commit here upon successful exit

        # Update core Streamlit reactive application state variables layout framework
        st.session_state.current_sim_date = new_date
        st.session_state.current_sim_date_display = new_date.strftime('%d/%m/%Y')
        if 'perf_data' in st.session_state:
            del st.session_state.perf_data
            
        return True

    except Exception as e:
        logger.error(f"Global time jump processing pipeline sequence crashed: {e}")
        st.error(f"Time Jump Failed: {e}")
        return False
    
# for getting recomendations to buy/sell



