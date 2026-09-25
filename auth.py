import streamlit as st
from streamlit_cookies_controller import CookieController
from database import get_pass


# -------------------------------------------------
# Cookie Manager
# -------------------------------------------------
def get_cookie_manager():

    if "cookie_manager" not in st.session_state:
        st.session_state.cookie_manager = CookieController()

    return st.session_state.cookie_manager


# -------------------------------------------------
# Authentication
# -------------------------------------------------
def authenticate_user(username, password):
    stored_password = get_pass(username)
    if stored_password is None:
        return False
    return stored_password == password


# -------------------------------------------------
# Cookie helpers
# -------------------------------------------------
def set_cookie(name: str, value: str) -> bool: 
    try: 
        manager = get_cookie_manager() 
        manager.set( name, value, max_age=60 * 60 * 24 * 30, # 30 days 
                    ) 
        print(f"Cookie '{name}' set to value '{value}' successfully.")
        return True 
    except Exception as e: 
        print(f"Cookie set error: {e}") 
        return False


def get_cookie(name: str):
    try:
        print(f"Attempting to retrieve cookie '{name}' = {st.context.cookies.get(name)}")
        return st.context.cookies.get(name)
    except Exception as e:
        print(f"Cookie get error: {e}")
        return None

def clear_cookie(name: str) -> bool:
    try:
        manager = get_cookie_manager()
        manager.remove(name)
        print(f"Cookie '{name}' cleared successfully.")
        return True
    except KeyError:
        # Removing an already-absent cookie is a successful no-op.
        print(f"Cookie '{name}' was already absent.")
        return True
    except Exception as e:
        print(f"Cookie clear error: {e}")
        return False


# -------------------------------------------------
# Logout
# -------------------------------------------------
def logout_user():
    print("Logging out user...")
    clear_cookie("logged_user")

    # Clear authentication state without deleting the cookie manager mid-logout.
    for key in ("authenticated", "user_role", "user_type", "party_filter", "logged_user"):
        st.session_state.pop(key, None)
    st.session_state.update({
        "authenticated": False,
        "user_role": None,
        "user_type": None,
        "party_filter": None,
        "page": "dashboard"
    })

    st.rerun()

