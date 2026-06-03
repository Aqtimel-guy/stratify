import streamlit as st
import duckdb
import pandas as pd
import datetime
import re
import os  # Added to handle environment-agnostic file paths

from Code.functions.db_manager import *
from Code.functions.portfolio_managment import *
from Code.functions.trading_logic import *
from Code.functions.users_managment import *
from Code.functions.UI_components import *
from Code.functions.pages import *

# -----------------------------------------------------------------------------
# DYNAMIC DATABASE PATH RESOLUTION
# Supports both local Windows pathing and Streamlit Cloud Linux environments
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Check if running on Streamlit Cloud deployment vs Local machine
if "mount/src" in BASE_DIR.replace("\\", "/"):
    # Streamlit Cloud Linux structure (Assumes Data_Storage is in your root or synced subfolder)
    DB_PATH = os.path.join(BASE_DIR, "Data_Storage", "stratify.duckdb")
    # Mark cloud environment as active for downstream query engine routers
    if 'use_cloud' not in st.session_state:
        st.session_state.use_cloud = True
else:
    # Local fallback using your absolute path structure
    DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'
    if 'use_cloud' not in st.session_state:
        st.session_state.use_cloud = False

# Update streamlit session state with the globally resolved database path
st.session_state.DB_PATH = DB_PATH


def main():
    # setting initial states (Establishes st.session_state.con driver mapping)
    init_session_state()
    
    # -------------------------------------------------------------------------
    # CLOUD DATABASE ENGINE INJECTION LAYER
    # Registers remote Parquet references into active memory context schema
    # -------------------------------------------------------------------------
    if st.session_state.get('use_cloud', False) and 'con' in st.session_state:
        con = st.session_state.con
        base_url = "https://storage.googleapis.com/stratify-historical-data/data_snapshots"
        
        try:
            # Install and configure httpfs driver parameters cleanly
            con.execute("INSTALL httpfs;")
            con.execute("LOAD httpfs;")
            
            # Map logical relation targets directly to underlying cloud storage binaries
            con.execute(f"CREATE OR REPLACE VIEW assets AS SELECT * FROM read_parquet('{base_url}/assets.parquet');")
            con.execute(f"CREATE OR REPLACE VIEW prices AS SELECT * FROM read_parquet('{base_url}/prices.parquet');")
            con.execute(f"CREATE OR REPLACE VIEW fundamentals AS SELECT * FROM read_parquet('{base_url}/fundamentals.parquet');")
            con.execute(f"CREATE OR REPLACE VIEW asset_factors_normalized_final AS SELECT * FROM read_parquet('{base_url}/asset_factors_normalized_final.parquet');")
            con.execute(f"CREATE OR REPLACE VIEW holdings_cloud AS SELECT * FROM read_parquet('{base_url}/holdings.parquet');")
        except Exception as schema_err:
            st.sidebar.error(f"⚠️ Cloud catalog registration failed: {schema_err}")

    ###########################################
    ###                                     ###
    ###              PAGES - UI             ###
    ###                                     ###
    ###########################################
    
    # configuration
    st.set_page_config(page_title="Stratify 2026", layout="wide")

    # if unknown page - back to loggin 
    if "page" not in st.session_state:
        st.error("oops, somthing went wrong. please log in again") 
        st.session_state.page = "login_page"
        
    ###########################################
    ###                                     ###
    ###              Router                 ###
    ###                                     ###
    ###########################################
    
    if st.session_state.page == "login_page":
        show_login_page()
    elif st.session_state.page == "regestration_page":
        show_registration_page()
        
    elif st.session_state.page == "password_recovery_page":
        show_password_recovery_page()
    
    elif st.session_state.page == "home_page":
        show_home_page()
        
    elif st.session_state.page == "portfolios":
         show_portfolios_page()
         
    elif st.session_state.page =="dashboard_home":
        show_dashboard_home()
    
    elif st.session_state.page == "asset_explorer":
        show_asset_explorer()
    
    elif st.session_state.page == "strategy_builder":
        show_strategy_builder()
        
    elif st.session_state.page == "portfolio_performance_analysis":
        show_portfolio_performance_analysis()
        
        
if __name__ == "__main__":
    main()