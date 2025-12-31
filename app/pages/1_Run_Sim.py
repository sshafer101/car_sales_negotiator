# app/pages/1_Run_Sim.py
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
    if "seed" not in st.session_state:
        st.session_state.seed = "18422"
    if "show_profile" not in st.session_state:
        st.session_state.show_profile = False
    if "show_tags" not in st.session_state:
        st.session_state.show_tags = False


def _safe_list_runs(limit: int = 75) -> List[Dict[str, Any]]:
    try:
        return list_runs(limit=limit)
    except Exception:
        return []


def _start_new_run(seed: int, pack_dir: str, mode: str, llm_model: str, reference_k: int) -> Dict[str, Any]:
    run_id, payload = start_run(
        seed=seed,
        pack_dir=pack_dir,
        overrides={},
        mode=mode,
        llm_model=llm_model,
        reference_k=reference_k if mode == "flavor" else 0,
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


def _count_llm_fallbacks(turns: List[Dict[str, Any]]) -> int:
    n = 0
    for t in turns:
        tags = t.get("tags") or []
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("llm_fallback:"):
                n += 1
    return n


def _last_llm_fallback_reason(turns: List[Dict[str, Any]]) -> str:
    for t in reversed(turns):
        tags = t.get("tags") or []
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("llm_fallback:"):
                return tag.replace("llm_fallback:", "", 1)
    return ""


def _render_chat(payload: Dict[str, Any]) -> None:
    session = payload.get("session") or {}
    turns = session.get("turns") or []

    mode = str((payload.get("mode") or session.get("mode") or "strict")).strip()

    fallbacks = _count_llm_fallbacks(turns)
    if mode in ("freeplay", "flavor"):
        if fallbacks:
            reason = _last_llm_fallback_reason(turns)
            st.warning(f"LLM fallback occurred {fallbacks} time(s). Last reason: {reason}")
        else:
            st.success("LLM active (no fallback tags detected).")
    else:
        st.info("Strict mode active (no LLM).")

    chat_box = st.container(height=520, border=True)
    with chat_box:
        for t in turns:
            seller = (t.get("seller") or "").strip()
            customer = (t.get("customer") or "").strip()
            tags = t.get("tags") or []

            if seller:
                with st.chat_message("user"):
                    st.markdown(seller)

            if customer:
                with st.chat_message("assistant"):
                    st.markdown(customer)
                    if st.session_state.show_tags and tags:
                        st.caption(f"tags: {tags}")


def _render_controls() -> Dict[str, Any]:
    with st.sidebar:
        st.header("Controls")

        pack_dir = "data/car_sales_pack"

        seed = st.text_input("Seed", value=st.session_state.seed)
        st.session_state.seed = seed

        mode = st.selectbox("Mode", options=["strict", "freeplay", "flavor"], index=2)
        llm_model = st.text_input("LLM model", value="gpt-5.2")
        reference_k = st.slider("Reference runs (flavor mode)", min_value=0, max_value=6, value=3, step=1)

        st.session_state.show_tags = st.toggle("Show turn tags (debug)", value=st.session_state.show_tags)

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

        selected = st.selectbox(
            "Open run",
            options=[""] + run_options,
            format_func=lambda x: "Select a run" if x == "" else run_labels.get(x, x),
        )
        if selected:
            _set_active_run(selected)
            st.rerun()

    return {"pack_dir": pack_dir}


def _maybe_load_openai_key_from_secrets() -> None:
    # Optional convenience: load st.secrets into env for OpenAI SDK
    if "OPENAI_API_KEY" in st.secrets and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = str(st.secrets["OPENAI_API_KEY"])


def main() -> None:
    _ensure()

    if not require_login():
        st.stop()
    if not require_paid():
        st.stop()

    _maybe_load_openai_key_from_secrets()

    st.title("Run Sim")

    _render_controls()

    payload = st.session_state.active_payload
    if not payload:
        st.info("Start a new run from the sidebar.")
        st.stop()

    run_id = st.session_state.active_run_id
    st.caption(
        f"seed={payload.get('seed')} run_id={run_id} run_key={payload.get('run_key')} "
        f"buyer_profile_hash={payload.get('buyer_profile_hash')} ref_hash={payload.get('reference_set_hash')}"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.page_link("pages/2_Replay.py", label="Open Replay", icon="📼", use_container_width=True)
    with col2:
        st.button("Share seed", use_container_width=True, disabled=True)
    with col3:
        st.button("Share run_id", use_container_width=True, disabled=True)

    st.divider()

    _render_chat(payload)

    seller_text = st.chat_input("Type your next message and press Enter")
    if seller_text:
        payload = step_run(payload, seller_text.strip())
        st.session_state.active_payload = payload
        if run_id:
            save_run(run_id, payload)
        st.rerun()


main()
