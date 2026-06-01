import streamlit as st
from .db_manager import *
from .users_managment import *
from .portfolio_managment import *
from .UI_components import *
from .trading_logic import *





def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()
    


def show_login_page():
    # Check if redirected from a successful registration - display green success message
    if st.session_state.get('reg_success'):
        st.success("Registration successful! Please login with your new credentials.")
        # Reset the flag so the message doesn't persist on page refresh
        st.session_state.reg_success = False

    # Centered and styled Title using custom HTML/CSS
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #2E4057; font-family: 'Helvetica Neue', sans-serif;">Sign In to Stratify</h1>
            <p style="color: #7F8C8D; font-size: 16px;">Gamify your financial strategy</p>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    # Use prefilled email from registration if available
    prefilled_email = st.session_state.get('prefilled_email', "")
    
    # Create a layout with 3 columns to center the login container (ratio: 1:2:1)
    left_co, main_co, right_co = st.columns([1, 2, 1])
    
    with main_co:
        # Styled container using Streamlit's native card aesthetic
        with st.container(border=True):
            with st.form("login_form", clear_on_submit=False):
                st.markdown("<h4 style='color: #34495E;'>Credentials</h4>", unsafe_allow_html=True)
                
                user_email = st.text_input("Email", value=prefilled_email, placeholder="example@mail.com")
                user_password = st.text_input("Password", type="password", placeholder="••••••••")
            
                # Custom CSS inject to make the login button full-width and styled
                st.markdown(
                    """
                    <style>
                    div[data-testid="stFormSubmitButton"] > button {
                        width: 100%;
                        background-color: #4CAF50;
                        color: white;
                        border-radius: 5px;
                        border: none;
                        padding: 0.5rem 1rem;
                        font-weight: bold;
                    }
                    div[data-testid="stFormSubmitButton"] > button:hover {
                        background-color: #45a049;
                        border: none;
                        color: white;
                    }
                    </style>
                    """, 
                    unsafe_allow_html=True
                )
                
                submit_button_loggin = st.form_submit_button("Login")
                
                if submit_button_loggin:
                    if not user_email or not user_password:
                        st.warning("Please fill in all fields.")
                    else:
                        user_id, first_name = loggin_func(user_email, user_password)
                    
                        if user_id is not None:
                            # Save credentials to Session State
                            st.session_state.user_id = user_id
                            st.session_state.first_name = first_name
                            st.session_state.logged_in = True
                            
                            # Clean up temporary prefilled email after successful login
                            if 'prefilled_email' in st.session_state:
                                del st.session_state.prefilled_email
                            
                            st.success("Logged in successfully!")
                            go_to("home_page")
                        else:
                            st.error("Login failed. Check your details.")

        # Secondary actions (Registration and Forgot Password) positioned cleanly below the form
        st.write("") # Spacer
        col_reg, col_forgot = st.columns(2)
        
        with col_reg:
            if st.button("New here? Register", use_container_width=True):
                go_to("regestration_page")
                
        with col_forgot:
            if st.button("Forgot password?", use_container_width=True):
                go_to("password_recovery_page")
        
  
        


def show_registration_page():
    # Centered and styled Title using custom HTML/CSS
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #2E4057; font-family: 'Helvetica Neue', sans-serif;">Create Your Stratify Account</h1>
            <p style="color: #7F8C8D; font-size: 16px;">Join us and start gamifying your financial strategy</p>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    # Create a layout with 3 columns to center the registration container (ratio: 1:2:1)
    left_co, main_co, right_co = st.columns([0.5, 2, 0.5])
    
    with main_co:
        # Styled container for the registration form
        with st.container(border=True):
            with st.form("registration_form", clear_on_submit=False):
                st.markdown("<h4 style='color: #34495E;'>Personal Information</h4>", unsafe_allow_html=True)
                
                # Names section distributed into 3 columns
                col_first, col_middle, col_last = st.columns(3)
                with col_first:
                    first_name = st.text_input("First name *", placeholder="John")
                with col_middle:
                    middle_name = st.text_input("Middle name", placeholder="Snow")  # Swapped the placeholder slightly for cleaner look
                with col_last:
                    last_name = st.text_input("Last name *", placeholder="Stark")
                
                # Account Details section
                st.markdown("<hr style='margin: 15px 0; border-style: dashed;'>", unsafe_allow_html=True)
                user_email = st.text_input("Email Address *", placeholder="example@mail.com")
                
                # Passwords section distributed into 2 columns
                col_pass, col_confirm = st.columns(2)
                with col_pass:
                    user_password = st.text_input("Password *", type="password", placeholder="••••••••")
                with col_confirm:
                    user_password_confirm = st.text_input("Confirm password *", type="password", placeholder="••••••••")
                
                # Date of Birth
                today = datetime.date.today()
                hundred_years_ago = today.replace(year=today.year - 100)
                date_of_birth = st.date_input(
                    "Date of Birth",
                    value=datetime.date(2000, 1, 1),
                    min_value=hundred_years_ago,    
                    max_value=today,                
                    help="Click to open the calendar and select your birth date"
                )
                
                st.markdown("<p style='color: #7F8C8D; font-size: 12px;'>* Indicates mandatory fields</p>", unsafe_allow_html=True)
                
                # Custom CSS inject to make the register button full-width and styled green
                st.markdown(
                    """
                    <style>
                    div[data-testid="stFormSubmitButton"] > button {
                        width: 100%;
                        background-color: #4CAF50;
                        color: white;
                        border-radius: 5px;
                        border: none;
                        padding: 0.5rem 1rem;
                        font-weight: bold;
                    }
                    div[data-testid="stFormSubmitButton"] > button:hover {
                        background-color: #45a049;
                        border: none;
                        color: white;
                    }
                    </style>
                    """, 
                    unsafe_allow_html=True
                )
                
                submit_button = st.form_submit_button("Register")

                # Form Validations
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

                    # Final Submission Process
                    if is_valid:
                        m_name = middle_name.strip() if middle_name.strip() else None
                        
                        success = registration_func(
                            user_email, first_name, m_name, last_name, date_of_birth, user_password, user_password_confirm
                        )
                        
                        if success:
                            # State management for redirection and pre-filling the login form
                            st.session_state.reg_success = True
                            st.session_state.prefilled_email = user_email
                            
                            st.success("Registration completed! Redirecting to login...")
                            go_to("login_page")
                        else:
                            st.error("Something went wrong during registration.")

        # Back to Login secondary action below the main container
        st.write("") # Spacer
        if st.button("← Already have an account? Login", use_container_width=True):
            go_to("login_page")
        
 

def show_password_recovery_page():
    # Centered and styled Title using custom HTML/CSS
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #2E4057; font-family: 'Helvetica Neue', sans-serif;">Reset Your Password</h1>
            <p style="color: #7F8C8D; font-size: 16px;">We'll help you get back into Stratify</p>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    # Create a layout with 3 columns to center the recovery container (ratio: 1:2:1)
    left_co, main_co, right_co = st.columns([1, 2, 1])
    
    with main_co:
        # Styled container for the password recovery form
        with st.container(border=True):
            with st.form("password_recovery_form", clear_on_submit=False):
                st.markdown("<h4 style='color: #34495E;'>Account Recovery</h4>", unsafe_allow_html=True)
                
                email = st.text_input("Enter your registered email *", placeholder="example@mail.com")
                
                # Custom CSS inject to make the recovery button full-width and styled blue/steel
                st.markdown(
                    """
                    <style>
                    div[data-testid="stFormSubmitButton"] > button {
                        width: 100%;
                        background-color: #2E4057;
                        color: white;
                        border-radius: 5px;
                        border: none;
                        padding: 0.5rem 1rem;
                        font-weight: bold;
                    }
                    div[data-testid="stFormSubmitButton"] > button:hover {
                        background-color: #1F2D3E;
                        border: none;
                        color: white;
                    }
                    </style>
                    """, 
                    unsafe_allow_html=True
                )
                
                submit_button = st.form_submit_button("Recover Password")
        
                # Form Validation and Submission
                if submit_button:
                    if email.strip():
                        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                            st.error("Please enter a valid email address.")
                        elif get_data("SELECT 1 FROM users WHERE email = ? LIMIT 1", [email]).empty:
                            st.error("No account found with that email.")
                        # Placeholder for future logic
                        else:
                            st.info("Password recovery feature: Once the app is live, a reset link will be sent to this email.")
                    else:
                        st.warning("Please enter a valid email address.")
        
        # Back to Login secondary action positioned cleanly below the form container
        st.write("") # Spacer
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
                 """, [int(st.session_state.user_id)])
            
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
    # --- INITIALIZE STATE COUNTER FOR COMPONENT RESET ---
    # This prevents the creation popover from staying open post-rerun
    if "portfolio_create_version" not in st.session_state:
        st.session_state.portfolio_create_version = 0

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

        /* Glassmorphism Portfolio Cards */
        .portfolio-card {
            background: rgba(255, 255, 255, 0.4);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
            padding: 12px !important;
            margin-bottom: 15px;
        }

        /* Small Pill-shaped Action Buttons for Main Content */
        .stButton > button {
            border-radius: 20px !important;
            padding: 0.2rem 0.8rem !important;
            font-size: 11px !important;
            border: 1px solid #2E4057;
            background: transparent;
            color: #2E4057;
            transition: all 0.2s ease-in-out;
        }
        
        .stButton > button:hover {
            background: rgba(46, 64, 87, 0.1);
            color: #2E4057;
            border-color: #2E4057;
        }

        /* Clean styling for popovers inside the card grid */
        div[data-testid="stPopover"] > button {
            border-radius: 20px !important;
            padding: 0.2rem 0.8rem !important;
            font-size: 11px !important;
            background: transparent !important;
            color: #7F8C8D !important;
            border: 1px solid #E0E0E0 !important;
        }
        
        div[data-testid="stPopover"] > button:hover {
            border-color: #F44336 !important;
            color: #F44336 !important;
            background: rgba(244, 67, 54, 0.05) !important;
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

        /* --- TARGETED SIDEBAR NAVIGATION OVERRIDES --- */
        /* Forced base style for all navigation sidebar buttons */
        [data-testid="stSidebar"] button:not([key="sidebar_logout_small"]) {
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
        
        [data-testid="stSidebar"] button:not([key="sidebar_logout_small"]):hover {
            background-color: rgba(56, 189, 248, 0.2) !important; 
            border-color: #38BDF8 !important;
            color: #38BDF8 !important;
            transform: translateY(-1px);
        }

        /* --- CUSTOM CRIMSON LOGOUT CONTAINER TARGETING --- */
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
        
        .custom-logout-container button, 
        .custom-logout-container button p,
        .custom-logout-container button span {
            color: #EF4444 !important;
        }
        
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

    # ==========================================
    # SIDEBAR GENERATION & RENDER FRAME
    # ==========================================
    # --- App Branding Header ---
    st.sidebar.markdown(
        """
        <div style="text-align: center; margin-bottom: 20px;">
            <h2 style="color: #00F0FF; margin: 0; letter-spacing: 1px; text-shadow: 0 2px 4px rgba(0, 240, 255, 0.2);">🛡️ STRATIFY</h2>
            <span style="font-size: 10px; color: #94A3B8; text-transform: uppercase;">Simulation Engine v1.0</span>
        </div>
        """, 
        unsafe_allow_html=True
    )

    # --- Investor Profile Header Section ---
    first_name = st.session_state.get("first_name", "Investor")
    st.sidebar.markdown(
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
    
    st.sidebar.write("") # Micro-spacer
    
    # --- System Logout Trigger Action Wrapped in Custom Div Container ---
    st.sidebar.markdown('<div class="custom-logout-container">', unsafe_allow_html=True)
    if st.sidebar.button("Logout", key="sidebar_logout_small"):
        st.session_state.clear()  # Clear all memory frame cache states
        st.sidebar.rerun()  # Rerun the app context back to the authentication screen
    st.sidebar.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # MAIN SURFACE SURFACE: PORTFOLIOS GRID
    # ==========================================
    # --- Header ---
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 15px;">
            <h2 style="color: #2E4057; margin: 0;">💼 My Portfolios</h2>
        </div>
        """, 
        unsafe_allow_html=True
    )
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
        # Generate 2 columns layout for portfolio cards grid
        cols = st.columns(2)

        for index, row in user_portfolios.iterrows():
            p_id = row['portfolio_id']
            p_name = row['portfolio_name']
            
            with cols[index % 2]:
                # Custom Glass container wrapping each portfolio element
                with st.container():
                    st.markdown(f"<h4 style='color: #2E4057; margin-bottom: 8px;'>📁 {p_name}</h4>", unsafe_allow_html=True)

                    # Format dates safely
                    start_dt = row["starting_at"].strftime("%Y-%m-%d") if pd.notnull(row["starting_at"]) else "N/A"
                    curr_dt = row["current_sim_date"].strftime("%Y-%m-%d") if pd.notnull(row["current_sim_date"]) else "N/A"

                    # Calculate live portfolio value
                    try:
                        p_value = portfolio_value_calculator(p_id, row["current_sim_date"])
                        val_str = f"${p_value:,.2f}"
                    except Exception:
                        val_str = "Error calculating"

                    # Display portfolio details compactly with scaled typography for advanced readability
                    m_col1, m_col2, m_col3 = st.columns(3)
                    with m_col1:
                        st.markdown(f"<p style='font-size: 16px; margin:0; color:#7F8C8D;'>📅 Start<br><strong style='color:#2E4057; font-size: 18px;'>{start_dt}</strong></p>", unsafe_allow_html=True)
                    with m_col2:
                        st.markdown(f"<p style='font-size: 16px; margin:0; color:#7F8C8D;'>⏳ Current Sim<br><strong style='color:#2E4057; font-size: 18px;'>{curr_dt}</strong></p>", unsafe_allow_html=True)
                    with m_col3:
                        st.markdown(f"<p style='font-size: 16px; margin:0; color:#7F8C8D;'>💰 Net Value<br><strong style='color:#4CAF50; font-size: 18px;'>{val_str}</strong></p>", unsafe_allow_html=True)
                    
                    st.write("") # Tiny vertical spacer inside the card
                    
                    # Inside-card action row split into 2 compact halves (Enter / Delete)
                    btn_col_left, btn_col_right = st.columns([2, 1])
                    
                    with btn_col_left:
                        if st.button("Enter Portfolio", key=f"enter_{p_id}", use_container_width=True):
                            st.session_state.current_portfolio_id = p_id
                            st.session_state.current_portfolio_name = p_name
                            st.session_state.current_sim_date = row["current_sim_date"]
                            st.session_state.current_portfolio_starting_at = row["starting_at"]
                            go_to("dashboard_home")
                            
                    with btn_col_right:
                        # FIX 1: Explicit key bound to p_id forces delete popover to auto-close on deletion
                        with st.popover("🗑️ Delete", key=f"popover_del_{p_id}", use_container_width=True):
                            st.markdown("<p style='font-size: 11px; color:#F44336; font-weight:bold;'>⚠️ Permanent Action</p>", unsafe_allow_html=True)
                            
                            if st.button("Confirm", key=f"delete_{p_id}", use_container_width=True):
                                success, message = delete_portfolio(p_id)
                                if success:
                                    st.toast(f"🗑️ {p_name} deleted successfully!")
                                    st.rerun()
                                else:
                                    st.error(message)

    st.write("---")

    # --- Footer Action Bar (Create New / Return Home) ---
    col_a, col_b = st.columns(2)

    with col_b:
        # FIX 2: Dynamic state version key to automatically close the creation popover form after submit
        create_popover_key = f"create_portfolio_popover_v{st.session_state.portfolio_create_version}"
        
        with st.popover("➕ Create New Portfolio", key=create_popover_key, use_container_width=True):
            st.markdown(
                """
                <div style="text-align: center; margin-bottom: 15px;">
                    <h4 style="color: #2E4057; margin: 0;">🚀 New Strategy Setup</h4>
                    <p style="font-size: 11px; color: #7F8C8D; margin: 5px 0 0 0;">Configure your backtesting parameters below</p>
                </div>
                """, 
                unsafe_allow_html=True
            )
            
            with st.form("create_portfolio_form", clear_on_submit=True):
                # Clean split columns for balanced data layout
                form_col1, form_col2 = st.columns(2)
                
                with form_col1:
                    new_name = st.text_input("🏷️ Portfolio Name", placeholder="e.g., Aggressive Growth").strip()
                    
                with form_col2:
                    min_date = datetime.date(2000, 2, 2)
                    yesterday = datetime.date.today() - datetime.timedelta(days=1)

                    start_date = st.date_input(
                        "📅 Simulation Start Date",
                        value=yesterday,
                        min_value=min_date,
                        max_value=yesterday,
                        help="Select a historical benchmark date starting from Feb 2nd, 2000."
                    )
                    
                st.write("") # Micro spacer
                
                # Center the submit option
                submit_col_left, submit_btn_col, submit_col_right = st.columns([1, 2, 1])
                
                with submit_btn_col:
                    submit_clicked = st.form_submit_button("🔨 Create Strategy Now", use_container_width=True)
                    
                if submit_clicked:
                    if not new_name:
                        st.error("Portfolio name is required")
                    else:
                        success, message = create_portfolio(user_id, new_name, start_date)
                        if success:
                            # Advanced state mutation to force re-render components as closed
                            st.session_state.portfolio_create_version += 1
                            st.toast(f"🚀 Portfolio '{new_name}' created successfully!")
                            st.rerun()
                        else:
                            st.error(message)

    with col_a:
        if st.button("🏠 Back to Home", use_container_width=True):
            go_to("home_page")          
            

def show_dashboard_home():
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

    # Maintain global system database state context safely
    if 'con' not in st.session_state:
        st.session_state.con = duckdb.connect(DB_PATH)
    
    con = st.session_state.con

    # Initialize a clean component reset key versioning tracker for forms
    if "cash_op_version" not in st.session_state:
        st.session_state.cash_op_version = 0

    # ==========================================
    # STEP 2: DATA EXTRACTION & CALCULATIONS
    # ==========================================
    portfolio_data = get_data("""
        SELECT portfolio_name, available_cash, created_at, starting_at, current_sim_date 
        FROM portfolios 
        WHERE portfolio_id = ? AND user_id = ?
    """, [portfolio_id, user_id])

    if portfolio_data.empty:
        st.error("⚠️ Portfolio not found or access denied.")
        if st.button("Return to My Portfolios", key="err_return_portfolios"):
            go_to("portfolios")
        return

    # Extract raw record variables
    p_row = portfolio_data.iloc[0]
    p_name = p_row['portfolio_name']
    p_cash = p_row['available_cash']
    sim_date = p_row['current_sim_date']
    
    # Calculate global real-time metric assets value valuation
    p_value = portfolio_value_calculator(portfolio_id, sim_date, con)
    
    # Commit synchronized application memory context updates
    st.session_state.current_available_cash = p_cash
    st.session_state.current_portfolio_name = p_name
    st.session_state.current_sim_date = sim_date
    st.session_state.current_sim_date_display = sim_date.strftime('%d/%m/%Y')

    # Extract net historical deposit transaction flows
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

    # Dynamic Dashboard Header Layout
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
                width: 480px; /* Locked precise gadget width */
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
    
    # Financial KPI Metrics Block Row
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
    
    # Initialize a global anti-spam timestamp tracker
    if "last_transaction_time" not in st.session_state:
        st.session_state.last_transaction_time = 0.0

    v_key = st.session_state.cash_op_version
    with col2:
            # Single master popover entry point to clear main dashboard space
            with st.popover("💰 Deposit/Withdraw", key=f"master_capital_pop_v{v_key}", use_container_width=False):
                st.markdown("### 🛠️ Strategy Capital Operations")
                st.caption("Execute safe fluid balance adjustments for this active strategy context frame.")
                
                # ------------------------------------------
                # DYNAMIC TRANSACTION MODE SELECTOR
                # ------------------------------------------
                # ALL CODE FROM HERE DOWN MUST BE INDENTED UNDER THE POPOVER
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
                    mode_color = "#10B981" # Emerald Green
                    submit_label = "Confirm Inbound Deposit"
                    
                    # Kept as floats to prevent StreamlitMixedNumericTypesError
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
                    mode_color = "#EF4444" # Crimson Red
                    submit_label = "Confirm Outbound Withdrawal"
                    has_cash = p_cash >= 1
                    
                    # Kept as floats to prevent StreamlitMixedNumericTypesError
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

                # ------------------------------------------
                # UNIFIED DYNAMIC TRANSACTION FORM
                # ------------------------------------------
                with st.form(f"unified_capital_form_v{v_key}", clear_on_submit=True):
                    
                    # Context-aware number input enforcing live financial boundaries
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
                    
                    # Submission handling with strict runtime validations
                    if st.form_submit_button(submit_label, use_container_width=True, disabled=is_disabled):
                        current_click_time = time.time()
                        time_delta = current_click_time - st.session_state.last_transaction_time
                        
                        # Safety Layer 1: Anti-spam double click mitigation UI cooldown
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
                        
                        # Safety Layer 2: Hard cash boundary enforcement for withdrawals
                        elif tx_type == "withdrawal" and amount > p_cash:
                            st.error(f"🛑 Insufficient funds! You requested ${amount:,.2f} but only have ${p_cash:,.2f} available.")
                        
                        # Safety Layer 3: Secure database write and execution block
                        else:
                            st.session_state.last_transaction_time = current_click_time
                            success, message = execute_cash_transaction(con, portfolio_id, amount, tx_type, sim_date, note)
                            
                            if success:
                                st.session_state.cash_op_version += 1
                                st.toast(f"{mode_emoji} Processed ${amount:,.2f} successfully!")
                                st.rerun()
                            else:
                                st.error(message)
                            
    with col3:
        

        with st.popover("📜 Portfolio Cash History", use_container_width=True , width="stretch"):

            df = get_portfolio_cash_history(con, portfolio_id, sim_date)

            if df.empty:
                st.info("No cash history available.")

            else:
                # =========================
                # FILTER SECTION
                # =========================
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

                # =========================
                # FORMAT FOR DISPLAY
                # =========================
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


                # =========================
                # SIMPLE VISUAL ENHANCEMENT (SAFE FOR STREAMLIT)
                # =========================
                def highlight_type(row):

                    tx_type = str(row["Type"]).lower()
                    amount = float(row["Amount"])

                    # Dividends → green
                    if tx_type == "dividend":
                        return [
                            "background-color: rgba(34,197,94,0.12); color:#166534; font-weight:600;"
                        ] * len(row)

                    # Money entering account → blue
                    elif amount > 0:
                        return [
                            "background-color: rgba(59,130,246,0.10); color:#1D4ED8;"
                        ] * len(row)

                    # Money leaving account → red
                    elif amount < 0:
                        return [
                            "background-color: rgba(239,68,68,0.10); color:#991B1B;"
                        ] * len(row)

                    return [""] * len(row)

                styled_df = (
                    display_df.style
                    .apply(highlight_type, axis=1)
                    .format({"Amount": "{:,.2f}"})
                )
                # =========================
                # RENDER
                # =========================
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
    
    render_holdings_table(con, portfolio_id, sim_date)
    
    
    
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
    
    # Initialize database connection if not already exists
    if 'con' not in st.session_state:
        st.session_state.con = duckdb.connect(DB_PATH)
    con = st.session_state.con
    
    # 1. Asset search component
    asset_search_component(con)

    # 2. Load asset data only if a ticker is selected
    selected_ticker = st.session_state.get('selected_ticker_for_analysis')
    
    if selected_ticker:
        asset = get_asset_snapshot(
            con, 
            selected_ticker, 
            st.session_state.current_sim_date
        )
        
        # Ensure asset exists before rendering UI
        if asset:
            col_info, col_actions = st.columns([2, 1])
            
            with col_info:
                display_asset_card(asset)
            
            with col_actions:
                if asset['current_price']:
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