import streamlit as st
import duckdb
import pandas as pd
from datetime import timedelta
import plotly.graph_objects as go
from .trading_logic import execute_asset_trade , execute_cash_transaction
from .portfolio_managment import calculate_fifo_avg_price
from Code.functions.db_manager import *

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
        with st.popover("➕ Deposit Cash", use_container_width=True):
            dep_amount = st.number_input("Amount to Deposit", min_value=1, step=100, key="dep_val")
            
            confirm_dep = st.checkbox(f"I confirm depositing ${dep_amount:,.2f}", key="conf_dep_check")
            
            if confirm_dep:
                if st.button("🚀 Execute Deposit", use_container_width=True):
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
        with st.popover("➖ Withdraw Cash", use_container_width=True):
            with_amount = st.number_input("Amount to Withdraw", min_value=1, step=100, key="with_val")
            
            confirm_with = st.checkbox(f"I confirm withdrawing ${with_amount:,.2f}", key="conf_with_check")
            
            if confirm_with:
                if st.button("💸 Execute Withdrawal", use_container_width=True):
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

# עדכון קטן לפונקציית display_asset_card כדי לשמור על עקביות
def display_asset_card(asset):
    """מציגה את נתוני הנכס בצורה ויזואלית יפה עם בדיקת זמינות"""
    if asset['current_price'] is None:
        first_date = asset['first_trade_date']
        date_str = first_date.strftime('%Y-%m-%d') if hasattr(first_date, 'strftime') else str(first_date)
        
        st.warning(f"⚠️ המנייה **{asset['ticker']}** לא נסחרה בזמן זה.")
        st.info(f"היא התחילה להיסחר בתאריך: **{date_str}**")
        st.subheader(f"{asset['name']} ({asset['ticker']})")
        return 

    c1, c2 , c3= st.columns([1, 2 , 1])
    with c1:
        st.metric("Price", f"${asset['current_price']:,.2f}")
    with c2:
        st.subheader(f"{asset['name']} ({asset['ticker']})")
        st.caption(f"**Sector:** {asset['sector']} | **Industry:** {asset['industry']}")
    with c3:
        st.subheader("logo of the company")
    # כפתור אנליזה - הוספנו שימוש ב-is_action_allowed גם כאן לביטחון
    


# for showing purchese 
def show_buy_component(ticker, asset_price):
    """
    קומפוננטת רכישה משופרת עם ניהול State חכם ואישור בתוך ה-Popover.
    """
    portfolio_id = st.session_state.get('current_portfolio_id')
    sim_date = st.session_state.get('current_sim_date')
    
    # 1. שימוש במזומן מה-State (חוסך פנייה מיותרת ל-DB עד רגע הקנייה)
    current_cash = st.session_state.get('current_available_cash', 0.0)

    # מפתח ייחודי למצב האישור של הנכס הספציפי
    confirm_key = f"confirm_buy_{ticker}"
    if confirm_key not in st.session_state:
        st.session_state[confirm_key] = False

    with st.popover(f"🛒 Buy {ticker}", use_container_width=True):
        st.subheader(f"Purchase {ticker}")
        st.write(f"Cash Available: **${current_cash:,.2f}**")
        
        # 2. חישוב מגבלות
        max_shares = int(current_cash // asset_price) if asset_price > 0 else 0
        
        if max_shares <= 0:
            st.warning("Insufficient funds to buy this asset.")
            return

        # 3. בחירת שיטת קנייה (שימוש ב-form כדי למנוע ריענון על כל הקלדה)
        buy_method = st.radio("Buy by:", ["Quantity", "Total price ($)"], horizontal=True, key=f"method_{ticker}")

        if buy_method == "Quantity":
            qty = st.number_input("Quantity", min_value=1, max_value=max_shares, step=1, key=f"buy_qty_{ticker}")
            total_cost = qty * asset_price
        else:
            amount_to_spend = st.number_input("Amount ($)", min_value=float(asset_price), max_value=float(current_cash), step=100.0, key=f"buy_amt_{ticker}")
            qty = int(amount_to_spend // asset_price)
            total_cost = qty * asset_price

        st.info(f"Total Order: **{qty}** shares for **${total_cost:,.2f}**")

        # 4. מנגנון אישור דו-שלבי חכם (ללא rerun מיותר)
        if not st.session_state[confirm_key]:
            if st.button("Review Order", use_container_width=True):
                st.session_state[confirm_key] = True
                st.rerun() # כאן rerun נחוץ כדי להציג את כפתור ה-Confirm במקום ה-Review
        else:
            st.warning("Confirm Transaction?")
            col_a, col_b = st.columns(2)
            
            with col_a:
                if st.button("✅ Confirm", type="primary", use_container_width=True):
                    # בדיקת מחסום זמן (2 שניות)
                    if is_action_allowed(wait_time=2):
                        with duckdb.connect(DB_PATH) as con:
                            success, msg = execute_asset_trade(con, portfolio_id, ticker, sim_date, qty, side='buy')
                            
                            if success:
                                st.session_state[confirm_key] = False
                                # עדכון ה-State המקומי כדי שהדף הבא יראה את המזומן המעודכן מיד
                                st.session_state.current_available_cash -= total_cost
                                st.session_state.page = "dashboard_home"
                                st.toast(msg)
                                con.close()
                                
                                st.rerun()
                            else:
                                st.error(msg)
                    else:
                        st.warning("Slow down...")

            with col_b:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state[confirm_key] = False
                    st.rerun()

# for showing holding positions
def render_holdings_table(con, portfolio_id, sim_date):
    st.subheader("🏢 Current Holdings (FIFO)")

    # 1. שליפת כל הטרנזקציות ההיסטוריות לחישוב FIFO
    tx_query = """
    SELECT asset_id, quantity, price_per_share, side, timestamp
    FROM assets_transactions
    WHERE portfolio_id = ? AND timestamp <= ?
    ORDER BY timestamp, transaction_id
    """
    all_tx = con.execute(tx_query, [portfolio_id, sim_date]).df()

    # 2. שליפת האחזקות הנוכחיות
    holdings_query = """
    SELECT a.asset_id, a.ticker, a.name, h.quantity
    FROM holdings h
    JOIN assets a ON h.asset_id = a.asset_id
    WHERE h.portfolio_id = ? AND h.quantity > 0
    """
    holdings_df = con.execute(holdings_query, [portfolio_id]).df()

    if holdings_df.empty:
        st.info("Your portfolio is currently empty.")
        return

    # כותרות הטבלה
    header_cols = st.columns([1, 2, 1, 1, 1, 1, 1.2 ])
    cols_names = ["Ticker", "Name", "Qty", "Avg Buy", "Current", "Value", "Action" , ""]
    for col, name in zip(header_cols, cols_names):
        col.markdown(f"**{name}**")
    st.divider()

    for _, row in holdings_df.iterrows():
        asset_id = row['asset_id']
        ticker = row['ticker']
        available_qty = int(row['quantity'])
        
        # א) חישוב FIFO
        asset_tx = all_tx[all_tx['asset_id'] == asset_id]
        avg_buy_price = calculate_fifo_avg_price(asset_tx)
        
        # ב) שליפת מחיר עדכני
        current_price = con.execute("""
            SELECT close FROM prices 
            WHERE asset_id = ? AND timestamp <= ? 
            ORDER BY timestamp DESC LIMIT 1
        """, [asset_id, sim_date]).fetchone()[0]

        total_value = available_qty * current_price
        pnl_perc = ((current_price / avg_buy_price) - 1) * 100 if avg_buy_price > 0 else 0

        # ג) רינדור השורה
        cols = st.columns([1, 2, 1, 1, 1, 1, 1.2 , 0.5])
        cols[0].write(ticker)
        cols[1].write(row['name'])
        cols[2].write(f"{available_qty:,}")
        cols[3].write(f"${avg_buy_price:,.2f}")
        cols[4].write(f"${current_price:,.2f}")
        cols[5].write(f"${total_value:,.2f}")
        
        pnl_color = "green" if pnl_perc >= 0 else "red"
        cols[5].caption(f":{pnl_color}[{pnl_perc:+.2f}%]")
        
        # ד) מנגנון מכירה חסין
        with cols[6]:
            with st.popover("📉 Sell", use_container_width=True):
                st.write(f"Available to sell: **{available_qty}**")
                
                # הסרנו את max_value כדי למנוע תיקון אוטומטי של Streamlit
                sell_qty = st.number_input(
                    "Quantity to sell", 
                    min_value=1, 
                    value=available_qty, 
                    step=1, 
                    key=f"s_input_{ticker}"
                )
                
                if st.button("Confirm Sale", key=f"btn_s_{ticker}", type="primary", use_container_width=True):
                    # בדיקת חסימה ידנית
                    if sell_qty > available_qty:
                        st.error(f"❌ Cannot sell {sell_qty}. You only have {available_qty} shares.")
                    else:
                        success, msg = execute_asset_trade(
                            con, portfolio_id, ticker, sim_date, sell_qty, side='sell'
                        )
                        if success:
                            st.success("Sold!")
                            st.rerun()
                        else:
                            st.error(msg)
        if cols[7].button("🔍", key=f"analyze_hold_{ticker}", help="View Deep Analysis"):
            show_asset_analysis_dialog(ticker)
    st.divider()


# for plotting the graph
def render_performance_chart(df, title="Portfolio Performance History"):
    if df is None or df.empty:
        st.warning("No performance data available.")
        return

    # 1. בחירת טווח זמן ע"י המשתמש (במקום הכפתורים של Plotly)
    col_t1, col_t2 = st.columns([2, 1])
    with col_t2:
        time_range = st.selectbox(
            "Select Timeframe",
            ["1 Week","1 Month", "6 Months", "Year to Date", "1 Year", "All Time"],
            index=4,
            label_visibility="collapsed"
        )

    # 2. פילטור הנתונים ידנית
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    last_date = df['timestamp'].max()
    
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
        start_date = df['timestamp'].min()

    filtered_df = df[df['timestamp'] >= start_date].copy()

    # 3. חישוב טווח ציר Y על בסיס הנתונים המפולטרים בלבד
    y_min = filtered_df['value'].min()
    y_max = filtered_df['value'].max()
    y_range = y_max - y_min
    
    # הוספת מרווח עדין (5%) כדי שהקו לא ייגע בתקרה/רצפה
    padding = y_range * 0.05 if y_range > 0 else y_min * 0.05
    y_limit_min = y_min - padding
    y_limit_max = y_max + padding

    # --- חישובי תשואה (רק לטווח הנבחר) ---
    p_start = filtered_df['value'].iloc[0]
    p_end = filtered_df['value'].iloc[-1]
    ret_pct = ((p_end / p_start) - 1) * 100
    ret_cash = p_end - p_start

    # הצגת מטריקות
    m1, m2, m3 = st.columns(3)
    m1.metric("Value", f"${p_end:,.0f}")
    m2.metric("Return in Period ($)", f"${ret_cash:,.0f}", delta=f"{ret_cash:,.0f}")
    m3.metric("Return in Period (%)", f"{ret_pct:.2f}%", delta=f"{ret_pct:.2f}%")

    # 4. יצירת הגרף
    line_color = "#2ecc71" if ret_cash >= 0 else "#e74c3c"
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=filtered_df['timestamp'],
        y=filtered_df['value'],
        mode='lines',
        line=dict(width=3, color=line_color, shape='spline'),
        fill='tonexty',
        fillcolor=f"rgba{tuple(list(int(line_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + [0.05])}",
        hovertemplate="<b>Value:</b> $%{y:,.0f}<extra></extra>"
    ))

    fig.update_layout(
        template="plotly_white",
        height=400,
        margin=dict(l=0, r=0, t=20, b=0),
        xaxis=dict(showgrid=False),
        yaxis=dict(
            range=[y_limit_min, y_limit_max], # כאן אנחנו כופים את הטווח המחושב
            showgrid=True,
            gridcolor="#f0f0f0",
            tickprefix="$",
            separatethousands=True
        )
    )

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# for the assets serch component
def asset_search_component(con):
    """מנהלת את החיפוש ושומרת את הבחירה ב-State"""
    
    # טעינה ראשונית של הרשימה ל-Cache
    if 'all_assets_list' not in st.session_state:
        assets_df = con.execute("SELECT ticker, name FROM assets").df()
        st.session_state.all_assets_list = [f"{row['ticker']} | {row['name']}" for _, row in assets_df.iterrows()]

    st.subheader("Search by Ticker or Company Name")
    
    selected_option = st.selectbox(
        "",
        options=[""] + st.session_state.all_assets_list,
        format_func=lambda x: "Type to search..." if x == "" else x,
        index=0,
        key="strategy_search_box"
    )

    if selected_option:
        st.session_state.selected_ticker_for_analysis = selected_option.split(" | ")[0]


# for analysing an asset (analysis diolog pop up)
@st.dialog("Asset Analysis Deep-Dive", width="large")
def show_asset_analysis_dialog( asset_ticker):
    # 1. שליפת מידע בסיסי וזיהוי ה-ID
    if 'con' not in st.session_state:
        st.error("Connection lost")
        return
        
    con = st.session_state.con
    
    
    asset_data = con.execute("SELECT asset_id, name, sector FROM assets WHERE ticker = ?", [asset_ticker]).fetchone()
    if not asset_data:
        st.error("Asset not found")
        return
    
    a_id, a_name, a_sector = asset_data
    sim_date = st.session_state.current_sim_date

    st.title(f"{a_name} ({asset_ticker})")
    st.caption(f"Analysis up to simulation date: {sim_date.strftime('%Y-%m-%d')}")

    # 2. שליפת היסטוריית מחירים עד תאריך הסימולציה
    price_df = con.execute("""
        SELECT timestamp, close, volume 
        FROM prices 
        WHERE asset_id = ? AND timestamp <= ?
        ORDER BY timestamp ASC
    """, [a_id, sim_date]).df()

    # 3. שליפת נתונים פונדמנטליים אחרונים (הכי קרובים לתאריך הסימולציה)
    fund_data = con.execute("""
        SELECT pe_ratio, market_cap, revenue, eps 
        FROM fundamentals 
        WHERE asset_id = ? AND timestamp <= ?
        ORDER BY timestamp DESC LIMIT 1
    """, [a_id, sim_date]).fetchone()
    
    
    # יצירת טאבים בתוך הדיאלוג
    tab1, tab2, tab3 = st.tabs(["📈 Price Chart", "📊 Fundamentals", "🏆 Performance"])

    with tab1:
    # 1. בחירת טווח זמן
        time_range = st.segmented_control(
        "Select Range",
        options=["1W" ,"1M", "6M", "1Y", "All"],
        default="All",
        key=f"range_{asset_ticker}"
    )

    # 2. חישוב תאריך ההתחלה לפי הבחירה
    
    
        end_date = st.session_state.current_sim_date
        if time_range == "1W":
            start_date = end_date - timedelta(days=7)
        elif time_range == "1M":
            start_date = end_date - timedelta(days=30)
        elif time_range == "6M":
            start_date = end_date - timedelta(days=180)
        elif time_range == "1Y":
            start_date = end_date - timedelta(days=365)
        else: # "All"
            start_date = pd.Timestamp.min # תאריך מוקדם מאוד

        # 3. שליפת הנתונים המפלטרת (גם עד ה-sim_date וגם לפי הטווח)
        filtered_price_df = con.execute("""
            SELECT timestamp, close 
            FROM prices 
            WHERE asset_id = ? 
            AND timestamp <= ? 
            AND timestamp >= ?
            ORDER BY timestamp ASC
        """, [a_id, end_date, start_date]).df()

        # 4. הכנת הנתונים והצגת הגרף
        if not filtered_price_df.empty:
            # חישוב נתונים מספריים לטווח הנבחר
            first_price = filtered_price_df['close'].iloc[0]
            last_price = filtered_price_df['close'].iloc[-1]
            
            abs_change = last_price - first_price
            pct_change = (abs_change / first_price) * 100
            
            # בחירת צבעים לפי הביצועים
            if abs_change >= 0:
                chart_color = '#2ecc71'
                fill_color = 'rgba(46, 204, 113, 0.1)'
                delta_color = "normal" # ירוק ב-st.metric
            else:
                chart_color = '#e74c3c'
                fill_color = 'rgba(231, 76, 60, 0.1)'
                delta_color = "inverse" # אדום ב-st.metric

            # --- הוספת שורת המדדים מעל הגרף ---
            col_m1, col_m2, col_m3 = st.columns(3)
            
            with col_m1:
                st.metric("Price", f"${last_price:,.2f}")
            
            with col_m2:
                st.metric("Change ($)", f"{abs_change:+,.2f}$", delta_color=delta_color)
                
            with col_m3:
                st.metric("Change (%)", f"{pct_change:+.2f}%", delta_color=delta_color)
                
            st.divider() # קו מפריד דק בין המספרים לגרף

            # --- בניית הגרף (עם הלוגיקה הקודמת) ---
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
            st.plotly_chart(fig, use_container_width=True)
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
        if not price_df.empty:
            start_p = price_df['close'].iloc[0]
            end_p = price_df['close'].iloc[-1]
            total_ret = ((end_p / start_p) - 1) * 100
            
            st.write(f"**Period Performance:** {total_ret:.2f}%")
            st.write(f"**Start Price:** ${start_p:,.2f}")
            st.write(f"**Current Price (Sim):** ${end_p:,.2f}")
            
            # כאן אפשר להוסיף כפתורי קנייה/מכירה מהירים בתוך הניתוח
            st.divider()
            if st.button(f"Trade {asset_ticker}", use_container_width=True):
                st.session_state.trade_target = asset_ticker
                st.rerun()