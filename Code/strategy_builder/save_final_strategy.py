import streamlit as st

def save_final_strategy(con, user_id, portfolio_id, strategy1_id, strategy1_pct=100, 
                        strategy2_id=None, strategy2_pct=0, 
                        strategy3_id=None, strategy3_pct=0, 
                        strategy4_id=None, strategy4_pct=0, 
                        diversification=1, preferred_sectors=None, 
                        excluded_sectors=None, monthly_deposit=0, 
                        initial_investment=0, buy_fee=0, sell_fee=0, 
                        deposit_fee=0, withdrawal_fee=0):
    
    # 1. Validation: Ensure total allocation is 100%
    total_pct = strategy1_pct + strategy2_pct + strategy3_pct + strategy4_pct
    if not (99.9 <= total_pct <= 100.1):
        with st.container(border=True):
            st.write("Go back to Multi-Strategy Allocation tab to confirm your allocation")
            if st.button("go back to Allocation"):
                st.session_state.active_tab = 2
                st.rerun()
            
        raise ValueError(f"Total allocation percentage must be 100%. Current sum: {total_pct}%")

    # 2. Prepare data for storage
    if preferred_sectors is None:
        preferred_sectors = []

    if excluded_sectors is None:
        excluded_sectors = []
    
    pref_str = ",".join(preferred_sectors) if preferred_sectors else ""
    excl_str = ",".join(excluded_sectors) if excluded_sectors else ""

    try:
        # 3. Remove old record to ensure no duplicates for the same portfolio
        con.execute("DELETE FROM multi_strategy WHERE portfolio_id = ?", [portfolio_id])
        
        # 4. Insert the new strategy configuration
        query = """
        INSERT INTO multi_strategy (
            user_id, portfolio_id, strategy_1_id, strategy_1_pct, 
            strategy_2_id, strategy_2_pct, strategy_3_id, strategy_3_pct, 
            strategy_4_id, strategy_4_pct, monthly_deposit, initial_investment, 
            buy_fee, sell_fee, deposit_fee, withdrawal_fee, 
            preferred_sectors, excluded_sectors, diversification
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        params = (
            user_id, portfolio_id, strategy1_id, strategy1_pct,
            strategy2_id, strategy2_pct, strategy3_id, strategy3_pct,
            strategy4_id, strategy4_pct, monthly_deposit, initial_investment,
            buy_fee, sell_fee, deposit_fee, withdrawal_fee,
            pref_str, excl_str, diversification
        )
        
        con.execute(query, params)
        return True
    except Exception as e:
        st.error(f"Database error: {e}")
        return False
    
    
    
    
# Helper function to map strategy names to IDs
def get_strategy_id_by_name(con, strategy_name, portfolio_id):
    """
    Fetch the strategy ID from the database based on its name.
    """
    query = "SELECT strategy_id FROM strategies WHERE strategy_name = ? and portfolio_id = ?"
    result = con.execute(query, [strategy_name, portfolio_id]).fetchone()
    return result[0] if result else None







