import streamlit as st

st.set_page_config(page_title="Login", page_icon="🔐", layout="wide")
st.title("Login")

if "user" not in st.session_state:
    st.session_state.user = None

email = st.text_input("Email", placeholder="you@company.com")
password = st.text_input("Password", type="password")

col1, col2 = st.columns(2)

with col1:
    if st.button("Login", use_container_width=True):
        if email.strip() and password.strip():
            st.session_state.user = {"email": email.strip()}
            st.success("Logged in.")
            st.page_link("pages/1_Run_Sim.py", label="Go to Run Sim", icon="🧪", use_container_width=True)
        else:
            st.error("Enter email and password.")

with col2:
    if st.button("Logout", use_container_width=True):
        st.session_state.user = None
        st.success("Logged out.")

st.divider()
st.subheader("Notes")
st.write("This is an MVP login gate using session state.")
st.write("Production should use real auth (OAuth) and a real user store.")
