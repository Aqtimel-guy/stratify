import streamlit as st
from .db_manager import *
from .users_managment import *
from .portfolio_managment import *
from .UI_components import *
from .trading_logic import *
import logging



def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()
    

def show_login_page():
    # בדיקה אם הגענו מהרשמה מוצלחת - הצגת הודעה ירוקה
    if st.session_state.get('reg_success'):
        st.success("Registration successful! Please login with your new credentials.")
        # איפוס הדגל כדי שההודעה לא תופיע שוב בריענון הבא
        st.session_state.reg_success = False

    # כותרת ועיצוב
    st.markdown("<h1 style='text-align: center;'>Login to Stratify</h1>", unsafe_allow_html=True)
    st.write("---")
    
    # שימוש באימייל שנשמר מההרשמה (אם קיים) כערך ברירת מחדל
    prefilled_email = st.session_state.get('prefilled_email', "")
    
    # טופס התחברות
    with st.form("login_form"):
        st.write("Please enter your credentials:")
        
        user_email = st.text_input("Email", value=prefilled_email, placeholder="example@mail.com")
        user_password = st.text_input("Password", type="password")
    
        submit_button_loggin = st.form_submit_button("Login")
        
        if submit_button_loggin:
            if not user_email or not user_password:
                st.warning("Please fill in all fields.")
            else:
                user_id , first_name  = loggin_func(user_email, user_password)
            
                if user_id != None:
                    # שמירת הנתונים ב-Session
                    st.session_state.user_id = user_id
                    st.session_state.first_name = first_name
                    st.session_state.logged_in = True
                    
                    # ניקוי האימייל הזמני מה-state (כבר אין בו צורך אחרי לוגין מוצלח)
                    if 'prefilled_email' in st.session_state:
                        del st.session_state.prefilled_email
                    
                    st.success("Logged in successfully!")
                    go_to("home_page")
                else:
                    st.error("Login failed. Check your details.")

    # ניתוב להרשמה
    if st.button("For registration"):
        go_to("regestration_page")
        
    # שחזור סיסמה
    if st.button("forgot my password"):
        go_to("password_recovery_page")
        
  
        
def show_registration_page():
    # title and appearance
    st.markdown("<h1 style='text-align: center;'>Register to Stratify</h1>", unsafe_allow_html=True)
    st.write("---")
    
    # Form approach for registration
    with st.form("registration_form"):
        st.write("Please enter your credentials:")  
        
        first_name =  st.text_input("First name", placeholder="John")
        middle_name = st.text_input("Middle name", placeholder="Who knows nothing")
        last_name = st.text_input("Last name", placeholder="Snow")
        user_email = st.text_input("Email", placeholder="example@mail.com")
        user_password = st.text_input("Password", type="password")
        user_password_confirm = st.text_input("Confirm password", type="password")
        
        today = datetime.date.today()
        hundred_years_ago = today.replace(year=today.year - 100)
        date_of_birth = st.date_input(
            "Date of Birth",
            value=datetime.date(2000, 1, 1),
            min_value=hundred_years_ago,    
            max_value=today,                
            help="Click to open the calendar and select your birth date"
        )
        
        submit_button = st.form_submit_button("Register")

        ## Validations
        if submit_button:
            is_valid = True
            
            if not first_name.strip() or not last_name.strip() or not user_email.strip() or not user_password.strip():
                st.error("All mandatory fields must be filled.")
                is_valid = False
            
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if is_valid and not re.match(email_pattern, user_email):
                st.error("Please enter a valid email address.")
                is_valid = False
                
            if is_valid and not get_data("SELECT 1 FROM users WHERE email = ? LIMIT 1", [user_email]).empty:
                st.error("Email is already in use at Stratify")
                is_valid = False
                
            if is_valid and len(user_password) < 8:
                st.error("Password too short! Minimum 8 characters.")
                is_valid = False
                
            if is_valid and user_password != user_password_confirm:
                st.error("Passwords do not match.")
                is_valid = False

            # --- שליחה סופית ---
            if is_valid:
                m_name = middle_name.strip() if middle_name.strip() else None
                
                success = registration_func(
                    user_email, first_name, m_name, last_name, date_of_birth, user_password, user_password_confirm
                )
                
                if success:
                    # --- כאן הוספתי את ניהול ה-State לטובת דף הלוגין ---
                    st.session_state.reg_success = True
                    st.session_state.prefilled_email = user_email # שומרים את האימייל כדי להציג אותו בלוגין
                    
                    # הודעה זמנית (למקרה שה-go_to לוקח חלקיק שנייה)
                    st.success("Registration completed! Redirecting to login...")
                    
                    go_to("login_page")
                else:
                    st.error("Something went wrong during registration.")

    if st.button("Back to login"):
        go_to("login_page")
        
 
        
        
def show_home_page():
    # 1. בדיקה ושליפת נתוני משתמש (רק אם הם לא קיימים בסטייט)
    if 'first_name' not in st.session_state or st.session_state.first_name is None:
        try:
            user_data = get_data("""
                 SELECT first_name 
                 FROM users
                 WHERE user_id = ?
                 """, [int(st.session_state.user_id)])
            
            if not user_data.empty:
                st.session_state.first_name = user_data.iloc[0, 0]
            else:
                st.session_state.first_name = "Investor" # ברירת מחדל אם לא נמצא שם
        except Exception as e:
            st.error(f"Error fetching user data: {e}")
            st.session_state.first_name = "Guest"

    # שימוש בשם שנשמר בסטייט
    first_name = st.session_state.first_name

    # --- כותרת ועיצוב ---
    st.markdown(f"<h1 style='text-align: center;'>Welcome back, {first_name}! 👋</h1>", unsafe_allow_html=True)
    st.write("---")
    
    st.subheader("What would you like to do today?")
    st.write("") # מרווח

    # --- יצירת שלוש עמודות (Dashboard Grid) ---
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 📈 Stock Market")
        st.write("Analyze real-time data, view charts, and explore market trends.")
        if st.button("Explore Stocks", use_container_width=True, key="btn_stocks"):
            go_to("asset_selection")

    with col2:
        st.markdown("### 💼 My Portfolios")
        st.write("Track your investments, performance, and asset allocation.")
        if st.button("View Portfolios", use_container_width=True, key="btn_portfolios"):
            go_to("portfolios")

    with col3:
        st.markdown("### 🚀 Coming Soon")
        st.write("We are working on AI insights and crypto tracking. Stay tuned!")
        st.button("More Features", disabled=True, use_container_width=True, key="btn_soon")

    st.write("---")
    
    # Pro Tip
    st.info("💡 **Pro Tip:** Don't forget to check your risk distribution in the dashboard!")

    # --- תפריט צדדי (Sidebar) ---
    with st.sidebar:
        st.write(f"Logged in as: **{first_name}**")
        if st.button("Logout", use_container_width=True):
            st.session_state.clear()  # מוחק את כל הזיכרון
            st.rerun()  # ה-main כבר יזהה שאין משתמש וישלח ללוגין

    return



def show_portfolios_page():
    st.markdown("<h1 style='text-align: center;'>💼 My Portfolios</h1>", unsafe_allow_html=True)
    st.write("---")

    user_id = int(st.session_state.user_id)

    # Always fetch fresh data to avoid stale state issues
    user_portfolios = get_data("""
        SELECT 
            portfolio_id, 
            portfolio_name, 
            available_cash, 
            starting_at,
            current_sim_date
        FROM portfolios
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, [user_id])

    if user_portfolios.empty:
        st.info("No portfolios found. Start by creating your first strategy!")
    else:
        cols = st.columns(2)

        for index, row in user_portfolios.iterrows():
            with cols[index % 2]:
                st.markdown(f"### 📁 {row['portfolio_name']}")

                start_dt = (
                    row["starting_at"].strftime("%Y-%m-%d")
                    if pd.notnull(row["starting_at"])
                    else "N/A"
                )

                curr_dt = (
                    row["current_sim_date"].strftime("%Y-%m-%d")
                    if pd.notnull(row["current_sim_date"])
                    else "N/A"
                )

                st.write(f"📅 **Start Date:** {start_dt}")
                st.write(f"⏳ **Current Sim Date:** {curr_dt}")

                # Portfolio value calculation
                try:
                    p_value = portfolio_value_calculator(
                        row["portfolio_id"], row["current_sim_date"]
                    )
                    st.write(f"💰 **Value:** ${p_value:,.2f}")
                except Exception:
                    st.write("💰 **Value:** Error calculating")

                # Enter portfolio
                if st.button(
                    f"Enter Portfolio: {row['portfolio_name']}",
                    key=f"enter_{row['portfolio_id']}",
                    use_container_width=True,
                ):
                    st.session_state.current_portfolio_id = row["portfolio_id"]
                    st.session_state.current_portfolio_name = row["portfolio_name"]
                    st.session_state.current_sim_date = row["current_sim_date"]
                    st.session_state.current_portfolio_starting_at = row["starting_at"]
                    go_to("dashboard_home")

                # Delete portfolio
                with st.popover(
                    f"🗑️ Delete: {row['portfolio_name']}",
                    use_container_width=True
                ):
                    st.warning("⚠️ Permanent action!")

                    if st.button(
                        "Confirm Delete",
                        key=f"delete_{row['portfolio_id']}",
                        type="primary"
                    ):
                        success, message = delete_portfolio(row["portfolio_id"])

                        if success:
                            st.success(message)
                            st.rerun()

    st.write("---")

    # Create new portfolio
    col_a, col_b = st.columns(2)

    with col_a:
        with st.popover("➕ Create New Portfolio", use_container_width=True):
            with st.form("create_portfolio_form", clear_on_submit=True):
                new_name = st.text_input("Name").strip()

                min_date = datetime.date(2000, 2, 2)
                yesterday = datetime.date.today() - datetime.timedelta(days=1)

                start_date = st.date_input(
                    "Simulation Start Date",
                    value=yesterday,
                    min_value=min_date,
                    max_value=yesterday,
                    help="Select a date between Feb 2nd, 2000 and yesterday."
                )

                if st.form_submit_button("Create Now"):
                    if not new_name:
                        st.error("Portfolio name is required")
                    else:
                        success, message = create_portfolio(user_id, new_name, start_date)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

    with col_b:
        if st.button("🏠 Back to Home", use_container_width=True):
            go_to("home_page")
            
            
            
def show_dashboard_home():
    # 1. בדיקה ראשונית של מזהים
    raw_p_id = st.session_state.get('current_portfolio_id')
    raw_u_id = st.session_state.get('user_id')

    if raw_p_id is None or raw_u_id is None:
        st.warning("No portfolio selected or user not logged in.")
        if st.button("Go to My Portfolios"):
            go_to("portfolios")
        return

    user_id = int(raw_u_id)
    portfolio_id = int(raw_p_id)

    # 2. שימוש בחיבור הקיים בסטייט (בלי לפתוח חדש ובלי with)
    if 'con' not in st.session_state:
        st.session_state.con = duckdb.connect(DB_PATH)
    
    con = st.session_state.con

    # 3. שליפת הנתונים מה-DB (הסרנו con=con)
    portfolio_data = get_data("""
        SELECT portfolio_name, available_cash, created_at, starting_at, current_sim_date 
        FROM portfolios 
        WHERE portfolio_id = ? AND user_id = ?
    """, [portfolio_id, user_id])

    if portfolio_data.empty:
        st.error("⚠️ Portfolio not found or access denied.")
        if st.button("Return to My Portfolios"):
            go_to("portfolios")
        return

    # 4. חילוץ נתונים
    p_row = portfolio_data.iloc[0]
    p_name = p_row['portfolio_name']
    p_cash = p_row['available_cash']
    sim_date = p_row['current_sim_date']
    
    # חישוב שווי התיק (הפונקציה תשתמש ב-con מהסטייט או שתקבל אותו כפרמטר רגיל אם היא צריכה)
    p_value = portfolio_value_calculator(portfolio_id, sim_date, con)
    
    # עדכון ה-State
    st.session_state.current_available_cash = p_cash
    st.session_state.current_portfolio_name = p_name
    st.session_state.current_sim_date = sim_date
    st.session_state.current_sim_date_display = sim_date.strftime('%d/%m/%Y')

    # --- UI ---
    dashboard_sidebar()
    
    st.markdown(f"<h1 style='text-align: center;'>📊 Dashboard: {p_name}</h1>", unsafe_allow_html=True)
    st.info(f"🕒 **Current Simulation Date:** {st.session_state.current_sim_date_display}")
    st.write("---")

    # תצוגת מדדים
    col1, col2, col3 = st.columns(3)
    cash_ratio = (p_cash / p_value * 100) if p_value > 0 else 0
    
    # שליפת סך ההפקדות נטו
    cash_stats = con.execute("""
        SELECT 
            SUM(CASE WHEN transaction_type = 'deposit' THEN amount ELSE 0 END) - 
            SUM(CASE WHEN transaction_type = 'withdrawal' THEN amount ELSE 0 END) as net_invested
        FROM cash_transactions 
        WHERE portfolio_id = ?
    """, [portfolio_id]).fetchone()

    net_invested = cash_stats[0] if cash_stats and cash_stats[0] is not None else 0
    total_profit_cash = p_value - net_invested
    profit_pct = (total_profit_cash / net_invested * 100) if net_invested > 0 else 0

    profit_color = "normal" if total_profit_cash >= 0 else "inverse"
    prefix = "+" if total_profit_cash >= 0 else ""
    
    col1.metric("Total Portfolio Value", f"${p_value:,.2f}")
    col2.metric(
        label="Available Cash", 
        value=f"${p_cash:,.2f}", 
        delta=f"{cash_ratio:.1f}% of total",
        delta_color="blue" ,
        delta_arrow="off"
    )
    
    col3.metric(
        label="Total Profit", 
        value=f"${total_profit_cash:,.2f}", 
        delta=f"{prefix}{profit_pct:.1f}% ROI",
        delta_color=profit_color
    ) 

    st.write("---")
    show_cash_management_ui() 
    st.write("---")
    
    # הצגת טבלת האחזקות
    render_holdings_table(con, portfolio_id, sim_date)
    
    


def dashboard_sidebar():
    with st.sidebar:
        st.title("🛡️ Stratify Menu")
        
        # --- שליפת נתונים ---
        p_name = st.session_state.get('current_portfolio_name', 'Unknown')
        p_id = st.session_state.get('current_portfolio_id')
        fmt_start = st.session_state.get('current_portfolio_starting_at')
        
        fmt_start_str = fmt_start.strftime('%d/%m/%Y') if hasattr(fmt_start, 'strftime') else str(fmt_start)
        fmt_sim = st.session_state.get('current_sim_date_display', 'Unknown')

        st.subheader(f"Portfolio: {p_name}")
        st.caption(f"📅 Started: {fmt_start_str}")
        st.info(f"⏳ Currently at: {fmt_sim}")
        
        st.divider()
        
        # --- Time Machine ---
        st.write("**Time Machine**")
        
        # חישוב תאריך הגג - אתמול
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        yesterday_dt = datetime.datetime.combine(yesterday.date(), datetime.time.min)
        
        def safe_jump(new_d):
            """מקפיץ לתאריך החדש, או לאתמול אם החדש עתידי"""
            target = min(new_d, yesterday_dt)
            if handle_time_jump(target, p_id):
                st.rerun()

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("➕ 1 Day", use_container_width=True):
                safe_jump(st.session_state.current_sim_date + datetime.timedelta(days=1))
        
        with col2:
            if st.button("➕ 1 Month", use_container_width=True):
                safe_jump(st.session_state.current_sim_date + datetime.timedelta(days=30))
        
        with col3:
            if st.button("➕ 1 Year", use_container_width=True):
                safe_jump(st.session_state.current_sim_date + datetime.timedelta(days=365))

        # Jump To Date - בחירת תאריך חופשית
        current_dt = st.session_state.get('current_sim_date')
        min_d = current_dt.date() if hasattr(current_dt, 'date') else current_dt
        
        # מגבילים את ה-date_input לעד אתמול
        picked_date = st.date_input(
            "Jump to date", 
            value=min_d, 
            min_value=min_d, 
            max_value=yesterday.date(), 
            key="sb_date_picker"
        )
        
        picked_dt = datetime.datetime.combine(picked_date, datetime.time.min)
        
        if picked_dt > current_dt:
            if st.button("🚀 Confirm Jump", use_container_width=True, type="primary"):
                # כאן לא צריך min כי ה-max_value ב-date_input כבר חוסם את הבחירה
                if handle_time_jump(picked_dt, p_id):
                    st.rerun()

        st.divider()
        
        # --- ניווט פנימי ---
        st.write("**Navigation**")
        
        # מילוי דפים (Label: Page_Name)
        nav_pages = {
            "🏠 Dashboard Home": "dashboard_home",
            "📈 Performance": "portfolio_performance_analysis",
            "🛠️ Strategy Builder": "strategy_builder",
            "🔍 Asset Explorer" :"asset_explorer"
        }
        
        for label, page_val in nav_pages.items():
            # הדגשת הכפתור של הדף הנוכחי
            is_current = st.session_state.get('page') == page_val
            if st.button(label, use_container_width=True, type="primary" if is_current else "secondary"):
                st.session_state.page = page_val
                st.rerun()
        
        st.divider()
        
        # --- יציאה (ניקוי Context מוחלט) ---
        if st.button("🔙 Exit Portfolio", use_container_width=True):
            # רשימת מפתחות לניקוי למניעת "זליגת" נתונים בין תיקים
            keys_to_clear = [
                'current_portfolio_id', 
                'current_portfolio_name', 
                'current_available_cash', 
                'current_sim_date',
                'current_sim_date_display',
                'portfolio_data_cache'
            ]
            for key in keys_to_clear:
                if key in st.session_state:
                    del st.session_state[key]
            
            st.session_state.page = "portfolios"
            st.rerun()
            
 
 
            
def show_asset_explorer():
    dashboard_sidebar()
    st.title("🔍 Asset Explorer")
    
    # אתחול המשתנה למניעת שגיאת UnboundLocalError
    asset = None 
    
    if 'con' not in st.session_state:
        st.session_state.con = duckdb.connect(DB_PATH)
    con = st.session_state.con
    
    # 1. רכיב החיפוש
    asset_search_component(con)

    # 2. שליפת נתונים רק אם נבחר טיקר
    selected_ticker = st.session_state.get('selected_ticker_for_analysis')
    
    if selected_ticker:
        asset = get_asset_snapshot(con, selected_ticker, st.session_state.current_sim_date)
        
        # עכשיו asset קיים בוודאות (או כ-None או כ-Dictionary)
        if asset:
            col_info, col_actions = st.columns([2, 1])
            with col_info:
                display_asset_card(asset)
            
            with col_actions:
                if asset['current_price']:
                    show_buy_component(selected_ticker, asset['current_price'])
                    
                    if st.button(f"🔍 Analyze {asset['ticker']}", 
                                 key=f"btn1_{asset['ticker']}", 
                                 use_container_width=True): 
                        st.session_state.last_inspected_ticker = asset['ticker']
                        st.rerun()
            
            # לוגיקת הדיאלוג (עם התיקון מהשלב הקודם)
            if st.session_state.get('last_inspected_ticker') == asset['ticker']:
                st.session_state.last_inspected_ticker = None
                show_asset_analysis_dialog(asset['ticker'])
                
        st.divider()
    

       
def show_portfolio_performance_analysis():
    dashboard_sidebar()
    
    portfolio_id = st.session_state.get('current_portfolio_id')
    sim_date = st.session_state.get('current_sim_date') # תיקון שם המשתנה מ-current_current...

    if not portfolio_id:
        st.error("Please select a portfolio first.")
        return

    # --- מנגנון מטמון חכם (Cache) ---
    # בודקים אם יש לנו כבר נתונים ב-State ואם הם שייכים לפורטפוליו הנוכחי
    if ('perf_data' not in st.session_state or 
        st.session_state.get('perf_portfolio_id') != portfolio_id):
        
        # שליפה מלאה רק כשצריך (בכניסה ראשונה או החלפת תיק)
        with duckdb.connect(DB_PATH) as con:
            query = """
            SELECT timestamp, portfolio_value as value
            FROM portfolio_history
            WHERE portfolio_id = ? AND timestamp <= ?
            ORDER BY timestamp
            """
            st.session_state.perf_data = con.execute(query, [portfolio_id, sim_date]).df()
            st.session_state.perf_portfolio_id = portfolio_id
            st.session_state.last_perf_update = sim_date

    # --- עדכון אופטימי (Delta Update) ---
    # אם התאריך בסימולציה התקדם מאז השליפה האחרונה, נשלוף רק את הפער
    elif sim_date > st.session_state.last_perf_update:
        with duckdb.connect(DB_PATH) as con:
            delta_query = """
            SELECT timestamp, portfolio_value as value
            FROM portfolio_history
            WHERE portfolio_id = ? AND timestamp > ? AND timestamp <= ?
            ORDER BY timestamp
            """
            new_rows = con.execute(delta_query, [
                portfolio_id, 
                st.session_state.last_perf_update, 
                sim_date
            ]).df()
            
            if not new_rows.empty:
                # משרשרים את הנקודות החדשות ל-DataFrame הקיים ב-State
                import pandas as pd
                st.session_state.perf_data = pd.concat([st.session_state.perf_data, new_rows]).drop_duplicates()
                st.session_state.last_perf_update = sim_date

    # --- תצוגה ---
    if not st.session_state.perf_data.empty:
        # חיתוך הנתונים עד לתאריך הנוכחי (למקרה שהמשתמש קפץ אחורה בזמן, אם תאפשר זאת בעתיד)
        df_to_show = st.session_state.perf_data[st.session_state.perf_data['timestamp'] <= sim_date]
        render_performance_chart(df_to_show, title="Portfolio Performance History")
    else:
        st.info("No performance history found for this portfolio yet.")
    
    
def show_strategy_builder():
    import streamlit as st

    dashboard_sidebar()
    st.title("🛠️ Strategy Builder")

    # ---------------------------------------
    # Get required state
    # ---------------------------------------
    con = st.session_state.get("con")
    portfolio_id = st.session_state.get('current_portfolio_id')

    # ---------------------------------------
    # Validations
    # ---------------------------------------
    if con is None:
        st.error("Database connection is missing.")
        return

    if portfolio_id is None:
        st.warning("Please select a portfolio first.")
        return

    # ---------------------------------------
    # Render main component
    # ---------------------------------------
    strategy_creating_component(con, portfolio_id)