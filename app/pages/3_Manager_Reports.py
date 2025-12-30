import os
import streamlit as st
import pandas as pd

from engine.storage import list_runs, EXPORTS_DIR
from engine.utils import ensure_dir

st.title("Manager Reports")

runs = list_runs(limit=500)
if not runs:
    st.info("No runs yet.")
    st.stop()

rows = []
for r in runs:
    score = r.get("score") or {}
    rows.append(
        {
            "run_id": r.get("run_id"),
            "seed": r.get("seed"),
            "created_at": r.get("created_at"),
            "run_key": r.get("run_key"),
            "buyer_profile_hash": r.get("buyer_profile_hash"),
            "outcome": (r.get("session") or {}).get("outcome"),
            "total": score.get("total"),
            "discovery": score.get("discovery"),
            "trust": score.get("trust"),
            "objection_handling": score.get("objection_handling"),
            "efficiency": score.get("efficiency"),
            "constraint_accuracy": score.get("constraint_accuracy"),
            "deal_quality": score.get("deal_quality"),
        }
    )

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True)

st.divider()
st.subheader("Export CSV")

ensure_dir(EXPORTS_DIR)
export_name = st.text_input("Filename", value="manager_report.csv")
if st.button("Export"):
    path = os.path.join(EXPORTS_DIR, export_name)
    df.to_csv(path, index=False)
    st.success(f"Exported to {path}")
