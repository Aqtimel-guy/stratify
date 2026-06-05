import streamlit as st
import duckdb
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from .trading_logic import execute_asset_trade , execute_cash_transaction
from .portfolio_managment import calculate_fifo_avg_price
from Code.functions.db_manager import *
from Code.strategy_builder.user_prefrence import *

DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'


# for moving between pages
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()
    
    

# for showing cash management 
def show_cash_management_ui():
    st.subheader("💰 Cash Management")
    col1, col2 = st.columns(2)
    
    # 1. Deposit
    with col1:
        # שימוש במפתח ייחודי שניתן לאפס אם רוצים (אופציונלי)
        with st.popover("➕ Deposit Cash", width="stretch"):
            dep_amount = st.number_input("Amount to Deposit", min_value=1, step=100, key="dep_val")
            
            confirm_dep = st.checkbox(f"I confirm depositing ${dep_amount:,.2f}", key="conf_dep_check")
            
            if confirm_dep:
                if st.button("🚀 Execute Deposit", width="stretch"):
                    if is_action_allowed(wait_time=2):
                        with duckdb.connect(DB_PATH) as con:
                            success, msg = execute_cash_transaction(
                                con, 
                                st.session_state.current_portfolio_id, 
                                dep_amount, 
                                'deposit', 
                                st.session_state.current_sim_date
                            )
                            if success:
                                st.success(msg)
                                
                                # ניקוי המפתחות מה-Session State כדי לאפס את הווידג'טים
                                # משתמשים ברשימה של מפתחות שרוצים לנקות
                                keys_to_reset = ["dep_val", "conf_dep_check", "with_val", "conf_with_check"]
                                
                                for key in keys_to_reset:
                                    if key in st.session_state:
                                        del st.session_state[key]
                                
                                # השהיה קלה לסגירת הדיאלוג/פופאוובר
                                time.sleep(0.5)
                                
                                # סגירת חיבור לפני ריענון
                                if 'con' in locals():
                                    con.close()
                                    
                                st.rerun()
                            else:
                                st.error(msg)
                    else:
                        st.warning("Please wait a moment between actions.")

    # 2. Withdrawal
    with col2:
        with st.popover("➖ Withdraw Cash", width="stretch"):
            with_amount = st.number_input("Amount to Withdraw", min_value=1, step=100, key="with_val")
            
            confirm_with = st.checkbox(f"I confirm withdrawing ${with_amount:,.2f}", key="conf_with_check")
            
            if confirm_with:
                if st.button("💸 Execute Withdrawal", width="stretch"):
                    if is_action_allowed(wait_time=2):
                        with duckdb.connect(DB_PATH) as con:
                            success, msg = execute_cash_transaction(
                                con, 
                                st.session_state.current_portfolio_id, 
                                with_amount, 
                                'withdrawal', 
                                st.session_state.current_sim_date
                            )
                            if success:
                                st.success(msg)
                                
                                # במקום השמה (=), אנחנו משתמשים ב-del כדי למחוק את המפתח מה-Session State.
                                # זה מונע את שגיאת ה-StreamlitAPIException.
                                if "with_val" in st.session_state:
                                    del st.session_state["with_val"]
                                    
                                if "conf_with_check" in st.session_state:
                                    del st.session_state["conf_with_check"]
                                
                                # השהיה קלה כדי שהמשתמש יספיק לראות את הודעת ההצלחה
                                time.sleep(0.5)
                                
                                # חשוב: לסגור את החיבור לפני הריצה מחדש
                                con.close()
                                
                                # קריאה לריצה מחדש - כעת הווידג'טים ייווצרו מחדש עם ערכי ברירת המחדל שלהם
                                st.rerun()
                            else:
                                st.error(msg)
                    else:
                        st.warning("Please wait a moment between actions.")



# Function to visually present asset metrics
def display_asset_card(asset):
    """
    Renders an asset summary card within the UI block.
    Validates availability based on timeframe price data and manages fallback alerts.
    """
    if asset['current_price'] is None:
        first_date = asset['first_trade_date']
        date_str = first_date.strftime('%Y-%m-%d') if hasattr(first_date, 'strftime') else str(first_date)
        
        # FIXED: Converted all UI warning and info strings strictly to English
        st.warning(f"⚠️ The stock **{asset['ticker']}** was not traded during this specific period.")
        st.info(f"Initial public trading for this asset started on: **{date_str}**")
        st.subheader(f"{asset['name']} ({asset['ticker']})")
        return 

    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        st.metric("Price", f"${asset['current_price']:,.2f}")
    with c2:
        st.subheader(f"{asset['name']} ({asset['ticker']})")
        st.caption(f"**Sector:** {asset['sector']} | **Industry:** {asset['industry']}")
    with c3:
        # Placeholder or container logic for active asset tracking imagery
        st.subheader("logo of the company")
        
    # Analysis Trigger Component aligned with execution state safeguards
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("📊 Run Deep Financial Analysis", key=f"analysis_btn_{asset['ticker']}", type="primary", width="stretch"):
        st.session_state.selected_ticker_for_analysis = asset['ticker']
        st.success(f"Selected {asset['ticker']} for quantitative research down-screen.")


# for showing purchase 
def show_buy_component(ticker, asset_price):
    """
    Enhanced purchase component with smart state management and 
    in-popover transaction confirmation connected directly to cloud engine.
    All source documentation and comments are maintained strictly in English.
    """
    portfolio_id = st.session_state.get('current_portfolio_id')
    sim_date = st.session_state.get('current_sim_date')
    
    # 1. Fetch available cash from state to prevent redundant DB calls before submission
    current_cash = st.session_state.get('current_available_cash', 0.0)

    # Unique state key to handle dynamic confirmation flow for this specific asset
    confirm_key = f"confirm_buy_{ticker}"
    if confirm_key not in st.session_state:
        st.session_state[confirm_key] = False

    with st.popover(f"🛒 Buy {ticker}", width="stretch"):
        st.subheader(f"Purchase {ticker}")
        st.write(f"Cash Available: **${current_cash:,.2f}**")
        
        # 2. Constraint validation
        max_shares = int(current_cash // asset_price) if asset_price > 0 else 0
        
        if max_shares <= 0:
            st.warning("Insufficient funds to buy this asset.")
            return

        # 3. Choose order sizing method
        buy_method = st.radio("Buy by:", ["Quantity", "Total price ($)"], horizontal=True, key=f"method_{ticker}")

        if buy_method == "Quantity":
            qty = st.number_input("Quantity", min_value=1, max_value=max_shares, step=1, key=f"buy_qty_{ticker}")
            total_cost = qty * asset_price
        else:
            amount_to_spend = st.number_input("Amount ($)", min_value=float(asset_price), max_value=float(current_cash), step=100.0, key=f"buy_amt_{ticker}")
            qty = int(amount_to_spend // asset_price)
            total_cost = qty * asset_price

        st.info(f"Total Order: **{qty}** shares for **${total_cost:,.2f}**")

        # 4. Smart two-step verification mechanism without redundant reruns
        if not st.session_state[confirm_key]:
            if st.button("Review Order", width="stretch"):
                st.session_state[confirm_key] = True
                st.rerun()  # Rerun is required here to switch to confirmation buttons layout
        else:
            st.warning("Confirm Transaction?")
            col_a, col_b = st.columns(2)
            
            with col_a:
                if st.button("✅ Confirm", type="primary", width="stretch"):
                    # Rate-limiting action boundary check
                    if is_action_allowed(wait_time=2):
                        
                        # 1. Get engine
                        cloud_engine = get_supabase_engine()
                        
                        # 2. FIX: Open a clean connection, NOT a transaction block (.connect() instead of .begin())
                        with cloud_engine.connect() as con:
                            success, msg = execute_asset_trade(
                                con=con, 
                                portfolio_id=portfolio_id, 
                                ticker=ticker, 
                                timestamp=sim_date, 
                                quantity=qty, 
                                side='buy'
                            )
                            
                        if success:
                            st.session_state[confirm_key] = False
                            st.session_state.current_available_cash -= total_cost
                            st.session_state.page = "dashboard_home"
                            st.toast(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.warning("Slow down...")

            with col_b:
                if st.button("❌ Cancel", width="stretch"):
                    st.session_state[confirm_key] = False
                    st.rerun()

# For showing holding positions
def render_holdings_table(con, portfolio_id, sim_date):
    st.subheader("🏢 Current Holdings (FIFO)")

    # --- INJECTING TARGETED STYLE FOR HOLDINGS TABLE ---
    st.markdown(
        """
        <style>
        /* Base row container alignment */
        .holding-row-item {
            display: flex;
            align-items: center;
            height: 96px; 
            font-size: 18px; 
            color: #1E293B;
            font-weight: 500;
            padding: 0 8px;
        }

        /* Force the entire Streamlit column row block to adopt a subtle background color 
            whenever an alternating row marker class is active inside it.
        */
        div[data-testid="stHorizontalBlock"]:has(.zebra-marker-even) {
            background-color: #F8FAFC !important;
            border-radius: 6px;
            padding: 4px 0;
        }
        
        /* PnL Badge configurations */
        .pnl-badge {
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 13px; 
            font-weight: 600;
            display: inline-block;
            margin-top: 2px;
        }
        .pnl-green {
            background-color: rgba(34, 197, 94, 0.15);
            color: #16A34A;
        }
        .pnl-red {
            background-color: rgba(239, 110, 110, 0.15);
            color: #DC2626;
        }

        /* Central Trade Button (Popover Wrapper) */
        div[data-testid="stPopover"]:has(button:contains("Trade")) > button {
            background-color: #6366F1 !important; /* Indigo Blue */
            color: #FFFFFF !important;
            border: 1px solid #4F46E5 !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
            font-size: 13px !important;
            height: 32px !important;
            padding: 0 12px !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
            transition: all 0.2s ease-in-out !important;
        }

        div[data-testid="stPopover"]:has(button:contains("Trade")) > button:hover {
            background-color: #4F46E5 !important; /* Darker Indigo */
            border-color: #4338CA !important;
            box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2) !important;
            transform: translateY(-0.5px);
        }

        /* Secondary Analyze Button (Outline Style) */
        button[key^="analyze_hold_"] {
            background-color: #FFFFFF !important;
            color: #4F46E5 !important; 
            border: 1px solid #E0E7FF !important; /* Soft Indigo Border */
            border-radius: 6px !important;
            font-weight: 500 !important;
            font-size: 13px !important;
            height: 32px !important;
            padding: 0 12px !important;
            margin-top: 6px !important; /* Visual breathing room from top button */
            transition: all 0.2s ease-in-out !important;
        }

        button[key^="analyze_hold_"]:hover {
            background-color: #F5F7FF !important; 
            border-color: #C7D2FE !important;
            color: #3730A3 !important;
            transform: translateY(-0.5px);
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # 1. FIXED: Convert query to Named Binds and wrap with text() to resolve the execution ArgumentError
    tx_query = """
    SELECT asset_id, quantity, price_per_share, side, timestamp
    FROM assets_transactions
    WHERE portfolio_id = :portfolio_id AND timestamp <= :sim_date
    ORDER BY timestamp, transaction_id
    """
    
    # We execute using the dictionary parameter layout required by SQLAlchemy 2.0
    tx_result = con.execute(text(tx_query), {"portfolio_id": portfolio_id, "sim_date": sim_date})
    all_tx = pd.DataFrame(tx_result.fetchall(), columns=tx_result.keys()) if hasattr(tx_result, 'keys') else pd.DataFrame()

    # 2. FIXED: Convert holdings query to Named Binds and wrap with text()
    holdings_query = """
    SELECT a.asset_id, a.ticker, a.name, a.industry, h.quantity
    FROM holdings h
    JOIN assets a ON h.asset_id = a.asset_id
    WHERE h.portfolio_id = :portfolio_id AND h.quantity > 0
    ORDER BY h.quantity DESC
    """
    hold_result = con.execute(text(holdings_query), {"portfolio_id": portfolio_id})
    holdings_df = pd.DataFrame(hold_result.fetchall(), columns=hold_result.keys()) if hasattr(hold_result, 'keys') else pd.DataFrame()

    if holdings_df.empty:
        st.info("Your portfolio is currently empty.")
        return

    # --- TABLE HEADER ---
    col_ratios = [1.0, 1.8, 1.8, 0.8, 1.0, 1.0, 1.3, 1.6]
    header_cols = st.columns(col_ratios)
    cols_names = ["Ticker", "Asset Name", "Industry", "Quantity", "Avg Buy", "Current Price", "Market Value & PnL", "Actions"]
    
    for col, name in zip(header_cols, cols_names):
        col.markdown(f"<p style='color:#64748B; font-weight:600; font-size:13px; margin:0; padding:0 8px;'>{name}</p>", unsafe_allow_html=True)
    st.markdown("<hr style='margin: 8px 0 12px 0; border-color: rgba(0,0,0,0.08);'>", unsafe_allow_html=True)

    # --- TABLE BODY ROWS ---
    for idx, row_data in holdings_df.iterrows():
        asset_id = row_data['asset_id']
        ticker = row_data['ticker']
        industry = row_data['industry']
        available_qty = int(row_data['quantity'])
        
        # Check if row is even to attach our targetable style marker class
        zebra_marker = "zebra-marker-even" if idx % 2 == 0 else ""
        
        # A) Calculate FIFO metrics
        if not all_tx.empty:
            asset_tx = all_tx[all_tx['asset_id'] == asset_id]
            avg_buy_price = calculate_fifo_avg_price(asset_tx)
        else:
            avg_buy_price = 0.0
        
        # B) FIXED: Convert prices query to Named Binds and wrap with text()
        current_price_res = con.execute(text("""
            SELECT close FROM prices 
            WHERE asset_id = :asset_id AND timestamp <= :sim_date 
            ORDER BY timestamp DESC LIMIT 1
        """), {"asset_id": asset_id, "sim_date": sim_date}).fetchone()
        
        current_price = current_price_res[0] if current_price_res else 0.0

        total_value = available_qty * current_price
        pnl_perc = ((current_price / avg_buy_price) - 1) * 100 if avg_buy_price > 0 else 0
        pnl_class = "pnl-green" if pnl_perc >= 0 else "pnl-red"

        # C) Render current table row
        cols = st.columns(col_ratios)
        
        # We put the marker class inside the first column wrapper to activate the CSS row rule
        cols[0].markdown(f"<div class='holding-row-item {zebra_marker}'><strong>{ticker}</strong></div>", unsafe_allow_html=True)
        cols[1].markdown(f"<div class='holding-row-item' style='color:#475569;'>{row_data['name']}</div>", unsafe_allow_html=True)
        cols[2].markdown(f"<div class='holding-row-item' style='color:#475569;'>{industry}</div>", unsafe_allow_html=True)
        cols[3].markdown(f"<div class='holding-row-item'>{available_qty:,}</div>", unsafe_allow_html=True)
        cols[4].markdown(f"<div class='holding-row-item'>${avg_buy_price:,.2f}</div>", unsafe_allow_html=True)
        cols[5].markdown(f"<div class='holding-row-item'>${current_price:,.2f}</div>", unsafe_allow_html=True)
        
        # Combined Value & PnL Block
        cols[6].markdown(
            f"""
            <div class='holding-row-item' style='display: flex; flex-direction: column; justify-content: center;'>
                <span style='font-weight: 600; font-size: 16px; color: #1E293B;'>${total_value:,.2f}</span>
                <div><span class='pnl-badge {pnl_class}'>{pnl_perc:+.2f}%</span></div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # D) Combined Actions Layout (Trade Popover / Deep Analysis Dialog)
        with cols[7]:
            # Safeguard cash extraction from session state layout
            p_cash = st.session_state.get('current_available_cash', 0.0)
            if hasattr(p_cash, 'fetchone'):
                p_cash = float(p_cash.fetchone()[0])
            else:
                p_cash = float(p_cash)

            with st.popover("💼 Trade", width="stretch"):
                # 1. Select Trade Side using a unique persistent key anchor blueprint
                trade_side = st.radio(
                    "Direction",
                    options=["Buy", "Sell"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key=f"trade_side_radio_{ticker}_{idx}"
                )
                
                st.markdown("<hr style='margin: 8px 0; border-color: rgba(0,0,0,0.05);'>", unsafe_allow_html=True)
                
                if trade_side == "Sell":
                    st.markdown(f"<p style='font-size:12px; margin:0 0 8px 0; color:#64748B;'>Available to sell: <strong style='color:#1E293B;'>{available_qty:,} shares</strong></p>", unsafe_allow_html=True)
                    
                    trade_qty = st.number_input(
                        "Quantity to sell", 
                        min_value=1, 
                        max_value=max(1, available_qty),
                        value=available_qty, 
                        step=1, 
                        key=f"t_input_sell_val_{ticker}_{idx}",
                        label_visibility="collapsed"
                    )
                    
                    # Estimated credit display
                    est_credit = trade_qty * current_price
                    st.markdown(f"<p style='font-size:11px; color:#64748B; margin-top:2px;'>Est. Credit: <strong>${est_credit:,.2f}</strong></p>", unsafe_allow_html=True)
                    
                    if st.button("Confirm Sale", key=f"btn_s_commit_{ticker}_{idx}", type="primary", width="stretch"):
                        if trade_qty > available_qty:
                            st.error(f"❌ Cannot sell {trade_qty}. You only have {available_qty} shares.")
                        else:
                            success, msg = execute_asset_trade(
                                con, portfolio_id, ticker, sim_date, trade_qty, side='sell'
                            )
                            if success:
                                st.toast(f"📉 Successfully sold {trade_qty:,} shares of {ticker}!")
                                st.rerun()
                            else:
                                st.error(msg)
                                
                else: # BUY SIDE
                    st.markdown(f"<p style='font-size:12px; margin:0 0 8px 0; color:#64748B;'>Available Cash: <strong style='color:#1E293B;'>${p_cash:,.2f}</strong></p>", unsafe_allow_html=True)
                    
                    trade_qty = st.number_input(
                        "Quantity to buy", 
                        min_value=1, 
                        value=1, 
                        step=1, 
                        key=f"t_input_buy_val_{ticker}_{idx}",
                        label_visibility="collapsed"
                    )
                    
                    # Estimated cost calculation
                    est_cost = trade_qty * current_price
                    max_affordable = int(p_cash // current_price) if current_price > 0 else 0
                    
                    st.markdown(
                        f"""
                        <p style='font-size:11px; color:#64748B; margin: 2px 0 0 0;'>Est. Cost: <strong>${est_cost:,.2f}</strong></p>
                        <p style='font-size:10px; color:#94A3B8; margin: 0 0 4px 0;'>Max affordable: {max_affordable:,} shares</p>
                        """, 
                        unsafe_allow_html=True
                    )
                    
                    if st.button("Confirm Purchase", key=f"btn_b_commit_{ticker}_{idx}", type="primary", width="stretch"):
                        if est_cost > p_cash:
                            st.error(f"❌ Insufficient cash. Total cost is ${est_cost:,.2f} but you only have ${p_cash:,.2f}")
                        else:
                            success, msg = execute_asset_trade(
                                con, portfolio_id, ticker, sim_date, trade_qty, side='buy'
                            )
                            if success:
                                st.toast(f"🚀 Successfully purchased {trade_qty:,} shares of {ticker}!")
                                st.rerun()
                            else:
                                st.error(msg)
                            
            if st.button("🔍 Analyze", key=f"analyze_hold_{ticker}_{idx}", help="View Deep Analysis", width="stretch"):
                show_asset_analysis_dialog(ticker)

        # Subtle structural line break between rows 
        st.markdown("<hr style='margin: 6px 0; border-color: rgba(0,0,0,0.04);'>", unsafe_allow_html=True)


# for portfolio performance analsys 
def render_performance_chart(df, title="Portfolio Performance History"):
    """
    Renders a clean performance chart with safe return calculations
    that are robust to deposits and zero-start portfolios.
    """

    if df is None or df.empty:
        st.warning("No performance data available.")
        return

    # =======================================
    # DATA PREPARATION
    # =======================================
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    last_date = df["timestamp"].max()

    # =======================================
    # TIME RANGE SELECTION
    # =======================================
    col_left, col_right = st.columns([3, 1])

    with col_right:
        time_range = st.selectbox(
            "Timeframe",
            ["1 Week", "1 Month", "6 Months", "Year to Date", "1 Year", "All Time"],
            index=4,
            label_visibility="collapsed",
        )

    # =======================================
    # TIME FILTERING
    # =======================================
    if time_range == "1 Week":
        start_date = last_date - pd.Timedelta(days=7)
    elif time_range == "1 Month":
        start_date = last_date - pd.Timedelta(days=30)
    elif time_range == "6 Months":
        start_date = last_date - pd.Timedelta(days=180)
    elif time_range == "Year to Date":
        start_date = pd.Timestamp(year=last_date.year, month=1, day=1)
    elif time_range == "1 Year":
        start_date = last_date - pd.Timedelta(days=365)
    else:
        start_date = df["timestamp"].min()

    filtered_df = df[df["timestamp"] >= start_date].copy()

    if filtered_df.empty:
        st.warning("No data in selected timeframe.")
        return

    # =======================================
    # SAFE RETURN CALCULATION
    # (prevents INF / fake returns from deposits)
    # =======================================

    valid_values = filtered_df[filtered_df["value"] > 0]

    if len(valid_values) < 2:
        p_start = None
        p_end = None
    else:
        p_start = valid_values["value"].iloc[0]
        p_end = valid_values["value"].iloc[-1]

    if p_start and p_start > 0:
        ret_pct = ((p_end / p_start) - 1) * 100
        ret_cash = p_end - p_start
    else:
        ret_pct = 0.0
        ret_cash = 0.0

    # =======================================
    # METRICS DISPLAY
    # =======================================
    m1, m2, m3 = st.columns(3)

    m1.metric(
        "Portfolio Value",
        f"${filtered_df['value'].iloc[-1]:,.0f}",
    )

    m2.metric(
        "Absolute Change",
        f"${ret_cash:,.0f}",
    )

    m3.metric(
        "Return (%)",
        f"{ret_pct:.2f}%",
    )

    # =======================================
    # CHART STYLING
    # =======================================
    y_min = filtered_df["value"].min()
    y_max = filtered_df["value"].max()

    y_range = y_max - y_min
    padding = y_range * 0.05 if y_range > 0 else y_max * 0.05

    y_min -= padding
    y_max += padding

    # Color based on performance
    line_color = "#2ecc71" if ret_cash >= 0 else "#e74c3c"

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=filtered_df["timestamp"],
            y=filtered_df["value"],
            mode="lines",
            line=dict(width=3, color=line_color, shape="spline"),
            fill="tozeroy",
            fillcolor=f"rgba{tuple(list(int(line_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + [0.08])}",
            hovertemplate="<b>Value:</b> $%{y:,.0f}<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_white",
        height=420,
        margin=dict(l=0, r=0, t=20, b=0),
        xaxis=dict(
            showgrid=False,
            title=None,
        ),
        yaxis=dict(
            range=[y_min, y_max],
            showgrid=True,
            gridcolor="#f2f2f2",
            tickprefix="$",
            separatethousands=True,
        ),
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False},
    )


# for the assets serch component
def asset_search_component(con):
    """
    Manages asset search functionality and caches global asset list from public cloud storage.
    Persists the selected asset ticker in session state for downstream financial deep analysis.
    """
    
    # Initial load of the asset list into persistent session state cache from GCS
    if 'all_assets_list' not in st.session_state:
        try:
            # Direct public HTTP access to the Google Cloud Storage bucket containing the parquet dataset
            # Replace the mock URL below with your exact public asset bucket endpoint link
            gcs_public_url = "https://storage.googleapis.com/stratify-historical-data/data_snapshots/assets.parquet"
            
            # DuckDB natively reads column subsets remotely from raw public cloud URLs extremely fast
            assets_df = con.execute(f"SELECT ticker, name FROM read_parquet('{gcs_public_url}')").df()
            st.session_state.all_assets_list = [f"{row['ticker']} | {row['name']}" for _, row in assets_df.iterrows()]
        except Exception as e:
            st.error(f"⚠️ Failed to pull assets directory from cloud layer: {e}")
            st.session_state.all_assets_list = []

    st.subheader("Search by Ticker or Company Name")
    
    # Render searchable configuration box populated with structured cloud metadata
    selected_option = st.selectbox(
    label="Select Asset to Analyze",   # Clean structural accessibility label
    label_visibility="collapsed",
    options=[""] + st.session_state.all_assets_list,
    format_func=lambda x: "Type to search..." if x == "" else x,
    index=0,
    key="strategy_search_box"
    )

    # Parse and anchor selected node metadata securely across runtime cycles
    if selected_option:
        st.session_state.selected_ticker_for_analysis = selected_option.split(" | ")[0]


# for analysing an asset (analysis diolog pop up)
@st.dialog("Asset Analysis Deep-Dive", width="large")
def show_asset_analysis_dialog(asset_ticker):
    """
    Renders a comprehensive quantitative analysis modal popup window for a selected asset.
    Handles temporal slice queries across pricing, fundamentals, and strategic factor indices.
    Safely resolves catalog contexts to prevent database isolation drops inside cloud threads.
    """
    # 1. Extraction of basic metadata and validation of active data architecture
    if 'con' not in st.session_state:
        st.error("Connection lost")
        return
        
    con = st.session_state.con
    
    # SAFETIES: If running inside an isolated dialog thread, ensure the catalog is bound to the file
    if con is None:
        db_path = st.session_state.get('DB_PATH', 'stratify.duckdb')
        con = duckdb.connect(database=db_path, read_only=False)
        
    asset_ticker_upper = asset_ticker.upper()
    
    # Context query executed smoothly via standard database driver routing
    asset_data = con.execute("SELECT asset_id, name, sector FROM assets WHERE ticker = ?", [asset_ticker_upper]).fetchone()
    if not asset_data:
        st.error("Asset not found")
        return
        
    a_id, a_name, a_sector = asset_data
    sim_date = st.session_state.current_sim_date

    st.title(f"{a_name} ({asset_ticker_upper})")
    st.caption(f"Analysis up to simulation date: {sim_date.strftime('%Y-%m-%d') if hasattr(sim_date, 'strftime') else str(sim_date)}")

    # 2. Fetch tracking datasets via modern virtual relation routing architectures
    price_df = con.execute("""
        SELECT timestamp, close, volume 
        FROM prices 
        WHERE asset_id = ? AND timestamp <= ?
        ORDER BY timestamp ASC
    """, [a_id, sim_date]).df()

    fund_data = con.execute("""
        SELECT pe_ratio, market_cap, revenue, eps 
        FROM fundamentals 
        WHERE asset_id = ? AND timestamp <= ?
        ORDER BY timestamp DESC LIMIT 1
    """, [a_id, sim_date]).fetchone()
    
    factors_data = con.execute("""
        SELECT *
        FROM asset_factors_normalized_final
        WHERE asset_id = ?
          AND timestamp <= ?
          AND timestamp >= ? + INTERVAL '-1 week'
    """, [a_id, sim_date, sim_date]).df()
    
    # Presentation initialization via tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Price Chart", "📊 Fundamentals", "🔍 Strategy Analysis (Market)", "🗺️ Factor Mapping"])

    with tab1:
        time_range = st.segmented_control(
            "Select Range",
            options=["1W", "1M", "6M", "1Y", "All"],
            default="1W",
            key=f"range_{asset_ticker_upper}"
        )

        end_date = st.session_state.current_sim_date
        if time_range == "1W":
            start_date = end_date - timedelta(days=7)
        elif time_range == "1M":
            start_date = end_date - timedelta(days=30)
        elif time_range == "6M":
            start_date = end_date - timedelta(days=180)
        elif time_range == "1Y":
            start_date = end_date - timedelta(days=365)
        else:
            start_date = pd.Timestamp.min

        # Direct SQL pipeline fetch executed flawlessly
        filtered_price_df = con.execute("""
            SELECT timestamp, close 
            FROM prices 
            WHERE asset_id = ? 
              AND timestamp <= ? 
              AND timestamp >= ?
            ORDER BY timestamp ASC
        """, [a_id, end_date, start_date]).df()

        if not filtered_price_df.empty:
            first_price = filtered_price_df['close'].iloc[0]
            last_price = filtered_price_df['close'].iloc[-1]
            abs_change = last_price - first_price
            pct_change = (abs_change / first_price) * 100
            
            if abs_change >= 0:
                chart_color = '#2ecc71'
                fill_color = 'rgba(46, 204, 113, 0.1)'
                delta_color = "normal" 
            else:
                chart_color = '#e74c3c'
                fill_color = 'rgba(231, 76, 60, 0.1)'
                delta_color = "inverse" 

            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("Price", f"${last_price:,.2f}")
            with col_m2:
                st.metric("Change ($)", f"{abs_change:+,.2f}$", delta_color=delta_color)
            with col_m3:
                st.metric("Change (%)", f"{pct_change:+.2f}%", delta_color=delta_color)
                
            st.divider()

            y_min = filtered_price_df['close'].min()
            y_max = filtered_price_df['close'].max()
            padding = (y_max - y_min) * 0.15

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=filtered_price_df['timestamp'], 
                y=filtered_price_df['close'], 
                mode='lines', 
                line=dict(color=chart_color, width=2.5),
                fill='tonexty',
                fillcolor=fill_color,
                hovertemplate="<b>Date:</b> %{x}<br><b>Price:</b> $%{y:,.2f}<extra></extra>"
            ))
            
            fig.update_layout(
                height=300,
                margin=dict(l=0, r=0, t=5, b=0),
                xaxis=dict(showgrid=False),
                yaxis=dict(
                    showgrid=True, 
                    gridcolor='rgba(200, 200, 200, 0.2)', 
                    range=[y_min - padding, y_max + padding],
                    zeroline=False
                ),
                template="plotly_white",
                hovermode="x unified"
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.warning("No data available for this specific time range.")

    with tab2:
        if fund_data:
            pe, mcap, rev, eps = fund_data
            c1, c2 = st.columns(2)
            c1.metric("P/E Ratio", f"{pe:.2f}" if pe else "N/A")
            c1.metric("Market Cap", f"${mcap/1e9:.1f}B" if mcap else "N/A")
            c2.metric("Revenue", f"${rev/1e9:.1f}B" if rev else "N/A")
            c2.metric("EPS", f"${eps:.2f}" if eps else "N/A")
        else:
            st.info("No fundamental data recorded up to this date.")

    with tab3:
        u_id = int(st.session_state.get('user_id', 1))
        p_id = int(st.session_state.get('current_portfolio_id', 0))
        use_cloud = st.session_state.get('use_cloud', False)
        
        # 1. Architectural routing to fetch user strategy preferences
        if use_cloud:
            query_strat = "SELECT * FROM user_preferences_strategy WHERE user_id = :user_id AND portfolio_id = :portfolio_id"
            strategies_df = get_data(query_strat, {"user_id": u_id, "portfolio_id": p_id}, use_cloud=True)
        else:
            query_strat = "SELECT * FROM user_preferences_strategy WHERE user_id = ? AND portfolio_id = ?"
            strategies_df = get_data(query_strat, [u_id, p_id], use_cloud=False)

        if strategies_df.empty:
            st.info("No customized asset target strategies formulated for this portfolio yet.")
        else:
            selected_name = st.selectbox("Compare with Strategy:", strategies_df['strategy_name'], key="strat_select_market", placeholder="Select a strategy")
            if selected_name:
                strat_row = strategies_df[strategies_df['strategy_name'] == selected_name].iloc[0]

            # 2. Architectural routing to fetch target asset normalized factors
            FACTORS_SOURCE = "asset_factors_normalized_final_cloud" if use_cloud else "asset_factors_normalized_final"
            
            if use_cloud:
                query_stock_factors = f"SELECT * FROM {FACTORS_SOURCE} WHERE asset_id = :asset_id ORDER BY timestamp DESC LIMIT 1"
                stock_data = get_data(query_stock_factors, {"asset_id": int(a_id)}, use_cloud=True)
            else:
                query_stock_factors = f"SELECT * FROM {FACTORS_SOURCE} WHERE asset_id = ? ORDER BY timestamp DESC LIMIT 1"
                stock_data = get_data(query_stock_factors, [int(a_id)], use_cloud=False)

            if stock_data.empty:
                st.warning(f"No factors found for {asset_ticker_upper} in tracking matrices.")
            else:
                comparison_map = {
                    "momentum_preference": "momentum_factor_market", 
                    "value_preference": "value_factor_market",
                    "quality_preference": "quality_factor_market",
                    "growth_preference": "growth_factor_market",
                    "defensive_preference": "defensive_factor_market",
                    "size_preference": "size_factor_market",
                }
                
                h1, h2, h3 = st.columns([1, 2, 1.5])
                h1.caption("FACTOR")
                h2.caption("ASSET PERFORMANCE (0-100)")
                h3.caption("STRATEGY MATCH")

                for pref_col, actual_col in comparison_map.items():
                    target_val = float(strat_row.get(pref_col, 50))
                    actual_val = float(stock_data.iloc[0].get(actual_col, 0))
                    
                    diff = abs(target_val - actual_val)
                    match_pct = max(0, 100 - diff)
                    gap = actual_val - target_val

                    if actual_val >= 70:
                        score_color = "#28a745"  
                    elif actual_val >= 40:
                        score_color = "#ffc107"  
                    else:
                        score_color = "#dc3545"  

                    if match_pct >= 70:
                        match_color = "#28a745"  
                    elif match_pct >= 50:
                        match_color = "#1f77b4"  
                    elif match_pct >= 30:
                        match_color = "#ffc107"  
                    else:
                        match_color = "#dc3545"  

                    c1, c2, c3 = st.columns([1, 2, 1.5])
                    factor_key = actual_col.replace('_factor_market', '').lower()
                    label = factor_key.capitalize()

                    FACTOR_HELP = {
                        "momentum": "**Momentum Factor**\n\nIdentifies assets in a strong upward trend.",
                        "value": "**Value Factor**\n\nIdentifies stocks trading at a discount relative to fundamentals.",
                        "quality": "**Quality Factor**\n\nFocuses on companies with strong financial health.",
                        "growth": "**Growth Factor**\n\nIdentifies companies expanding business rapidly.",
                        "defensive": "**Defensive Factor**\n\nPrioritizes stability and risk reduction.",
                        "size": "**Size Factor**\n\nCaptures the Small-Cap Effect profile metrics."
                    }
                    
                    help_text = FACTOR_HELP.get(factor_key, "Factor explanation not found.")

                    with c1:
                        st.markdown("<div style='padding-top: 10px;'></div>", unsafe_allow_html=True)
                        st.markdown(f"**{label}**", help=help_text)

                    bar_html = f"""
                    <div style="margin-top: 5px; padding-right: 15px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                            <span style="font-size: 0.9rem; font-weight: bold; color: {score_color};">{actual_val:.0f}</span>
                        </div>
                        <div style="width: 100%; background-color: #e9ecef; border-radius: 4px; height: 10px;">
                            <div style="width: {actual_val}%; background-color: {score_color}; height: 100%; border-radius: 4px;"></div>
                        </div>
                    </div>
                    """
                    c2.markdown(bar_html, unsafe_allow_html=True)

                    with c3:
                        if match_pct >= 85:
                            fit_label = "Perfect Match"; icon = "🌟"
                        elif match_pct >= 70:
                            fit_label = "Good Fit"; icon = "✅"
                        elif match_pct >= 50:
                            fit_label = "Slight Deviation"; icon = "⚖️"
                        else:
                            fit_label = "Too High" if gap > 0 else "Too Low"; icon = "⚠️"

                        st.markdown(f"""
                            <div style='text-align: right; border-left: 2px solid #f0f2f6; padding-left: 10px; padding-top: 2px;'>
                                <div style='font-size: 0.9rem; font-weight: bold; color: {match_color}; margin-bottom: -2px;'>
                                    {icon} {fit_label}
                                </div>
                                <div style='font-size: 0.75rem; color: #888;'>
                                    {match_pct:.0f}% similarity
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                    st.divider()     
        
    with tab4:
        try:
            st.divider()
            st.subheader("📊 Factor Positioning")
            render_stock_factor_maps(con, asset_ticker_upper)
            st.divider()
        except Exception as e:
            st.warning(f"Factor visualization unavailable: {e}")



# Strategy creation and editing component
def strategy_creating_component(con, portfolio_id):

    # =======================================
    # FACTORS DEFINITION
    # =======================================
    FACTORS = [
        "momentum",
        "value",
        "quality",
        "growth",
        "defensive",
        "size",
    ]

    # =======================================
    # SESSION STATE INITIALIZATION
    # =======================================
    if "weights" not in st.session_state:

        row = con.execute(
            """
            SELECT momentum_preference, value_preference, quality_preference, 
                   growth_preference, defensive_preference, size_preference, liquidity_preference 
            FROM user_preferences_strategy
            WHERE portfolio_id = ?
            """,
            [portfolio_id],
        ).fetchone()

        if row:
            # Map only the first 7 elements to FACTORS
            st.session_state.weights = dict(zip(FACTORS, row[:7]))
        else:
            st.session_state.weights = {f: 50.0 for f in FACTORS}

    if "slider_rev" not in st.session_state:
        st.session_state.slider_rev = 0

    if "answers" not in st.session_state:
        st.session_state.answers = [None] * 7

    if "show_questions" not in st.session_state:
        st.session_state.show_questions = False

    if "current_question" not in st.session_state:
        st.session_state.current_question = 0

    if "show_save_box" not in st.session_state:
        st.session_state.show_save_box = False
        
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = 0

    # =======================================
    # TAB CONFIG
    # =======================================
    tab_options = [
        "🧠 Questionnaire",
        "⚙️ Strategies Settings",
        "📊 Multi-Strategy Allocation",
        "🏆 Final Step",
    ]

    # =======================================
    # STATE INIT
    # =======================================
    # FIX: Initialize with integer index 0 instead of the string name
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = 0

    # Render the radio selector with the correct integer index
    tab_selector = st.radio(
        "",
        tab_options,
        horizontal=True,
        index=st.session_state.active_tab,
    )

    # FIX: Update the session state to the newly selected index dynamically
    new_index = tab_options.index(tab_selector)
    if new_index != st.session_state.active_tab:
        st.session_state.active_tab = new_index
        st.rerun()

    # =======================================
    # STEP 1 — QUESTIONNAIRE
    # =======================================
    if st.session_state.active_tab == 0:

        st.markdown(
            """
            <div class="section-card">
                <h2>🧠 Investment Personality Questionnaire</h2>
                <p style="font-size:15px; opacity:0.75; margin-top:10px;">
                    Answer a few simple questions to automatically generate
                    an investment strategy tailored to your preferences.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        questions_list = [
    "I prefer paying more for a trusted, reliable brand rather than taking a chance on a cheaper alternative.",
    
    "When a stock is getting a lot of attention in the news, I feel more interested in investing in it.",
    
    "I prefer stable and predictable investments over the possibility of very large short-term gains.",
    
    'When a stock becomes chaper than it "supposed" to be, I see it as a buying opportunity - even if recovery is uncertain.',
    
    "I only feel comfortable investing in large, well-established companies that most people recognize.",
    
    "Even small temporary declines in my portfolio can make me feel uncomfortable or stressed. (up to 10 %)",
    
    "I prefer companies with strong and proven profits today over companies promising rapid future growth.",
]

        if not st.session_state.show_questions:

            st.info(
                "You may skip this step and configure everything manually in the next tab."
            )
            col_start , col_skip = st.columns([3,2])
            with col_start:
                if st.button("Skip Questionnaire"):
                    st.session_state.active_tab = 1
                    st.rerun()
            with col_skip:
                if st.button(
                    "🚀 Start Questionnaire",
                    width="stretch",
                    type="primary",
                ):
                    st.session_state.show_questions = True
                    st.session_state.current_question = 0
                    st.rerun()

        else:
            i = st.session_state.current_question

            st.markdown(
                f"""
                <div class="question-box">
                    <div style="font-size:13px; font-weight:600; color:#4f46e5; margin-bottom:12px;">
                        QUESTION {i+1} OF 7
                    </div>
                    <div style="font-size:24px; font-weight:700; line-height:1.5;">
                        {questions_list[i]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            answer = st.radio(
                "Choose your answer:",
                ["Yes", "No"],
                horizontal=True,
                index=None,
                key=f"q_radio_{portfolio_id}_{i}",
            )

            if answer == "Yes":
                st.session_state.answers[i] = True
            elif answer == "No":
                st.session_state.answers[i] = False

            st.progress((i + 1) / 7)
            st.write("")

            # Action layout inside the questionnaire step
            col1, col2, col3 = st.columns([1, 1, 1])

            with col1:
                if i > 0:
                    if st.button("⬅ Previous", width="stretch"):
                        st.session_state.current_question -= 1
                        st.rerun()

            with col2:
                if st.button("❌ Exit", width="stretch"):
                    st.session_state.show_questions = False
                    st.rerun()

            with col3:
                if i < 6:
                    if st.button("Next ➡", width="stretch", type="primary"):
                        st.session_state.current_question += 1
                        st.rerun()
                else:
                    if st.button("✅ Proceed to Sliders", width="stretch", type="primary"):

                        @st.dialog("Processing your strategy 🧠")
                        def processing_modal():

                            st.write("We received your answers.")
                            st.write("Building a personalized investment strategy...")

                            with st.spinner("Calculating..."):
                                time.sleep(5)

                            st.success("Done! Redirecting...")

                        processing_modal()

                        q_data = build_questionnaire(*st.session_state.answers)
                        new_weights = questionnaire_to_weights(q_data, FACTORS)

                        st.session_state.weights = new_weights
                        st.session_state.slider_rev += 1
                        st.session_state.show_questions = False
                        st.session_state.active_tab = 1

                        st.rerun()
    # =======================================
    # STEP 2 — STRATEGY SETTINGS AND SAVING
    # =======================================
    if st.session_state.active_tab == 1:
        
        # Modern global UI styling for main container action buttons
        st.markdown(
            """
            <style>
            /* Target step action button specifically */
            div[data-testid="stColumn"] button[key^="proceed_btn"] {
                background-color: #2563EB !important; 
                color: #FFFFFF !important; 
                border-radius: 8px !important;
                font-weight: 600 !important; 
                font-size: 14px !important;
                border: none !important;
                box-shadow: 0px 4px 6px rgba(37, 99, 235, 0.15) !important;
                transition: all 0.2s ease-in-out !important;
                padding: 10px 20px !important;
                height: 44px !important;
            }
            
            div[data-testid="stColumn"] button[key^="proceed_btn"]:hover {
                background-color: #1D4ED8 !important;
                box-shadow: 0px 4px 12px rgba(29, 78, 216, 0.3) !important;
                transform: translateY(-1px);
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        
        # Top Section: Strategy Header Block
        with st.container(border=True):
            col_text, col_btn = st.columns([7, 3])
            
            with col_text:
                st.markdown(
                    """
                    <div style="padding: 0px 0px;">
                        <h2 style="margin: 0; font-weight: 700; color: #1E293B; font-size: 24px;">⚙️ Strategy Configuration</h2>
                        <p style="font-size: 14px; color: #64748B; margin-top: 0px; margin-bottom: 0;">
                            Fine-tune the importance weights of each core investment factor. 
                            Higher value states reflect a stronger model priority preference.
                        </p>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
            with col_btn:
                # Vertical alignment structural spacing
                st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                # Replace the standalone button with an interactive popover component
                # 1. Toast listener: check if a success message was pending from a previous rerun
                toast_key = f"save_success_msg_{portfolio_id}"
                if toast_key in st.session_state:
                    st.toast(st.session_state[toast_key], icon="✅")
                    del st.session_state[toast_key] # Clean up state immediately after triggering

                # Initialize a revision counter for the popover to force close it when needed
                if f"pop_rev_{portfolio_id}" not in st.session_state:
                    st.session_state[f"pop_rev_{portfolio_id}"] = 0

                # Render popover with a dynamic key configuration
                with st.popover("💾 Save Strategy", key=f"proceed_btn_action_{portfolio_id}_rev_{st.session_state[f'pop_rev_{portfolio_id}']}", width="stretch"):
                    st.markdown("<p style='font-size:14px; font-weight:600; margin-bottom:4px;'>Strategy Name</p>", unsafe_allow_html=True)
                    
                    new_strat_name = st.text_input(
                        label="Strategy Name Input",
                        placeholder="Example: Defensive Growth",
                        key=f"pop_new_strat_name_{portfolio_id}",
                        label_visibility="collapsed"
                    )

                    # Dynamic database injection execution block
                    if st.button("✅ Save Configuration", width="stretch", type="primary", key=f"pop_save_confirm_{portfolio_id}"):
                        if new_strat_name.strip():
                            u_id = int(st.session_state.get("user_id", 0))
                            p_id = int(portfolio_id)

                            # Check the total number of strategies already saved for this specific portfolio and user
                            strategy_count_check = con.execute(
                                """
                                SELECT COUNT(*) 
                                FROM user_preferences_strategy 
                                WHERE portfolio_id = ? AND user_id = ?
                                """,
                                [p_id, u_id]
                            ).fetchone()

                            # Extract count value safely
                            current_strategy_count = strategy_count_check[0] if strategy_count_check else 0

                            # Enforce a maximum limit of 4 strategies per portfolio
                            if current_strategy_count >= 4:
                                st.error(
                                    """
                                    ❌ Limit reached: You cannot save more than 4 strategies per portfolio.
                                    
                                    Delete one of your strategies to make room.
                                    """
                                )
                            else:
                                # Verify that the targeted strategy identity does not cause a collision
                                existing_check = con.execute(
                                    """
                                    SELECT strategy_name
                                    FROM user_preferences_strategy
                                    WHERE strategy_name = ? AND portfolio_id = ? AND user_id = ?
                                    """,
                                    [new_strat_name.strip(), p_id, u_id],
                                ).fetchone()

                                if existing_check:
                                    st.error("This strategy name already exists.")
                                else:
                                    try:
                                        w = st.session_state.weights
                                        
                                        con.execute(
                                            """
                                            INSERT INTO user_preferences_strategy (
                                                strategy_name, user_id, portfolio_id, timestamp,
                                                momentum_preference, value_preference, quality_preference,
                                                growth_preference, defensive_preference, size_preference,
                                                liquidity_preference, diversification_preference
                                            )
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,)
                                            """,
                                            [
                                                new_strat_name.strip(),
                                                u_id,
                                                p_id,
                                                datetime.now(),
                                                w.get("momentum", 50),
                                                w.get("value", 50),
                                                w.get("quality", 50),
                                                w.get("growth", 50),
                                                w.get("defensive", 50),
                                                w.get("size", 50),
                                                w.get("liquidity", 50),
                                                w.get("diversification", 50),
                                            ]
                                        )
                                        # 2. Store success message into session state before forcing page mutation refresh
                                        st.session_state[f"is_custom_{portfolio_id}"] = False
                                        st.session_state[toast_key] = f"Strategy '{new_strat_name.strip()}' saved successfully!"
                                        
                                        # Increment key revision to force close the popover component layout
                                        st.session_state[f"pop_rev_{portfolio_id}"] += 1
                                        
                                        st.rerun()

                                    except Exception as e:
                                        st.error(f"Database error: {e}")
                        else:
                            st.warning("Please enter a strategy name.")

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        # ===================================
        # Main Dashboard Grid Layout
        # ===================================
        col_strategies, col_sliders = st.columns([2, 5])
        
        # Left Configuration Sidebar Pane
        with col_strategies:
        
            # Block 1: Saved Profiles Management
            with st.container(border=True):
                # Initialize custom flag state if missing
                if f"is_custom_{portfolio_id}" not in st.session_state:
                    st.session_state[f"is_custom_{portfolio_id}"] = False

                # Dynamic title displaying "(Custom)" badge when sliders are modified
                if st.session_state[f"is_custom_{portfolio_id}"]:
                    st.markdown("<p style='font-size: 16px; font-weight: 700; margin: 0 0 12px 0; color: #0F172A;'>📂 Saved Profiles <span style='color: #EA580C; font-size: 12px; font-weight: 500; background-color: #FFEDD5; padding: 2px 6px; border-radius: 4px; margin-left: 4px;'>Custom</span></p>", unsafe_allow_html=True)
                else:
                    st.markdown("<p style='font-size: 16px; font-weight: 700; margin: 0 0 12px 0; color: #0F172A;'>📂 Saved Profiles</p>", unsafe_allow_html=True)
                saved_strategies = con.execute(
                    """
                    SELECT strategy_name,
                        momentum_preference, value_preference, quality_preference,
                        growth_preference, defensive_preference, size_preference,
                        liquidity_preference, diversification_preference
                    FROM user_preferences_strategy
                    WHERE portfolio_id = ?
                    ORDER BY timestamp DESC
                    """,
                    [portfolio_id],
                ).fetchall()

                if saved_strategies:
                    strategy_options = {
                        s[0]: {
                            "momentum": s[1],
                            "value": s[2],
                            "quality": s[3],
                            "growth": s[4],
                            "defensive": s[5],
                            "size": s[6],
                            "liquidity": s[7],
                            "diversification": s[8],
                        }
                        for s in saved_strategies
                    }

                    def on_strategy_change():
                        new_selection = st.session_state[f"load_strat_{portfolio_id}"]
                        st.session_state.weights = strategy_options[new_selection]
                        
                        # Reset custom flag when a clean saved profile is loaded
                        st.session_state[f"is_custom_{portfolio_id}"] = False
                        st.session_state.slider_rev += 1

                    selected_name = st.selectbox(
                        "Active Strategy Profile",
                        options=list(strategy_options.keys()),
                        key=f"load_strat_{portfolio_id}",
                        on_change=on_strategy_change,
                        label_visibility="collapsed"
                    )

                    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                    
                    with st.popover("🗑 Delete Strategy", width="stretch"):
                        st.write(f"Permanently delete '{selected_name}'?")
                        
                        # The actual inner confirmation execution action button
                        if st.button("⚠️ Confirm Delete", key=f"pop_del_btn_{portfolio_id}", width="stretch", type="primary"):
                            con.execute(
                                """
                                DELETE FROM user_preferences_strategy
                                WHERE strategy_name = ? AND portfolio_id = ?
                                """,
                                [selected_name, portfolio_id],
                            )
                            st.success(f"Deleted '{selected_name}'")
                            st.rerun()
                            
                        
                        
                        
                        
                        
                        
                        
                else:
                    st.info("No saved strategy profiles detected.")
            
            
            # Block 3: AI Copilot Placeholder Panel
            with st.container(border=True):
                st.markdown("<p style='font-size: 15px; font-weight: 700; margin: 0 0 6px 0; color: #475569;'>🤖 AI Assistant</p>", unsafe_allow_html=True)
                st.markdown("<p style='font-size: 13px; color: #94A3B8; font-style: italic; margin: 0;'>Interactive strategy generation copilot coming soon.</p>", unsafe_allow_html=True)

        # Right Sliders Grid (Your existing sliders block rendering goes directly here)
        with col_sliders:
            pass # Keep your exact slider rendering loop intact here as it was setup before
            
            
            
            
            
            
            
        # =======================================
        # SHOW THE SLIDERS IN A 2-COLUMN GRID
        # =======================================
        FACTOR_HELP = {
            "momentum": "Favors assets with strong upward trends.",
            "value": "Focuses on undervalued companies.",
            "quality": "Prioritizes financially healthy businesses.",
            "growth": "Targets companies with rapid expansion.",
            "defensive": "Reduces risk and volatility.",
            "size": "Focuses more on small-cap opportunities.",
            "liquidity": "Prioritizes easier buying and selling.",
        }
        
        with col_sliders:
            # Callback logic triggered upon moving any slider item
            def on_slider_touch(factor_name):
                # Construct the dynamic slider key based on the current revision
                specific_slider_key = f"slider_{factor_name}_{portfolio_id}_rev_{st.session_state.slider_rev}"
                
                # Check if the key exists in session_state to prevent KeyError during state transitions
                if specific_slider_key in st.session_state:
                    # Safely update the factor weight with the slider's current value
                    st.session_state.weights[factor_name] = st.session_state[specific_slider_key]
                    
                    # Mark this portfolio configuration as custom/modified
                    st.session_state[f"is_custom_{portfolio_id}"] = True

            # Loop through factors two at a time to build a neat responsive grid layout
            for i in range(0, len(FACTORS), 2):
                
                # Get the current pair of factors for this row
                pair = FACTORS[i:i+2]
                
                # Dynamic column mapping for 2 items per row
                grid_cols = st.columns([1, 1])
                
                for idx, f in enumerate(pair):
                    with grid_cols[idx]:
                        
                        val_from_state = float(st.session_state.weights.get(f, 50.0))
                        slider_key = f"slider_{f}_{portfolio_id}_rev_{st.session_state.slider_rev}"

                        st.markdown(
                            f"""
                            <div class="slider-card">
                                <div class="factor-title">{f.capitalize()}</div>
                                <div class="factor-description">{FACTOR_HELP[f]}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        # Render the native slider bound directly underneath its visual custom header card
                        st.session_state.weights[f] = st.slider(
                            label="",
                            min_value=0.0,
                            max_value=100.0,
                            value=val_from_state,
                            step=1.0,
                            key=slider_key,
                            on_change=on_slider_touch,
                            args=(f,),
                            label_visibility="collapsed" 
                        )
                        st.write("") # Spacer padding below each individual pair block

    # =======================================
    # STEP 3 — MULTI-STRATEGY ALLOCATION AND VISUAL SYNCHRONIZATION
    # =======================================

    if st.session_state.active_tab == 2:

            # =======================================
            # Modern Styling
            # =======================================
            st.html(
                """
                <style>
                /* Main header card */
                .allocation-header-card {
                    background: white;
                    border: 1px solid #E2E8F0;
                    border-radius: 18px;
                    padding: 22px;
                    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
                    margin-bottom: 18px;
                }

                /* Section title */
                .allocation-title {
                    font-size: 28px;
                    font-weight: 700;
                    color: #0F172A;
                    margin-bottom: 6px;
                }

                /* Section subtitle */
                .allocation-subtitle {
                    color: #64748B;
                    font-size: 15px;
                    line-height: 1.5;
                }

                /* Targeted styling for st.container(border=True) to match your design */
                div[data-testid="stVVerticalBlockBorderContainer"] {
                    background-color: white !important;
                    border: 1px solid #E2E8F0 !important;
                    border-radius: 16px !important;
                    padding: 16px !important;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.02) !important;
                }

                /* Execute button styling */
                div.stButton > button[kind="primary"] {
                    border-radius: 14px !important;
                    font-weight: 700 !important;
                    height: 48px !important;
                    background-color: #2563EB !important;
                    border: none !important;
                }

                div.stButton > button[kind="primary"]:hover {
                    background-color: #1D4ED8 !important;
                }
                </style>
                """
            )

            # =======================================
            # Header Section
            # =======================================
            st.html(
                """
                <div class="allocation-header-card">
                    <div class="allocation-title">
                        📊 Multi-Strategy Allocation
                    </div>
                    <div class="allocation-subtitle">
                        Distribute your portfolio across your saved strategies.
                        Slider colors are synchronized with the portfolio chart
                        for faster visual understanding.
                    </div>
                </div>
                """
            )

            # =======================================
            # Load Saved Strategies
            # =======================================
            u_id = int(st.session_state.get("user_id", 0))
            p_id = int(portfolio_id)

            saved_strategies = con.execute(
                """
                SELECT strategy_name
                FROM user_preferences_strategy
                WHERE portfolio_id = ?
                AND user_id = ?
                ORDER BY timestamp DESC
                """,
                [p_id, u_id]
            ).fetchall()

            strategy_names = [row[0] for row in saved_strategies]

            if not strategy_names:
                st.info(
                    "💡 You haven't saved any strategies yet. "
                    "Go back to previous steps to create one."
                )
            else:
                # =======================================
                # Strategy Colors
                # =======================================
                strategy_colors = [
                    "#3B82F6", "#10B981", "#F59E0B", "#EF4444",
                    "#8B5CF6", "#EC4899", "#14B8A6", "#F97316"
                ]

                strategy_color_map = {
                    name: strategy_colors[i % len(strategy_colors)]
                    for i, name in enumerate(strategy_names)
                }

                num_strategies = len(strategy_names)
                default_weight = round(100.0 / num_strategies, 1)

                # =======================================
                # Hidden Strategies State
                # =======================================
                if "hidden_strategies" not in st.session_state:
                    st.session_state.hidden_strategies = set()

                # =======================================
                # Slider Sync Logic
                # =======================================
                def sync_sliders(changed_strategy):
                    new_val = st.session_state[f"alloc_slider_{p_id}_{changed_strategy}"]
                    visible_strategies = [
                        s for s in strategy_names
                        if s not in st.session_state.hidden_strategies
                    ]

                    if len(visible_strategies) == 1:
                        st.session_state[f"alloc_slider_{p_id}_{changed_strategy}"] = 100.0
                        return

                    remaining_pool = 100.0 - new_val
                    other_strategies = [name for name in visible_strategies if name != changed_strategy]
                    current_other_total = sum(st.session_state[f"alloc_slider_{p_id}_{name}"] for name in other_strategies)

                    if current_other_total > 0:
                        for name in other_strategies:
                            current_val = st.session_state[f"alloc_slider_{p_id}_{name}"]
                            proportional_share = (current_val / current_other_total) * remaining_pool
                            st.session_state[f"alloc_slider_{p_id}_{name}"] = round(proportional_share, 1)
                    else:
                        even_share = remaining_pool / len(other_strategies)
                        for name in other_strategies:
                            st.session_state[f"alloc_slider_{p_id}_{name}"] = round(even_share, 1)

                # =======================================
                # Layout Setup
                # =======================================
                col_controls, col_chart = st.columns([1.2, 1], gap="large")
                allocations = {}


                # =======================================
                # LEFT SIDE — CONTROLS
                # =======================================
                with col_controls:
                    # Header info for controls inside a clean container
                    with st.container(border=True):
                        st.html(
                            """
                            <div style="font-size:20px; font-weight:700; color:#0F172A; margin-bottom:6px;">
                                🎛 Strategy Controls
                            </div>
                            <div style="color:#64748B; font-size:14px; margin-bottom:12px;">
                                Adjust allocations, set monthly deposits, or temporarily hide strategies.
                            </div>
                            """
                        )
                        
                        
                    # Loop through strategies
                    # Create the layout columns once outside the loop (50/50 split)
                    left, right = st.columns([1, 1])

                    # Single loop over all strategies using 'enumerate' to track the layout index
                    for idx, name in enumerate(strategy_names):
                        slider_key = f"alloc_slider_{p_id}_{name}"

                        # Initialize the session state for the slider if it doesn't exist yet
                        if slider_key not in st.session_state:
                            st.session_state[slider_key] = default_weight

                        # Check state conditions
                        is_hidden = name in st.session_state.hidden_strategies
                        strategy_color = strategy_color_map[name]

                        # Dynamic Column Assignment: Even indices go to Left column, Odd to Right
                        target_column = left if idx % 2 == 0 else right

                        # Inject the entire card UI into the selected column
                        with target_column:
                            with st.container(border=True):
                                # Split the top header area: Title on the left, Visibility toggle on the right
                                top_left, top_right = st.columns([5, 1])

                                # Render strategy title alongside its specific indicator color
                                with top_left:
                                    st.html(
                                        f"""
                                        <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
                                            <div style="width:14px; height:14px; border-radius:50%; background:{strategy_color}; flex-shrink:0;"></div>
                                            <div style="font-weight:700; font-size:16px; color:#1E293B;">{name}</div>
                                        </div>
                                        """
                                    )

                                # Visibility Button: Using 'idx' and 'p_id' in the key to guarantee absolute uniqueness
                                
                                    # Inject custom CSS scoped to this specific slider's HTML data attribute
                                    st.html(
                                        f"""
                                        <style>
                                        div[data-testid="stSliderKey-{slider_key}"] div[data-testid="stSliderTrack"] > div div[style*="background"] {{
                                            background: {strategy_color} !important;
                                        }}
                                        div[data-testid="stSliderKey-{slider_key}"] div[data-basebutton="true"] {{
                                            background-color: {strategy_color} !important;
                                        }}
                                        div[data-testid="stSliderKey-{slider_key}"] div[role="slider"] {{
                                            background-color: {strategy_color} !important;
                                            border-color: {strategy_color} !important;
                                            box-shadow: 0 0 0 2px white, 0 0 0 40px {strategy_color}33 !important;
                                        }}
                                        </style>
                                        """
                                    )

                                    # Render the responsive interactive slider component
                                    allocations[name] = st.slider(
                                        label="",
                                        min_value=0.0,
                                        max_value=100.0,
                                        step=1.0,
                                        key=slider_key,
                                        on_change=sync_sliders,
                                        args=(name,)
                                    )
                                    
    
                # =======================================
                # RIGHT SIDE — PIE CHART
                # =======================================
                total_allocated = sum(allocations.values())

                with col_chart:

                    active_labels = [name for name, val in allocations.items() if val > 0]
                    active_values = [val for name, val in allocations.items() if val > 0]
                    active_colors = [strategy_color_map[name] for name, val in allocations.items() if val > 0]

                    if active_values:
                        fig = go.Figure(data=[
                            go.Pie(
                                labels=active_labels,
                                values=active_values,
                                hole=0.48,
                                textinfo='percent+label',
                                hoverinfo='label+value+percent',
                                marker=dict(
                                    colors=active_colors,
                                    line=dict(color='white', width=3)
                                ),
                                textfont=dict(size=14, color="#0F172A")
                            )
                        ])

                        fig.update_layout(
                            showlegend=False,
                            margin=dict(t=10, b=10, l=10, r=10),
                            height=420,
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                        )

                        st.plotly_chart(
                            fig,
                            width="stretch",
                            config={'displayModeBar': False}
                        )
                    else:
                        st.html(
                            """
                            <div style="height:350px; display:flex; align-items:center; justify-content:center; background:#F8FAFC; border:2px dashed #CBD5E1; border-radius:18px;">
                                <p style="color:#94A3B8; font-size:16px;">
                                    No active strategies selected
                                </p>
                            </div>
                            """
                        )

                # =======================================
                # Footer Summary
                # =======================================
                st.write("")
                if abs(total_allocated - 100.0) < 0.1:
                    pass
                else:
                    st.warning(f"⚠ Current allocation total: {total_allocated:.1f}%")

                # =======================================
                # Further Button
                # =======================================
                st.write("")
                if st.button(
                    " 🚀 Procceed to the last step",
                    type="primary",
                    width="stretch"
                ):
                    st.session_state.active_tab = 3
                    st.rerun()



    # =======================================
    # STEP 4 - FINAL PORTFOLIO CONFIG
    # =======================================
    if st.session_state.active_tab == 3:

        p_id = int(portfolio_id)

        # -------------------------------
        # HEADER
        # -------------------------------
        st.markdown(
            """
            <div style="
                padding: 18px;
                border-radius: 16px;
                background: linear-gradient(135deg, #0f172a, #1e293b);
                color: white;
                margin-bottom: 20px;
            ">
                <div style="font-size:20px; font-weight:700;">
                    🚀 Final Portfolio Setup
                </div>
                <div style="font-size:13px; opacity:0.8; margin-top:6px;">
                    Simple preferences → optimized portfolio construction
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # ======================================================
        # INJECT GLOBAL EQUAL-HEIGHT LAYOUT & ALIGNMENT CSS
        # ======================================================
        st.html(
            """
            <style>
            /* 1. Force the main layout container blocks to stretch to 100% height */
            div[data-testid="stHorizontalBlock"] div[data-testid="stVerticalBlockBorderWrapper"] > div {
                height: 100% !important;
                display: flex !important;
                flex-direction: column !important;
            }
            
            /* 2. Make the inner wrapper grow evenly so all main container card borders line up perfectly */
            div[data-testid="stHorizontalBlock"] div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] {
                height: 100% !important;
                flex-grow: 1 !important;
                display: flex !important;
                flex-direction: column !important;
                justify-content: flex-start !important;
            }

            /* 3. Micro-alignment for execution settings sub-headers to prevent height gaps if text wraps */
            .fee-section-title {
                font-size: 13px;
                font-weight: 600;
                color: #475569;
                margin-bottom: -10px;
                min-height: 38px; /* Ensures titles with different line counts stay perfectly aligned */
                display: flex;
                align-items: center;
            }
            </style>
            """
        )

        # Main layout generation with a 1:1:2 container width ratio
        col_left, center_col, col_right = st.columns([1, 1, 2], gap="medium")

        # ======================================================
        # LEFT COLUMN: INVESTMENT FOCUS
        # ======================================================
        with col_left:
            with st.container(border=True):
                st.markdown("### 🎯 Investment Focus")

                # Fetch the master list of unique available sectors from the database
                sector_query = con.execute("""
                    SELECT sector 
                    FROM assets
                    WHERE sector IS NOT NULL
                    GROUP BY sector
                """).df()
                master_sector_list = sector_query["sector"].tolist()
                
                # Setup specific unique session state tracking keys
                pref_key = f"pref_sectors_{p_id}"
                excl_key = f"excl_sectors_{p_id}"

                # Preferred Sectors (Focus) - Filter out anything already excluded
                currently_excluded = st.session_state.get(excl_key, [])
                focus_options = [s for s in master_sector_list if s not in currently_excluded]

                preferred_sectors = st.multiselect(
                    "Sectors you want to focus on",
                    options=focus_options,
                    key=pref_key,
                    help="We will slightly overweight these sectors in your portfolio."
                )

                # Excluded Sectors (Avoid) - Filter out anything already focused
                currently_focused = st.session_state.get(pref_key, [])
                avoid_options = [s for s in master_sector_list if s not in currently_focused]

                excluded_sectors = st.multiselect(
                    "Sectors you want to avoid",
                    options=avoid_options,
                    key=excl_key,
                    help="These sectors will be fully removed from recommendations."
                )

        # ======================================================
        # CENTER COLUMN: DEPOSITS
        # ======================================================
        with center_col:
            with st.container(border=True):
                st.markdown("### 💰 Deposits")

                # Monthly ongoing investment configuration
                monthly_deposit = st.number_input(
                    "Monthly deposit (€)",
                    min_value=0,
                    step=50,
                    key=f"monthly_{p_id}",
                    help="How much you plan to invest every month."
                )

                # Optional initial up-front capital injection input
                lump_sum = st.number_input(
                    "One-time investment (€)",
                    min_value=0,
                    step=100,
                    key=f"lump_{p_id}",
                    help="Initial capital injection (if any)."
                )

        # ======================================================
        # RIGHT COLUMN: EXECUTION SETTINGS (FEES)
        # ======================================================
        with col_right:
            with st.container(border=True):
                st.markdown("### ⚙️ Execution Settings")

                # Split execution settings into 2 symmetrical sub-columns for fees
                fee_col1, fee_col2 = st.columns(2, gap="small")
                
                # Sub-Section A: Individual trading metrics
                with fee_col1:
                    st.html("<div class='fee-section-title'>💼 Transaction fees ($ per trade)</div>")

                    buy_fee = st.number_input(
                        "Buy fee",
                        min_value=0.0,
                        step=0.1,
                        key=f"buy_fee_{p_id}"
                    )

                    sell_fee = st.number_input(
                        "Sell fee",
                        min_value=0.0,
                        step=0.1,
                        key=f"sell_fee_{p_id}"
                    )
                
                # Sub-Section B: Capital actions metrics
                with fee_col2:
                    st.html("<div class='fee-section-title'>🏦 Deposit/Withdrawals fees ($ per action)</div>")

                    deposit_fee = st.number_input(
                        "Deposit fee",
                        min_value=0.0,
                        step=0.1,
                        key=f"dep_fee_{p_id}"
                    )

                    withdrawal_fee = st.number_input(
                        "Withdrawal fee",
                        min_value=0.0,
                        step=0.1,
                        key=f"with_fee_{p_id}"
                    )
            
            
            
        # ======================================================
        # DIVERSIFICATION LEVEL 
        # ======================================================

        st.markdown("### 📊 Diversification Level")

        div_key = f"div_{p_id}"

        if div_key not in st.session_state:
            st.session_state[div_key] = "Medium"

        div_options = {
            "Low": {
                "icon": "🎯",
                "range": 'Maximum 10 different assets',
                "desc": "Invests in fewer assets. Bigger gains possible, but also bigger risks."
            },
            "Medium": {
                "icon": "⚖️",
                "range": "10 - 20 different assets",
                "desc": "Balanced mix of assets. Good balance between growth and stability."
            },
            "High": {
                "icon": "🧱",
                "range": "no limit on number of assets",
                "desc": "Spreads money across many assets. Lower risk, but usually slower growth."
            }
        }

        # Callback function to handle the card selection cleanly
        def set_diversification(selected_option):
            st.session_state[div_key] = selected_option

        # CSS to make the selection look tight and clean
        st.html(
            """
            <style>
            .div-card {
                padding: 5px;
                text-align: center;
            }
            /* Scope styling to button container just for vertical alignment */
            div[data-testid="stBlock"] {
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }
            </style>
            """
        )

        cols = st.columns(3, gap="small")

        for i, (option, data) in enumerate(div_options.items()):
            with cols[i]:
                selected = st.session_state[div_key] == option
                
                # 1. Native container with border
                with st.container(border=True):
                    
                    # 2. Rich HTML Content for the description
                    st.html(
                        f"""
                        <div class="div-card">
                            <div style="font-size: 26px; margin-bottom: 4px;">{data['icon']}</div>
                            <div style="font-weight: 700; font-size: 16px; color: {'#2563EB' if selected else '#0F172A'};">{option}</div>
                            <div style="font-size: 13px; font-weight: 600; color: {'#3B82F6' if selected else '#64748B'}; margin-top: 2px;">
                                {data['range']}
                            </div>
                            <div style="font-size: 11px; color: #94A3B8; margin-top: 6px; line-height: 1.2; min-height: 28px;">
                                {data['desc']}
                            </div>
                        </div>
                        """
                    )
                    
                    # 3. Fixed Native Button (Replaced 'kind' with native 'type')
                    st.button(
                        label="✓ Selected" if selected else f"Select {option}",
                        key=f"native_click_{div_key}_{option}",
                        width="stretch",
                        type="primary" if selected else "secondary", # Primary colors it blue based on your theme
                        on_click=set_diversification,
                        args=(option,)
                    )

        # Final value for your recommendation system
        diversification = st.session_state[div_key]


        
        
        # ======================================================
        # FOOTER ACTION
        # ======================================================
        st.write("")

        if st.button(
            "🚀 Generate Portfolio",
            type="primary",
            width="stretch"
        ):

            st.toast("Building your optimized portfolio...", icon="⚙️")

            #st.session_state.active_tab = 4
            st.rerun()
        
        
        
        
        
        
# for showing easily the factors of an asset
def render_stock_factor_maps(con, ticker: str):
    """
    Displays 3 factor scatter plots for a selected stock:
    1. Defensive vs Growth
    2. Size vs Value
    3. Quality vs Momentum
    """


    # ----------------------------
    # Load latest snapshot
    # ----------------------------
    df = con.execute("""
        SELECT 
            a.ticker,
            a.name,

            f.defensive_factor_market,
            f.growth_factor_market,
            f.size_factor_market,
            f.value_factor_market,
            f.quality_factor_market,
            f.momentum_factor_market

        FROM asset_factors_normalized_final f
        JOIN assets a ON a.asset_id = f.asset_id
        WHERE f.timestamp = (SELECT MAX(timestamp) FROM asset_factors_normalized_final)
    """).df()

    if df.empty:
        st.warning("No data available")
        return

    # ----------------------------
    # Clean numeric data ONCE (important fix)
    # ----------------------------
    factor_cols = [
        "defensive_factor_market",
        "growth_factor_market",
        "size_factor_market",
        "value_factor_market",
        "quality_factor_market",
        "momentum_factor_market"
    ]

    for col in factor_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=factor_cols)

    selected = df[df["ticker"] == ticker]

    # ----------------------------
    # Helper function
    # ----------------------------
    def make_scatter(x, y, title, x_label, y_label):

        fig = go.Figure()

        # ensure numeric safety (critical fix)
        x_vals = pd.to_numeric(df[x], errors="coerce")
        y_vals = pd.to_numeric(df[y], errors="coerce")

        mask = x_vals.notna() & y_vals.notna()

        x_vals = x_vals[mask]
        y_vals = y_vals[mask]
        tickers = df["ticker"][mask]

        x_mean = x_vals.mean()
        y_mean = y_vals.mean()

        # ----------------------------
        # Universe
        # ----------------------------
        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode='markers',
            marker=dict(
                size=5,
                opacity=0.25,
                color='lightgray'
            ),
            text=tickers,
            hovertemplate="%{text}<br>X: %{x}<br>Y: %{y}<extra></extra>",
            name="Universe"
        ))

        # ----------------------------
        # Mean lines
        # ----------------------------
        fig.add_shape(
            type="line",
            x0=x_mean, x1=x_mean,
            y0=y_vals.min(), y1=y_vals.max(),
            line=dict(color="rgba(0,0,0,0.25)", width=1, dash="dot")
        )

        fig.add_shape(
            type="line",
            x0=x_vals.min(), x1=x_vals.max(),
            y0=y_mean, y1=y_mean,
            line=dict(color="rgba(0,0,0,0.25)", width=1, dash="dot")
        )

        # ----------------------------
        # Selected stock
        # ----------------------------
        selected_row = df[df["ticker"] == ticker]

        if not selected_row.empty:
            sx = pd.to_numeric(selected_row[x], errors="coerce").values[0]
            sy = pd.to_numeric(selected_row[y], errors="coerce").values[0]

            fig.add_trace(go.Scatter(
                x=[sx],
                y=[sy],
                mode='markers+text',
                marker=dict(
                    size=16,
                    color='#ff4b4b',
                    line=dict(width=3, color='white')
                ),
                text=[ticker],
                textposition="top center",
                hovertemplate=f"<b>{ticker}</b><br>X: {sx}<br>Y: {sy}<extra></extra>",
                name="Selected"
            ))

        # ----------------------------
        # Layout
        # ----------------------------
        fig.update_layout(
            title=title,
            xaxis_title=x_label,
            yaxis_title=y_label,
            height=360,
            margin=dict(l=10, r=10, t=40, b=10),
            plot_bgcolor="white",
            paper_bgcolor="white",
            showlegend=False
        )

        fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)")
        fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)")

        return fig

    # ----------------------------
    # Render charts
    # ----------------------------
    col1, col2, col3 = st.columns(3)

    with col1:
        st.plotly_chart(
            make_scatter(
                "growth_factor_market",
                "defensive_factor_market",
                "Defensive vs Growth",
                "Growth",
                "Defensive"
            ),
            width="stretch"
        )

    with col2:
        st.plotly_chart(
            make_scatter(
                "value_factor_market",
                "size_factor_market",
                "Size vs Value",
                "Value",
                "Size"
            ),
            width="stretch"
        )

    with col3:
        st.plotly_chart(
            make_scatter(
                "momentum_factor_market",
                "quality_factor_market",
                "Quality vs Momentum",
                "Momentum",
                "Quality"
            ),
            width="stretch"
        )