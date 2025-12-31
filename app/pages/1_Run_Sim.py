from __future__ import annotations

import os
from typing import Any, Dict, List

import streamlit as st

from app._auth import require_login, require_paid
from engine.conversation_runner import start_run, step_run
from engine.storage import load_run, save_run, list_runs


st.set_page_config(page_title="Run Sim", page_icon="🧪", layout="wide")


def _ensure() -> None:
    if "active_run_id" not in st.session_state:
        st.session_state.active_run_id = None
    if "active_payload" not in st.session_state:
        st.session_state.active_payload = None


def _project_root() -> str:
    return os.getcwd()


def _default_pack_dir() -> str:
    return os.path.join(_project_root(), "data", "car_sales_pack")


def _safe_list_runs(limit: int = 75) -> List[Dict[str, Any]]:
    try:
        return list_runs(limit=limit) or []
    except Exception:
        return []


def _load_active_payload() -> Dict[str, Any] | None:
    rid = st.session_state.active_run_id
    if not rid:
        return None
    try:
        return load_run(rid)
    except Exception:
        return None


def _render_chat(payload: Dict[str, Any]) -> None:
    session = payload.get("session") or {}
    turns = session.get("turns") or []

    chat_box = st.container(height=520, border=True)
    with chat_box:
        for t in turns:
            customer = (t.get("customer") or "").strip()
            seller = (t.get("seller") or "").strip()
            if customer:
                with st.chat_message("assistant"):
                    st.markdown(customer)
            if seller:
                with st.chat_message("user"):
                    st.markdown(seller)


def _start_new_run(seed: int, pack_dir: str, mode: str, llm_model: str, reference_k: int) -> Dict[str, Any]:
    run_id, payload = start_run(
        seed=seed,
        pack_dir=pack_dir,
        overrides={},
        mode=mode,
        llm_model=llm_model,
        reference_k=reference_k,
    )
    st.session_state.active_run_id = run_id
    st.session_state.active_payload = payload
    return payload


def _set_active_run(run_id: str) -> Dict[str, Any] | None:
    try:
        payload = load_run(run_id)
    except Exception:
        return None
    st.session_state.active_run_id = run_id
    st.session_state.active_payload = payload
    return payload


def _download_payload(payload: Dict[str, Any]) -> None:
    import json

    st.download_button(
        label="Download run JSON",
        data=json.dumps(payload, indent=2, sort_keys=True),
        file_name=f"run_{payload.get('run_id','unknown')}.json",
        mime="application/json",
        use_container_width=True,
    )


_ensure()

st.title("Run Sim")

if not require_login():
    st.stop()
if not require_paid():
    st.stop()

with st.sidebar:
    st.header("Controls")

    user = st.session_state.get("user") or {}
    st.caption(f"User: {user.get('email','unknown')}")
    st.caption("Paid: yes")

    st.divider()
    st.subheader("Run settings")

    seed = st.number_input("Seed", min_value=0, max_value=99999999, value=18422, step=1)

    pack_dir = st.text_input("Pack dir", value=_default_pack_dir())

    mode = st.selectbox("Mode", options=["strict", "flavor"], index=1)

    llm_model = st.text_input("LLM model", value="gpt-5.2")

    reference_k = st.slider("Reference runs (flavor)", min_value=0, max_value=6, value=3, step=1)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Start new run", use_container_width=True):
            _start_new_run(int(seed), pack_dir, mode, llm_model.strip(), int(reference_k))
            st.rerun()
    with col_b:
        if st.button("Reset active", use_container_width=True):
            st.session_state.active_run_id = None
            st.session_state.active_payload = None
            st.rerun()

    st.divider()
    st.subheader("Run selector")

    runs = _safe_list_runs(limit=75)
    run_options: List[str] = []
    run_labels: Dict[str, str] = {}

    for r in runs:
        rid = str(r.get("run_id", "")).strip()
        if not rid:
            continue
        s = r.get("seed", "")
        m = r.get("mode", "")
        created = str(r.get("created_at", ""))[:19]
        label = f"{rid[:8]}  seed={s}  {m}  {created}"
        run_options.append(rid)
        run_labels[rid] = label

    if run_options:
        selected = st.selectbox(
            "Select run",
            options=run_options,
            format_func=lambda rid: run_labels.get(rid, rid),
            index=0,
        )
        if st.button("Load selected", use_container_width=True):
            _set_active_run(selected)
            st.rerun()
    else:
        st.caption("No runs yet.")

payload = st.session_state.active_payload or _load_active_payload()

if not payload:
    st.info("Start a new run to begin.")
    st.stop()

seed_val = payload.get("seed")
run_id = payload.get("run_id")
run_key = payload.get("run_key")
bp_hash = payload.get("buyer_profile_hash")
ref_hash = payload.get("reference_set_hash", "")

st.caption(f"seed={seed_val}  run_id={run_id}  run_key={run_key}  buyer_profile_hash={bp_hash}  ref_hash={ref_hash}")

col_top1, col_top2, col_top3 = st.columns([2, 1, 1])
with col_top1:
    st.text_input("Share seed", value=str(seed_val), label_visibility="visible")
with col_top2:
    st.text_input("Share run_id", value=str(run_id), label_visibility="visible")
with col_top3:
    st.page_link("app/pages/2_Replay.py", label="Open Replay", icon="📼", use_container_width=True)

_render_chat(payload)

seller_text = st.chat_input("Type your message and press Enter")
if seller_text:
    payload = step_run(payload, seller_text.strip())
    save_run(payload["run_id"], payload)
    st.session_state.active_payload = payload
    st.rerun()

with st.expander("Export", expanded=False):
    _download_payload(payload)

with st.expander("Score", expanded=False):
    st.json(payload.get("score") or {})

with st.expander("Debug", expanded=False):
    st.json(
        {
            "reference_set": payload.get("reference_set"),
            "llm_cache_size": len(payload.get("llm_cache") or {}),
            "controller_state": payload.get("controller_state"),
        }
    )
