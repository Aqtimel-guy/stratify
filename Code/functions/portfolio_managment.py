import duckdb
import datetime
import logging
import streamlit as st
import pandas as pd
from .db_manager import capture_portfolio_snapshot , get_data , get_supabase_engine
from sqlalchemy import text
DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'


# for creating a portfolio 
def create_portfolio(cloud_con, duckdb_con, user_id, portfolio_name, starting_at):
    """
    Creates a new portfolio and triggers an initial snapshot.

    Responsibilities:
    - Validates input
    - Enforces business constraints
    - Persists portfolio in cloud DB
    - Triggers initial snapshot (non-blocking)

    Data sources:
    - cloud_con: SQLAlchemy connection (Supabase/Postgres)
    - duckdb_con: analytics engine (passed to snapshot via calculator chain)
    """

    logger = logging.getLogger(__name__)

    # ------------------------------------------------------------
    # 0. Basic validation (no DB calls)
    # ------------------------------------------------------------
    if not portfolio_name or not portfolio_name.strip():
        return False, "Portfolio name is required."

    today = datetime.date.today()

    if starting_at > today:
        return False, "Starting date cannot be in the future."

    try:
        with cloud_con.begin():

            # --------------------------------------------------------
            # 1. Validate user exists
            # --------------------------------------------------------
            user_exists = cloud_con.execute(
                text("SELECT 1 FROM users WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).fetchone()

            if not user_exists:
                return False, "User not found."

            # --------------------------------------------------------
            # 2. Portfolio limit check
            # --------------------------------------------------------
            portfolio_count = cloud_con.execute(
                text("""
                    SELECT COUNT(*)
                    FROM portfolios
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id}
            ).fetchone()[0]

            if portfolio_count >= 10:
                return False, "Maximum portfolio limit reached."

            # --------------------------------------------------------
            # 3. Unique name check
            # --------------------------------------------------------
            name_exists = cloud_con.execute(
                text("""
                    SELECT 1
                    FROM portfolios
                    WHERE user_id = :user_id
                      AND portfolio_name = :name
                """),
                {"user_id": user_id, "name": portfolio_name}
            ).fetchone()

            if name_exists:
                return False, f"Portfolio '{portfolio_name}' already exists."

            # --------------------------------------------------------
            # 4. Insert portfolio
            # --------------------------------------------------------
            result = cloud_con.execute(
                text("""
                    INSERT INTO portfolios (
                        user_id,
                        portfolio_name,
                        created_at,
                        starting_at,
                        available_cash,
                        portfolio_value,
                        current_sim_date
                    )
                    VALUES (
                        :user_id,
                        :portfolio_name,
                        :created_at,
                        :starting_at,
                        0.0,
                        0.0,
                        :starting_at
                    )
                    RETURNING portfolio_id
                """),
                {
                    "user_id": user_id,
                    "portfolio_name": portfolio_name,
                    "created_at": datetime.datetime.combine(datetime.date.today(), datetime.time.min),
                    "starting_at": starting_at
                }
            )

            portfolio_id = result.fetchone()[0]

        # ------------------------------------------------------------
        # 5. Snapshot (outside transaction, safe side-effect)
        # ------------------------------------------------------------
        try:
            capture_portfolio_snapshot(
                cloud_con=cloud_con,
                duckdb_con=duckdb_con,
                portfolio_id=portfolio_id,
                sim_date=starting_at
            )

        except Exception as snap_err:
            logger.error(f"Initial snapshot failed (non-blocking): {snap_err}")

        logger.info(f"Portfolio created successfully: {portfolio_id}")

        return True, "Portfolio created successfully!"

    except Exception as e:
        logger.error(f"Portfolio creation failed: {e}")
        return False, "Internal error occurred."


# for deleting a portfolio 
def delete_portfolio(portfolio_id):
    """
    Deletes a portfolio and all dependent relational data safely
    using a single atomic transaction.
    """

    logger = logging.getLogger(__name__)
    engine = get_supabase_engine()

    payload = {"portfolio_id": portfolio_id}

    try:
        with engine.begin() as connection:

            # -------------------------------
            # 1. Verify existence
            # -------------------------------
            result = connection.execute(
                text("""
                    SELECT portfolio_name
                    FROM portfolios
                    WHERE portfolio_id = :portfolio_id
                """),
                payload
            ).fetchone()

            if not result:
                logger.warning(f"Portfolio {portfolio_id} not found")
                return False, "Portfolio not found."

            portfolio_name = result[0]

            # -------------------------------
            # 2. Cascade delete (safe order)
            # -------------------------------
            tables = [
                "portfolio_history",
                "portfolio_performance",
                "user_preferences_strategy",
                "holdings",
                "cash_transactions",
                "assets_transactions",
            ]

            for table in tables:
                connection.execute(
                    text(f"DELETE FROM {table} WHERE portfolio_id = :portfolio_id"),
                    payload
                )

            # -------------------------------
            # 3. Delete parent
            # -------------------------------
            connection.execute(
                text("""
                    DELETE FROM portfolios
                    WHERE portfolio_id = :portfolio_id
                """),
                payload
            )

            logger.info(f"Deleted portfolio {portfolio_id} ({portfolio_name})")

        # -------------------------------
        # 4. UI cleanup (safe + complete)
        # -------------------------------
        if st.session_state.get("current_portfolio_id") == portfolio_id:

            keys_to_clear = [
                "current_portfolio_id",
                "current_portfolio_name",
                "current_sim_date",
                "current_portfolio_starting_at",
                "current_available_cash",
                "current_sim_date_display",
            ]

            for k in keys_to_clear:
                if k in st.session_state:
                    st.session_state[k] = None

        return True, f"Portfolio '{portfolio_name}' deleted successfully!"

    except Exception as e:
        logger.error(f"Delete failed for portfolio {portfolio_id}: {e}")
        return False, f"Error deleting portfolio: {str(e)}"
    
    
######################################################3
    
def move_time_forward(cloud_con, duckdb_con, portfolio_id, amount_of_time="1d"):
    """
    Advances the simulation timeline and records a portfolio snapshot before updating state.

    Responsibilities:
    - Reads current simulation state from cloud DB
    - Captures portfolio snapshot (cloud + DuckDB)
    - Advances simulation time safely
    - Persists updated simulation state
    """

    import logging
    import datetime
    import pandas as pd
    from sqlalchemy import text

    logger = logging.getLogger(__name__)

    try:
        with cloud_con.begin():

            # --------------------------------------------------------
            # 1. Fetch current simulation date
            # --------------------------------------------------------
            current_data = cloud_con.execute(
                text("""
                    SELECT current_sim_date
                    FROM portfolios
                    WHERE portfolio_id = :id
                """),
                {"id": portfolio_id}
            ).fetchone()

            if not current_data:
                return False, "Portfolio not found"

            raw_date = current_data[0]

            # --------------------------------------------------------
            # 2. Normalize datetime
            # --------------------------------------------------------
            if isinstance(raw_date, pd.Timestamp):
                current_sim_date = raw_date.to_pydatetime()

            elif isinstance(raw_date, datetime.date) and not isinstance(raw_date, datetime.datetime):
                current_sim_date = datetime.datetime.combine(raw_date, datetime.time.min)

            elif isinstance(raw_date, str):
                current_sim_date = pd.to_datetime(raw_date).to_pydatetime()

            else:
                current_sim_date = raw_date

            # --------------------------------------------------------
            # 3. Snapshot BEFORE time advance
            # --------------------------------------------------------
            capture_portfolio_snapshot(
                cloud_con=cloud_con,
                duckdb_con=duckdb_con,
                portfolio_id=portfolio_id,
                sim_date=current_sim_date
            )

            # --------------------------------------------------------
            # 4. Compute new simulation date
            # --------------------------------------------------------
            offset = pd.tseries.frequencies.to_offset(amount_of_time)
            new_sim_date = current_sim_date + offset

            # --------------------------------------------------------
            # 5. Prevent future leakage
            # --------------------------------------------------------
            now_real = datetime.datetime.now()
            if new_sim_date > now_real:
                new_sim_date = now_real

            # --------------------------------------------------------
            # 6. Persist new simulation date
            # --------------------------------------------------------
            cloud_con.execute(
                text("""
                    UPDATE portfolios
                    SET current_sim_date = :new_date
                    WHERE portfolio_id = :id
                """),
                {"new_date": new_sim_date, "id": portfolio_id}
            )

        # ------------------------------------------------------------
        # 7. Update Streamlit state (UI layer only)
        # ------------------------------------------------------------
        st.session_state.current_sim_date = new_sim_date

        return True, new_sim_date

    except Exception as e:
        logger.error(f"Time advancement failed: {e}")
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