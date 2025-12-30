import streamlit as st

st.set_page_config(page_title="Car Sales Negotiator", layout="wide")

st.title("Car Sales Negotiator")
st.write("Text-first negotiation trainer showcasing deterministic seed replay using persona_engine.")

st.markdown(
    """
What this app proves:
- Same seed yields the same buyer persona
- Strict mode yields deterministic behavior and scoring
- You can share a seed and reproduce the scenario
"""
)

st.info("Use the pages on the left: Run Sim, Replay, Manager Reports.")
