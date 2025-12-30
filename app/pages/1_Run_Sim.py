import os
import streamlit as st

from engine.storage import load_run, save_run
from engine.conversation_runner import start_run, step_run

APP_ROOT = os.getcwd()
PACK_DIR = os.path.join(APP_ROOT, "data", "car_sales_pack")

st.title("Run Simulation")

if "OPENAI_API_KEY" in st.secrets and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

col1, col2 = st.columns([1, 2])

with col1:
    seed = st.number_input("Seed", min_value=0, max_value=99999999, value=18422, step=1)

    mode = st.selectbox("Mode", ["strict", "flavor"], index=0)
    llm_model = st.text_input("LLM model (Flavor)", value="gpt-5.2")

    role = st.selectbox("Viewer role", ["sales_rep", "manager"], index=0)

    show_hints = st.checkbox("Show training hints (rep)", value=False)
    if role == "manager":
        show_debug = st.checkbox("Show debug JSON (manager)", value=True)
    else:
        show_debug = False

    if mode == "flavor":
        has_key = bool(os.environ.get("OPENAI_API_KEY"))
        if has_key:
            st.success("OPENAI_API_KEY is set")
        else:
            st.error("OPENAI_API_KEY missing. Set env var or .streamlit/secrets.toml")

    start = st.button("Start new run")

    if start:
        run_id, _ = start_run(
            seed=int(seed),
            pack_dir=PACK_DIR,
            overrides={},
            mode=mode,
            llm_model=llm_model.strip() if llm_model.strip() else "gpt-5.2",
        )
        st.session_state["active_run_id"] = run_id
        st.session_state["viewer_role"] = role
        st.session_state["show_hints"] = show_hints
        st.session_state["show_debug"] = show_debug
        st.success(f"Started run {run_id}")

    st.divider()
    st.subheader("Active run")
    active = st.session_state.get("active_run_id")
    st.write(active if active else "None")

with col2:
    active = st.session_state.get("active_run_id")
    if not active:
        st.info("Start a new run to begin.")
        st.stop()

    payload = load_run(active)

    viewer_role = st.session_state.get("viewer_role", "sales_rep")
    show_hints = st.session_state.get("show_hints", False)
    show_debug = st.session_state.get("show_debug", False)

    if viewer_role == "manager" and show_debug:
        st.subheader("Buyer profile (manager debug)")
        st.json(payload["buyer_profile"])
    elif viewer_role == "sales_rep" and show_hints:
        st.subheader("Training hints (rep)")
        bp = payload["buyer_profile"]
        hints = {
            "goal": "Discover constraints without pressure",
            "soft_hint": f"Buyer seems: {bp['style']['objection_style'].replace('_', ' ')}",
            "one_hint": "Ask about budget, payment, must-haves, and timeline",
        }
        st.json(hints)

    st.subheader("Conversation")
    session = payload["session"]
    for t in session.get("turns", []):
        if t.get("seller"):
            st.markdown(f"**You:** {t['seller']}")
        st.markdown(f"**Customer:** {t['customer']}")
        st.write("")

    seller_text = st.text_input("Your next message", value="")
    if st.button("Send"):
        if seller_text.strip():
            payload = step_run(payload, seller_text.strip())
            save_run(active, payload)
            st.rerun()

    st.subheader("Score")
    if payload.get("score"):
        st.json(payload["score"])
    else:
        st.write("No score yet.")
