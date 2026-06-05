import streamlit as st
from .db_manager import *
from .users_managment import *
from .portfolio_managment import *
from .UI_components import *
from .trading_logic import *
from sqlalchemy import text
from Code.functions.db_manager import get_supabase_engine


def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()
    

def show_login_page():
    """
    Renders the login page and handles authentication flow.
    """

    # ---------------------------------------------------------------------
    # 1. Registration success message (one-time)
    # ---------------------------------------------------------------------
    if st.session_state.get("reg_success"):
        st.success("Registration successful! Please log in.")
        st.session_state["reg_success"] = False

    # ---------------------------------------------------------------------
    # 2. Title section
    # ---------------------------------------------------------------------
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #2E4057;">Sign In to Stratify</h1>
            <p style="color: #7F8C8D;">Gamify your financial strategy</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    prefilled_email = st.session_state.get("prefilled_email", "")

    # ---------------------------------------------------------------------
    # 3. Layout
    # ---------------------------------------------------------------------
    _, main_co, _ = st.columns([1, 2, 1])

    with main_co:
        with st.container(border=True):
            with st.form("login_form", clear_on_submit=False):

                st.markdown("### Credentials")

                user_email = st.text_input(
                    "Email",
                    value=prefilled_email,
                    placeholder="example@mail.com"
                )

                user_password = st.text_input(
                    "Password",
                    type="password",
                    placeholder="••••••••"
                )

                submit_button = st.form_submit_button("Login")

                # ---------------------------------------------------------
                # 4. Form submission
                # ---------------------------------------------------------
                if submit_button:

                    if not user_email or not user_password:
                        st.warning("Please fill in all fields.")
                        return

                    user_id, first_name = loggin_func(
                        user_email,
                        user_password
                    )

                    if user_id is not None:
                        # ---------------- SUCCESS LOGIN ----------------
                        st.session_state["user_id"] = user_id
                        st.session_state["first_name"] = first_name
                        st.session_state["logged_in"] = True

                        # clear sensitive temp data
                        st.session_state.pop("prefilled_email", None)

                        # reset any auth protection state if exists
                        if "auth_attempts" in st.session_state:
                            st.session_state["auth_attempts"] = 0
                        if "auth_locked_until" in st.session_state:
                            st.session_state["auth_locked_until"] = 0

                        st.success("Logged in successfully!")
                        go_to("home_page")

                    else:
                        st.error("Invalid email or password.")

    # ---------------------------------------------------------------------
    # 5. Secondary actions
    # ---------------------------------------------------------------------
    st.write("")
    col_reg, col_forgot = st.columns(2)

    with col_reg:
        if st.button("New here? Register", use_container_width=True):
            go_to("regestration_page")

    with col_forgot:
        if st.button("Forgot password?", use_container_width=True):
            go_to("password_recovery_page")
  
  
  
def show_registration_page():
    """
    Renders user registration page and handles signup flow.
    """

    # ---------------------------------------------------------------------
    # 1. Title
    # ---------------------------------------------------------------------
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #2E4057;">Create Your Stratify Account</h1>
            <p style="color: #7F8C8D;">Join us and start gamifying your financial strategy</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    left_co, main_co, right_co = st.columns([0.5, 2, 0.5])

    with main_co:
        with st.container(border=True):
            with st.form("registration_form", clear_on_submit=False):

                st.markdown("### Personal Information")

                # ---------------------------------------------------------
                # Inputs
                # ---------------------------------------------------------
                col_first, col_middle, col_last = st.columns(3)

                with col_first:
                    first_name = st.text_input("First name *", placeholder="John")

                with col_middle:
                    middle_name = st.text_input("Middle name", placeholder="Snow")

                with col_last:
                    last_name = st.text_input("Last name *", placeholder="Stark")

                st.markdown("---")

                user_email = st.text_input("Email Address *", placeholder="example@mail.com")

                col_pass, col_confirm = st.columns(2)

                with col_pass:
                    user_password = st.text_input("Password *", type="password")

                with col_confirm:
                    user_password_confirm = st.text_input("Confirm password *", type="password")

                today = datetime.date.today()
                hundred_years_ago = today.replace(year=today.year - 100)

                date_of_birth = st.date_input(
                    "Date of Birth",
                    value=datetime.date(2000, 1, 1),
                    min_value=hundred_years_ago,
                    max_value=today
                )

                st.markdown("* Required fields")

                submit = st.form_submit_button("Register")

                # ---------------------------------------------------------
                # 2. Submission
                # ---------------------------------------------------------
                if submit:

                    # Basic validation (UI-level only)
                    if not all([first_name, last_name, user_email, user_password]):
                        st.error("Please fill in all required fields.")
                        return

                    if user_password != user_password_confirm:
                        st.error("Passwords do not match.")
                        return

                    if len(user_password) < 8:
                        st.error("Password must be at least 8 characters.")
                        return

                    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                    if not re.match(email_pattern, user_email):
                        st.error("Invalid email format.")
                        return

                    # -----------------------------------------------------
                    # 3. Duplicate check (cloud)
                    # -----------------------------------------------------
                    exists = get_data(
                        "SELECT 1 FROM users WHERE LOWER(email) = LOWER(:email) LIMIT 1",
                        {"email": user_email},
                        use_cloud=True
                    )

                    if not exists.empty:
                        st.error("Email already registered.")
                        return

                    # -----------------------------------------------------
                    # 4. Call backend service
                    # -----------------------------------------------------
                    m_name = middle_name.strip() if middle_name.strip() else None

                    success = registration_func(
                        user_email,
                        first_name,
                        m_name,
                        last_name,
                        date_of_birth,
                        user_password,
                        user_password_confirm
                    )

                    if success:
                        st.session_state["reg_success"] = True
                        st.session_state["prefilled_email"] = user_email

                        st.success("Account created successfully!")
                        go_to("login_page")
                    else:
                        st.error("Registration failed. Please try again.")

    # ---------------------------------------------------------------------
    # 5. Back to login
    # ---------------------------------------------------------------------
    st.write("")

    if st.button("← Already have an account? Login", use_container_width=True):
        go_to("login_page") 
 
 
 
 
def show_password_recovery_page():
    """
    Placeholder password recovery page (development mode only).
    No real recovery logic is executed yet.
    """

    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #2E4057;">Reset Your Password</h1>
            <p style="color: #7F8C8D;">We'll help you get back into Stratify</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    left_co, main_co, right_co = st.columns([1, 2, 1])

    with main_co:
        with st.container(border=True):
            with st.form("password_recovery_form", clear_on_submit=False):

                st.markdown("### Account Recovery")

                email = st.text_input(
                    "Enter your registered email *",
                    placeholder="example@mail.com"
                )

                submit = st.form_submit_button("Recover Password")

                if submit:

                    # -----------------------------------------------------
                    # Basic validation only (no backend logic yet)
                    # -----------------------------------------------------
                    if not email or not email.strip():
                        st.warning("Please enter your email.")
                        return

                    email = email.strip()

                    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

                    if not re.match(email_pattern, email):
                        st.error("Invalid email format.")
                        return

                    # -----------------------------------------------------
                    # SAFE PLACEHOLDER (no user enumeration)
                    # -----------------------------------------------------
                    st.info(
                        "If this email exists in our system, "
                        "you will receive recovery instructions once the feature is enabled."
                    )

    # ---------------------------------------------------------------------
    # Navigation
    # ---------------------------------------------------------------------
    st.write("")

    if st.button("← Back to Login", use_container_width=True):
        go_to("login_page")      
    
    
    
            
           

def show_home_page():
    # 1. Check and fetch user data (only if not already present in session state)
    if 'first_name' not in st.session_state or st.session_state.first_name is None:
        try:
            user_data = get_data("""
                 SELECT first_name 
                 FROM users
                 WHERE user_id = ?
                 """, [int(st.session_state.user_id)], use_cloud=True)
            
            if not user_data.empty:
                st.session_state.first_name = user_data.iloc[0, 0]
            else:
                st.session_state.first_name = "Investor" # Default fallback if name not found
        except Exception as e:
            st.error(f"Error fetching user data: {e}")
            st.session_state.first_name = "Guest"

    # Use the name stored in session state
    first_name = st.session_state.first_name


    # ==========================================
    # SYSTEM INJECTION: UNIFIED ADVANCED UX & SIDEBAR STYLES
    # ==========================================
    st.markdown(
        """
        <style>
        /* --- MAIN APP LAYOUT BASE STYLES --- */
        /* Compact, modern layout & soft light-slate background */
        [data-testid="stAppViewContainer"] {
            background-color: #F7F9FB;
            padding: 10px 10px;
        }

        /* Glassmorphic card containers for main app content view grids */
        .stContainer, [data-testid="stForm"] {
            background: rgba(255, 255, 255, 0.4); 
            backdrop-filter: blur(10px); 
            -webkit-backdrop-filter: blur(10px);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
            margin-bottom: 10px !important;
            padding: 10px !important;
        }

        /* Global Button Override for Main View: Minimalist pills built for high density */
        .stButton > button {
            border-radius: 20px !important;
            padding: 0.15rem 0.6rem !important; 
            font-size: 11px !important;
            border: 1px solid #2E4057;
            background: transparent;
            color: #2E4057;
            transition: all 0.2s ease-in-out;
        }
        
        .stButton > button:hover {
            background: rgba(46, 64, 87, 0.1);
            border-color: #2E4057;
        }

        /* --- PREMIUM DARK SIDEBAR CORE STYLES --- */
        /* Forces a strict 200px layout width footprint and sets deep premium dark slate background */
        [data-testid="stSidebar"], [data-testid="stSidebarUserContent"] {
            width: 200px !important; 
            min-width: 200px !important;
            max-width: 200px !important;
            background-color: #1E293B !important; 
            color: #F8FAFC !important;
            border-right: 1px solid rgba(0, 0, 0, 0.1);
        }

        /* Completely removes the default sidebar collapse toggle arrow button */
        [data-testid="stSidebarCollapseButton"] {
            display: none !important;
        }
        
        /* Forces all internal sidebar content to snap directly to the absolute top edge */
        [data-testid="stSidebarUserContent"] {
            padding-top: 0.2rem !important;
        }

        /* Wipes out hidden default padding/margin gaps on the first structural inner block */
        [data-testid="stSidebarUserContent"] > div:first-child {
            padding-top: 0px !important;
            margin-top: 0px !important;
        }
        
        /* Typography corrections for clear dark-mode contrast readability */
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p {
            color: #F8FAFC !important;
            font-weight: 600 !important;
        }
        
        /* Glassmorphic Dark Portfolio Meta Summary Card structure */
        .sidebar-meta-card {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        /* --- TARGETED SIDEBAR BUTTONS & NAVIGATION OVERRIDES --- */
        /* Forced base style for all sidebar buttons including System Time Machine and Exit */
        [data-testid="stSidebar"] button {
            border-radius: 10px !important;
            border: 1px solid rgba(255, 255, 255, 0.15) !important;
            background-color: rgba(255, 255, 255, 0.04) !important;
            color: #E2E8F0 !important; 
            transition: all 0.2s ease-in-out !important;
            font-size: 13px !important;
            font-weight: 500 !important;
            padding: 0.4rem 0.8rem !important;
            width: 100% !important;
            display: block;
        }
        
        /* Hover states highlighting actions with a premium electric cyan accent glow */
        [data-testid="stSidebar"] button:hover {
            background-color: rgba(56, 189, 248, 0.2) !important; 
            border-color: #38BDF8 !important;
            color: #38BDF8 !important;
            transform: translateY(-1px);
        }
        
        /* Strict styling override mapping the active current navigation button state */
        [data-testid="stSidebar"] div.element-container:has(button[id^="active_nav_"]) button {
            background-color: #38BDF8 !important; 
            color: #0F172A !important; 
            border-color: #38BDF8 !important;
            font-weight: 600 !important;
        }

        [data-testid="stSidebar"] div.element-container:has(button[id^="active_nav_"]) button:hover {
            background-color: #7DD3FC !important;
            color: #0F172A !important;
            border-color: #7DD3FC !important;
        }
        
        /* Minimalist structural fallback layout for default sidebar date pickers */
        [data-testid="stSidebar"] div[data-component="stDateInput"] {
            background: transparent !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # --- App Branding Header ---
    # Injected corporate branding stack using neon cyber-cyan text shadow treatments
    st.sidebar.markdown(
        """
        <div style="text-align: center; margin-bottom: 20px;">
            <h2 style="color: #00F0FF; margin: 0; letter-spacing: 1px; text-shadow: 0 2px 4px rgba(0, 240, 255, 0.2);">🛡️ STRATIFY</h2>
            <span style="font-size: 10px; color: #94A3B8; text-transform: uppercase;">Simulation Engine v1.0</span>
        </div>
        """, 
        unsafe_allow_html=True
    )

    # --- MAIN CONTENT AREA: Glassmorphism Header ---
    with st.container():
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; justify-content: center; gap: 10px;">
                <h2 style="color: #2E4057; margin: 0;">Welcome, {first_name}! 👋</h2>
            </div>
            """, 
            unsafe_allow_html=True
        )
    
    st.write("") # Tiny spacer

    # --- GADGET GRID: Smaller Columns for minimal icons/buttons ---
    # Using small icons as the primary focal point, text minimized
    gadget1, gadget2, gadget3 = st.columns(3)

    with gadget1:
        with st.container():
            st.markdown("💼 **Real time Market**", unsafe_allow_html=True)
            st.write("Current market coming soon.")
            st.button("Tuned", disabled=True, use_container_width=True, key="market_btn")

    with gadget2:
        with st.container():
            st.markdown("📈 **My Simulation portfolios**", unsafe_allow_html=True)
            st.write("Define your investment strategy and test it.")
            if st.button("Go to simulation portfolios", use_container_width=True, key="view_port"):
                go_to("portfolios")

    with gadget3:
        with st.container():
            st.markdown("🚀 **Labs**", unsafe_allow_html=True)
            st.write("AI & Crypto coming soon.")
            st.button("Tuned", disabled=True, use_container_width=True, key="labs_btn")

    st.write("") # Micro-spacer
    
    # --- Dynamic Pro Tip (Compact Glass style) ---
    with st.container():
        st.markdown("<p style='font-size: 11px; color: #7F8C8D; margin: 0;'>💡 **Risk Pro Tip:** Review allocation weekly to align with strategy.</p>", unsafe_allow_html=True)

    # --- SIDEBAR: Ultra-compact, centered profile & tiny logout ---
    with st.sidebar:
        # --- Investor Profile Header Section ---
        st.markdown(
            f"""
            <div class="sidebar-profile" style="
                display: flex; 
                flex-direction: column; 
                align-items: center; 
                justify-content: center; 
                text-align: center; 
                width: 100%;
                margin-bottom: 20px; 
                padding-bottom: 15px;
                border-bottom: 1px dashed rgba(255, 255, 255, 0.1);
            ">
                <span style="color: #94A3B8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; display: block;">Investor Profile</span>
                <strong style="color: #FFFFFF; font-size: 22px; font-weight: 700; line-height: 1.3; display: block; margin-top: 4px;">{first_name}</strong>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        st.write("") # Micro-spacer
        
        # --- Ultra-Specific Crimson Logout Button CSS Style Override ---
        # Wrapping the button inside a custom class container (.custom-logout-container)
        # to guarantee strict CSS specificity superiority.
        st.markdown(
            """
            <style>
            .custom-logout-container button {
                background-color: rgba(239, 68, 68, 0.1) !important;
                border: 1px solid #EF4444 !important;
                border-radius: 10px !important;
                padding: 0.4rem 0.8rem !important;
                font-size: 13px !important;
                font-weight: 600 !important;
                transition: all 0.2s ease-in-out !important;
                width: 100% !important;
                display: block !important;
            }
            
            /* Target both the button text wrapper and the button core frame for color sync */
            .custom-logout-container button, 
            .custom-logout-container button p,
            .custom-logout-container button span {
                color: #EF4444 !important;
            }
            
            /* High-visibility hover trigger state styling */
            .custom-logout-container button:hover {
                background-color: #EF4444 !important;
                border-color: #EF4444 !important;
                transform: translateY(-1px) !important;
                box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3) !important;
            }
            
            .custom-logout-container button:hover p,
            .custom-logout-container button:hover span {
                color: #FFFFFF !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        
        # --- System Logout Trigger Action Wrapped in Custom Div Container ---
        st.markdown('<div class="custom-logout-container">', unsafe_allow_html=True)
        if st.button("Logout", key="sidebar_logout_small"):
            st.session_state.clear()  # Clear all memory frame cache states
            st.rerun()  # Rerun the app context back to the authentication screen
        st.markdown('</div>', unsafe_allow_html=True)

    return



def show_portfolios_page():
    """
    Clean UI layer.
    No business logic. Only rendering.
    """

    if "portfolio_create_version" not in st.session_state:
        st.session_state.portfolio_create_version = 0

    # --- styles (unchanged) ---
    st.markdown("""<style> ... your css ... </style>""", unsafe_allow_html=True)

    # --- sidebar (unchanged) ---
    first_name = st.session_state.get("first_name", "Investor")

    st.sidebar.markdown(f"""
        <div style="text-align:center;">
            <h2>🛡️ STRATIFY</h2>
            <strong>{first_name}</strong>
        </div>
    """, unsafe_allow_html=True)

    if st.sidebar.button("Logout", key="sidebar_logout_small"):
        st.session_state.clear()
        st.rerun()

    # --- title ---
    st.markdown("<h2 style='text-align:center;'>💼 My Portfolios</h2>", unsafe_allow_html=True)
    st.write("---")

    user_id = st.session_state.user_id

    # 🔥 ALL LOGIC MOVED OUT
    portfolios_df = get_portfolio_card_data(user_id)

    if portfolios_df.empty:
        st.info("No portfolios found. Start by creating your first strategy!")
        return

    cols = st.columns(2)

    for i, row in portfolios_df.iterrows():
        with cols[i % 2]:

            st.markdown(f"### 📁 {row['portfolio_name']}")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Start", row["start_date"])

            with col2:
                st.metric("Sim Date", row["sim_date"])

            with col3:
                val = row["value"]
                st.metric("Value", f"${val:,.2f}" if val else "N/A")

            c1, c2 = st.columns([2, 1])

            with c1:
                if st.button("Enter Portfolio", key=f"enter_{row['portfolio_id']}"):
                    st.session_state.current_portfolio_id = row["portfolio_id"]
                    st.session_state.current_portfolio_name = row["portfolio_name"]
                    go_to("dashboard_home")

            with c2:
                with st.popover("🗑️ Delete", key=f"del_{row['portfolio_id']}"):
                    if st.button("Confirm", key=f"confirm_{row['portfolio_id']}"):
                        success, message = delete_portfolio(row["portfolio_id"])
                        if success:
                            st.rerun()
                        else:
                            st.error(message)

    st.write("---")

    col_a, col_b = st.columns(2)

    with col_b:
        with st.popover("➕ Create New Portfolio"):
            with st.form("create_portfolio_form"):
                name = st.text_input("Name")
                date = st.date_input("Start date")

                if st.form_submit_button("Create"):
                    if name:
                        create_portfolio(user_id, name, date)
                        st.rerun()

    with col_a:
        if st.button("🏠 Back"):
            go_to("home_page")
            
######################################

def show_dashboard_home():
    """
    Renders the main simulation strategy control center dashboard home view.
    Handles cloud-native portfolio statistics, interim asset metrics caching,
    fluid capital adjustments, and data ledger layout metrics.
    All source documentation and comments are maintained strictly in English.
    """
    # ==========================================
    # STEP 1: INITIAL VALIDATION & AUTH CHECK
    # ==========================================
    raw_p_id = st.session_state.get('current_portfolio_id')
    raw_u_id = st.session_state.get('user_id')

    if raw_p_id is None or raw_u_id is None:
        st.warning("No portfolio selected or user not logged in.")
        if st.button("Go to My Portfolios", key="err_go_portfolios"):
            go_to("portfolios")
        return

    user_id = int(raw_u_id)
    portfolio_id = int(raw_p_id)

    # Initialize a clean component reset key versioning tracker for forms
    if "cash_op_version" not in st.session_state:
        st.session_state.cash_op_version = 0

    # ==========================================
    # STEP 2: DATA EXTRACTION & CALCULATIONS
    # ==========================================
    # Extract structural configuration state metadata from the cloud engine
    portfolio_data = get_data("""
        SELECT portfolio_name, available_cash, created_at, starting_at, current_sim_date 
        FROM portfolios 
        WHERE portfolio_id = :portfolio_id AND user_id = :user_id
    """, {"portfolio_id": portfolio_id, "user_id": user_id}, use_cloud=True)

    if portfolio_data.empty:
        st.error("⚠️ Portfolio not found or access denied.")
        if st.button("Return to My Portfolios", key="err_return_portfolios"):
            go_to("portfolios")
        return

    # Extract raw record variables from the verified operational data container row
    p_row = portfolio_data.iloc[0]
    p_name = p_row['portfolio_name']
    p_cash = float(p_row['available_cash'])
    sim_date = p_row['current_sim_date']
    
    # Calculate global real-time metric assets value valuation using the isolated cloud interface
    p_value = float(portfolio_value_calculator(portfolio_id=portfolio_id, timestamp=sim_date))
    
    # Commit synchronized application memory context updates
    st.session_state.current_available_cash = p_cash
    st.session_state.current_portfolio_name = p_name
    st.session_state.current_sim_date = sim_date
    st.session_state.current_sim_date_display = sim_date.strftime('%d/%m/%Y')

    # Spin up an isolated transaction connection context frame block for metrics calculation
    cloud_engine = get_supabase_engine()
    with cloud_engine.connect() as cloud_con:
        cash_stats_res = cloud_con.execute(
            text("""
                SELECT 
                    COALESCE(SUM(CASE WHEN transaction_type = 'deposit' THEN amount ELSE 0 END), 0) - 
                    COALESCE(SUM(CASE WHEN transaction_type = 'withdrawal' THEN amount ELSE 0 END), 0) as net_invested
                FROM cash_transactions 
                WHERE portfolio_id = :portfolio_id
            """), 
            {"portfolio_id": portfolio_id}
        ).fetchone()

    net_invested = float(cash_stats_res[0]) if cash_stats_res and cash_stats_res[0] is not None else 0.0
    total_profit_cash = p_value - net_invested
    profit_pct = (total_profit_cash / net_invested * 100) if net_invested > 0 else 0.0

    # ==========================================
    # STEP 3: USER INTERFACE & CSS STYLING
    # ==========================================
    dashboard_sidebar() # Render navigation structure panel

    st.markdown(
        """
        <style>
        /* =========================================
           COMPACT METRIC CARDS
        ========================================= */
        div[data-testid="stMetric"] {
            background: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 10px !important;
            padding: 8px 14px !important;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02) !important;
        }

        div[data-testid="stMetric"] label [data-testid="stMetricLabel"] {
            font-size: 0.8rem !important;
            color: #64748B !important;
            font-weight: 500 !important;
        }

        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.4rem !important;
            font-weight: 700 !important;
            letter-spacing: -0.5px !important;
            line-height: 1.2 !important;
        }

        div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
            font-size: 0.75rem !important;
        }

        /* =========================================
           HEADER / TIMELINE FIX
        ========================================= */
        .timeline-wrapper {
            width: 200%;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        .timeline-card {
            background: #E0F2FE;
            border: 1px solid #BAE6FD;
            border-radius: 10px;
            padding: 120px 160px;
            display: inline-flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-width: 170px;
            max-width: 320px;
            box-sizing: border-box;
        }

        .timeline-title {
            font-size: 11px;
            color: #0369A1;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            text-align: center;
            line-height: 1;
        }

        .timeline-date {
            font-size: 15px;
            color: #0C4A6E;
            font-weight: 700;
            margin-top: 6px;
            text-align: center;
            direction: ltr;
            line-height: 1.2;
        }

        /* =========================================
           BUTTONS & POPOVERS
        ========================================= */
        div[data-testid="stForm"] button[kind="primaryFormSubmit"] {
            transition: all 0.2s ease-in-out !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            padding: 0.35rem 0.75rem !important;
            font-size: 13px !important;
        }

        div[data-testid="stPopover"] 
        div[data-testid="stForm"]:has(input[value="Manual Cash Deposit"]) button {
            background-color: #22C55E !important;
            color: white !important;
            border-color: #22C55E !important;
        }

        div[data-testid="stPopover"] 
        div[data-testid="stForm"]:has(input[value="Manual Cash Deposit"]) button:hover {
            background-color: #16A34A !important;
            border-color: #16A34A !important;
        }

        div[data-testid="stPopover"] 
        div[data-testid="stForm"]:has(input[value="Manual Cash Withdrawal"]) button {
            background-color: #EF4444 !important;
            color: white !important;
            border-color: #EF4444 !important;
        }

        div[data-testid="stPopover"] 
        div[data-testid="stForm"]:has(input[value="Manual Cash Withdrawal"]) button:hover {
            background-color: #DC2626 !important;
            border-color: #DC2626 !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Dynamic Dashboard Header Layout Render Sequence
    header_col1, header_col2 , header_col3 = st.columns([2, 3 , 1.6])
    with header_col1:
        st.markdown(f"<h1 style='margin:0; padding:0; color:#1E293B;'>📊 {p_name}</h1>", unsafe_allow_html=True)
    with header_col2:
        st.markdown(
            f"""
            <div style="display: flex; justify-content: center; align-items: center; width: 80%;">
                <div style='
                    background: #E0F2FE; 
                    border: 1px solid #BAE6FD; 
                    border-radius: 8px; 
                    padding: 12px 8px; 
                    text-align: center;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    width: 480px;
                '>
                    <span style='
                        font-size: 18px; 
                        color: #0369A1; 
                        font-weight: bold; 
                        display: block; 
                        text-transform: uppercase; 
                        letter-spacing: 0.5px;
                        text-align: center;
                        width: 100%;
                    '>Engine Timeline</span>
                    <span style='
                        font-size: 16px; 
                        color: #0C4A6E; 
                        font-weight: bold; 
                        display: block; 
                        margin-top: 2px;
                        text-align: center;
                        direction: ltr;
                        width: 100%;
                    '>⏳ {st.session_state.current_sim_date_display}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with header_col3:
        st.write("to be filled later with a task progress to teach the users")

    st.write("") # Layout spacer
    
    # Financial KPI Metrics Block Row Setup
    m_col1, m_col2, m_col3 = st.columns(3)
    
    cash_ratio = (p_cash / p_value * 100) if p_value > 0 else 0
    profit_color = "green" if total_profit_cash >= 0 else "red"
    prefix = "+" if total_profit_cash >= 0 else ""

    with m_col1:
        st.metric("Total Portfolio Value", f"${p_value:,.2f}")
    with m_col2:
        st.metric(
            label="Available Cash Allocation", 
            value=f"${p_cash:,.2f}", 
            delta=f"{cash_ratio:.1f}% of total net",
            delta_color="blue",
            delta_arrow="off"
        )
    with m_col3:
        st.metric(
            label="Absolute Net Return", 
            value=f"${total_profit_cash:,.2f}", 
            delta=f"{prefix}{profit_pct:.1f}% Total ROI",
            delta_color=profit_color
        )

    st.write("---")

    # ==========================================
    # STEP 4: QUICK ACTIONS HUD BAR (Single Popover Architecture)
    # ==========================================
    col1 , col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.markdown("<p style='font-size:12px; font-weight:bold; color:#64748B; text-transform:uppercase; margin-bottom:10px;'>⚡ Portfolio Capital Control</p>", unsafe_allow_html=True)
    
    # Initialize a global anti-spam timestamp tracker inside state storage
    if "last_transaction_time" not in st.session_state:
        st.session_state.last_transaction_time = 0.0

    v_key = st.session_state.cash_op_version
    with col2:
        # Single master popover entry point to clear main dashboard space
        with st.popover("💰 Deposit/Withdraw", key=f"master_capital_pop_v{v_key}", use_container_width=False):
            st.markdown("### 🛠️ Strategy Capital Operations")
            st.caption("Execute safe fluid balance adjustments for this active strategy context frame.")
            
            # Dynamic transaction operation split selector
            tx_mode = st.segmented_control(
                "Select Operation Type",
                options=["Deposit", "Withdraw"],
                default="Deposit",
                key=f"tx_mode_selector_v{v_key}",
                label_visibility="collapsed"
            )

            # Pre-calculating UI states, colors, and boundary limits based on selected mode
            if tx_mode == "Deposit":
                mode_emoji = "📥"
                mode_title = "Deposit Funds"
                mode_color = "#10B981"
                submit_label = "Confirm Inbound Deposit"
                default_val = 1000.0
                min_val = 1.0
                max_val = None
                step_val = 100.0
                is_disabled = False
                tx_type = "deposit"
                memo_default = "Manual Cash Deposit"
            else:
                mode_emoji = "📤"
                mode_title = "Withdraw Funds"
                mode_color = "#EF4444"
                submit_label = "Confirm Outbound Withdrawal"
                has_cash = p_cash >= 1
                default_val = float(min(1000, int(p_cash))) if has_cash else 1.0
                min_val = 1.0
                max_val = float(p_cash) if has_cash else 1.0
                step_val = 100.0
                is_disabled = not has_cash
                tx_type = "withdrawal"
                memo_default = "Manual Cash Withdrawal"

            # High-visibility visual context header using the calculated mode color
            st.markdown(
                f"""
                <div style='padding: 10px; border-left: 4px solid {mode_color}; background: rgba(255,255,255,0.02); border-radius: 4px; margin-bottom: 15px;'>
                    <h4 style='margin: 0; color: {mode_color};'>{mode_emoji} {mode_title}</h4>
                    <p style='margin: 4px 0 0 0; font-size: 12px; color: #94A3B8;'>Executing asset allocation changes inside this portfolio frame context.</p>
                </div>
                """, 
                unsafe_allow_html=True
            )

            # Unified transactional submission block form entry
            with st.form(f"unified_capital_form_v{v_key}", clear_on_submit=True):
                amount = st.number_input(
                    "Amount ($)", 
                    min_value=min_val, 
                    max_value=max_val,
                    value=default_val, 
                    step=step_val,
                    disabled=is_disabled,
                    key=f"dynamic_amount_input_v{v_key}"
                )
                
                note = st.text_input(
                    "Memo/Reference", 
                    value=memo_default, 
                    key=f"dynamic_note_input_v{v_key}"
                )
                
                if st.form_submit_button(submit_label, use_container_width=True, disabled=is_disabled):
                    current_click_time = time.time()
                    time_delta = current_click_time - st.session_state.last_transaction_time
                    
                    # Safety Layer 1: Anti-spam double click cooldown engine mitigation
                    if time_delta < 5.0:
                        remaining_time = 5.0 - time_delta
                        countdown_text = st.empty()
                        progress_bar = st.progress(0.0)
                        
                        while remaining_time > 0:
                            countdown_text.warning(f"⏳ Action blocked to prevent duplicate submission. Cooling down: {remaining_time:.1f}s")
                            progress_percent = min(max(remaining_time / 5.0, 0.0), 1.0)
                            progress_bar.progress(progress_percent)
                            time.sleep(0.1)
                            remaining_time -= 0.1
                        
                        countdown_text.empty()
                        progress_bar.empty()
                    
                    # Safety Layer 2: Hard cash balance boundary enforcement
                    elif tx_type == "withdrawal" and amount > p_cash:
                        st.error(f"🛑 Insufficient funds! You requested ${amount:,.2f} but only have ${p_cash:,.2f} available.")
                    
                    # Safety Layer 3: Execute ledger entry directly inside cloud engine context
                    else:
                        st.session_state.last_transaction_time = current_click_time
                        with cloud_engine.connect() as tx_con:
                            # Direct transaction proxy deployment sequence logic
                            success, message = execute_cash_transaction(tx_con, portfolio_id, amount, tx_type, sim_date, note)
                        
                        if success:
                            st.session_state.cash_op_version += 1
                            st.toast(f"{mode_emoji} Processed ${amount:,.2f} successfully!")
                            st.rerun()
                        else:
                            st.error(message)
                            
    with col3:
        with st.popover("📜 Portfolio Cash History", use_container_width=True):
            with cloud_engine.connect() as hist_con:
                df = get_portfolio_cash_history(hist_con, portfolio_id, sim_date)

            if df.empty:
                st.info("No cash history available.")
            else:
                types = ["All"] + sorted(df["type"].dropna().unique().tolist())
                selected_type = st.selectbox(
                    "Filter by type",
                    types,
                    index=0,
                    key="cash_history_filter"
                )

                filtered_df = df.copy()
                if selected_type != "All":
                    filtered_df = filtered_df[filtered_df["type"] == selected_type]

                display_df = filtered_df.copy()
                display_df["timestamp"] = pd.to_datetime(display_df["timestamp"]).dt.strftime("%Y-%m-%d")
                display_df = display_df.sort_values("timestamp", ascending=False)

                display_df = display_df.rename(columns={
                    "timestamp": "Date",
                    "amount": "Amount",
                    "type": "Type",
                    "reference": "Reference"
                })
                display_df["Amount"] = pd.to_numeric(display_df["Amount"], errors="coerce").fillna(0).round(2)

                def highlight_type(row):
                    tx_type_str = str(row["Type"]).lower()
                    amount_val = float(row["Amount"])
                    if tx_type_str == "dividend":
                        return ["background-color: rgba(34,197,94,0.12); color:#166534; font-weight:600;"] * len(row)
                    elif amount_val > 0:
                        return ["background-color: rgba(59,130,246,0.10); color:#1D4ED8;"] * len(row)
                    elif amount_val < 0:
                        return ["background-color: rgba(239,68,68,0.10); color:#991B1B;"] * len(row)
                    return [""] * len(row)

                styled_df = (
                    display_df.style
                    .apply(highlight_type, axis=1)
                    .format({"Amount": "{:,.2f}"})
                )
                
                st.dataframe(
                    styled_df,
                    use_container_width=True,
                    hide_index=True
                )
    
    st.write("---")

    # ==========================================
    # STEP 5: SECURITIES HOLDINGS LEDGER MATRIX
    # ==========================================
    st.markdown("<p style='font-size:12px; font-weight:bold; color:#64748B; text-transform:uppercase; margin-bottom:5px;'>📊 Strategy Asset Allocation Ledger</p>", unsafe_allow_html=True)
    
    with cloud_engine.connect() as holdings_con:
        render_holdings_table(holdings_con, portfolio_id, sim_date)

    
    
def dashboard_sidebar():
    with st.sidebar:
        # --- INJECTING ADVANCED UX & GLASSMORPHISM SIDEBAR STYLES ---
        st.markdown(
            """
            <style>
            /* --- REMOVE SIDEBAR COLLAPSE BUTTON & TOP PADDING --- */
            /* This completely hides the toggle arrow button */
            [data-testid="stSidebarCollapseButton"] {
                display: none !important;
            }
            
            /* Forces all sidebar content to the absolute top edge */
            [data-testid="stSidebarUserContent"] {
                padding-top: 0.2rem !important;
            }

            /* Wipes out hidden default padding gaps on the first structural inner container */
            [data-testid="stSidebarUserContent"] > div:first-child {
                padding-top: 0px !important;
                margin-top: 0px !important;
            }
            
            /* Sidebar Container background adjustment */
            [data-testid="stSidebar"] {
                background-color: #1E293B !important; /* Deep dark Slate for premium contrast */
                color: #F8FAFC !important;
            }
            
            /* Typography Tweaks for Sidebar Headers */
            [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p {
                color: #F8FAFC !important;
                font-weight: 600 !important;
            }
            
            /* Glassmorphic Portfolio Meta Summary Card */
            .sidebar-meta-card {
                background: rgba(255, 255, 255, 0.05);
                backdrop-filter: blur(8px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 12px;
                margin-bottom: 10px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            
            /* FORCED GLOBAL BASE STYLE FOR ALL SIDEBAR BUTTONS (Fixes Time Machine & Exit layout) */
            [data-testid="stSidebar"] button {
                border-radius: 10px !important;
                border: 1px solid rgba(255, 255, 255, 0.15) !important;
                background-color: rgba(255, 255, 255, 0.04) !important;
                color: #E2E8F0 !important; /* Forces high-contrast text visibility */
                transition: all 0.2s ease-in-out !important;
                font-size: 13px !important;
                font-weight: 500 !important;
                padding: 0.4rem 0.8rem !important;
            }
            
            /* TARGETED HOVER STATE FOR ALL BUTTONS (Time Machine, Navigation, Exit) */
            [data-testid="stSidebar"] button:hover {
                background-color: rgba(56, 189, 248, 0.2) !important; /* Soft Electric Blue highlight */
                border-color: #38BDF8 !important;
                color: #38BDF8 !important;
                transform: translateY(-1px);
            }
            
            /* STRICT OVERRIDE FOR THE ACTIVE/CURRENT PAGE NAVIGATION BUTTON */
            [data-testid="stSidebar"] div.element-container:has(button[id^="active_nav_"]) button {
                background-color: #38BDF8 !important; /* Bright Cyan fill for active indicator */
                color: #0F172A !important; /* Deep dark slate text for perfect reading contrast */
                border-color: #38BDF8 !important;
                font-weight: 600 !important;
            }

            [data-testid="stSidebar"] div.element-container:has(button[id^="active_nav_"]) button:hover {
                background-color: #7DD3FC !important;
                color: #0F172A !important;
                border-color: #7DD3FC !important;
            }
            
            /* Minimalist Date Picker Input styling inside Sidebar */
            [data-testid="stSidebar"] div[data-component="stDateInput"] {
                background: transparent !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        # --- App Branding Header ---
        # Updated with an ultra-bright neon cyan and clean text-shadow definition
        st.markdown(
            """
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="color: #00F0FF; margin: 0; letter-spacing: 1px; text-shadow: 0 2px 4px rgba(0, 240, 255, 0.2);">🛡️ STRATIFY</h2>
                <span style="font-size: 10px; color: #94A3B8; text-transform: uppercase;">Simulation Engine v1.0</span>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # --- Fetch Context Data ---
        p_name = st.session_state.get('current_portfolio_name', 'Unknown')
        p_id = st.session_state.get('current_portfolio_id')
        fmt_start = st.session_state.get('current_portfolio_starting_at')
        
        fmt_start_str = fmt_start.strftime('%d/%m/%Y') if hasattr(fmt_start, 'strftime') else str(fmt_start)
        fmt_sim = st.session_state.get('current_sim_date_display', 'Unknown')

        # --- Portfolio Meta Custom Card Component ---
        st.markdown(
            f"""
            <div class="sidebar-meta-card">
                <div style="font-size: 11px; color: #94A3B8; text-transform: uppercase; font-weight: bold; margin-bottom: 4px;">Active Portfolio</div>
                <div style="font-size: 16px; font-weight: bold; color: #F8FAFC; margin-bottom: 8px;">📁 {p_name}</div>
                <div style="display: flex; justify-content: space-between; font-size: 11px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 6px;">
                    <span style="color: #94A3B8;">📅 Inception:</span>
                    <span style="color: #E2E8F0; font-weight: 500;">{fmt_start_str}</span>
                </div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # Display Simulator Clock compactly as a distinct sub-badge
        st.markdown(
            f"""
            <div style="background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 8px; padding: 8px 12px; text-align: center; margin-bottom: 15px;">
                <div style="font-size: 10px; color: #38BDF8; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">⏳ Simulation Timeclock</div>
                <div style="font-size: 14px; font-weight: bold; color: #F8FAFC; margin-top: 2px;">{fmt_sim}</div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # ==========================================
        # SECTION 1: NAVIGATION
        # ==========================================
        st.markdown("<p style='font-size: 11px; color:#64748B; font-weight:bold; text-transform:uppercase; margin-bottom:8px;'>🧭 Workspace Navigation</p>", unsafe_allow_html=True)
        
        nav_pages = {
            "🏠 Dashboard Home": "dashboard_home",
            "📈 Performance Analysis": "portfolio_performance_analysis",
            "🛠️ Strategy Builder": "strategy_builder",
            "🔍 Asset Explorer": "asset_explorer"
        }
        
        for label, page_val in nav_pages.items():
            is_current = st.session_state.get('page') == page_val
            # Setting a unique dynamic key prefix so the CSS can securely detect the active element
            btn_key = f"active_nav_{page_val}" if is_current else f"nav_{page_val}"
            
            if st.button(label, use_container_width=True, key=btn_key):
                st.session_state.page = page_val
                st.rerun()
        
        st.write("") 
        st.divider()
        
        # ==========================================
        # SECTION 2: TIME MACHINE
        # ==========================================
        st.markdown("<p style='font-size: 11px; color:#64748B; font-weight:bold; text-transform:uppercase; margin-bottom:8px;'>⏳ Backtest Time Control</p>", unsafe_allow_html=True)
        
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        yesterday_dt = datetime.datetime.combine(yesterday.date(), datetime.time.min)
        current_dt = st.session_state.get('current_sim_date')
        
        def safe_jump(new_d):
            target = min(new_d, yesterday_dt)
            if handle_time_jump(target, p_id):
                st.rerun()

        # Step Increments Row
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("＋ 1D", use_container_width=True, help="Advance 1 day", key="tm_jump_1d"):
                safe_jump(current_dt + datetime.timedelta(days=1))
                st.rerun()

        with col2:
            if st.button("＋ 1M", use_container_width=True, help="Advance 30 days", key="tm_jump_1m"):
                safe_jump(current_dt + datetime.timedelta(days=30))
                st.rerun()

        with col3:
            if st.button("＋ 1Y", use_container_width=True, help="Advance 365 days", key="tm_jump_1y"):
                safe_jump(current_dt + datetime.timedelta(days=365))
                st.rerun()

        # Precision Custom Date Input Jump
        min_d = current_dt.date() if hasattr(current_dt, 'date') else current_dt
        
        # We pass value=None so it doesn't pre-populate with a date, and set a clear label
        picked_date = st.date_input(
            "📅 choose a date to jump to", 
            value=None, 
            min_value=min_d, 
            max_value=yesterday.date(), 
            key="sb_date_picker",
            label_visibility="visible" # Changed to visible to show the clear call-to-action
        )
        
        # Only process time travel if the user has actually interacted and picked a date
        if picked_date is not None:
            picked_dt = datetime.datetime.combine(picked_date, datetime.time.min)
            
            if picked_dt > current_dt:
                if st.button("🚀 Execute Time Travel", use_container_width=True, key="tm_execute_travel"):
                    if handle_time_jump(picked_dt, p_id):
                        st.rerun()

        # Spacer pushing exit action gracefully to the bottom layout boundary
        st.markdown("<div style='margin-top: 60px;'></div>", unsafe_allow_html=True)
        st.divider()
        
        # ==========================================
        # SECTION 3: SYSTEM CONTEXT SAFE RESET
        # ==========================================
        if st.button("🔙 Unload & Exit Portfolio", use_container_width=True, help="Safely discard session context state and go home", key="sys_exit_portfolio"):
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
    
    # Initialize asset variable to avoid UnboundLocalError
    asset = None 
    
    # Fetch the dynamically resolved environment-agnostic path from session state
    # Fallback to a locally defined variable if main.py hasn't set it yet
    current_db_path = st.session_state.get('DB_PATH')
    
    # Track path mutations or initial connections to enforce state consistency across deployments
    if 'con' not in st.session_state:
        st.session_state.con = duckdb.connect(current_db_path)
    elif st.session_state.get('last_db_path') != current_db_path:
        try:
            st.session_state.con.close()
        except:
            pass
        st.session_state.con = duckdb.connect(current_db_path)
        
    # Keep track of the active connection configuration path
    st.session_state.last_db_path = current_db_path
    con = st.session_state.con
    
    # Initialize cloud SQLAlchemy engine connection if not already exists for dual-write/cloud reading
    if 'supabase_engine' not in st.session_state:
        # st.session_state.supabase_engine = create_engine(CLOUD_DB_URL)
        pass # Replace with your actual global engine initialization
    
    # 1. Asset search component
    asset_search_component(con)

    # 2. Load asset data only if a ticker is selected
    selected_ticker = st.session_state.get('selected_ticker_for_analysis')
    
    if selected_ticker:
        # Check if the application is running in cloud mode or local development
        # This parameter determines if we pull from the cloud storage bucket or local tables
        use_cloud_storage = st.session_state.get('use_cloud', False)
        
        # get_asset_snapshot must handle SQLAlchemy text(:param) for cloud and con.execute(?) for local
        asset = get_asset_snapshot(
            con, 
            selected_ticker, 
            st.session_state.current_sim_date,
            use_cloud=use_cloud_storage
        )
        
        # Ensure asset exists before rendering UI
        if asset:
            col_info, col_actions = st.columns([2, 1])
            
            with col_info:
                display_asset_card(asset)
            
            with col_actions:
                if asset['current_price']:
                    # show_buy_component will execute the dual-write logic (Cloud + Local Mirror)
                    show_buy_component(
                        selected_ticker, 
                        asset['current_price']
                    )
                    
                    if st.button(
                        f"🔍 Analyze {asset['ticker']}", 
                        key=f"btn1_{asset['ticker']}", 
                        use_container_width=True
                    ): 
                        st.session_state.last_inspected_ticker = asset['ticker']
                        st.rerun()
            
            # ----------------------------------------------------
            # Existing analysis dialog logic (unchanged)
            # ----------------------------------------------------
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