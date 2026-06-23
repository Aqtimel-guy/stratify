import streamlit as st
from .db_manager import get_data
import logging
import datetime
import re
import duckdb
import bcrypt
DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'

# for incripting the password
def hash_password(password: str) -> str:
    """הופכת סיסמה רגילה ל-Hash מאובטח"""
    # הפיכת הסטרינג לבייטים
    password_bytes = password.encode('utf-8')
    # יצירת Salt והצפנה
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    # החזרה כסטרינג כדי שנוכל לשמור ב-DuckDB
    return hashed.decode('utf-8')

# for decripting the password
def check_password(password: str, hashed_password: str) -> bool:
    """בודקת אם הסיסמה שהוזנה תואמת ל-Hash השמור"""
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'), 
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False
    
# for logging in   
def loggin_func(email, entered_password):
    """
    user give their ID data to log in
    if the data is correct returns the user_id , first_name
    if there is no match of email / password - return FALSE
    """
    
    # We only fetch the data by email first
    df_loggin = get_data("""SELECT user_id, first_name ,email, password_hash 
                            FROM users
                            WHERE
                            email = ?
                            LIMIT 1
                         """, [email])
    
    # checking if EMAIL exists
    if df_loggin.empty:
        st.warning("Unknown Email")
        return None , None
    
    # Extract the stored hash from the database
    stored_hash = df_loggin.iloc[0]['password_hash']
    
    # checking if password matches using bcrypt
    # bcrypt.checkpw expects bytes, so we encode both the password and the hash
    if not bcrypt.checkpw(entered_password.encode('utf-8'), stored_hash.encode('utf-8')):
        st.warning("Wrong password")
        return None , None
    
    # returning user_id if everything is correct
    return df_loggin.iloc[0]['user_id'] , df_loggin.iloc[0]['first_name'] 
    
    
# for registration  
def registration_func(email, first_name, middle_name, last_name, date_of_birth, raw_password , raw_password_confirm):
    """
    this function check the arg's, and update the DB with our new user
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
    
    # --- Password validation and hashing ---
    if not raw_password or not isinstance(raw_password, str) or len(raw_password) < 6:
        logger.warning("Password does not meet security requirements")
        return False
    if not raw_password == raw_password_confirm:
        logger.warning("Password confirmation must be identical to your password")
    # Hashing the password before saving to DB
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(raw_password.encode('utf-8'), salt).decode('utf-8')

    #### if everything passed ####
    con = st.session_state.con
    
    # check if Email is available
    df_email = con.execute("""
                           SELECT 1 FROM users
                           WHERE email = ?
                           LIMIT 1
                           """ ,[email]).df()
    if not df_email.empty:
        logger.warning("Email is already has an account")
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
                    """, [email, first_name, middle_name, last_name, date_of_birth, hashed_password])
    except Exception as e:
        logger.error(f"DB Error {e}")
        return False

    # logging and closing connection
    logger.info("new user have been registerd successfuly")
    return True
    
# for fixing allocation bug in strategy (not used yet)
def normalize_allocations(strategy_names, p_id):
    keys = [f"alloc_slider_{p_id}_{name}" for name in strategy_names]

    values = [st.session_state[k] for k in keys]
    total = sum(values)

    if total == 0:
        return

    # normalize to 100%
    for k in keys:
        st.session_state[k] = round((st.session_state[k] / total) * 100, 1)