import streamlit as st


def is_logged_in() -> bool:
    return bool(st.session_state.get("user"))


def is_paid() -> bool:
    return bool(st.session_state.get("is_paid"))


def require_login() -> bool:
    if is_logged_in():
        return True
    st.warning("Please login to continue.")
    st.page_link("pages/0_Login.py", label="Go to Login", icon="🔐")
    return False


def require_paid() -> bool:
    if is_paid():
        return True
    st.warning("Subscription required to use this page.")
    st.page_link("pages/3_Billing.py", label="Go to Billing", icon="💳")
    return False
