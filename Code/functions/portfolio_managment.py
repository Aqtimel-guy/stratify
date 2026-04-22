import duckdb
import datetime
import logging
import streamlit as st
import pandas as pd
from .db_manager import capture_portfolio_snapshot , get_data
DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'


# for creating a portfolio 
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
        if portfolio_count > 9:
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
    
# for deleting a portfolio 
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
    
# for going forward in time of the simulation
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
    
# for FIFO tracking 
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

