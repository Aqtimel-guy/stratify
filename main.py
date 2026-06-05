import streamlit as st
import duckdb
import pandas as pd
import datetime
import re
import os

# -------------------------------------------------------------------
# STREAMLIT CONFIG (MUST BE FIRST)
# -------------------------------------------------------------------
st.set_page_config(page_title="Stratify 2026", layout="wide")

# -------------------------------------------------------------------
# IMPORTS
# -------------------------------------------------------------------
from Code.functions.db_manager import *
from Code.functions.portfolio_managment import *
from Code.functions.trading_logic import *
from Code.functions.users_managment import *
from Code.functions.UI_components import *
from Code.functions.pages import *

# -------------------------------------------------------------------
# PATH RESOLUTION
# -------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if "mount/src" in BASE_DIR.replace("\\", "/"):
    DB_PATH = os.path.join(BASE_DIR, "Data_Storage", "stratify.duckdb")

    if not os.path.exists(DB_PATH):
        alt = os.path.join(os.path.dirname(BASE_DIR), "Data_Storage", "stratify.duckdb")
        if os.path.exists(alt):
            DB_PATH = alt

    USE_CLOUD = True
else:
    DB_PATH = r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb"
    USE_CLOUD = False

st.session_state["DB_PATH"] = DB_PATH
st.session_state["use_cloud"] = USE_CLOUD


# -------------------------------------------------------------------
# CONNECTIONS
# -------------------------------------------------------------------
@st.cache_resource
def get_duckdb_connection(db_path: str):
    return duckdb.connect(db_path)


def init_connections():
    # DuckDB (always exists)
    if "duckdb_con" not in st.session_state:
        st.session_state.duckdb_con = get_duckdb_connection(st.session_state["DB_PATH"])

    # cloud connection placeholder (never None surprise)
    if "con" not in st.session_state:
        st.session_state.con = None

    if "cloud_con" not in st.session_state:
        st.session_state.cloud_con = None


# -------------------------------------------------------------------
# SESSION INIT (SAFE DEFAULTS)
# -------------------------------------------------------------------
def init_session_state():
    defaults = {
        "page": "login_page",
        "user_id": None,
        "use_cloud": st.session_state.get("use_cloud", False),
        "cloud_con": None,
        "con": None
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# -------------------------------------------------------------------
# CLOUD SETUP (SAFE)
# -------------------------------------------------------------------
def setup_cloud_catalog():
    if not st.session_state.get("use_cloud", False):
        return

    con = st.session_state.get("con")

    if con is None:
        try:
            con = duckdb.connect(st.session_state["DB_PATH"])
            st.session_state.con = con
        except Exception as e:
            st.sidebar.error(f"Cloud connection failed: {e}")
            return

    try:
        base_url = "https://storage.googleapis.com/stratify-historical-data/data_snapshots"

        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")

        con.execute(f"""
            CREATE OR REPLACE VIEW assets AS 
            SELECT * FROM read_parquet('{base_url}/assets.parquet');
        """)

        con.execute(f"""
            CREATE OR REPLACE VIEW prices AS 
            SELECT * FROM read_parquet('{base_url}/prices.parquet');
        """)

        con.execute(f"""
            CREATE OR REPLACE VIEW fundamentals AS 
            SELECT * FROM read_parquet('{base_url}/fundamentals.parquet');
        """)

        con.execute(f"""
            CREATE OR REPLACE VIEW asset_factors_normalized_final AS 
            SELECT * FROM read_parquet('{base_url}/asset_factors_normalized_final.parquet');
        """)

    except Exception as e:
        st.sidebar.error(f"⚠️ Cloud catalog registration failed: {e}")


# -------------------------------------------------------------------
# MAIN APP
# -------------------------------------------------------------------
def main():
    init_session_state()
    init_connections()
    setup_cloud_catalog()

    # ---------------- ROUTER ----------------
    page = st.session_state.get("page", "login_page")

    if page == "login_page":
        show_login_page()

    elif page == "regestration_page":
        show_registration_page()

    elif page == "password_recovery_page":
        show_password_recovery_page()

    elif page == "home_page":
        show_home_page()

    elif page == "portfolios":
        show_portfolios_page()

    elif page == "dashboard_home":
        show_dashboard_home()

    elif page == "asset_explorer":
        show_asset_explorer()

    elif page == "strategy_builder":
        show_strategy_builder()

    elif page == "portfolio_performance_analysis":
        show_portfolio_performance_analysis()


# -------------------------------------------------------------------
# ENTRY POINT
# -------------------------------------------------------------------
if __name__ == "__main__":
    main()
    
    

