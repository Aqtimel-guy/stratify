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
    """
    Converts a plaintext password into a bcrypt hashed string.
    The result is safe to store in any database (Supabase or DuckDB).
    """

    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)

    return hashed.decode("utf-8")


# for decripting the password
def check_password(password: str, hashed_password: str) -> bool:
    """
    Verifies whether a plaintext password matches a stored bcrypt hash.
    """

    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False
    
    
# for security
class AuthProtection:
    """
    Lightweight in-memory protection layer for authentication abuse prevention.
    Designed for Streamlit session_state (single-user session scope).
    """

    def __init__(self, max_attempts=5, lockout_seconds=60):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds

        if "auth_attempts" not in st.session_state:
            st.session_state["auth_attempts"] = 0

        if "auth_last_attempt_time" not in st.session_state:
            st.session_state["auth_last_attempt_time"] = 0

        if "auth_locked_until" not in st.session_state:
            st.session_state["auth_locked_until"] = 0

    def is_locked(self) -> bool:
        """Checks if user is currently locked out."""
        return time.time() < st.session_state["auth_locked_until"]

    def register_failed_attempt(self):
        """Registers a failed login attempt."""
        st.session_state["auth_attempts"] += 1
        st.session_state["auth_last_attempt_time"] = time.time()

        if st.session_state["auth_attempts"] >= self.max_attempts:
            st.session_state["auth_locked_until"] = (
                time.time() + self.lockout_seconds
            )

    def reset(self):
        """Resets attempt counter after successful login."""
        st.session_state["auth_attempts"] = 0
        st.session_state["auth_locked_until"] = 0


# for logging in
def loggin_func(email, entered_password):
    auth_guard = AuthProtection(max_attempts=20, lockout_seconds=60)

    # ---------------------------------------------------------------------
    # 0. Block if locked
    # ---------------------------------------------------------------------
    if auth_guard.is_locked():
        st.warning("Too many failed attempts. Try again later.")
        return None, None

    query = """
        SELECT user_id, first_name, email, password_hash
        FROM users
        WHERE LOWER(email) = LOWER(:email)
        LIMIT 1
    """

    df_login = get_data(query, {"email": email}, use_cloud=True)

    if df_login.empty:
        auth_guard.register_failed_attempt()
        st.warning("Unknown email")
        return None, None

    stored_hash = df_login.iloc[0]["password_hash"]

    try:
        password_valid = bcrypt.checkpw(
            entered_password.encode("utf-8"),
            stored_hash.encode("utf-8")
        )
    except Exception:
        auth_guard.register_failed_attempt()
        st.warning("Authentication error")
        return None, None

    if not password_valid:
        auth_guard.register_failed_attempt()
        st.warning("Wrong password")
        return None, None

    # ---------------------------------------------------------------------
    # SUCCESS → reset protection state
    # ---------------------------------------------------------------------
    auth_guard.reset()

    return int(df_login.iloc[0]["user_id"]), df_login.iloc[0]["first_name"]
    

# for registration  
def registration_func(
    email,
    first_name,
    middle_name,
    last_name,
    date_of_birth,
    raw_password,
    raw_password_confirm
):
    """
    Secure user registration using Supabase as source of truth.
    No manual ID generation. DB handles identity safely.
    """

    logger = logging.getLogger(__name__)

    # ---------------------------------------------------------------------
    # 1. Validation
    # ---------------------------------------------------------------------
    if not email or not isinstance(email, str):
        return False

    email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_pattern, email):
        return False

    if not first_name or len(first_name.strip()) < 2:
        return False

    if not last_name or len(last_name.strip()) < 2:
        return False

    if middle_name and not isinstance(middle_name, str):
        return False

    if not isinstance(date_of_birth, (datetime.date, datetime.datetime)):
        return False

    if not raw_password or len(raw_password) < 6:
        logger.warning("Password too weak")
        return False

    if raw_password != raw_password_confirm:
        logger.warning("Password mismatch")
        return False

    # ---------------------------------------------------------------------
    # 2. Hash password
    # ---------------------------------------------------------------------
    hashed_password = bcrypt.hashpw(
        raw_password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    dob_str = date_of_birth.strftime("%Y-%m-%d")

    # ---------------------------------------------------------------------
    # 3. Check duplicate email (cloud)
    # ---------------------------------------------------------------------
    check_query = """
        SELECT 1 FROM users WHERE LOWER(email) = LOWER(:email) LIMIT 1
    """

    existing = get_data(check_query, {"email": email}, use_cloud=True)

    if not existing.empty:
        logger.warning(f"Email already exists: {email}")
        return False

    # ---------------------------------------------------------------------
    # 4. Insert into Supabase (NO manual ID)
    # ---------------------------------------------------------------------
    try:
        engine = get_supabase_engine()

        insert_query = """
            INSERT INTO users (
                email,
                first_name,
                middle_name,
                last_name,
                date_of_birth,
                password_hash
            )
            VALUES (
                :email,
                :first_name,
                :middle_name,
                :last_name,
                :date_of_birth,
                :password_hash
            )
            RETURNING user_id;
        """

        params = {
            "email": email,
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "date_of_birth": dob_str,
            "password_hash": hashed_password
        }

        with engine.begin() as conn:
            result = conn.execute(text(insert_query), params)
            new_user_id = result.fetchone()[0]

    except Exception as e:
        logger.error(f"Cloud registration failed: {e}")
        st.error("Registration failed")
        return False

    # ---------------------------------------------------------------------
    # 5. Optional local mirror (DuckDB)
    # ---------------------------------------------------------------------
    try:
        with duckdb.connect(DB_PATH) as local_con:
            local_con.execute("""
                INSERT INTO users (
                    user_id,
                    email,
                    first_name,
                    middle_name,
                    last_name,
                    date_of_birth,
                    password_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                new_user_id,
                email,
                first_name,
                middle_name,
                last_name,
                dob_str,
                hashed_password
            ])

    except Exception as e:
        logger.error(f"Local sync failed (non-critical): {e}")

    logger.info(f"User registered successfully: {new_user_id}")
    return True


