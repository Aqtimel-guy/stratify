import streamlit as st
from .db_manager import *
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
    Authenticates a user by checking their credentials against the cloud database (Supabase).
    If successful, returns (user_id, first_name).
    If authentication fails, returns (None, None).
    """
    # 1. FIXED: Changed %s to :email to support SQLAlchemy text() format combined with LOWER()
    query = """
        SELECT user_id, first_name, email, password_hash 
        FROM users
        WHERE LOWER(email) = LOWER(:email)
        LIMIT 1
    """
    
    # 2. FIXED: Passed params as a dictionary mapping 'email' to the variable
    df_login = get_data(query, {"email": email}, use_cloud=True)
    
    # 3. Validate if the email exists in the system
    if df_login.empty:
        st.warning("Unknown Email")
        return None, None
    
    # 4. Extract the stored cryptographic hash
    stored_hash = df_login.iloc[0]['password_hash']
    
    # 5. Verify the password match using bcrypt
    if not bcrypt.checkpw(entered_password.encode('utf-8'), stored_hash.encode('utf-8')):
        st.warning("Wrong password")
        return None, None
    
    # 6. Credentials are valid; return session identifiers
    return int(df_login.iloc[0]['user_id']), df_login.iloc[0]['first_name']

    
# for registration  
def registration_func(email, first_name, middle_name, last_name, date_of_birth, raw_password, raw_password_confirm):
    """
    Validates user credentials and signs up a new user.
    Coordinates a Dual-Write process to save user details to both 
    the external Supabase cloud database and the local DuckDB instance.
    All source documentation and comments are maintained strictly in English.
    """
    logger = logging.getLogger(__name__)
    
    # ---- STEP 1: Argument Validation ----

    # Email validation
    if not email or not isinstance(email, str):
        return False
    
    email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_pattern, email):
        return False

    # First name validation
    if not first_name or not isinstance(first_name, str):
        return False
        
    if middle_name and not isinstance(middle_name, str):
        return False
    
    if len(first_name.strip()) < 2:
        return False

    # Last name validation
    if not last_name or not isinstance(last_name, str):
        return False
    
    if len(last_name.strip()) < 2:
        return False

    # Date of birth validation
    if not isinstance(date_of_birth, (datetime.date, datetime.datetime)):
        return False
    
    # Password validation and hashing
    if not raw_password or not isinstance(raw_password, str) or len(raw_password) < 6:
        logger.warning("Password does not meet security requirements")
        return False
    if not raw_password == raw_password_confirm:
        logger.warning("Password confirmation must be identical to your password")
        return False

    # Generate secure cryptographic hash
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(raw_password.encode('utf-8'), salt).decode('utf-8')

    # ---- STEP 2: Database Cross-Checking (Cloud First) ----
    
    # FIXED: Convert to named parameter syntax to comply with internal get_data text() wrapping
    email_check_query = "SELECT 1 FROM users WHERE email = :email LIMIT 1"
    df_email = get_data(email_check_query, {"email": email}, use_cloud=True)
    
    if not df_email.empty:
        logger.warning(f"Registration failed: Email '{email}' is already registered.")
        return False

    # Format date for database insertion
    dob_str = date_of_birth.strftime('%Y-%m-%d') if isinstance(date_of_birth, (datetime.date, datetime.datetime)) else date_of_birth

    # ---- STEP 3: Dual-Write Execution (Atomic ID Generation in Cloud) ----
    
    new_user_id = None

    # A. Execute Cloud Write (Supabase) with Atomic ID Generation
    try:
        engine = get_supabase_engine()
        
        # FIXED: Using SQLAlchemy named parameters (:key) and passing a dictionary
        cloud_insert_query = """
            INSERT INTO users (user_id, email, first_name, middle_name, last_name, date_of_birth, password_hash)
            VALUES (
                (SELECT COALESCE(MAX(user_id), 0) + 1 FROM users),
                :email, :first_name, :middle_name, :last_name, :date_of_birth, :password_hash
            )
            RETURNING user_id;
        """
        
        # Mapping the variables strictly to a dictionary
        param_dict = {
            "email": email,
            "first_name": first_name,
            "middle_name": middle_name if middle_name else None,
            "last_name": last_name,
            "date_of_birth": dob_str,
            "password_hash": hashed_password
        }
        
        from sqlalchemy import text
        with engine.begin() as cloud_con:
            # text() is required by SQLAlchemy for literal SQL strings with named parameters
            result = cloud_con.execute(text(cloud_insert_query), param_dict)
            new_user_id = result.fetchone()[0]
            
    except Exception as e:
        logger.error(f"Cloud Registration Write Failed: {e}")
        import streamlit as st
        st.error(f"Supabase Real Cloud Error: {e}")
        return False  # If cloud insert fails, abort entire signup process

    # B. Execute Local Write (DuckDB) - Keeping local mirror synchronized with the exact same ID
    if new_user_id is not None:
        try:
            with duckdb.connect(DB_PATH) as local_con:
                local_con.execute("""
                    INSERT INTO users (user_id, email, first_name, middle_name, last_name, date_of_birth, password_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [new_user_id, email, first_name, middle_name, last_name, dob_str, hashed_password])
                
        except Exception as e:
            # Log the issue but don't crash since the source-of-truth (cloud) succeeded
            logger.error(f"Local database sync during registration failed: {e}")

    logger.info(f"New user with ID {new_user_id} has been registered successfully across systems.")
    return True

