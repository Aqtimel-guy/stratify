import streamlit as st
import duckdb
import pandas as pd
import datetime
import re
import logging
import time
import bcrypt
import plotly.graph_objects as go



# for runing tests 
# python -m streamlit run "C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Code\old versions\before_function_order(and_some_bugs).py"

# #### CONFIGURATION & DATABASE ####


st.set_page_config(page_title="Stratify 2026", layout="wide")

DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'



# ############################################################################################
# #### 1. operation functions
# ############################################################################################

# for easy querying (done)
def get_data(query, params=None):
    with duckdb.connect(DB_PATH) as con:
        if params:
            x = con.execute(query, params).df()
            con.close()
            return x
        x = con.execute(query).df()
        con.close()
        return x
    
# for moving between pages (done)
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()
    
 
# for logging in   (done)
def loggin_func(email , password_hash):
    
    """
    user give their ID data to log in
    if the data is correct returns a dict with users data
    if there is no match of email \ password - return FALSE
    """
        
    df_loggin = get_data("""SELECT user_id , email , password_hash 
                            FROM users
                            WHERE
                            email = ?
                            LIMIT 1
                         """ , [email])
    
    # checing if EMAIL exists
    if df_loggin.empty:
        st.warning("Unknown Email")
        return False
    
    # checking if password matches
    if df_loggin.iloc[0]['password_hash'] != password_hash:
        st.warning("Wrong password")
        return False
    
    #returning 
    return df_loggin.iloc[0]['user_id'] 
    
# for registration  (done)
def registration_func(email , first_name , middle_name ,last_name , date_of_birth , password_hash):
    """
    this function check the arg's , and update the DB with our new user
    if somthing fails, returns FALSE
    
    """
    logger = logging.getLogger(__name__)
    
    #### first validating args ####

    # --- Email validation ---
    if not email or not isinstance(email, str):
        return False
    
    email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_pattern, email):
        return False

    # --- First name validation ---
    if not first_name or not isinstance(first_name, str):
        return False
        # --- First name validation ---
    if middle_name and not isinstance(middle_name, str):
        return False
    
    if len(first_name.strip()) < 2:
        return False

    # --- Last name validation ---
    if not last_name or not isinstance(last_name, str):
        return False
    
    if len(last_name.strip()) < 2:
        return False

    # --- Date of birth validation ---
    if not isinstance(date_of_birth, (datetime.date, datetime.datetime)):
        return False
    
    
    # --- Password hash validation ---
    if not password_hash or not isinstance(password_hash, str):
        return False
    

    #### if everything passed ####
    con = duckdb.connect(DB_PATH)
    
    # cheack if Email is available
    df_email = con.execute("""
                           SELECT 1 FROM users
                           WHERE email = ?
                           LIMIT 1
                           """ ,[email]).df()
    if not df_email.empty:
        logger.warning("Email is already has an account")
        con.close()
        return False
        
    # creating a new user in the DB
    try:
        con.execute("""
                    INSERT INTO users (
                    user_id, 
                    email, 
                    first_name, 
                    middle_name, 
                    last_name, 
                    date_of_birth, 
                    password_hash
                        )
                        VALUES (
                            (SELECT COALESCE(MAX(user_id), 0) + 1 FROM users), -- for ID
                            ?, ?, ?, ?, ?, ? )
                        """, [email, first_name, middle_name, last_name, date_of_birth, password_hash])
    except Exception as e:
        logger.error(f"DB Error {e}")
        con.close()
        return False
    # logging and closing connection
    logger.info("new user have been registerd successfuly")
    con.close()
    return True
    
# for creating a portfolio (done)
def create_portfolio(user_id ,portfolio_name ,starting_at):
    """
    creating a portfolio in portfolios page
    
    """
    logger = logging.getLogger(__name__)
    con = duckdb.connect(DB_PATH)
    today = datetime.date.today() 
    today_datetime = datetime.datetime.combine(today, datetime.time.min)
       
    # Validation
    try:
        # Validating user
        user_exists = con.execute("SELECT 1 FROM users WHERE user_id = ?", [user_id]).fetchone()
        if not user_exists:
            logger.warning(f"Validation Failed: User ID {user_id} does not exist.")
            con.close()
            return False, "User not found."
        # each user is limited fo 10 portoflios max
        portfolio_count = con.execute("SELECT COUNT(*) FROM portfolios WHERE user_id = ?", [user_id]).fetchone()[0]
        if portfolio_count > 10:
            logger.warning(f"Validation Failed: User {user_id} reached portfolio limit (10).")
            con.close()
            return False, "You have reached the maximum limit of 10 portfolios."
        # Validating dates
        if starting_at > today:
            logger.warning(f"Validation Failed: Starting date {starting_at} is in the future.")
            con.close()
            return False, "Starting date cannot be in the future."

        # the same user cannot have 2 portfolios with the same name
        name_exists = con.execute("SELECT 1 FROM portfolios WHERE user_id = ? AND portfolio_name = ?", 
                                     [user_id, portfolio_name]).fetchone()
        if name_exists:
            con.close()
            return False, f"You already have a portfolio named '{portfolio_name}'."
        
    # creating portfolio in DB
        # Id creation
        portfolio_id = con.execute("SELECT COALESCE(MAX(portfolio_id), 0) + 1 FROM portfolios").fetchone()[0]
            
        con.execute("""
            INSERT INTO portfolios (portfolio_id, user_id, portfolio_name, created_at, starting_at, available_cash, portfolio_value, current_sim_date)
                VALUES (?, ?, ?, ?, ?, ?, ?,?)
            """, [
                portfolio_id, 
                user_id, 
                portfolio_name, 
                today_datetime,          # created_at תמיד היום
                starting_at, 
                0, 
                0 ,
                starting_at
            ])
            
        logger.info(f"Portfolio '{portfolio_name}' created successfully for user {user_id}.")
        capture_portfolio_snapshot(con , portfolio_id , starting_at)
        con.close()
        return True, "Portfolio created successfully!"

    except Exception as e:
        logger.error(f"Database error during portfolio creation: {e}")
        con.close()
        return False, "An internal error occurred. Please try again."
    
# for deleting a portfolio (done)
def delete_portfolio(portfolio_id):
    """
    Deletes a portfolio and all its associated data (history, holdings, transactions).
    """
    logger = logging.getLogger(__name__)
    con = duckdb.connect(DB_PATH)
    
    try:
        # 1. בדיקה אם הפורטפוליו קיים
        portfolio_exists = con.execute(
            "SELECT portfolio_name FROM portfolios WHERE portfolio_id = ?", 
            [portfolio_id]
        ).fetchone()
        
        if not portfolio_exists:
            logger.warning(f"Delete Failed: Portfolio ID {portfolio_id} does not exist.")
            con.close()
            return False, "Portfolio not found."
        
        p_name = portfolio_exists[0]

        # 2. מחיקת נתונים מטבלאות מקושרות (Foreign Key Constraints)
        # סדר המחיקה חשוב! קודם הטבלאות התלויות
        
        # מחיקת היסטוריית ערך התיק (הטבלה החדשה שיצרנו)
        con.execute("DELETE FROM portfolio_history WHERE portfolio_id = ?", [portfolio_id])
        
        # מחיקת אחזקות נוכחיות
        con.execute("DELETE FROM holdings WHERE portfolio_id = ?", [portfolio_id])
        
        # מחיקת היסטוריית טרנזקציות (מזומן ונכסים)
        con.execute("DELETE FROM cash_transactions WHERE portfolio_id = ?", [portfolio_id])
        con.execute("DELETE FROM assets_transactions WHERE portfolio_id = ?", [portfolio_id])
        
        # 3. מחיקת הפורטפוליו עצמו מהטבלה הראשית
        con.execute("DELETE FROM portfolios WHERE portfolio_id = ?", [portfolio_id])
        
        logger.info(f"Portfolio '{p_name}' (ID: {portfolio_id}) and all associated data deleted successfully.")
        
        # 4. ניקוי ה-session_state במידה והפורטפוליו שנמחק הוא זה שכרגע בשימוש
        if st.session_state.get('current_portfolio_id') == portfolio_id:
            st.session_state.current_portfolio_id = None
            st.session_state.current_portfolio_name = None
            # אם יש לך משתנים נוספים כמו current_available_cash, כדאי לאפס גם אותם
            if 'current_available_cash' in st.session_state:
                st.session_state.current_available_cash = 0.0

        con.close()
        return True, f"Portfolio '{p_name}' deleted successfully!"
    
    except Exception as e:
        logger.error(f"Database error during portfolio deletion: {e}")
        if con:
            con.close()
        return False, f"Error deleting portfolio: {str(e)}"
    
# for going forward in time of the simulation (done)
def move_time_forward(portfolio_id, amount_of_time="1d"):
    con = duckdb.connect(DB_PATH)
    
    # 1. שליפת התאריך הנוכחי
    current_data = get_data("SELECT current_sim_date FROM portfolios WHERE portfolio_id = ?", [portfolio_id])
    if current_data.empty:
        con.close()
        return False, "Portfolio not found"
    
    current_sim_date = current_data.iloc[0]['current_sim_date']
    
    # המרה ל-datetime במידת הצורך
    if isinstance(current_sim_date, pd.Timestamp):
        current_sim_date = current_sim_date.to_pydatetime()

    # --- ה-BIZ החדש: שמירת סנאפשוט לפני שזזים קדימה ---
    # זה מבטיח שבגרף תהיה נקודה על התאריך שבו היינו עד עכשיו
    capture_portfolio_snapshot(con, portfolio_id, current_sim_date)

    # 2. חישוב תאריך חדש
    offset = pd.tseries.frequencies.to_offset(amount_of_time)
    new_sim_date = current_sim_date + offset

    # 3. בדיקת חריגה (לא לעבור את היום הריאלי)
    today_real = datetime.datetime.now()
    if new_sim_date > today_real:
        new_sim_date = today_real

    # 4. עדכון בסיס הנתונים בתאריך החדש
    con.execute("UPDATE portfolios SET current_sim_date = ? WHERE portfolio_id = ?", [new_sim_date, portfolio_id])
    
    # עדכון ה-session_state כדי שה-UI יתעדכן מיד
    st.session_state.current_current_sim_date = new_sim_date
    
    con.close()
    return True, new_sim_date  
    
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

# for getting assets details (done)
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

# for getting all the data over an asset up to a sim_time (done)
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

# for the assets serch component (done)
def asset_search_component(con):
    """מנהלת את החיפוש ושומרת את הבחירה ב-State"""
    
    # טעינה ראשונית של הרשימה ל-Cache
    if 'all_assets_list' not in st.session_state:
        assets_df = con.execute("SELECT ticker, name FROM assets").df()
        st.session_state.all_assets_list = [f"{row['ticker']} | {row['name']}" for _, row in assets_df.iterrows()]

    st.subheader("🔍 Find an Asset")
    
    selected_option = st.selectbox(
        "Search by Ticker or Company Name",
        options=[""] + st.session_state.all_assets_list,
        format_func=lambda x: "Type to search..." if x == "" else x,
        index=0,
        key="strategy_search_box"
    )

    if selected_option:
        st.session_state.selected_ticker_for_analysis = selected_option.split(" | ")[0]


# for desplaying asset card (done)
def display_asset_card(asset):
    """מציגה את נתוני הנכס בצורה ויזואלית יפה עם בדיקת זמינות"""
    
    # בדיקה אם המניה נסחרת בתאריך הנוכחי
    if asset['current_price'] is None:
        first_date = asset['first_trade_date']
        # עיצוב התאריך אם הוא קיים
        date_str = first_date.strftime('%Y-%m-%d') if hasattr(first_date, 'strftime') else str(first_date)
        
        st.warning(f"⚠️ המנייה **{asset['ticker']}** לא נסחרה בזמן זה.")
        st.info(f"היא התחילה להיסחר בתאריך: **{date_str}**")
        
        # עדיין נציג את שם החברה למעלה כדי שהמשתמש ידע מה הוא מצא
        st.subheader(f"{asset['name']} ({asset['ticker']})")
        return # יוצאים מהפונקציה כדי לא לנסות להציג מחיר ריק

    # אם יש מחיר - מציגים רגיל
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.metric("Price", f"${asset['current_price']:,.2f}")
    
    with col2:
        st.subheader(f"{asset['name']} ({asset['ticker']})")
        st.caption(f"Sector: {asset['sector']} | Industry: {asset['industry']}")

    if st.button(f"Analyze {asset['ticker']} deeper"):
        st.session_state.last_inspected_ticker = asset['ticker']

# for executing cash transactions (withdrawl \ depost) (done)
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

        con.execute("COMMIT")
        logger.info(f"Successfully executed {transaction_type} of ${amount} for portfolio {portfolio_id}")
        return True, f"Successfully {transaction_type}ed ${amount:,.2f}"

    except Exception as e:
        con.execute("ROLLBACK")
        logger.error(f"Cash transaction failed: {e}")
        return False, str(e)

# for showing cash managment (done)
def show_cash_management_ui():
    # פתיחת חיבור בתחילת הפונקציה
    con = duckdb.connect(DB_PATH)
    
    try:
        st.subheader("💰 Cash Management")
        col1, col2 = st.columns(2)
        
        with col1:
            with st.popover("➕ Deposit Cash", use_container_width=True):
                dep_amount = st.number_input("Amount to Deposit", min_value=1.0, step=100.0, key="dep_val")
                if st.button("Confirm Deposit"):
                    success, msg = execute_cash_transaction(
                        con, 
                        st.session_state.current_portfolio_id, 
                        dep_amount, 
                        'deposit', 
                        st.session_state.current_current_sim_date
                    )
                    if success:
                        st.success(msg)
                        # סוגרים לפני ה-rerun כי הוא קוטע את ריצת הפונקציה
                        con.close()
                        st.rerun()
                    else:
                        st.error(msg)

        with col2:
            with st.popover("➖ Withdraw Cash", use_container_width=True):
                with_amount = st.number_input("Amount to Withdraw", min_value=1.0, step=100.0, key="with_val")
                if st.button("Confirm Withdrawal"):
                    success, msg = execute_cash_transaction(
                        con, 
                        st.session_state.current_portfolio_id, 
                        with_amount, 
                        'withdrawal', 
                        st.session_state.current_current_sim_date
                    )
                    if success:
                        st.success(msg)
                        con.close()
                        st.rerun()
                    else:
                        st.error(msg)
                        
    finally:
        # זה מבטיח שהחיבור ייסגר גם אם לא לחצו על כלום 
        # וגם אם קרתה שגיאה לא צפויה בקוד
        try:
            con.close()
        except:
            pass # אם הוא כבר נסגר ב-rerun, שלא יקרוסד

# for showing purchese (done)
def show_buy_component(con, ticker, asset_price):
    """
    קומפוננטת רכישה מאורגנת עם אישור דו-שלבי.
    נכנסת לשימוש בתוך Strategy Builder או בכל מקום אחר.
    """
    portfolio_id = st.session_state.get('current_portfolio_id')
    sim_date = st.session_state.get('current_current_sim_date')
    
    # 1. שליפת מזומן עדכני מה-DB (Source of Truth)
    res = con.execute("SELECT available_cash FROM portfolios WHERE portfolio_id = ?", [portfolio_id]).fetchone()
    current_cash = res[0] if res else 0

    with st.popover(f"🛒 Buy {ticker}", use_container_width=True):
        st.subheader(f"Purchase {ticker}")
        st.write(f"Cash Available: **${current_cash:,.2f}**")
        
        # 2. חישוב כמות מקסימלית (שלמה)
        max_shares = int(current_cash // asset_price) if asset_price > 0 else 0
        
        if max_shares <= 0:
            st.warning("Insufficient funds to buy this asset.")
            return

       # 3. בחירת שיטת קנייה והזנה
        buy_method = st.radio("Buy by:", ["Quantity", "Total price ($)"], horizontal=True, key=f"method_{ticker}")

        if buy_method == "Quantity":
            # הזנה לפי כמות מניות
            qty = st.number_input("Quantity to Buy", min_value=1, max_value=max_shares, step=1, key=f"buy_qty_{ticker}")
            total_cost = qty * asset_price
        else:
            # הזנה לפי סכום כספי
            max_budget = float(current_cash)
            amount_to_spend = st.number_input(
                "Amount to Spend ($)", 
                min_value=float(asset_price), 
                max_value=max_budget, 
                value=min(1000.0, max_budget), # ברירת מחדל או 1000 או המקסימום שיש
                step=100.0, 
                key=f"buy_amount_{ticker}"
            )
            # חישוב אוטומטי של כמות המניות המקסימלית בתקציב (עיגול למטה)
            qty = int(amount_to_spend // asset_price)
            total_cost = qty * asset_price

        # 4. מנגנון אישור דו-שלבי
        confirm_key = f"confirm_buy_{ticker}"
        
        if not st.session_state.get(confirm_key):
            # שלב א': כפתור סקירה
            if st.button("Review Order", use_container_width=True, type="secondary"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            # שלב ב': אישור סופי
            st.warning(f"Are you sure? Buy {qty} units of {ticker}?")
            col_a, col_b = st.columns(2)
            
            with col_a:
                if st.button("✅ Confirm", type="primary", use_container_width=True):
                    # ביצוע הטרייד בפועל
                    success, msg = execute_asset_trade(con, portfolio_id, ticker, sim_date, qty, side='buy')
                    
                    # איפוס הדגל
                    st.session_state[confirm_key] = False
                    
                    if success:
                        st.toast(f"Success! Bought {qty} shares of {ticker}.")
                        con.close()
                        st.rerun() # סוגר את ה-Popover ומחזיר לעמוד
                    else:
                        st.error(msg)
            
            with col_b:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state[confirm_key] = False
                    st.rerun()

# for showing holding positions (done)
def render_holdings_table(con, portfolio_id, sim_date):
    st.subheader("🏢 Current Holdings (FIFO)")

    # 1. שליפת כל הטרנזקציות ההיסטוריות לחישוב FIFO
    tx_query = """
    SELECT asset_id, quantity, price_per_share, side, timestamp
    FROM assets_transactions
    WHERE portfolio_id = ? AND timestamp <= ?
    ORDER BY timestamp, transaction_id
    """
    all_tx = con.execute(tx_query, [portfolio_id, sim_date]).df()

    # 2. שליפת האחזקות הנוכחיות
    holdings_query = """
    SELECT a.asset_id, a.ticker, a.name, h.quantity
    FROM holdings h
    JOIN assets a ON h.asset_id = a.asset_id
    WHERE h.portfolio_id = ? AND h.quantity > 0
    """
    holdings_df = con.execute(holdings_query, [portfolio_id]).df()

    if holdings_df.empty:
        st.info("Your portfolio is currently empty.")
        return

    # כותרות הטבלה
    header_cols = st.columns([1, 2, 1, 1, 1, 1, 1.2])
    cols_names = ["Ticker", "Name", "Qty", "Avg Buy", "Current", "Value", "Action"]
    for col, name in zip(header_cols, cols_names):
        col.markdown(f"**{name}**")
    st.divider()

    for _, row in holdings_df.iterrows():
        asset_id = row['asset_id']
        ticker = row['ticker']
        available_qty = int(row['quantity'])
        
        # א) חישוב FIFO
        asset_tx = all_tx[all_tx['asset_id'] == asset_id]
        avg_buy_price = calculate_fifo_avg_price(asset_tx)
        
        # ב) שליפת מחיר עדכני
        current_price = con.execute("""
            SELECT close FROM prices 
            WHERE asset_id = ? AND timestamp <= ? 
            ORDER BY timestamp DESC LIMIT 1
        """, [asset_id, sim_date]).fetchone()[0]

        total_value = available_qty * current_price
        pnl_perc = ((current_price / avg_buy_price) - 1) * 100 if avg_buy_price > 0 else 0

        # ג) רינדור השורה
        cols = st.columns([1, 2, 1, 1, 1, 1, 1.2])
        cols[0].write(ticker)
        cols[1].write(row['name'])
        cols[2].write(f"{available_qty:,}")
        cols[3].write(f"${avg_buy_price:,.2f}")
        cols[4].write(f"${current_price:,.2f}")
        cols[5].write(f"${total_value:,.2f}")
        
        pnl_color = "green" if pnl_perc >= 0 else "red"
        cols[5].caption(f":{pnl_color}[{pnl_perc:+.2f}%]")
        
        # ד) מנגנון מכירה חסין
        with cols[6]:
            with st.popover("📉 Sell", use_container_width=True):
                st.write(f"Available to sell: **{available_qty}**")
                
                # הסרנו את max_value כדי למנוע תיקון אוטומטי של Streamlit
                sell_qty = st.number_input(
                    "Quantity to sell", 
                    min_value=1, 
                    value=available_qty, 
                    step=1, 
                    key=f"s_input_{ticker}"
                )
                
                if st.button("Confirm Sale", key=f"btn_s_{ticker}", type="primary", use_container_width=True):
                    # בדיקת חסימה ידנית
                    if sell_qty > available_qty:
                        st.error(f"❌ Cannot sell {sell_qty}. You only have {available_qty} shares.")
                    else:
                        success, msg = execute_asset_trade(
                            con, portfolio_id, ticker, sim_date, sell_qty, side='sell'
                        )
                        if success:
                            st.success("Sold!")
                            st.rerun()
                        else:
                            st.error(msg)

    st.divider()


# for plotting graphs (done)
def render_performance_chart(df, title="Performance Over Time", y_label="Value ($)"):
    """
    מייצרת גרף אינטראקטיבי של ביצועים עם כפתורי בחירת טווח זמן.
    df: DataFrame עם עמודות 'timestamp' ו-'value'
    """
    if df.empty:
        st.warning("No data available for the chart.")
        return

    # יצירת הגרף
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['value'],
        mode='lines',
        line=dict(width=2, color='#1f77b4'),
        fill='tozeroy', # הוספת הצללה מתחת לקו (נראה מקצועי יותר)
        name=y_label
    ))

    # הגדרת עיצוב וכפתורי טווח זמן
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title=y_label,
        template="plotly_white",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(step="all", label="ALL")
                ])
            ),
            rangeslider=dict(visible=False), # אפשר להפוך ל-True אם רוצים סליידר למטה
            type="date"
        )
    )

    # הצגה ב-Streamlit
    st.plotly_chart(fig, use_container_width=True)

    
# for recording snapshots of portfolios (done)
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

# for FIFO tracking (done)
def calculate_fifo_avg_price(transactions):
    """
    מחשב מחיר קנייה ממוצע לפי שיטת FIFO
    transactions: DataFrame עם העמודות quantity, price_per_share, side
    """
    buys = [] # רשימה של שכבות קנייה: [כמות, מחיר]
    
    for _, tx in transactions.iterrows():
        qty = tx['quantity']
        price = tx['price_per_share']
        
        if tx['side'] == 'buy':
            buys.append([qty, price])
        else:
            # מכירה: מורידים מהקניות המוקדמות ביותר (FIFO)
            while qty > 0 and buys:
                if buys[0][0] <= qty:
                    qty -= buys[0][0]
                    buys.pop(0) # השכבה חוסלה לגמרי
                else:
                    buys[0][0] -= qty # הורדנו רק חלק מהשכבה
                    qty = 0
                    
    # חישוב ממוצע משוקלל למה שנשאר
    remaining_qty = sum(b[0] for b in buys)
    if remaining_qty == 0:
        return 0
    
    total_cost = sum(b[0] * b[1] for b in buys)
    return total_cost / remaining_qty

# for executing a trade (done)
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

        con.execute("COMMIT")
        return True, f"Successfully {side} {quantity} shares of {ticker}"

    except Exception as e:
        con.execute("ROLLBACK")
        logger.error(f"Trade failed: {e}")
        return False, str(e)

# for calculating portfolio's Value at a given time (done)
def portfolio_value_calculator(portfolio_id , timestamp):
    
    """
    this function will calculate the value of a portfolio
    
    tables:
    1. portfolios
    2. holdings
    3. prices
    
    """
    
     # connecting to DB and loggin
    con = duckdb.connect('C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb')
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

    con.close()
    
    return round(total_portfolio_value , 2)
    

# ############################################################################################
# #### 2. pages
# ############################################################################################


# if unknown page - back to loggin 
if "page" not in st.session_state:
    st.error("oops, somthing went wrong. please log in again") # explaining that you need to return to loggin page
    st.session_state.page = "login_page"
    
    
    
    
###################### GENERAL PAGES ###################

######### ------ LogIn Page --------- ##############
def show_login_page():
    
    # title and appearnce
    st.markdown("<h1 style='text-align: center;'>Login to Stratify</h1>", unsafe_allow_html=True)
    st.write("---")
    
    #  Form approach for loggin
    with st.form("login_form"):
        st.write("Please enter your credentials:")
        
        user_email = st.text_input("Email", placeholder="example@mail.com")
        user_password = st.text_input("Password", type="password")
    
    
        submit_button_loggin = st.form_submit_button("Login")
        
        # if pressing loggin
        if submit_button_loggin:
            if not user_email or not user_password:
                st.warning("Please fill in all fields.")
            else:
                user_id = loggin_func(user_email, user_password)
            
            if user_id != False:
                # שמירת הנתונים ב-Session
                st.session_state.user_id = user_id
                st.session_state.logged_in = True
                
                # מעבר לעמוד הבא
                st.success("Logged in successfully!")
                go_to("home_page")
            else:
                st.error("Login failed. Check your details.")

    
    #   redirecting for registration
    if st.button("For registration"):
        go_to("regestration_page")
        
        
    #   if forgot password
    if st.button("forgot my password"):
        go_to("password_recovery_page")

      
  
######### ------ Registration Page --------- ##############

def show_registration_page():
    
    # title and appearnce
    st.markdown("<h1 style='text-align: center;'>Registare to Stratify</h1>", unsafe_allow_html=True)
    st.write("---")
    
    #  Form approach for registration
    with st.form("registration_form"):
        st.write("Please enter your credentials:")  
        
        first_name =  st.text_input("First name", placeholder="John")
        middle_name = st.text_input("Middle name", placeholder="Who knows nothing")
        last_name = st.text_input("Last name", placeholder="Snow")
        user_email = st.text_input("Email", placeholder="example@mail.com")
        user_password = st.text_input("Password", type="password")
        today = datetime.date.today()
        hundred_years_ago = today.replace(year=today.year - 100)
        date_of_birth = st.date_input(
            "Date of Birth",
            value=datetime.date(2000, 1, 1),
            min_value=hundred_years_ago,    
            max_value=today,                
            help="Click to open the calendar and select your birth date"
        )
        
        submit_button = st.form_submit_button("Register")

        
        ## Validations
        if submit_button:
            # 1. הגדרת משתנה עזר לבדיקה
            is_valid = True
            
            # 2. בדיקת שדות חובה (בלי middle_name שהוא רשות)
            if not first_name.strip() or not last_name.strip() or not user_email.strip() or not user_password.strip():
                st.error("All mandatory fields must be filled.")
                is_valid = False
            
            # 3. ולידציה לאימייל בעזרת RegEx
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if is_valid and not re.match(email_pattern, user_email):
                st.error("Please enter a valid email address (e.g., name@domain.com).")
                is_valid = False
                
            if is_valid and not get_data("""
                           SELECT 1 FROM users
                           WHERE email = ?
                           LIMIT 1
                           """ ,[user_email]).empty:
                st.error("Email is already in use art Stratify")
                is_valid = False
                
            # 4. בדיקת חוזק סיסמה (למשל לפחות 8 תווים)
            if is_valid and len(user_password) < 8:
                st.error("Password is too short! Must be at least 8 characters.")
                is_valid = False
        

            # --- שליחה סופית רק אם הכל עבר ---
            if is_valid:
                # כאן אנחנו קוראים לפונקציה שכותבת ל-DB
                # שים לב שאנחנו שולחים None אם השם האמצעי ריק
                m_name = middle_name.strip() if middle_name.strip() else None
                
                success = registration_func(
                    user_email, first_name, m_name, last_name, date_of_birth, user_password)
                
                
                if success:
                    st.session_state.reg_success = True
                    st.success("Success!")
                    st.write(f"Moving to: login_page") # בדיקה: האם זה מודפס?
                    go_to("login_page")
                else:
                    st.error("Something went wrong in the function")
 

    if st.button("Back to loggin"):
        go_to("login_page")


######### ------ Home Page --------- ##############



def show_home_page():
    
    # retriving data from DB over the users account
    first_name = get_data("""
             select first_name 
             from users
             where user_id = ?
             """ , [int(st.session_state.user_id)]).iloc[0,0]

    # headline

    
    st.markdown(f"<h1 style='text-align: center;'>Welcome back, {first_name}! 👋</h1>", unsafe_allow_html=True)
    st.write("---")
    
    st.subheader("What would you like to do today?")
    st.write("") # מרווח קטן

    # יצירת שלוש עמודות לאפשרויות השונות
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 📈 Stock Market")
        st.write("Analyze real-time data, view charts, and explore market trends.")
        if st.button("Explore Stocks", use_container_width=True):
            go_to("asset_selection") # או השם שנתת לעמוד המניות

    with col2:
        st.markdown("### 💼 My Portfolios")
        st.write("Track your investments, performance, and asset allocation.")
        if st.button("View Portfolios", use_container_width=True):
            go_to("portfolios") # או עמוד ייעודי לפורטפוליו

    with col3:
        st.markdown("### 🚀 Coming Soon")
        st.write("We are working on AI insights and crypto tracking. Stay tuned!")
        st.button("More Features", disabled=True, use_container_width=True)

    st.write("---")
    
    # אפשר להוסיף כאן "תקציר" קטן של השוק או חדשות
    st.info("💡 **Pro Tip:** Don't forget to check your risk distribution in the dashboard!")

    # כפתור התנתקות בתחתית
    if st.sidebar.button("Logout"):
        st.session_state.clear() # מנקה את כל הנתונים
        go_to("login_page")
    return


#### ------- portfolios Page -------- ###########

def show_portfolios_page():
    st.markdown("<h1 style='text-align: center;'>💼 My Portfolios</h1>", unsafe_allow_html=True)
    st.write("---")

    user_id = int(st.session_state.user_id)
    user_portfolios = get_data("""
        SELECT 
            portfolio_id, 
            portfolio_name, 
            available_cash, 
            starting_at,
            current_sim_date
        FROM portfolios
        WHERE user_id = ?
    """, [user_id])

    if user_portfolios.empty:
        st.info("No portfolios found. Start by creating your first strategy!")
    else:
        cols = st.columns(2) 
        for index, row in user_portfolios.iterrows():
            with cols[index % 2]:
                st.markdown(f"### 📁 {row['portfolio_name']}")
                
                # תצוגת תאריכים בצורה נכונה (בלי $ ובלי פורמט של מספר)
                start_dt = row['starting_at'].strftime('%Y-%m-%d') if pd.notnull(row['starting_at']) else "N/A"
                curr_dt = row['current_sim_date'].strftime('%Y-%m-%d') if pd.notnull(row['current_sim_date']) else "N/A"
                
                st.write(f"📅 **Start Date:** {start_dt}")
                st.write(f"⏳ **Current Sim Date:** {curr_dt}")
                
                # חישוב שווי פורטפוליו (שים לב: העברת ערכים ולא רשימות של מחרוזות)
                try:
                    p_value = portfolio_value_calculator(row['portfolio_id'], row['current_sim_date'])
                    st.write(f"💰 **Value:** ${p_value:,.2f}")
                except Exception as e:
                    st.write(f"💰 **Value:** Error calculating")

                if st.button(f"Enter Portfolio: {row['portfolio_name']}", key=f"btn_{row['portfolio_id']}", use_container_width=True):
                    st.session_state.current_portfolio_id = row['portfolio_id']
                    st.session_state.current_portfolio_name = row['portfolio_name']
                    st.session_state.current_starting_at = row['starting_at']
                    st.session_state.current_current_sim_date = row["current_sim_date"]
                    # תיקון שם המפתח ל-starting_at כפי שמופיע ב-SQL
                    st.session_state.current_portfolio_starting_at = row['starting_at']
                    go_to("dashboard_home")
                    
                ## and delete button with popover for confirmation
                with st.popover(f"🗑️ Delete: {row['portfolio_name']}", use_container_width=True):
                    st.warning("⚠️ **Warning:** This action is permanent! There is no way to recover this portfolio once deleted.")
    
                  # כפתור האישור הסופי נמצא בתוך התיבה
                    confirm_delete = st.button(f"Yes, I'm sure. Delete '{row['portfolio_name']}'", 
                                key=f"confirm_del_{row['portfolio_id']}", 
                                type="primary", # צבע בולט (אדום בד"כ) כדי לסמן סכנה
                                use_container_width=True)
        
                    if confirm_delete:
                        success, message = delete_portfolio(row['portfolio_id'])
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

    st.write("---")

    # 3. כפתורי פעולה בתחתית
    col_a, col_b = st.columns(2)
    
    with col_a:
        # שימוש ב-popover יוצר כפתור שפותח תפריט מעליו, זה נראה מעולה ב-UI
        with st.popover("➕ Create New Portfolio", use_container_width=True):
            st.write("### New Portfolio Details")
            with st.form("create_new_portfolio_form", clear_on_submit=True):
                new_name = st.text_input("Portfolio Name", placeholder="e.g., Retirement Strategy")
                # הוספתי את התאריך כפי שביקשת בלוגיקה
                start_date = st.date_input("Simulation Start Date", 
                           value=datetime.date.today(),
                           min_value=datetime.date(2000 , 2 , 2),
                           max_value=datetime.date.today())
                
                submit_create = st.form_submit_button("Create Now", use_container_width=True)
                
                if submit_create:
                    if not new_name:
                        st.error("Please enter a name.")
                    else:
                        # קריאה לפונקציה שכתבת!
                        success, message = create_portfolio(user_id, new_name, start_date)
                        if success:
                            st.success(message)
                            st.rerun() # מרענן את הדף כדי שהכרטיס החדש יופיע מיד
                        else:
                            st.error(message)

    with col_b:
        if st.button("🏠 Back to Home", use_container_width=True):
            go_to("home_page")
        
        
#####################  ----- dashboard ------  #############################################
def dashboard_sidebar():
    with st.sidebar:
        st.title("🛡️ Stratify Menu")
        
        # שליפת נתונים בסיסיים
        p_name = st.session_state.get('current_portfolio_name', 'Unknown')
        p_id = st.session_state.get('current_portfolio_id')
        
        # עיצוב תאריכים בצורה בטוחה
        start_date = st.session_state.get('current_starting_at')
        sim_date = st.session_state.get('current_current_sim_date') # וודא שזה השם המדויק ב-state
        
        fmt_start = start_date.strftime('%d/%m/%Y') if hasattr(start_date, 'strftime') else "Unknown"
        fmt_sim = sim_date.strftime('%d/%m/%Y') if hasattr(sim_date, 'strftime') else "Unknown"

        st.subheader(f"Portfolio: {p_name}")
        st.caption(f"📅 Started: {fmt_start}")
        st.info(f"⏳ Currently at: {fmt_sim}")
        
        st.write("---")
        
        # --- חלק ניהול זמן (מכונת זמן) ---
        st.write("**Time Machine**")
        
        # שורה ראשונה: יום וחודש
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 1 Day", use_container_width=True):
                success, result = move_time_forward(p_id, "1d")
                if success:
                    st.session_state.current_current_sim_date = result
                    st.rerun()
        
        with col2:
            if st.button("➕ 1 Month", use_container_width=True):
                success, result = move_time_forward(p_id, "1ME")
                if success:
                    st.session_state.current_current_sim_date = result
                    st.rerun()

        # שורה שנייה: שנה ובחירה חופשית
        col3, col4 = st.columns(2)
        with col3:
            if st.button("➕ 1 Year", use_container_width=True):
                success, result = move_time_forward(p_id, "1YE") # YE עבור Year End
                if success:
                    st.session_state.current_current_sim_date = result
                    st.rerun()
        
        with col4:
            # 1. בחירת התאריך (נשמר בזיכרון זמני של הווידג'ט)
            min_d = st.session_state.get('current_current_sim_date')
            picked_date = st.date_input(
                "Jump to", 
                value=min_d, 
                min_value=min_d, 
                max_value=datetime.datetime.now(), 
                label_visibility="collapsed",
                key="date_picker_input" # מפתח ייחודי למניעת התנגשויות
            )
            
            # 2. כפתור אישור קטן מתחת ללוח השנה
            # אנחנו בודקים אם התאריך שנבחר שונה מהתאריך הנוכחי
            current_date_only = min_d.date() if hasattr(min_d, 'date') else min_d
            
            if picked_date != current_date_only:
                if st.button("✅ Confirm Jump", use_container_width=True, type="primary"):
                    # ביצוע העדכון רק לאחר לחיצה
                    con = duckdb.connect(DB_PATH)
                    new_dt = datetime.datetime.combine(picked_date, datetime.time.min)
                    
                    con.execute("""
                        UPDATE portfolios 
                        SET current_sim_date = ? 
                        WHERE portfolio_id = ?
                    """, [new_dt, p_id])
                    
                    st.session_state.current_current_sim_date = new_dt
                    con.close()
                    
                    st.success(f"Jumped to {picked_date}")
                    st.rerun()

        st.write("---")
        
        # --- ניווט פנימי ---
        if st.button("🏠 Dashboard Home", use_container_width=True):
            go_to("dashboard_home")
            
        if st.button("📈 Performance Analysis", use_container_width=True):
            go_to("portfolio_performance_analysis")
            
        if st.button("🛠️ Strategy Builder", use_container_width=True):
            go_to("portfolio_strategy_builder")
                
        if st.button("🔍 Data Explorer (Advanced)", use_container_width=True):
            go_to("data_explorer")
        
        st.write("---")
        
        # --- יציאה ---
        if st.button("🔙 Back to All Portfolios", use_container_width=True, type="secondary"):
            st.session_state.current_portfolio_id = None
            st.session_state.current_portfolio_name = None
            go_to("portfolios")





def show_dashboard_home(user_id , portfolio_id):
    st.markdown(f"<h1 style='text-align: center;'>📊 Dashboard for Portfolio {st.session_state.current_portfolio_name}</h1>", unsafe_allow_html=True)
    st.write("---")
    
    ## dashboard sidebar
    dashboard_sidebar()
    
# 1. שליפת הנתונים מה-DB
    # הוספנו את user_id לשאילתה כדי לוודא הרשאה כבר ברמת ה-SQL
    portfolio_data = get_data("""
        SELECT portfolio_name, portfolio_value, available_cash, created_at , starting_at , current_sim_date 
        FROM portfolios 
        WHERE portfolio_id = ? AND user_id = ?
    """, [portfolio_id, user_id])

    # 2. טיפול בשגיאת ה-ValueError (בדיקה אם חזרו נתונים)
    if portfolio_data.empty:
        st.error("⚠️ Portfolio not found or access denied.")
        if st.button("Return to My Portfolios"):
            st.session_state.page = "portfolios"
            st.rerun()
        return

    # 3. חילוץ נתונים (שימוש ב-iloc כדי למנוע אמביוולנטיות)
    p_name = portfolio_data.iloc[0]['portfolio_name']
    p_value = portfolio_value_calculator(portfolio_id , portfolio_data.iloc[0]['current_sim_date'] )
    p_cash = portfolio_data.iloc[0]['available_cash']
    st.session_state.current_available_cash = p_cash
    p_created = portfolio_data.iloc[0]['created_at']
    p_starting = portfolio_data.iloc[0]['starting_at']
    
    # 4. שליפת האחזקות (Holdings)
    holdings_data = get_data("""
        SELECT 
            asset_id , quantity
        FROM
            holdings
        WHERE
            portfolio_id = ?
    """, [portfolio_id])
    

    
    

    # --- תצוגת התוכן המרכזי ---
    st.markdown(f"<h1 style='text-align: center;'>📊 {p_name}</h1>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='text-align: center;'>📊 {'BULBUL'}</h1>", unsafe_allow_html=True)

  
    
    st.write("---")

    # תצוגת מדדים בולטים
    col1, col2, col3 = st.columns(3)
    
    # חישוב לדוגמה של אחוז מזומן מהתיק
    cash_ratio = (p_cash / p_value * 100) if p_value > 0 else 0
    
    col1.metric("Total Value", f"${p_value:,.2f}")
    col2.metric("Available Cash", f"${p_cash:,.2f}", f"{cash_ratio:.1f}% of total")
    col3.metric("Daily Change", "$0.00", "0.0%") # נמלא את זה כשנחבר נתוני שוק

    st.write("---")

    con = duckdb.connect(DB_PATH)
    
    # הצגת כפתורי הפקדה/משיכה
    show_cash_management_ui()
    
    st.write("---")
    
    # הצגת טבלת האחזקות
    sim_date = st.session_state.current_current_sim_date
    render_holdings_table(con, portfolio_id, sim_date)
    
    con.close()




    
#############################################
def show_portfolio_performance_analysis():
    dashboard_sidebar()
    # 1. חילוץ המשתנים הדרושים מה-session_state (כאן היה החוסר)
    portfolio_id = st.session_state.get('current_portfolio_id')
    sim_date = st.session_state.get('current_current_sim_date')
    
    # בדיקת בטיחות - אם המשתמש לא בחר פורטפוליו, שלא יקרוס
    if not portfolio_id:
        st.error("Please select a portfolio first.")
        return

    con = duckdb.connect(DB_PATH)
    
    # 2. השאילתה (שים לב שהמשתנים עכשיו מוגדרים)
    query = """
    SELECT timestamp, portfolio_value as value
    FROM portfolio_history
    WHERE portfolio_id = ? AND timestamp <= ?
    ORDER BY timestamp
    """
    
    try:
        df_perf = con.execute(query, [portfolio_id, sim_date]).df()
        
        # 3. קריאה לפונקציית הגרף שבנינו קודם
        render_performance_chart(df_perf, title="Portfolio Performance History")
    except Exception as e:
        st.error(f"Could not load performance data: {e}")
    finally:
        con.close()
    
    
####################################
def show_strategy_builder():
    dashboard_sidebar()
    st.title("🛠️ Strategy Builder")
    
    con = duckdb.connect(DB_PATH)
    
    # 1. חיפוש (כבר פונקציה נפרדת)
    asset_search_component(con)

    # 2. הצגת פרטי הנכס ורכישה
    if st.session_state.get('selected_ticker_for_analysis'):
        ticker = st.session_state.selected_ticker_for_analysis
        asset = get_asset_snapshot(con, ticker, st.session_state.current_current_sim_date)
        
        if asset:
            display_asset_card(asset) # מציג את המחיר והנתונים
            
            # אם יש מחיר - נציג את קומפוננטת הרכישה
            if asset['current_price']:
                st.write("---")
                show_buy_component(con, ticker, asset['current_price'])
    
    con.close()




##################################
def show_data_explorer():
    pass 
    

# ############################################################################################
# #### 3. Router
# ############################################################################################

if st.session_state.page == "login_page":
    show_login_page()
    
elif st.session_state.page == "home_page":
    show_home_page()
    
elif st.session_state.page == "dashboard_home":
    user_id = st.session_state.get('user_id')
    portfolio_id = st.session_state.get('current_portfolio_id')
    
    if user_id is not None and portfolio_id is not None:
        show_dashboard_home(int(user_id), int(portfolio_id))
    else:
        st.warning("Please select a portfolio first.")
        st.session_state.page = "portfolios"
        st.rerun()
    
elif st.session_state.page == "portfolio_performance_analysis":
    show_portfolio_performance_analysis()
    
elif st.session_state.page == "portfolio_strategy_builder":
    show_strategy_builder()


elif st.session_state.page =="Data_explorer":
    show_data_explorer()
    
elif st.session_state.page == "regestration_page":
    show_registration_page()
    
elif st.session_state.page == "portfolios":
    show_portfolios_page()
    
else:
    # אם הגעת לכאן, תדע בדיוק מה הערך ה"שגוי"
    st.error(f"Page '{st.session_state.page}' not found in Router!")
    if st.button("Emergency Back to Login"):
        st.session_state.page = "login_page"
        st.rerun()
        
        
        
        
        
