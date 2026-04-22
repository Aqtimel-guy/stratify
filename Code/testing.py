import streamlit as st
import duckdb
import pandas as pd
import datetime
import re
from functions.portfolio_managment import *
from functions.db_manager import *
from functions.trading_logic import *
from functions.users_managment import *
from functions.UI_components import *


# for runing tests 
# python -m streamlit run  "C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Code\testing.py"



# #### CONFIGURATION & DATABASE ####


st.set_page_config(page_title="Stratify 2026", layout="wide")

DB_PATH = 'C:\\Users\\Lavie\\OneDrive\\Desktop\\מוצאים עבודה\\פרוייקטים\\Stratify - gamify financial strategy\\Data_Storage\\stratify.duckdb'



# ############################################################################################
# #### 1. setting up st.state
# ############################################################################################


# ############################################################################################
# #### 2. pages
# ############################################################################################


# if unknown page - back to loggin 
if "page" not in st.session_state:
    st.error("oops, somthing went wrong. please log in again") 
    st.session_state.page = "login_page"
    
    
    
    
###################### GENERAL PAGES ###################

######### ------ LogIn Page --------- ##############
def show_login_page():
    
    # title and appearnce
    st.markdown("<h1 style='text-align: center;'>Login to Stratify</h1>", unsafe_allow_html=True)
    st.write("---")
    
    #  Form approach for loggin
    with st.form("login_form"):
        st.write("Please enter your credentials:")
        
        user_email = st.text_input("Email", placeholder="example@mail.com")
        user_password = st.text_input("Password", type="password")
    
    
        submit_button_loggin = st.form_submit_button("Login")
        
        # if pressing loggin
        if submit_button_loggin:
            if not user_email or not user_password:
                st.warning("Please fill in all fields.")
            else:
                user_id = loggin_func(user_email, user_password)
            
            if user_id != False:
                # שמירת הנתונים ב-Session
                st.session_state.user_id = user_id
                st.session_state.logged_in = True
                
                # מעבר לעמוד הבא
                st.success("Logged in successfully!")
                go_to("home_page")
            else:
                st.error("Login failed. Check your details.")

    
    #   redirecting for registration
    if st.button("For registration"):
        go_to("regestration_page")
        
        
    #   if forgot password
    if st.button("forgot my password"):
        go_to("password_recovery_page")

      
  
######### ------ Registration Page --------- ##############

def show_registration_page():
    
    # title and appearnce
    st.markdown("<h1 style='text-align: center;'>Registare to Stratify</h1>", unsafe_allow_html=True)
    st.write("---")
    
    #  Form approach for registration
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
            # 1. הגדרת משתנה עזר לבדיקה
            is_valid = True
            
            # 2. בדיקת שדות חובה (בלי middle_name שהוא רשות)
            if not first_name.strip() or not last_name.strip() or not user_email.strip() or not user_password.strip():
                st.error("All mandatory fields must be filled.")
                is_valid = False
            
            # 3. ולידציה לאימייל בעזרת RegEx
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if is_valid and not re.match(email_pattern, user_email):
                st.error("Please enter a valid email address (e.g., name@domain.com).")
                is_valid = False
                
            if is_valid and not get_data("""
                           SELECT 1 FROM users
                           WHERE email = ?
                           LIMIT 1
                           """ ,[user_email]).empty:
                st.error("Email is already in use art Stratify")
                is_valid = False
                
            # 4. בדיקת חוזק סיסמה (למשל לפחות 8 תווים)
            if is_valid and len(user_password) < 8:
                st.error("Password is too short! Must be at least 8 characters.")
                is_valid = False
                
            # checking password and password confrim match
            if is_valid and user_password != user_password_confirm:
                st.error("Password confirmation must be identical to your password")
                is_valid = False
        

            # --- שליחה סופית רק אם הכל עבר ---
            if is_valid:
                # כאן אנחנו קוראים לפונקציה שכותבת ל-DB
                # שים לב שאנחנו שולחים None אם השם האמצעי ריק
                m_name = middle_name.strip() if middle_name.strip() else None
                
                success = registration_func(
                    user_email, first_name, m_name, last_name, date_of_birth, user_password , user_password_confirm)
                
                
                if success:
                    st.session_state.reg_success = True
                    st.success("Success!")
                    st.write(f"Moving to: login_page") # בדיקה: האם זה מודפס?
                    go_to("login_page")
                else:
                    st.error("Something went wrong in the function")
 

    if st.button("Back to loggin"):
        go_to("login_page")


######### ------ Home Page --------- ##############



def show_home_page():
    
    # retriving data from DB over the users account
    first_name = get_data("""
             select first_name 
             from users
             where user_id = ?
             """ , [int(st.session_state.user_id)])

    # headline

    
    st.markdown(f"<h1 style='text-align: center;'>Welcome back, {first_name}! 👋</h1>", unsafe_allow_html=True)
    st.write("---")
    
    st.subheader("What would you like to do today?")
    st.write("") # מרווח קטן

    # יצירת שלוש עמודות לאפשרויות השונות
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 📈 Stock Market")
        st.write("Analyze real-time data, view charts, and explore market trends.")
        if st.button("Explore Stocks", use_container_width=True):
            go_to("asset_selection") # או השם שנתת לעמוד המניות

    with col2:
        st.markdown("### 💼 My Portfolios")
        st.write("Track your investments, performance, and asset allocation.")
        if st.button("View Portfolios", use_container_width=True):
            go_to("portfolios") # או עמוד ייעודי לפורטפוליו

    with col3:
        st.markdown("### 🚀 Coming Soon")
        st.write("We are working on AI insights and crypto tracking. Stay tuned!")
        st.button("More Features", disabled=True, use_container_width=True)

    st.write("---")
    
    # אפשר להוסיף כאן "תקציר" קטן של השוק או חדשות
    st.info("💡 **Pro Tip:** Don't forget to check your risk distribution in the dashboard!")

    # כפתור התנתקות בתחתית
    if st.sidebar.button("Logout"):
        st.session_state.clear() # מנקה את כל הנתונים
        go_to("login_page")
    return


#### ------- portfolios Page -------- ###########

def show_portfolios_page():
    st.markdown("<h1 style='text-align: center;'>💼 My Portfolios</h1>", unsafe_allow_html=True)
    st.write("---")

    user_id = int(st.session_state.user_id)
    user_portfolios = get_data("""
        SELECT 
            portfolio_id, 
            portfolio_name, 
            available_cash, 
            starting_at,
            current_sim_date
        FROM portfolios
        WHERE user_id = ?
    """, [user_id])

    if user_portfolios.empty:
        st.info("No portfolios found. Start by creating your first strategy!")
    else:
        cols = st.columns(2) 
        for index, row in user_portfolios.iterrows():
            with cols[index % 2]:
                st.markdown(f"### 📁 {row['portfolio_name']}")
                
                # תצוגת תאריכים בצורה נכונה (בלי $ ובלי פורמט של מספר)
                start_dt = row['starting_at'].strftime('%Y-%m-%d') if pd.notnull(row['starting_at']) else "N/A"
                curr_dt = row['current_sim_date'].strftime('%Y-%m-%d') if pd.notnull(row['current_sim_date']) else "N/A"
                
                st.write(f"📅 **Start Date:** {start_dt}")
                st.write(f"⏳ **Current Sim Date:** {curr_dt}")
                
                # חישוב שווי פורטפוליו (שים לב: העברת ערכים ולא רשימות של מחרוזות)
                try:
                    p_value = portfolio_value_calculator(row['portfolio_id'], row['current_sim_date'])
                    st.write(f"💰 **Value:** ${p_value:,.2f}")
                except Exception as e:
                    st.write(f"💰 **Value:** Error calculating")

                if st.button(f"Enter Portfolio: {row['portfolio_name']}", key=f"btn_{row['portfolio_id']}", use_container_width=True):
                    st.session_state.current_portfolio_id = row['portfolio_id']
                    st.session_state.current_portfolio_name = row['portfolio_name']
                    st.session_state.current_starting_at = row['starting_at']
                    st.session_state.current_current_sim_date = row["current_sim_date"]
                    # תיקון שם המפתח ל-starting_at כפי שמופיע ב-SQL
                    st.session_state.current_portfolio_starting_at = row['starting_at']
                    go_to("dashboard_home")
                    
                ## and delete button with popover for confirmation
                with st.popover(f"🗑️ Delete: {row['portfolio_name']}", use_container_width=True):
                    st.warning("⚠️ **Warning:** This action is permanent! There is no way to recover this portfolio once deleted.")
    
                  # כפתור האישור הסופי נמצא בתוך התיבה
                    confirm_delete = st.button(f"Yes, I'm sure. Delete '{row['portfolio_name']}'", 
                                key=f"confirm_del_{row['portfolio_id']}", 
                                type="primary", # צבע בולט (אדום בד"כ) כדי לסמן סכנה
                                use_container_width=True)
        
                    if confirm_delete:
                        success, message = delete_portfolio(row['portfolio_id'])
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

    st.write("---")

    # 3. כפתורי פעולה בתחתית
    col_a, col_b = st.columns(2)
    
    with col_a:
        # שימוש ב-popover יוצר כפתור שפותח תפריט מעליו, זה נראה מעולה ב-UI
        with st.popover("➕ Create New Portfolio", use_container_width=True):
            st.write("### New Portfolio Details")
            with st.form("create_new_portfolio_form", clear_on_submit=True):
                new_name = st.text_input("Portfolio Name", placeholder="e.g., Retirement Strategy")
                # הוספתי את התאריך כפי שביקשת בלוגיקה
                start_date = st.date_input("Simulation Start Date", 
                           value=datetime.date.today(),
                           min_value=datetime.date(2000 , 2 , 2),
                           max_value=datetime.date.today())
                
                submit_create = st.form_submit_button("Create Now", use_container_width=True)
                
                if submit_create:
                    if not new_name:
                        st.error("Please enter a name.")
                    else:
                        # קריאה לפונקציה שכתבת!
                        success, message = create_portfolio(user_id, new_name, start_date)
                        if success:
                            st.success(message)
                            st.rerun() # מרענן את הדף כדי שהכרטיס החדש יופיע מיד
                        else:
                            st.error(message)

    with col_b:
        if st.button("🏠 Back to Home", use_container_width=True):
            go_to("home_page")
        
        
#####################  ----- dashboard ------  #############################################
def dashboard_sidebar():
    with st.sidebar:
        st.title("🛡️ Stratify Menu")
        
        # שליפת נתונים בסיסיים
        p_name = st.session_state.get('current_portfolio_name', 'Unknown')
        p_id = st.session_state.get('current_portfolio_id')
        
        # עיצוב תאריכים בצורה בטוחה
        start_date = st.session_state.get('current_starting_at')
        sim_date = st.session_state.get('current_current_sim_date') # וודא שזה השם המדויק ב-state
        
        fmt_start = start_date.strftime('%d/%m/%Y') if hasattr(start_date, 'strftime') else "Unknown"
        fmt_sim = sim_date.strftime('%d/%m/%Y') if hasattr(sim_date, 'strftime') else "Unknown"

        st.subheader(f"Portfolio: {p_name}")
        st.caption(f"📅 Started: {fmt_start}")
        st.info(f"⏳ Currently at: {fmt_sim}")
        
        st.write("---")
        
        # --- חלק ניהול זמן (מכונת זמן) ---
        st.write("**Time Machine**")
        
        # שורה ראשונה: יום וחודש
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 1 Day", use_container_width=True):
                success, result = move_time_forward(p_id, "1d")
                if success:
                    st.session_state.current_current_sim_date = result
                    st.rerun()
        
        with col2:
            if st.button("➕ 1 Month", use_container_width=True):
                success, result = move_time_forward(p_id, "1ME")
                if success:
                    st.session_state.current_current_sim_date = result
                    st.rerun()

        # שורה שנייה: שנה ובחירה חופשית
        col3, col4 = st.columns(2)
        with col3:
            if st.button("➕ 1 Year", use_container_width=True):
                success, result = move_time_forward(p_id, "1YE") # YE עבור Year End
                if success:
                    st.session_state.current_current_sim_date = result
                    st.rerun()
        
        with col4:
            # 1. בחירת התאריך (נשמר בזיכרון זמני של הווידג'ט)
            min_d = st.session_state.get('current_current_sim_date')
            picked_date = st.date_input(
                "Jump to", 
                value=min_d, 
                min_value=min_d, 
                max_value=datetime.datetime.now(), 
                label_visibility="collapsed",
                key="date_picker_input" # מפתח ייחודי למניעת התנגשויות
            )
            
            # 2. כפתור אישור קטן מתחת ללוח השנה
            # אנחנו בודקים אם התאריך שנבחר שונה מהתאריך הנוכחי
            current_date_only = min_d.date() if hasattr(min_d, 'date') else min_d
            
            if picked_date != current_date_only:
                if st.button("✅ Confirm Jump", use_container_width=True, type="primary"):
                    # ביצוע העדכון רק לאחר לחיצה
                    con = duckdb.connect(DB_PATH)
                    new_dt = datetime.datetime.combine(picked_date, datetime.time.min)
                    
                    con.execute("""
                        UPDATE portfolios 
                        SET current_sim_date = ? 
                        WHERE portfolio_id = ?
                    """, [new_dt, p_id])
                    
                    st.session_state.current_current_sim_date = new_dt
                    con.close()
                    
                    st.success(f"Jumped to {picked_date}")
                    st.rerun()

        st.write("---")
        
        # --- ניווט פנימי ---
        if st.button("🏠 Dashboard Home", use_container_width=True):
            go_to("dashboard_home")
            
        if st.button("📈 Performance Analysis", use_container_width=True):
            go_to("portfolio_performance_analysis")
            
        if st.button("🛠️ Strategy Builder", use_container_width=True):
            go_to("asset_explorer")
                
        if st.button("🔍 Data Explorer (Advanced)", use_container_width=True):
            go_to("data_explorer")
        
        st.write("---")
        
        # --- יציאה ---
        if st.button("🔙 Back to All Portfolios", use_container_width=True, type="secondary"):
            st.session_state.current_portfolio_id = None
            st.session_state.current_portfolio_name = None
            go_to("portfolios")





def show_dashboard_home(user_id , portfolio_id):
    st.markdown(f"<h1 style='text-align: center;'>📊 Dashboard for Portfolio {st.session_state.current_portfolio_name}</h1>", unsafe_allow_html=True)
    st.write("---")
    
    ## dashboard sidebar
    dashboard_sidebar()
    
# 1. שליפת הנתונים מה-DB
    # הוספנו את user_id לשאילתה כדי לוודא הרשאה כבר ברמת ה-SQL
    portfolio_data = get_data("""
        SELECT portfolio_name, portfolio_value, available_cash, created_at , starting_at , current_sim_date 
        FROM portfolios 
        WHERE portfolio_id = ? AND user_id = ?
    """, [portfolio_id, user_id])

    # 2. טיפול בשגיאת ה-ValueError (בדיקה אם חזרו נתונים)
    if portfolio_data.empty:
        st.error("⚠️ Portfolio not found or access denied.")
        if st.button("Return to My Portfolios"):
            st.session_state.page = "portfolios"
            st.rerun()
        return

    # 3. חילוץ נתונים (שימוש ב-iloc כדי למנוע אמביוולנטיות)
    p_name = portfolio_data.iloc[0]['portfolio_name']
    p_value = portfolio_value_calculator(portfolio_id , portfolio_data.iloc[0]['current_sim_date'] )
    p_cash = portfolio_data.iloc[0]['available_cash']
    st.session_state.current_available_cash = p_cash
    p_created = portfolio_data.iloc[0]['created_at']
    p_starting = portfolio_data.iloc[0]['starting_at']
    
    # 4. שליפת האחזקות (Holdings)
    holdings_data = get_data("""
        SELECT 
            asset_id , quantity
        FROM
            holdings
        WHERE
            portfolio_id = ?
    """, [portfolio_id])
    

    
    

    # --- תצוגת התוכן המרכזי ---
    st.markdown(f"<h1 style='text-align: center;'>📊 {p_name}</h1>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='text-align: center;'>📊 {'BULBUL'}</h1>", unsafe_allow_html=True)

  
    
    st.write("---")

    # תצוגת מדדים בולטים
    col1, col2, col3 = st.columns(3)
    
    # חישוב לדוגמה של אחוז מזומן מהתיק
    cash_ratio = (p_cash / p_value * 100) if p_value > 0 else 0
    
    col1.metric("Total Value", f"${p_value:,.2f}")
    col2.metric("Available Cash", f"${p_cash:,.2f}", f"{cash_ratio:.1f}% of total")
    col3.metric("Daily Change", "$0.00", "0.0%") # נמלא את זה כשנחבר נתוני שוק

    st.write("---")

    con = duckdb.connect(DB_PATH)
    
    # הצגת כפתורי הפקדה/משיכה
    show_cash_management_ui()
    
    st.write("---")
    
    # הצגת טבלת האחזקות
    sim_date = st.session_state.current_current_sim_date
    render_holdings_table(con, portfolio_id, sim_date)
    
    con.close()




    
#############################################
def show_portfolio_performance_analysis():
    dashboard_sidebar()
    # 1. חילוץ המשתנים הדרושים מה-session_state (כאן היה החוסר)
    portfolio_id = st.session_state.get('current_portfolio_id')
    sim_date = st.session_state.get('current_current_sim_date')
    
    # בדיקת בטיחות - אם המשתמש לא בחר פורטפוליו, שלא יקרוס
    if not portfolio_id:
        st.error("Please select a portfolio first.")
        return

    con = duckdb.connect(DB_PATH)
    
    # 2. השאילתה (שים לב שהמשתנים עכשיו מוגדרים)
    query = """
    SELECT timestamp, portfolio_value as value
    FROM portfolio_history
    WHERE portfolio_id = ? AND timestamp <= ?
    ORDER BY timestamp
    """
    
    try:
        df_perf = con.execute(query, [portfolio_id, sim_date]).df()
        
        # 3. קריאה לפונקציית הגרף שבנינו קודם
        render_performance_chart(df_perf, title="Portfolio Performance History")
    except Exception as e:
        st.error(f"Could not load performance data: {e}")
    finally:
        con.close()
    
    
####################################
def show_strategy_builder():
    dashboard_sidebar()
    st.title("🛠️ Strategy Builder")
    
    con = duckdb.connect(DB_PATH)
    
    # 1. חיפוש (כבר פונקציה נפרדת)
    asset_search_component(con)

    # 2. הצגת פרטי הנכס ורכישה
    if st.session_state.get('selected_ticker_for_analysis'):
        ticker = st.session_state.selected_ticker_for_analysis
        asset = get_asset_snapshot(con, ticker, st.session_state.current_current_sim_date)
        
        if asset:
            display_asset_card(asset) # מציג את המחיר והנתונים
            
            # אם יש מחיר - נציג את קומפוננטת הרכישה
            if asset['current_price']:
                st.write("---")
                show_buy_component(con, ticker, asset['current_price'])
    
    con.close()




##################################
def show_data_explorer():
    pass 
    

# ############################################################################################
# #### 3. Router
# ############################################################################################

if st.session_state.page == "login_page":
    show_login_page()
    
elif st.session_state.page == "home_page":
    show_home_page()
    
elif st.session_state.page == "dashboard_home":
    user_id = st.session_state.get('user_id')
    portfolio_id = st.session_state.get('current_portfolio_id')
    
    if user_id is not None and portfolio_id is not None:
        show_dashboard_home(int(user_id), int(portfolio_id))
    else:
        st.warning("Please select a portfolio first.")
        st.session_state.page = "portfolios"
        st.rerun()
    
elif st.session_state.page == "portfolio_performance_analysis":
    show_portfolio_performance_analysis()
    
elif st.session_state.page == "portfolio_strategy_builder":
    show_strategy_builder()


elif st.session_state.page =="Data_explorer":
    show_data_explorer()
    
elif st.session_state.page == "regestration_page":
    show_registration_page()
    
elif st.session_state.page == "portfolios":
    show_portfolios_page()
    
else:
    # אם הגעת לכאן, תדע בדיוק מה הערך ה"שגוי"
    st.error(f"Page '{st.session_state.page}' not found in Router!")
    if st.button("Emergency Back to Login"):
        st.session_state.page = "login_page"
        st.rerun()
        
        
        
        
        
