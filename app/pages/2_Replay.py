import streamlit as st
from engine.storage import list_runs

st.title("Replay")

runs = list_runs(limit=200)
if not runs:
    st.info("No runs saved yet.")
    st.stop()

options = [(r["run_id"], r.get("seed"), r.get("created_at"), r.get("run_key")) for r in runs]
label_map = {rid: f"{rid} | seed={seed} | {created_at}" for rid, seed, created_at, _ in options}

chosen = st.selectbox("Select a run", [rid for rid, _, _, _ in options], format_func=lambda x: label_map[x])
run = next(r for r in runs if r["run_id"] == chosen)

st.subheader("Run identity")
st.write(f"Seed: {run.get('seed')}")
st.write(f"Run key: {run.get('run_key')}")
st.write(f"Buyer profile hash: {run.get('buyer_profile_hash')}")
st.write(f"Pack hash: {run.get('pack_hash')}")

st.subheader("Buyer profile")
st.json(run.get("buyer_profile"))

st.subheader("Conversation")
for t in run.get("session", {}).get("turns", []):
    if t.get("seller"):
        st.markdown(f"**You:** {t['seller']}")
    st.markdown(f"**Customer:** {t['customer']}")
    st.write("")

st.subheader("Score")
st.json(run.get("score"))
