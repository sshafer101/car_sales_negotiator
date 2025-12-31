import streamlit as st

st.set_page_config(page_title="Car Sales Negotiator", page_icon="🚗", layout="wide")

st.title("Car Sales Negotiator")
st.write("Deterministic negotiation simulator powered by persona_engine.")
st.write("Replay the same seed to get the same buyer persona and consistent buyer behavior.")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.page_link("pages/0_Login.py", label="Login", icon="🔐", use_container_width=True)
with col2:
    st.page_link("pages/3_Billing.py", label="Billing", icon="💳", use_container_width=True)
with col3:
    st.page_link("pages/1_Run_Sim.py", label="Run Sim", icon="🧪", use_container_width=True)
with col4:
    st.page_link("pages/2_Replay.py", label="Replay", icon="📼", use_container_width=True)

st.divider()
st.subheader("Fast demo")
st.write("1) Login")
st.write("2) Start Run Sim with seed 18422")
st.write("3) Send 3 to 6 messages")
st.write("4) Replay the same seed and show the run key and buyer profile hash stay the same")
