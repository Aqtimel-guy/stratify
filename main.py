import streamlit as st
import duckdb
import pandas as pd
import datetime
import re
from Code.functions.db_manager import *
from Code.functions.portfolio_managment import *
from Code.functions.trading_logic import *
from Code.functions.users_managment import *
from Code.functions.UI_components import *
from Code.functions.pages import *
DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'

# python -m streamlit run  "C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\main.py"






def main():
    # setting initial states
    init_session_state()
    
    
    ###########################################
    ###                                     ###
    ###     DB querying and setting args    ###
    ###                                     ###
    ###########################################
    
    
    
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
    ###             Router                  ###
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