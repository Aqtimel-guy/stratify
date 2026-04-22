import logging
import duckdb
import streamlit as st
import datetime
DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'



# for executing cash transactions (withdrawl \ depost)
def execute_cash_transaction(con, portfolio_id, amount, transaction_type, timestamp):
    """
    מבצעת הפקדה או משיכה של מזומן ומעדכנת את ה-DB.
    transaction_type: 'deposit' או 'withdrawal'
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 1. בדיקת יתרה נוכחית (רלוונטי בעיקר למשיכה)
        res = con.execute("SELECT available_cash FROM portfolios WHERE portfolio_id = ?", [portfolio_id]).fetchone()
        if not res:
            return False, "Portfolio not found"
        
        current_cash = res[0]

        # 2. ולידציה למשיכה
        if transaction_type == 'withdrawal' and amount > current_cash:
            return False, f"Insufficient funds. Available: ${current_cash:,.2f}"

        # 3. תחילת טרנזקציה
        con.execute("BEGIN TRANSACTION")

        # א. רישום בטבלת cash_transactions
        con.execute("""
                INSERT INTO cash_transactions (transaction_id, portfolio_id, timestamp, amount, transaction_type)
                VALUES (
                    (SELECT COALESCE(MAX(transaction_id), 0) + 1 FROM cash_transactions), -- מייצר את ה-ID הבא
                    ?, ?, ?, ?
                )
            """, [portfolio_id, timestamp, amount, transaction_type])

        # ב. עדכון היתרה בטבלת portfolios
        cash_change = amount if transaction_type == 'deposit' else -amount
        con.execute("""
            UPDATE portfolios 
            SET available_cash = ROUND(available_cash + ?, 2)
            WHERE portfolio_id = ?
        """, [cash_change, portfolio_id])
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