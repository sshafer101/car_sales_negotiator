# app/pages/2_Replay.py
from __future__ import annotations

import json
from typing import Any, Dict, List

import streamlit as st

from app._auth import require_login, require_paid
from engine.storage import list_runs, load_run


st.set_page_config(page_title="Replay", page_icon="📼", layout="wide")

st.title("Replay")

if not require_login():
    st.stop()
if not require_paid():
    st.stop()


def _safe_list_runs(limit: int = 250) -> List[Dict[str, Any]]:
    try:
        return list_runs(limit=limit)
    except Exception:
        return []


def _run_summary_row(r: Dict[str, Any]) -> Dict[str, Any]:
    score = r.get("score") or {}
    total = None
    if isinstance(score, dict):
        total = score.get("total")
    return {
        "run_id": r.get("run_id"),
        "seed": r.get("seed"),
        "mode": r.get("mode"),
        "created_at": str(r.get("created_at", ""))[:19],
        "total_score": total if total is not None else "",
        "buyer_profile_hash": r.get("buyer_profile_hash", ""),
    }


runs = _safe_list_runs(limit=250)

with st.sidebar:
    st.header("Filters")
    seed_filter = st.text_input("Seed (optional)", value="")
    mode_filter = st.selectbox("Mode", options=["any", "strict", "freeplay", "flavor"], index=0)
    limit = st.slider("Max runs", min_value=25, max_value=250, value=100, step=25)

filtered: List[Dict[str, Any]] = []
for r in runs:
    if seed_filter.strip():
        if str(r.get("seed", "")) != seed_filter.strip():
            continue
    if mode_filter != "any":
        if str(r.get("mode", "")) != mode_filter:
            continue
    filtered.append(r)

filtered = filtered[: int(limit)]

st.subheader("Runs")
summary_rows = [_run_summary_row(r) for r in filtered]
st.dataframe(summary_rows, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Open a run")

run_ids = [str(r.get("run_id")) for r in filtered if r.get("run_id")]
selected = st.selectbox("Run", options=run_ids) if run_ids else None

if not selected:
    st.stop()

payload = load_run(selected)

col1, col2 = st.columns([2, 1])
with col1:
    st.caption(
        f"seed={payload.get('seed')}  run_id={payload.get('run_id')}  run_key={payload.get('run_key')}  "
        f"buyer_profile_hash={payload.get('buyer_profile_hash')}"
    )
with col2:
    st.download_button(
        label="Download run JSON",
        data=json.dumps(payload, indent=2, sort_keys=True),
        file_name=f"run_{payload.get('run_id','unknown')}.json",
        mime="application/json",
        use_container_width=True,
    )

st.subheader("Conversation")
session = payload.get("session") or {}
turns = session.get("turns") or []

chat_box = st.container(height=520, border=True)
with chat_box:
    for t in turns:
        seller = (t.get("seller") or "").strip()
        customer = (t.get("customer") or "").strip()
        if seller:
            with st.chat_message("user"):
                st.markdown(seller)
        if customer:
            with st.chat_message("assistant"):
                st.markdown(customer)

st.subheader("Buyer profile")
st.json(payload.get("buyer_profile") or {})
