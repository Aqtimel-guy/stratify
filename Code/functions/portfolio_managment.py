import duckdb
import datetime
import logging
import streamlit as st
import pandas as pd
from .db_manager import capture_portfolio_snapshot , get_data , get_supabase_engine
from sqlalchemy import text
DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'


# for creating a portfolio 
def create_portfolio(user_id, portfolio_name, starting_at):
    """
    Creates a portfolio in the Supabase database after running dynamic validations.
    
    """
    logger = logging.getLogger(__name__)
    engine = get_supabase_engine()  # Fetching the central cloud engine
    today = datetime.date.today()
    today_datetime = datetime.datetime.combine(today, datetime.time.min)
    
    try:
        # engine.begin() opens a connection and starts a safe SQL transaction block
        with engine.begin() as connection:
            
            # Validation 1: Verify user existence in cloud database
            user_exists = connection.execute(
                text("SELECT 1 FROM users WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
            
            if not user_exists:
                logger.warning(f"Validation Failed: User ID {user_id} does not exist.")
                return False, "User not found."
            
            # Validation 2: Enforce a limit of max 10 portfolios per user scope
            portfolio_count = connection.execute(
                text("SELECT COUNT(*) FROM portfolios WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).fetchone()[0]
            
            if portfolio_count > 9:
                logger.warning(f"Validation Failed: User {user_id} reached portfolio limit (10).")
                return False, "You have reached the maximum limit of 10 portfolios."
            
            # Validation 3: Ensure simulation target timeline is not set in the future
            if starting_at > today:
                logger.warning(f"Validation Failed: Starting date {starting_at} is in the future.")
                return False, "Starting date cannot be in the future."

            # Validation 4: Maintain unique portfolio naming convention per user scope
            name_exists = connection.execute(
                text("SELECT 1 FROM portfolios WHERE user_id = :user_id AND portfolio_name = :name"),
                {"user_id": user_id, "name": portfolio_name}
            ).fetchone()
            
            if name_exists:
                return False, f"You already have a portfolio named '{portfolio_name}'."
            
            # Execution Phase: Primary key allocation & data insertion
            max_id = connection.execute(text("SELECT COALESCE(MAX(portfolio_id), 0) FROM portfolios")).fetchone()[0]
            portfolio_id = max_id + 1
                
            connection.execute(
                text("""
                    INSERT INTO portfolios (portfolio_id, user_id, portfolio_name, created_at, starting_at, available_cash, portfolio_value, current_sim_date)
                    VALUES (:portfolio_id, :user_id, :portfolio_name, :created_at, :starting_at, :available_cash, :portfolio_value, :current_sim_date)
                """),
                {
                    "portfolio_id": portfolio_id,
                    "user_id": user_id,
                    "portfolio_name": portfolio_name,
                    "created_at": today_datetime,
                    "starting_at": starting_at,
                    "available_cash": 0.0,
                    "portfolio_value": 0.0,
                    "current_sim_date": starting_at
                }
            )
            
            logger.info(f"Portfolio '{portfolio_name}' created successfully for user {user_id}.")
            
            # Triggering initial state history snapshot log
            # Note: We pass the active connection context to keep everything inside the same safe atomic transaction
            capture_portfolio_snapshot(connection, portfolio_id, starting_at)
            
            return True, "Portfolio created successfully!"

    except Exception as e:
        logger.error(f"Database error during portfolio creation: {e}")
        return False, "An internal error occurred. Please try again."


# for deleting a portfolio 
def delete_portfolio(portfolio_id):
    """
    Deletes a portfolio and cascades across child relational layers to preserve foreign key integration.
    Maintains clean runtime environment state frames.
    """
    logger = logging.getLogger(__name__)
    engine = get_supabase_engine()  # Fetching the central cloud engine
    
    try:
        # engine.begin() ensures that ALL deletes succeed together, or ALL rollback together
        with engine.begin() as connection:
            
            # 1. Verify target record existence before starting deletion process
            portfolio_exists = connection.execute(
                text("SELECT portfolio_name FROM portfolios WHERE portfolio_id = :portfolio_id"),
                {"portfolio_id": portfolio_id}
            ).fetchone()
            
            if not portfolio_exists:
                logger.warning(f"Delete Failed: Portfolio ID {portfolio_id} does not exist.")
                return False, "Portfolio not found."
            
            p_name = portfolio_exists[0]

            # 2. Purge cascading records sequentially to clear foreign key dependencies safely
            # We pack the payload inside a single dictionary for reuse across queries
            payload = {"id": portfolio_id}
            
            connection.execute(text("DELETE FROM portfolio_history WHERE portfolio_id = :id"), payload)
            connection.execute(text("DELETE FROM portfolio_performance WHERE portfolio_id = :id"), payload)
            connection.execute(text("DELETE FROM user_preferences_strategy WHERE portfolio_id = :id"), payload)
            connection.execute(text("DELETE FROM holdings WHERE portfolio_id = :id"), payload)
            connection.execute(text("DELETE FROM cash_transactions WHERE portfolio_id = :id"), payload)
            connection.execute(text("DELETE FROM assets_transactions WHERE portfolio_id = :id"), payload)
            
            # 3. Cleanse the parent core record now that all dependencies are dropped
            connection.execute(text("DELETE FROM portfolios WHERE portfolio_id = :id"), payload)
            
            logger.info(f"Portfolio '{p_name}' (ID: {portfolio_id}) and all linked sub-records dropped successfully.")
            
        # 4. Clean up active Streamlit UI session state context fields (Outside the SQL transaction context)
        if st.session_state.get('current_portfolio_id') == portfolio_id:
            st.session_state.current_portfolio_id = None
            st.session_state.current_portfolio_name = None
            
            if 'current_available_cash' in st.session_state:
                st.session_state.current_available_cash = 0.0

        return True, f"Portfolio '{p_name}' deleted successfully!"
    
    except Exception as e:
        logger.error(f"Database error during portfolio deletion: {e}")
        return False, f"Error deleting portfolio: {str(e)}"

# for going forward in time of the simulation
def move_time_forward(portfolio_id, amount_of_time="1d"):
    """
    Advances the simulation timeline baseline and records state history logs before modifying records.
    All comments and documentation are strictly in English.
    """
    logger = logging.getLogger(__name__)
    engine = get_supabase_engine()  # Fetching the central cloud engine
    
    try:
        with engine.begin() as connection:
            # 1. Retrieve the current simulation date directly within the active transaction
            current_data = connection.execute(
                text("SELECT current_sim_date FROM portfolios WHERE portfolio_id = :id"),
                {"id": portfolio_id}
            ).fetchone()
            
            if not current_data:
                return False, "Portfolio not found"
            
            raw_date = current_data[0]
            
            # Safe parsing: Ensure we possess a native datetime object for time math operations
            if isinstance(raw_date, pd.Timestamp):
                current_sim_date = raw_date.to_pydatetime()
            elif isinstance(raw_date, datetime.date) and not isinstance(raw_date, datetime.datetime):
                current_sim_date = datetime.datetime.combine(raw_date, datetime.time.min)
            elif isinstance(raw_date, str):
                current_sim_date = pd.to_datetime(raw_date).to_pydatetime()
            else:
                current_sim_date = raw_date

            # 2. Append history state matrix checkpoint before applying delta offsets
            # Pass the open connection context so the snapshot happens inside the same cloud transaction
            capture_portfolio_snapshot(connection, portfolio_id, current_sim_date)

            # 3. Calculate the new advanced timeline step using Pandas frequencies
            offset = pd.tseries.frequencies.to_offset(amount_of_time)
            new_sim_date = current_sim_date + offset

            # 4. Guard clause: Do not allow the simulation time frame to leak into the real-world future
            today_real = datetime.datetime.now()
            if new_sim_date > today_real:
                new_sim_date = today_real

            # 5. Flush and write the new time evolution point to Supabase server
            connection.execute(
                text("UPDATE portfolios SET current_sim_date = :new_date WHERE portfolio_id = :id"),
                {"new_date": new_sim_date, "id": portfolio_id}
            )
            
        # 6. Update Streamlit session state memory environment (Done outside the database lifecycle)
        st.session_state.current_current_sim_date = new_sim_date
        
        return True, new_sim_date  
            
    except Exception as e:
        logger.error(f"Error executing time slice transition shift: {e}")
        return False, str(e)
    

# for FIFO tracking 
def calculate_fifo_avg_price(transactions):
    """
    Evaluates historical transaction layers to calculate the weighted average buy cost 
    using the First-In, First-Out (FIFO) tracking methodology.
    
    transactions: pd.DataFrame containing structural columns: 'quantity', 'price_per_share', 'side'
    """
    buys = []  # Tracks dynamic asset inventory buy layers: [quantity, price_per_share]
    
    for _, tx in transactions.iterrows():
        qty = tx['quantity']
        price = tx['price_per_share']
        
        if tx['side'] == 'buy':
            buys.append([qty, price])
        else:
            # Sell operation: Deduct volume from the oldest active cost layers iteratively (FIFO execution)
            while qty > 0 and buys:
                if buys[0][0] <= qty:
                    qty -= buys[0][0]
                    buys.pop(0)  # The specific tracking layer has been entirely depleted
                else:
                    buys[0][0] -= qty  # Partial inventory layer reduction optimization
                    qty = 0
                    
    # Calculate the final weighted average price for remaining asset units
    remaining_qty = sum(layer[0] for layer in buys)
    if remaining_qty == 0:
        return 0
    
    total_cost = sum(layer[0] * layer[1] for layer in buys)
    return total_cost / remaining_qty