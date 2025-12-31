import streamlit as st

st.set_page_config(page_title="Billing", page_icon="💳", layout="wide")
st.title("Billing")

if "is_paid" not in st.session_state:
    st.session_state.is_paid = False

pay_url = ""
if "billing" in st.secrets:
    pay_url = str(st.secrets["billing"].get("stripe_payment_link", "")).strip()

st.write("MVP billing uses a Stripe hosted payment link.")

if pay_url:
    st.link_button("Subscribe", pay_url, use_container_width=True)
else:
    st.warning("No Stripe payment link configured.")
    st.code('Add this to .streamlit/secrets.toml:\n[billing]\nstripe_payment_link="https://..."')

st.divider()
st.subheader("Dev override")
col1, col2 = st.columns(2)
with col1:
    if st.button("Mark this session as paid", use_container_width=True):
        st.session_state.is_paid = True
        st.success("Paid flag enabled for this browser session.")
with col2:
    if st.button("Clear paid flag", use_container_width=True):
        st.session_state.is_paid = False
        st.success("Paid flag cleared.")
