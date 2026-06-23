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


DB_PATH = r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb"

# Run command:
# python -m streamlit run "C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\main.py"


def show_no_db_preview_mode():
    # Preview mode for checking UI pages without opening DuckDB.

    st.sidebar.warning("NO DB MODE is active")
    st.sidebar.write("DuckDB connection is disabled.")

    preview_page = st.sidebar.selectbox(
        "Preview page",
        [
            "login_page",
            "regestration_page",
            "password_recovery_page",
            "home_page",
            "portfolios",
            "dashboard_home",
            "asset_purchsing",
            "strategy_builder",
            "portfolio_performance_analysis",
            "strategy_managment",
            "test_page",
        ],
        index=0
    )

    preview_pages = {
        "login_page": show_login_page,
        "regestration_page": show_registration_page,
        "password_recovery_page": show_password_recovery_page,
        "home_page": show_home_page,
        "portfolios": show_portfolios_page,
        "dashboard_home": show_dashboard_home,
        "asset_purchsing": show_asset_purchsing,
        "strategy_builder": show_strategy_builder,
        "portfolio_performance_analysis": show_portfolio_performance_analysis,
        "strategy_managment": show_strategy_manager,
        "test_page": test_page,
    }

    # Minimal fake session state for UI preview
    if "page" not in st.session_state:
        st.session_state.page = preview_page

    try:
        preview_pages[preview_page]()

    except Exception as e:
        st.error("This page tried to use the database or missing session state.")
        st.exception(e)
def main():
    # ======================================================
    # PAGE CONFIGURATION
    # ======================================================
    st.set_page_config(
        page_title="Stratify 2026",
        layout="wide"
    )

    # ======================================================
    # NO DB LOCAL PREVIEW MODE
    # ======================================================
    # If enabled in .streamlit/secrets.toml, this prevents the app
    # from opening the local DuckDB database.
    if st.secrets.get("NO_DB_MODE", "false") == "true":
        show_no_db_preview_mode()
        st.stop()

    # ======================================================
    # INITIAL SESSION STATE
    # ======================================================
    init_session_state()

    # ======================================================
    # DATABASE CONNECTION
    # ======================================================
    # Create one DuckDB connection and keep it in Streamlit session state.
    # This prevents opening a new connection on every rerun.
    if "con" not in st.session_state:
        st.session_state.con = duckdb.connect(DB_PATH)

    # ======================================================
    # PAGE SAFETY CHECK
    # ======================================================
    # If page state is missing, send the user back to login.
    if "page" not in st.session_state:
        st.error("Oops, something went wrong. Please log in again.")
        st.session_state.page = "login_page"

    # ======================================================
    # ROUTER
    # ======================================================
    pages = {
        "login_page": show_login_page,
        "regestration_page": show_registration_page,
        "password_recovery_page": show_password_recovery_page,
        "home_page": show_home_page,
        "portfolios": show_portfolios_page,
        "dashboard_home": show_dashboard_home,
        "asset_purchsing": show_asset_purchsing,
        "strategy_builder": show_strategy_builder,
        "portfolio_performance_analysis": show_portfolio_performance_analysis,
        "strategy_managment": show_strategy_manager,
        "test_page": test_page,
    }

    current_page = st.session_state.page

    if current_page in pages:
        pages[current_page]()
    else:
        st.error(f"Unknown page: {current_page}. Redirecting to login page.")
        st.session_state.page = "login_page"
        st.rerun()


if __name__ == "__main__":
    main()