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
else:
    # Local fallback using your absolute path structure
    DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'

# Update streamlit session state with the globally resolved database path
st.session_state.DB_PATH = DB_PATH


def main():
    # setting initial states
    init_session_state()
    
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