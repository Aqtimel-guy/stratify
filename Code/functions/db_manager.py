import duckdb
import streamlit as st
import logging
import time

DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'



# for easy querying 
def get_data(query, params=None):
    # 1. בדיקה אם קיים חיבור פעיל בסטייט
    con = st.session_state.con
    if params:
        return con.execute(query, params).df()
    return con.execute(query).df()
    
# for getting assets details 
def get_asset_snapshot(con, ticker, sim_date):
    """
    שולפת מידע מקיף על נכס ספציפי נכון לזמן הסימולציה,
    כולל תאריך תחילת מסחר במידה והמניה עדיין לא קיימת בתאריך המבוקש.
    """
    # 1. שליפת מידע בסיסי מה-Assets
    asset_info = con.execute("""
        SELECT asset_id, ticker, name, sector, industry
        FROM assets
        WHERE ticker = ?
    """, [ticker.upper()]).fetchone()
    
    if not asset_info:
        return None

    asset_id, ticker_name, name, sector, industry = asset_info

    # 2. שליפת המחיר האחרון הזמין (לפני או ביום הסימולציה)
    price_info = con.execute("""
        SELECT close, timestamp
        FROM prices
        WHERE asset_id = ? AND timestamp <= ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, [asset_id, sim_date]).fetchone()

    current_price = price_info[0] if price_info else None

    # 3. שליפת התאריך הראשון בו המניה נסחרה (עבור הודעת שגיאה ידידותית)
    first_date_info = con.execute("""
        SELECT MIN(timestamp) 
        FROM prices 
        WHERE asset_id = ?
    """, [asset_id]).fetchone()
    
    first_trade_date = first_date_info[0] if first_date_info else None

    # 4. בדיקה אם יש אחזקות קיימות בתיק הנוכחי
    portfolio_id = st.session_state.get('current_portfolio_id')
    shares_held = 0
    if portfolio_id:
        holding_info = con.execute("""
            SELECT quantity
            FROM holdings
            WHERE portfolio_id = ? AND asset_id = ?
        """, [portfolio_id, asset_id]).fetchone()
        shares_held = holding_info[0] if holding_info else 0

    return {
        "asset_id": asset_id,
        "ticker": ticker_name,
        "name": name,
        "sector": sector,
        "industry": industry,
        "current_price": current_price,
        "first_trade_date": first_trade_date, # תאריך תחילת מסחר
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
    מחשבת את השווי הכולל של התיק ושומרת שורה בטבלת ההיסטוריה.
    """
    # 1. חישוב שווי התיק (מזומן + שווי שוק של מניות)
    # אני מניח שיש לך פונקציה כזו, אם לא - נשתמש בחישוב מהיר:
    total_value = portfolio_value_calculator(portfolio_id, sim_date)
    
    # 2. שליפת המזומן הפנוי בלבד
    cash_res = con.execute("SELECT available_cash FROM portfolios WHERE portfolio_id = ?", [portfolio_id]).fetchone()
    available_cash = cash_res[0] if cash_res else 0
    
    # 3. שמירה להיסטוריה
    # אנחנו משתמשים ב-UPSERT (INSERT ON CONFLICT) כדי שאם מריצים פעמיים באותו יום, זה פשוט יעדכן
    con.execute("""
        INSERT INTO portfolio_history (portfolio_id, timestamp, portfolio_value, available_cash)
        VALUES (?, ?, ?, ?)
    """, [portfolio_id, sim_date, total_value, available_cash])


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
    this function will calculate the value of a portfolio
    
    tables:
    1. portfolios
    2. holdings
    3. prices
    
    """
        
    logger = logging.getLogger(__name__)
    if con is None:
        con = st.session_state.con
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
        
        
        
