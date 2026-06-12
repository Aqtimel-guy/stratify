import logging
import duckdb
import streamlit as st
import datetime
import pandas as pd
import math
import numpy as np
import math
DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'



# for executing cash transactions (withdrawl \ depost)
def execute_cash_transaction(con, portfolio_id, amount, transaction_type, timestamp, reference=None):
    """
    Executes a cash deposit or withdrawal, updates the database,
    and records a portfolio history snapshot.
    
    transaction_type: 'deposit' or 'withdrawal'
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 1. Check current cash balance (crucial for withdrawals)
        res = con.execute("SELECT available_cash FROM portfolios WHERE portfolio_id = ?", [portfolio_id]).fetchone()
        if not res:
            return False, "Portfolio not found"
        
        current_cash = res[0]

        # 2. Validation for withdrawal requests
        if transaction_type == 'withdrawal' and amount > current_cash:
            return False, f"Insufficient funds. Available: ${current_cash:,.2f}"

        # 3. Begin Atomic Database Transaction
        con.execute("BEGIN TRANSACTION")

        # A. Record the event inside the cash_transactions audit ledger table
        con.execute("""
                INSERT INTO cash_transactions (transaction_id, portfolio_id, timestamp, amount, transaction_type, reference)
                VALUES (
                    (SELECT COALESCE(MAX(transaction_id), 0) + 1 FROM cash_transactions),
                    ?, ?, ?, ?, ?
                )
            """, [portfolio_id, timestamp, amount, transaction_type, reference])

        # B. Mutate and update the liquidity balance inside the portfolios table
        cash_change = amount if transaction_type == 'deposit' else -amount
        con.execute("""
            UPDATE portfolios 
            SET available_cash = ROUND(available_cash + ?, 2)
            WHERE portfolio_id = ?
        """, [cash_change, portfolio_id])
        
        # C. Trigger system historical timeline snapshot update
        record_portfolio_snapshot(con, portfolio_id, timestamp)
        
        con.execute("COMMIT")
        logger.info(f"Successfully executed {transaction_type} of ${amount} for portfolio {portfolio_id}")
        return True, f"Successfully {transaction_type}ed ${amount:,.2f}"

    except Exception as e:
        con.execute("ROLLBACK")
        logger.error(f"Cash transaction failed: {e}")
        return False, str(e)

# for executing a trade
def execute_asset_trade(con, portfolio_id, ticker, timestamp, quantity, side='buy'):
    logger = logging.getLogger(__name__)
    
    # --- Step 1: Query relevant data ---
    # (החלק הזה נשאר זהה)
    df_assets = con.execute("SELECT asset_id FROM assets WHERE ticker = ? LIMIT 1", [ticker]).fetchone()
    if not df_assets:
        return False, f"Asset {ticker} not found"
    asset_id = df_assets[0]

    df_prices = con.execute("""
        SELECT close FROM prices 
        WHERE asset_id = ? AND timestamp <= ? 
        ORDER BY timestamp DESC LIMIT 1
    """, [asset_id, timestamp]).fetchone()
    if not df_prices:
        return False, f"Price for {ticker} not found"
    asset_price = df_prices[0]

    df_portfolios = con.execute("SELECT starting_at, available_cash FROM portfolios WHERE portfolio_id = ?", [portfolio_id]).fetchone()
    portfolio_start_day, portfolio_available_cash = df_portfolios

    # --- Step 2: Validations ---
    total_amount = quantity * asset_price
    
    if side == 'buy' and portfolio_available_cash < total_amount:
        return False, "Insufficient funds"

    if side == 'sell':
        df_holdings = con.execute("SELECT quantity FROM holdings WHERE portfolio_id = ? AND asset_id = ?", [portfolio_id, asset_id]).fetchone()
        amount_held = df_holdings[0] if df_holdings else 0
        if amount_held < quantity:
            return False, f"Not enough shares (Held: {amount_held}, Request: {quantity})"

    # --- Step 3: Execute Trade ---
    try:
        con.execute("BEGIN TRANSACTION")

        # 1. Transactions table (שינוי קטן: הוספתי את ה-side לשאילתה שלך)
        con.execute("""
            INSERT INTO assets_transactions (portfolio_id, asset_id, timestamp, quantity, price_per_share, total_value, side)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [portfolio_id, asset_id, timestamp, quantity, asset_price, total_amount, side])

        # 2. Holdings table
        qty_change = quantity if side == 'buy' else -quantity
        con.execute("""
            INSERT INTO holdings (portfolio_id, asset_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT (portfolio_id, asset_id)
            DO UPDATE SET quantity = holdings.quantity + EXCLUDED.quantity
        """, [portfolio_id, asset_id, qty_change])

        # 3. Portfolios (Cash update)
        cash_change = -total_amount if side == 'buy' else total_amount
        con.execute("""
            UPDATE portfolios 
            SET available_cash = ROUND(available_cash + ?, 2)
            WHERE portfolio_id = ?
        """, [cash_change, portfolio_id])

        # 4. Clean up zero holdings (הוספת portfolio_id לביטחון)
        con.execute("DELETE FROM holdings WHERE quantity <= 0 AND portfolio_id = ?", [portfolio_id])
        record_portfolio_snapshot(con, portfolio_id, timestamp)
        con.execute("COMMIT")
        return True, f"Successfully {side} {quantity} shares of {ticker}"

    except Exception as e:
        con.execute("ROLLBACK")
        logger.error(f"Trade failed: {e}")
        return False, str(e)

# for easier performnce analysis
def record_portfolio_snapshot(con, portfolio_id, timestamp):
    """
    מחשבת את השווי הכולל הנוכחי ושומרת שורה ב-portfolio_history.
    """
    # א. חישוב שווי הנכסים (כמות ב-holdings כפול מחיר אחרון ב-prices)
    # שים לב: אנחנו לוקחים את המחיר הכי קרוב ל-timestamp של הסימולציה
    assets_val_query = """
        SELECT SUM(h.quantity * p.close)
        FROM holdings h
        JOIN prices p ON h.asset_id = p.asset_id
        WHERE h.portfolio_id = ?
        AND p.timestamp = (
            SELECT MAX(timestamp) FROM prices 
            WHERE asset_id = h.asset_id AND timestamp <= ?
        )
    """
    assets_value = con.execute(assets_val_query, [portfolio_id, timestamp]).fetchone()[0] or 0.0
    
    # ב. שליפת המזומן הנוכחי
    cash_val = con.execute("SELECT available_cash FROM portfolios WHERE portfolio_id = ?", [portfolio_id]).fetchone()[0]
    
    total_value = assets_value + cash_val
    
    # ג. הכנסה לטבלת ההיסטוריה
    con.execute("""
        INSERT INTO portfolio_history (portfolio_id, timestamp, portfolio_value, available_cash)
        VALUES (?, ?, ?, ?)
    """, [portfolio_id, timestamp, total_value, cash_val])
    
    

# for showing the history of transactions
@st.cache_data(show_spinner=False)
def get_portfolio_cash_history(_con, portfolio_id, sim_date):
    """
    Builds a unified portfolio cash ledger including:

    1. Deposits / withdrawals
    2. Buy / sell transactions
    3. Dividends based on historical holdings ownership

    Optimized with:
    - Streamlit cache
    - Single-pass portfolio simulation
    - Vectorized preprocessing
    """

    # =========================================
    # CASH TRANSACTIONS
    # =========================================
    cash_df = _con.execute("""
        SELECT
            timestamp,
            amount,
            transaction_type AS type,
            reference
        FROM cash_transactions
        WHERE portfolio_id = ?
          AND timestamp <= ?
    """, [portfolio_id, sim_date]).df()

    if not cash_df.empty:
        cash_df["type"] = cash_df["type"].astype(str).str.lower()

    # =========================================
    # ASSET TRANSACTIONS
    # =========================================
    tx_df = _con.execute("""
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
        WHERE t.portfolio_id = ?
          AND t.timestamp <= ?
        ORDER BY t.timestamp ASC
    """, [portfolio_id, sim_date]).df()

    # =========================================
    # DIVIDEND EVENTS
    # =========================================
    div_df = _con.execute("""
        SELECT
            d.asset_id,
            d.timestamp,
            d.dividend_amount,
            a.ticker
        FROM dividends d
        JOIN assets a
            ON d.asset_id = a.asset_id
        WHERE d.timestamp <= ?
        ORDER BY d.timestamp ASC
    """, [sim_date]).df()

    # =========================================
    # EMPTY CASE
    # =========================================
    if cash_df.empty and tx_df.empty and div_df.empty:
        return pd.DataFrame(
            columns=["timestamp", "amount", "type", "reference"]
        )

    # =========================================
    # CLEANING
    # =========================================
    if not tx_df.empty:
        tx_df["timestamp"] = pd.to_datetime(tx_df["timestamp"])
        tx_df["side"] = (
            tx_df["side"]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        tx_df["quantity"] = pd.to_numeric(
            tx_df["quantity"],
            errors="coerce"
        ).fillna(0)

        tx_df["price_per_share"] = pd.to_numeric(
            tx_df["price_per_share"],
            errors="coerce"
        ).fillna(0)

    if not div_df.empty:
        div_df["timestamp"] = pd.to_datetime(div_df["timestamp"])

    if not cash_df.empty:
        cash_df["timestamp"] = pd.to_datetime(cash_df["timestamp"])

    # =========================================
    # BUILD BUY / SELL LEDGER
    # =========================================
    trade_records = []

    if not tx_df.empty:

        for _, tx in tx_df.iterrows():

            trade_value = tx["quantity"] * tx["price_per_share"]

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

    trades_df = pd.DataFrame(trade_records)

    # =========================================
    # BUILD DIVIDEND LEDGER
    # =========================================
    dividend_records = []

    if not tx_df.empty and not div_df.empty:

        # Unified chronological event stream
        tx_events = tx_df.copy()
        tx_events["event_type"] = "transaction"

        div_events = div_df.copy()
        div_events["event_type"] = "dividend"

        events = pd.concat(
            [tx_events, div_events],
            ignore_index=True
        )

        # Critical ordering:
        # transactions BEFORE dividends on same day
        events["priority"] = events["event_type"].map({
            "transaction": 0,
            "dividend": 1
        })

        events = events.sort_values(
            ["timestamp", "priority"]
        )

        # Portfolio holdings state
        holdings = {}

        # Single simulation pass
        for _, event in events.iterrows():

            asset_id = event["asset_id"]

            # ---------------------------------
            # TRANSACTION EVENT
            # ---------------------------------
            if event["event_type"] == "transaction":

                qty = event["quantity"]

                if event["side"] == "buy":
                    holdings[asset_id] = (
                        holdings.get(asset_id, 0) + qty
                    )

                elif event["side"] == "sell":
                    holdings[asset_id] = (
                        holdings.get(asset_id, 0) - qty
                    )

                continue

            # ---------------------------------
            # DIVIDEND EVENT
            # ---------------------------------
            current_qty = holdings.get(asset_id, 0)

            if current_qty > 0:

                dividend_records.append({
                    "timestamp": event["timestamp"],
                    "amount": current_qty * event["dividend_amount"],
                    "type": "dividend",
                    "reference": event["ticker"]
                })

    dividend_df = pd.DataFrame(dividend_records)

    # =========================================
    # FINAL MERGE
    # =========================================
    frames = []

    if not cash_df.empty:
        frames.append(cash_df)

    if not trades_df.empty:
        frames.append(trades_df)

    if not dividend_df.empty:
        frames.append(dividend_df)

    # Handle brand new portfolios safely
    if len(frames) == 0:
        return pd.DataFrame(
            columns=["timestamp", "amount", "type", "reference"]
        )

    unified = pd.concat(frames, ignore_index=True)

    # Keep only date (not full timestamp)
    unified["timestamp"] = (
        pd.to_datetime(unified["timestamp"])
        .dt.date
    )

    # Clean formatting
    unified["amount"] = pd.to_numeric(
        unified["amount"],
        errors="coerce"
    ).fillna(0)

    unified["reference"] = (
        unified["reference"]
        .fillna("-")
        .astype(str)
    )

    unified["type"] = (
        unified["type"]
        .fillna("unknown")
        .astype(str)
        .str.lower()
    )

    # Newest first
    unified = unified.sort_values(
        "timestamp",
        ascending=False
    ).reset_index(drop=True)

    return unified


# for simulating time
def handle_time_jump(new_date, p_id):
    # 1. חישוב תאריך גג (אתמול)
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    yesterday_dt = datetime.datetime.combine(yesterday.date(), datetime.time.max)

    if new_date > yesterday_dt:
        st.error(f"Cannot travel to the future!")
        return False

    con = None
    try:
        con = duckdb.connect(DB_PATH)
        
        # שליפת התאריך הנוכחי
        res = con.execute("SELECT current_sim_date FROM portfolios WHERE portfolio_id = ?", [p_id]).fetchone()
        if not res:
            return False
        start_date = res[0]
        
        # אם אין באמת קפיצה קדימה
        if start_date >= new_date:
            return True

        con.execute("BEGIN TRANSACTION")
        
        # --- NEW: CALCULATE AND UPDATE DIVIDENDS DURING TIME JUMP ---
        # 1. Fetch total dividends earned for current holdings within the time jump window
        dividend_calc_query = """
            SELECT COALESCE(SUM(h.quantity * d.dividend_amount), 0) as total_div
            FROM holdings h
            JOIN dividends d ON h.asset_id = d.asset_id
            WHERE h.portfolio_id = ?
              AND h.quantity > 0
              AND d.timestamp > CAST(? AS DATE)
              AND d.timestamp <= CAST(? AS DATE)
        """
        total_dividends = con.execute(dividend_calc_query, [p_id, start_date, new_date]).fetchone()[0]

        # 2. If dividends were earned, update the user's available cash right now
        if total_dividends > 0:
            con.execute(
                "UPDATE portfolios SET available_cash = available_cash + ? WHERE portfolio_id = ?",
                [total_dividends, p_id]
            )
        # --- END OF NEW CODE ---

        # 2. שאילתת ה-Backfill המשופרת (יציבה יותר)
        # שים לב לשימוש ב-date_trunc וב-CAST מפורש
        backfill_query = """
        INSERT INTO portfolio_history (portfolio_id, timestamp, portfolio_value, available_cash)
        WITH date_series AS (
            -- נותנים שם מפורש לעמודה (day_raw) כדי למנוע את שגיאת ה-Binder
            SELECT CAST(day_raw AS TIMESTAMP) as day_ts
            FROM generate_series(
                CAST(? AS TIMESTAMP) + INTERVAL 1 DAY, 
                CAST(? AS TIMESTAMP), 
                INTERVAL 1 DAY
            ) AS t(day_raw)
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
            WHERE h.portfolio_id = ?
            GROUP BY ds.day_ts
        )
        SELECT 
            ?, 
            dv.day_ts, 
            dv.assets_value + p.available_cash, 
            p.available_cash
        FROM daily_valuation dv
        JOIN portfolios p ON p.portfolio_id = ?
        """
        
        con.execute(backfill_query, [start_date, new_date, p_id, p_id, p_id])
        

        # 3. עדכון תאריך נוכחי בתיק
        con.execute("UPDATE portfolios SET current_sim_date = ? WHERE portfolio_id = ?", [new_date, p_id])
        
        con.execute("COMMIT")
        con.close()

        # עדכון State
        st.session_state.current_sim_date = new_date
        st.session_state.current_sim_date_display = new_date.strftime('%d/%m/%Y')
        if 'perf_data' in st.session_state:
            del st.session_state.perf_data
            
        return True

    except Exception as e:
        if con:
            try:
                con.execute("ROLLBACK")
            except:
                pass # אם הטרנזקציה כבר נסגרה
            con.close()
        st.error(f"Time Jump Failed: {e}")
        return False

# for getting recomendations to buy
def get_closest_assets(con, strategy_id: int, sim_date: str):
    """
    Returns all assets ranked by similarity to the user strategy vector.

    This function is PURE backend logic:
    - Computes similarity
    - Joins metadata
    - Returns FULL sorted dataset

    No filtering, no limits, no UI decisions.
    """

    # ======================================================
    # 1. LOAD USER STRATEGY VECTOR
    # ======================================================
    strategy = con.sql(f"""
        SELECT *
        FROM user_preferences_strategy
        WHERE portfolio_strategy_id = {strategy_id}
    """).df().iloc[0]

    strategy_vector = np.array([
        strategy["momentum_preference"],
        strategy["value_preference"],
        strategy["quality_preference"],
        strategy["growth_preference"],
        strategy["defensive_preference"],
        strategy["size_preference"],
    ])

    # ======================================================
    # 2. LOAD ASSET FACTORS FOR GIVEN DATE
    # ======================================================
    assets_df = con.execute("""
        SELECT
            asset_id,
            momentum_factor_market,
            value_factor_market,
            quality_factor_market,
            growth_factor_market,
            defensive_factor_market,
            size_factor_market
        FROM asset_factors_normalized_final
        WHERE timestamp = (
            SELECT MAX(timestamp)
            FROM asset_factors_normalized_final
            WHERE timestamp <= ?
        )
    """, [sim_date]).df()

    if assets_df.empty:
        return assets_df

    # ======================================================
    # 3. COMPUTE EUCLIDEAN DISTANCE
    # ======================================================
    asset_matrix = assets_df.iloc[:, 1:].to_numpy()

    distances = np.sqrt(
        np.sum(
            (asset_matrix - strategy_vector) ** 2,
            axis=1
        )
    )

    assets_df = assets_df.copy()
    assets_df["distance"] = distances

    # ======================================================
    # 4. MERGE METADATA
    # ======================================================
    assets_meta = con.sql("""
        SELECT asset_id, ticker, sector, industry, name
        FROM assets
    """).df()

    merged_df = assets_df.merge(
        assets_meta,
        on="asset_id",
        how="left"
    )

    # ======================================================
    # 5. RETURN FULL RANKED LIST (NO LIMIT)
    # ======================================================
    return merged_df.sort_values("distance").reset_index(drop=True)


# for getting compleate multi-strategy context
def build_strategy_context(con, portfolio_id: int, sim_date: str):
    """
    Builds the execution context for a portfolio by allocating cash across strategies
    and filtering candidate assets based on market data and user preferences.

    Args:
        con: Database connection object.
        portfolio_id (int): The unique identifier for the portfolio.
        sim_date (str): The date string used for market data lookup.

    Returns:
    dict: A dictionary containing:
        - "meta": global portfolio-level parameters such as fees, deposits,
          investment settings, sector preferences, and available cash.
        - "strategies": a dictionary where keys are strategy IDs and values
          contain:
              - allocated cash for the strategy
              - preference vector (as a dict for debugging clarity)
              - filtered DataFrame of closest tradable assets after preference adjustments
    """
    # ======================================================
    # A.1 LOAD RELEVANT DATA
    # ======================================================

    multi = con.sql(f"""
        SELECT *
        FROM multi_strategy
        WHERE portfolio_id = {portfolio_id}
        ORDER BY multi_strategy_id DESC
        LIMIT 1
    """).df().iloc[0]
    
    prices_df = con.execute("""
        SELECT asset_id, close as price
        FROM prices p
        WHERE p.timestamp = (
            SELECT MAX(p2.timestamp)
            FROM prices p2
            WHERE p2.asset_id = p.asset_id
            AND p2.timestamp <= ?
        )
    """, [sim_date]).df()



    strategies = [
        (multi["strategy_1_id"], multi["strategy_1_pct"]),
        (multi["strategy_2_id"], multi["strategy_2_pct"]),
        (multi["strategy_3_id"], multi["strategy_3_pct"]),
        (multi["strategy_4_id"], multi["strategy_4_pct"]),
    ]

    monthly_deposit = multi["monthly_deposit"]
    initial_investment = multi["initial_investment"]
    buy_fee = multi["buy_fee"]
    sell_fee = multi["sell_fee"]
    deposit_fee = multi["deposit_fee"]
    withdrawal_fee = multi["withdrawal_fee"]
    diversification = multi["diversification"]

    # sector filters (clean handling)
    preferred_sectors = multi["preferred_sectors"]
    excluded_sectors = multi["excluded_sectors"]

    # parse excluded sectors
    if excluded_sectors:
        excluded_sectors = [s.strip() for s in excluded_sectors.split(",")]
    else:
        excluded_sectors = []

    # parse preferred sectors 
    if preferred_sectors:
        preferred_sectors = [s.strip() for s in preferred_sectors.split(",")]
    else:
        preferred_sectors = []

    # ======================================================
    # A.2 AVAILABLE CASH
    # ======================================================

    total_cash = st.session_state.get("current_available_cash")

    if total_cash is None:
        total_cash = con.execute(
            "SELECT available_cash FROM portfolios WHERE portfolio_id = ?",
            [portfolio_id]
        ).fetchone()[0]
        
        
    # ======================================================
    # A.3 META DATA
    # ======================================================
        
        
    meta = {
            "monthly_deposit": monthly_deposit,
            "initial_investment": initial_investment,
            "buy_fee": buy_fee,
            "sell_fee": sell_fee,
            "deposit_fee": deposit_fee,
            "withdrawal_fee": withdrawal_fee,
            "diversification": diversification,
            "preferred_sectors": preferred_sectors,
            "excluded_sectors": excluded_sectors,
            "total_cash": total_cash
        }

    # ======================================================
    # B. BUILD STRATEGY CONTEXT
    # ======================================================

    strategy_context = {}

    for strategy_id, pct in strategies:

        if strategy_id is None or pct == 0:
            continue

        # B.1 ALLOCATE CASH
        cash = total_cash * (pct / 100)

        # B.2 LOAD STRATEGY
        strategy = con.sql(f"""
            SELECT *
            FROM user_preferences_strategy
            WHERE portfolio_strategy_id = {strategy_id}
        """).df().iloc[0]

        # B.3 BUILD STRATEGY VECTOR
        vector = np.array([
            strategy["momentum_preference"],
            strategy["value_preference"],
            strategy["quality_preference"],
            strategy["growth_preference"],
            strategy["defensive_preference"],
            strategy["size_preference"],
        ])
        
        
        
        vector_as_dict = { ## for keeping track of order during development
            "momentum": strategy["momentum_preference"],
            "value": strategy["value_preference"],
            "quality": strategy["quality_preference"],
            "growth": strategy["growth_preference"],
            "defensive": strategy["defensive_preference"],
            "size": strategy["size_preference"],
        }

        # B.4 GET CLOSEST ASSETS
        closest_assets = get_closest_assets(con, strategy_id, sim_date)

        # sector filter
        if excluded_sectors:
            closest_assets = closest_assets[
                ~closest_assets["sector"].isin(excluded_sectors)
            ]
            
        closest_assets = closest_assets.merge(prices_df,on="asset_id",how="left")

        # feasibility filter (price vs cash)
        closest_assets = closest_assets[
            closest_assets["price"] <= cash
        ].reset_index(drop=True)
        
        # B.5 SCORE ASSETS
        
        closest_assets = closest_assets.reset_index(drop=True)
        closest_assets["base_score"] = 1.0 / ((closest_assets.index) / 100 + 1)
        closest_assets["score"] = closest_assets["base_score"]


        if preferred_sectors:

            mask = closest_assets["sector"].isin(preferred_sectors)

            closest_assets.loc[mask, "score"] *= 1.05
            
        # B.6 RE ORDER TABLE BASED ON SCORE AN NOT DIST
        
        closest_assets = closest_assets.sort_values(
                by="score",
                ascending=False
            ).reset_index(drop=True)


        # B.7 STORE CONTEXT
        strategy_context[strategy_id] = {
            "cash": cash,
            "vector": vector,  ### (need to change to vector, now vector_as_dict for development reasons)
            "closest_assets": closest_assets ,
        }
    
    

    return  {"meta": meta, "strategies": strategy_context}




# for dynamic re scoring of relevancy of assets depending on strategy and holdings
def re_score_assets(context, strategy_id, current_step_holdings):
    """
    Re-ranks candidate assets based on current portfolio state.

    This function implements a stateful re-scoring mechanism used inside a greedy
    allocation loop. The goal is to dynamically adjust asset attractiveness based on:

    1. Current asset-level exposure (to avoid over-concentration in single assets)
    2. Current sector-level exposure (to enforce diversification constraints)
    3. Strategy-level diversification settings
    4. Preference bias from the initial context (e.g., preferred sectors)

    The function is intended to be called iteratively during portfolio construction,
    where `current_step_holdings` is updated after each allocation step.

    Args:
        context (dict):
            Full strategy execution context containing:
            - "meta": global portfolio configuration (fees, diversification level, etc.)
            - "strategies": per-strategy asset universe and precomputed scores

        strategy_id (int):
            Identifier of the active strategy.

        current_step_holdings (dict):
            Dictionary mapping:
                asset_id -> current portfolio weight (0..1 or normalized share)

    Returns:
        pd.DataFrame:
            Re-ranked asset universe with updated "score" column.
            Higher score indicates higher priority for allocation.
    """

    ctx = context["strategies"][strategy_id]
    meta = context["meta"]

    df = ctx["closest_assets"].copy().reset_index(drop=True).head(200)

    diversification = meta["diversification"]

    # ======================================================
    # 1. DIVERSIFICATION POLICY PARAMETERS
    # ======================================================

    if diversification == 1:
        max_assets = 10
        a = 0.09
        b = 0.06

    elif diversification == 2:
        max_assets = 25
        a = 0.1
        b = 0.08

    elif diversification == 3:
        max_assets = 40
        a = 0.14
        b = 0.10

    else:
        raise ValueError("Invalid diversification level")

    # ======================================================
    # 2. PORTFOLIO STATE ESTIMATION (FIXED)
    # ======================================================

    asset_exposure = {}
    sector_exposure = {}

    if current_step_holdings:

        asset_to_sector = {
            row["asset_id"]: row["sector"]
            for _, row in df.iterrows()
        }

        for asset_id, shares in current_step_holdings.items():

            if shares <= 0:
                continue

            asset_exposure[asset_id] = shares

            sector = asset_to_sector.get(asset_id)

            if sector is None:
                continue

            sector_exposure[sector] = sector_exposure.get(sector, 0) + shares

    # ======================================================
    # 3. PENALTY FUNCTIONS
    # ======================================================

    def asset_penalty(w):
        return 1 / (1 + a * math.log(1 + w))

    def sector_penalty(w):
        return 1 / (1 + b * math.log(1 + w))

    # ======================================================
    # 4. BASE SCORING
    # ======================================================

    df["score"] = df["base_score"]

    preferred_sectors = meta["preferred_sectors"]

    if preferred_sectors:
        mask = df["sector"].isin(preferred_sectors)
        df.loc[mask, "score"] *= 1.05

    # ======================================================
    # 5. DYNAMIC RE-SCORING
    # ======================================================

    for i, row in df.iterrows():

        asset_id = row["asset_id"]
        sector = row["sector"]

        w_asset = asset_exposure.get(asset_id, 0)
        w_sector = sector_exposure.get(sector, 0)

        penalty = asset_penalty(w_asset) * sector_penalty(w_sector)

        df.loc[i, "score"] *= penalty
        
        
    if len(current_step_holdings) >= max_assets:

        held_assets = set(current_step_holdings.keys())

        df = df[df["asset_id"].isin(held_assets)].reset_index(drop=True)

    # ======================================================
    # 6. FINAL SORTING
    # ======================================================

    df = df.sort_values("score", ascending=False).reset_index(drop=True)

    return df


       
# for actual allocation building
def build_allocation(strategy_id, context, df, cash, current_step_holdings, max_assets=25):
    """
    Greedy portfolio construction engine.

    This function iteratively builds a portfolio by:
    1. Re-scoring candidate assets based on current holdings state
    2. Selecting the best affordable asset
    3. Adding one unit (share) of the selected asset
    4. Updating remaining cash
    5. Repeating until constraints are met

    The process is stateful and dynamic:
    - Each iteration updates holdings
    - Each update triggers a re-scoring step
    - The scoring function reflects diversification pressure and exposure penalties

    Final weights are normalized only at the end of the process.

    Args:
        strategy_id (int):
            Identifier of the active investment strategy.

        context (dict):
            Full execution context containing:
            - meta configuration (diversification, preferences, etc.)
            - strategy-specific asset universe and metadata

        df (pd.DataFrame):
            Candidate assets DataFrame. Must include:
            - asset_id
            - price
            - score (precomputed base score)

        cash (float):
            Total available capital for allocation.

        current_step_holdings (dict):
            Dictionary mapping:
                asset_id -> shares

            where:
                weight: current portfolio weight (0..1, recomputed at end)
                shares: number of units held

        max_assets (int):
            Maximum number of distinct assets allowed in the portfolio.

    Returns:
        dict:
            Updated holdings in the format:
                asset_id -> (final_weight, shares)

            where:
                final_weight is normalized based on total invested capital.
    """
    

    if current_step_holdings is None:
        current_step_holdings = {}

    remaining_cash = cash
    price_map = dict(zip(df["asset_id"], df["price"]))

    df = df.copy().reset_index(drop=True)

    # initial scoring based on empty or partial state
    df = re_score_assets(context, strategy_id, current_step_holdings)

    while True:

        df = df.sort_values("score", ascending=False).reset_index(drop=True)

        bought = False

        for _, row in df.iterrows():

            asset_id = row["asset_id"]
            price = row["price"]

            # skip unaffordable assets
            if price > remaining_cash:
                continue

            # ==========================
            # UPDATE HOLDINGS (GREEDY STEP)
            # ==========================

            if asset_id in current_step_holdings:
                current_step_holdings[asset_id] += 1
            else:
                current_step_holdings[asset_id] = 1

            remaining_cash -= price

            bought = True
            break

        # ==========================
        # TERMINATION CONDITIONS
        # ==========================

        if not bought:
            break

        if remaining_cash <= df["price"].min():
            break

        # re-score after state update
        df = re_score_assets(context, strategy_id, current_step_holdings)

    # ==========================
    # FINAL NORMALIZATION STEP
    # ==========================

    total_invested = cash - remaining_cash

    for asset_id, shares in current_step_holdings.items():

        price = price_map.get(asset_id)

        current_step_holdings[asset_id] = (
            (price * shares) / total_invested,
            shares
        )
        
    buy_fee = context["meta"]["buy_fee"]
    sell_fee = context["meta"]["sell_fee"]
    min_position_value = 50 * max(buy_fee , sell_fee)
    
    # ==========================
    # MIN POSITION VALUE FILTER
    # ==========================
    def min_position_filter(current_step_holdings):

        while True:

            # ==========================
            # CALCULATE CURRENT VALUES
            # ==========================

            asset_values = {
                asset_id: price_map[asset_id] * shares
                for asset_id, (_, shares) in current_step_holdings.items()
            }

            violating_assets = [
                aid for aid, val in asset_values.items()
                if val < min_position_value
            ]

            if not violating_assets:
                break

            # ==========================
            # COMPUTE FREED VALUE (BEFORE DELETION)
            # ==========================

            freed_value = sum(asset_values[aid] for aid in violating_assets)

            # ==========================
            # REMOVE VIOLATIONS
            # ==========================

            for aid in violating_assets:
                del current_step_holdings[aid]

            if not current_step_holdings:
                break

            # ==========================
            # FIND WEAKEST REMAINING ASSET
            # ==========================

            asset_values = {
                asset_id: price_map[asset_id] * shares
                for asset_id, (_, shares) in current_step_holdings.items()
            }

            weakest_asset = min(asset_values, key=asset_values.get)

            # ==========================
            # REDISTRIBUTE FREED VALUE
            # ==========================

            price = price_map[weakest_asset]

            extra_shares = int(freed_value // price)

            if extra_shares > 0:
                weight, shares = current_step_holdings[weakest_asset]

                current_step_holdings[weakest_asset] = (
                    weight,
                    shares + extra_shares
                )

        return current_step_holdings
        
    
    return min_position_filter(current_step_holdings)        
            

