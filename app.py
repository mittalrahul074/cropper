import os
import warnings
import streamlit as st
import logging

from auth import authenticate_user, logout_user, set_cookie, get_cookie,get_cookie_manager
from database import init_database, get_party, get_user_type
from product_lookup import render_product_lookup_panel
from label_image import render_label_stamper_panel

# -------------------------------------------------------------------
# SUPPRESS WARNINGS (DEPENDENCY NOISE)
# -------------------------------------------------------------------
# warnings.filterwarnings("ignore", message=".*st.cache.*deprecated.*")

# -------------------------------------------------------------------
# CONSTANTS
# -------------------------------------------------------------------
APP_TITLE = "Order Management System"
CSS_PATH = "assets/styles.css"

PAGE_DASHBOARD = "dashboard"
PAGE_ADMIN = "admin"
PAGE_PICKER = "picker"
PAGE_VALIDATOR = "validator"
PAGE_SEARCH = "search"
PAGE_RETURN_SCAN = "return_scan"
PAGE_ACCEPT_RETURNS = "accept_returns"
PAGE_CANCELLED_LIST = "cancelled_list"
PAGE_OUT_OF_STOCK_LIST = "out_of_stock_list"
PAGE_DELETE = "delete"
LOOKUP = "lookup"
LABEL_STAMPER = "label_stamper"

# User types (document these clearly)
USER_PICKER_ONLY = 1
USER_RETURNS_ACCESS = {2, 3, 4, 5}
#keep login feature off to allow any user and keep it on to restrict access to only those with login credentials
LOGIN_FEATURE = 1

# -------------------------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------------------------
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# -------------------------------------------------------------------
def init_session_state() -> None:
    defaults = {
        "authenticated": False,
        "user_role": None,
        "user_type": None,
        "party_filter": "Both",
        "page": PAGE_DASHBOARD,
        "db_initialized": False,
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

init_session_state()

# -------------------------------------------------------------------
# DATABASE INIT (ONCE)
# -------------------------------------------------------------------
if not st.session_state.db_initialized:
    init_database()
    st.session_state.db_initialized = True

# -------------------------------------------------------------------
# LOAD GLOBAL CSS
# -------------------------------------------------------------------
if os.path.exists(CSS_PATH):
    with open(CSS_PATH, "r", encoding="utf-8") as css_file:
        st.markdown(
            f"<style>{css_file.read()}</style>",
            unsafe_allow_html=True,
        )

# -------------------------------------------------------------------
# AUTH: AUTO LOGIN FROM COOKIE
# -------------------------------------------------------------------
def attempt_auto_login() -> None:
    print("Attempting auto-login from cookie...")
    if st.session_state.authenticated:
        print("User already authenticated, skipping auto-login.")
        return

    try:
        username = get_cookie("logged_user")
        if not username:
            print("No logged_user cookie found.")
            return

        st.session_state.authenticated = True
        st.session_state.user_role = username
        st.session_state.user_type = get_user_type(username)

        try:
            st.session_state.party_filter = get_party(username)
        except Exception:
            st.session_state.party_filter = "Both"

    except Exception as e:
        print(f"Auto-login error: {e}")

# -------------------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------------------
def render_login_sidebar() -> None:
    with st.sidebar:
        st.header("Login")

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            if not username or not password:
                st.error("Please enter both username and password")
                return

            if not authenticate_user(username, password):
                st.error("Invalid username or password")
                return

            # Login success

            if set_cookie("logged_user", username):
                manager = get_cookie_manager()

                st.write("COOKIE CONTROLLER:")
                st.write(manager.getAll())
                st.success("Logged in successfully")
            else:
                st.warning("Logged in, but persistent login could not be saved.")

            st.session_state.authenticated = True
            st.session_state.user_role = username
            st.session_state.user_type = get_user_type(username)

            try:
                st.session_state.party_filter = get_party(username)
            except Exception:
                st.session_state.party_filter = "Both"

            st.rerun()

def render_navigation_sidebar() -> None:
    with st.sidebar:
        if LOGIN_FEATURE:
            st.success(f"Logged in as {st.session_state.user_role}")
            st.markdown("---")

        # =========================
        # Navigation
        # =========================
        PAGES = {
            "Label Image Stamper": LABEL_STAMPER,
            "Analysis": LOOKUP,
        }

        if LOGIN_FEATURE:
            ROLE_ACCESS = {
                1: {"LOOKUP", "Label Image Stamper"}, # Picker only
                2: {"LOOKUP"}, # Returns access only
                3: {"LOOKUP", "Label Image Stamper"}, # Full access except Admin
                4: {"LOOKUP", "Label Image Stamper"}, # Full access except Admin
                5: set(PAGES.keys()), # Admin has access to all pages
            }

            user_type = st.session_state.user_type
            print(f"USER TYPE: {user_type}")
            allowed_pages = sorted(ROLE_ACCESS.get(user_type, {"Dashboard"}))
        else:
            allowed_pages = sorted(PAGES.keys())

        print(f"ALLOWED PAGES: {allowed_pages}")

        selected_page = st.selectbox(
            "Navigate",
            allowed_pages,
            index=allowed_pages.index(
                next(
                    (k for k, v in PAGES.items() if v == st.session_state.page),
                    "Label Image Stamper",
                )
            ),
        )

        st.session_state.page = PAGES[selected_page]

        st.markdown("---")

        if st.button("Logout"):
            logout_user()
            st.rerun()

# -------------------------------------------------------------------
# MAIN ENTRY
# -------------------------------------------------------------------
logging.info(f"LOGIN_FEATURE: {LOGIN_FEATURE}, Authenticated: {st.session_state.authenticated}")
print(f"LOGIN_FEATURE: {LOGIN_FEATURE}, Authenticated: {st.session_state.authenticated}")
if LOGIN_FEATURE and not st.session_state.authenticated:

    attempt_auto_login()

    if not st.session_state.authenticated:
        render_login_sidebar()
        st.info("Please log in to access the system.")
    else:
        render_navigation_sidebar()

        page = st.session_state.page

        if page == LOOKUP:
            render_product_lookup_panel()
        elif page == LABEL_STAMPER:
            render_label_stamper_panel()

else:
    render_navigation_sidebar()

    page = st.session_state.page

    if page == LOOKUP:
        render_product_lookup_panel()
    elif page == LABEL_STAMPER:
        logging.info("Rendering Label Stamper Panel")
        print("Rendering Label Stamper Panel")
        render_label_stamper_panel()