from __future__ import annotations

from typing import Any, Dict, List, Tuple
import uuid
import json
import os

from persona_engine import generate_persona, persona_to_prompt

from .buyer_profile import build_buyer_profile, buyer_profile_to_dict
from .conversation import new_session, step_session, session_to_dict, SessionState, Turn, _extract_keywords
from .scoring import score_session, score_to_dict
from .utils import stable_hash, to_jsonable
from .storage import save_run
from .llm_client import customer_reply_llm
from .reference_selector import select_reference_set, build_reference_excerpts, reference_set_hash


def load_pack(pack_dir: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for fn in os.listdir(pack_dir):
        if not fn.endswith(".json"):
            continue
        key = fn.replace(".json", "")
        with open(os.path.join(pack_dir, fn), "r", encoding="utf-8") as f:
            out[key] = json.load(f)
    return out


def _persona_to_dict(persona_obj: Any) -> Dict[str, Any]:
    data = to_jsonable(persona_obj)
    if not isinstance(data, dict):
        raise TypeError(f"Persona conversion produced {type(data)} not dict")
    return data


def start_run(
    *,
    seed: int,
    pack_dir: str,
    overrides: Dict[str, Any] | None = None,
    mode: str = "strict",
    llm_model: str = "gpt-5.2",
    reference_k: int = 3,
) -> Tuple[str, Dict[str, Any]]:
    overrides = overrides or {}

    persona_obj = generate_persona(seed=seed, **overrides)
    persona_prompt = persona_to_prompt(persona_obj)
    persona = _persona_to_dict(persona_obj)

    pack = load_pack(pack_dir)

    persona_lib_hash = str(persona.get("library_hash", ""))
    pack_hash = stable_hash(pack)
    overrides_hash = stable_hash(overrides)

    run_key = stable_hash(
        {
            "seed": seed,
            "persona_lib_hash": persona_lib_hash,
            "pack_hash": pack_hash,
            "overrides_hash": overrides_hash,
            "mode": mode,
            "llm_model": llm_model if mode == "flavor" else "",
        }
    )

    run_rng_seed = abs(hash(run_key)) % (2**31 - 1)
    bp = build_buyer_profile(persona=persona, pack=pack, run_rng_seed=run_rng_seed)
    bp_hash = stable_hash(buyer_profile_to_dict(bp))

    session = new_session(
        seed=seed,
        run_key=run_key,
        persona=persona,
        persona_prompt=persona_prompt,
        buyer_profile=bp,
        buyer_profile_hash=bp_hash,
    )

    ref_ids: List[str] = []
    if mode == "flavor" and reference_k > 0:
        ref_ids = select_reference_set(
            current_run_key=run_key,
            current_seed=seed,
            current_pack_hash=pack_hash,
            current_buyer_profile=buyer_profile_to_dict(bp),
            k=reference_k,
        )

    ref_hash = reference_set_hash(ref_ids)

    run_id = str(uuid.uuid4())
    payload: Dict[str, Any] = {
        "run_id": run_id,
        "run_key": run_key,
        "seed": seed,
        "mode": mode,
        "llm_model": llm_model,
        "persona": persona,
        "persona_prompt": persona_prompt,
        "buyer_profile": buyer_profile_to_dict(bp),
        "buyer_profile_hash": bp_hash,
        "session": session_to_dict(session),
        "score": None,
        "created_at": session.created_at,
        "pack_hash": pack_hash,
        "overrides": overrides,
        "llm_cache": {},
        "reference_set": ref_ids,
        "reference_set_hash": ref_hash,
        "reference_k": reference_k,
        # deterministic controller state for flavor mode
        "controller_state": {
            "revealed_budget": False,
            "revealed_payment": False,
            "revealed_features": False,
            "revealed_down": False,
            "revealed_trade": False,
            "patience": 3,
            "last_seller_norm": "",
        },
    }

    save_run(run_id, payload)
    return run_id, payload


def _cache_key(run_payload: Dict[str, Any], turn_index: int, seller_text: str) -> str:
    seller_hash = stable_hash({"seller": seller_text})
    return stable_hash(
        {
            "run_key": run_payload.get("run_key"),
            "turn_index": turn_index,
            "seller_hash": seller_hash,
            "reference_set_hash": run_payload.get("reference_set_hash", ""),
            "llm_model": run_payload.get("llm_model", ""),
        }
    )


def _normalize(s: str) -> str:
    return " ".join((s or "").lower().split())


def _build_decision(run_payload: Dict[str, Any], seller_text: str) -> Dict[str, Any]:
    """
    Deterministic conversation controller.
    It decides what can be revealed and what the customer should do this turn.
    """
    state = run_payload.get("controller_state") or {}
    tags = _extract_keywords(seller_text)
    seller_norm = _normalize(seller_text)

    # repeated seller prompt
    if seller_norm and seller_norm == state.get("last_seller_norm", ""):
        state["patience"] = int(state.get("patience", 3)) - 1
    else:
        state["last_seller_norm"] = seller_norm

    patience = int(state.get("patience", 3))

    reveal: Dict[str, bool] = {
        "budget_max_otd": False,
        "payment_target_monthly": False,
        "must_have_features": False,
        "down_payment": False,
        "trade_in_status": False,
    }

    intent = "respond_and_ask"
    must_redirect = False

    # if seller is off-topic (pitching random sports car etc)
    off_topic = any(x in seller_norm for x in ["corvette", "ferrari", "lamborghini", "supercar"])
    if off_topic and ("features" not in tags) and ("budget" not in tags) and ("payment" not in tags):
        intent = "redirect_to_constraints"
        must_redirect = True

    # map seller asks to reveals
    if "budget" in tags and not state.get("revealed_budget"):
        reveal["budget_max_otd"] = True
        state["revealed_budget"] = True

    if "payment" in tags and not state.get("revealed_payment"):
        reveal["payment_target_monthly"] = True
        state["revealed_payment"] = True

    if "features" in tags and not state.get("revealed_features"):
        reveal["must_have_features"] = True
        state["revealed_features"] = True

    if "down_payment" in tags and not state.get("revealed_down"):
        reveal["down_payment"] = True
        state["revealed_down"] = True

    if "trade_in" in tags and not state.get("revealed_trade"):
        reveal["trade_in_status"] = True
        state["revealed_trade"] = True

    if patience <= 0:
        intent = "end_pause"
        must_redirect = False

    run_payload["controller_state"] = state

    return {
        "intent": intent,
        "reveal": reveal,
        "patience": patience,
        "must_redirect": must_redirect,
        "seller_tags": tags,
    }


def _append_flavor_turn(run_payload: Dict[str, Any], seller_text: str) -> Dict[str, Any]:
    session = run_payload["session"]
    turns = session.get("turns", [])
    turn_index = len(turns)

    cache: Dict[str, str] = run_payload.get("llm_cache") or {}
    ck = _cache_key(run_payload, turn_index, seller_text)

    if ck in cache:
        customer_text = cache[ck]
        err = None
    else:
        decision = _build_decision(run_payload, seller_text)

        ref_ids = run_payload.get("reference_set") or []
        ref_excerpts = build_reference_excerpts(ref_ids, max_turns_per_run=3)

        prev_customer = ""
        if turns:
            prev_customer = str((turns[-1].get("customer") or "")).strip()

        customer_text, err = customer_reply_llm(
            model=run_payload.get("llm_model", "gpt-5.2"),
            persona_prompt=run_payload["persona_prompt"],
            buyer_profile=run_payload["buyer_profile"],
            turns=turns,
            seller_message=seller_text,
            reference_excerpts=ref_excerpts,
            decision=decision,
            prev_customer_message=prev_customer,
        )

        if err:
            # Deterministic fallback to strict step engine
            strict_turns: List[Turn] = [Turn(**t) for t in turns]
            ss = SessionState(
                seed=session["seed"],
                run_key=session["run_key"],
                mode="strict",
                created_at=session["created_at"],
                persona=session["persona"],
                persona_prompt=session["persona_prompt"],
                buyer_profile=session["buyer_profile"],
                buyer_profile_hash=session["buyer_profile_hash"],
                turns=strict_turns,
                outcome=session.get("outcome"),
                notes=session.get("notes", []),
            )
            if "_internal_state" in session:
                ss.__dict__["_internal_state"] = session["_internal_state"]
            else:
                ss.__dict__["_internal_state"] = {}

            ss = step_session(ss, seller_text)
            customer_text = ss.turns[-1].customer
            session["_internal_state"] = ss.__dict__.get("_internal_state", {})

        cache[ck] = customer_text
        run_payload["llm_cache"] = cache

    tags = _extract_keywords(seller_text)
    extra_tags = ["llm_flavor_ctrl"]
    if err:
        extra_tags.append(f"llm_fallback:{err}")

    turns.append(
        {
            "turn_index": turn_index,
            "seller": seller_text,
            "customer": customer_text,
            "tags": tags + extra_tags,
        }
    )

    lowered = customer_text.lower()
    if "walk" in lowered or "pause here" in lowered:
        session["outcome"] = "bad_exit"
    elif ("appointment" in seller_text.lower()) or ("follow up" in seller_text.lower()):
        if session.get("outcome") == "ongoing":
            session["outcome"] = "good_exit"
    elif ("deal" in seller_text.lower()) and (("out the door" in seller_text.lower()) or ("otd" in seller_text.lower())):
        if session.get("outcome") == "ongoing":
            session["outcome"] = "deal"

    session["turns"] = turns
    run_payload["session"] = session
    return run_payload


def step_run(run_payload: Dict[str, Any], seller_text: str) -> Dict[str, Any]:
    mode = run_payload.get("mode", "strict")

    if mode == "flavor":
        run_payload = _append_flavor_turn(run_payload, seller_text)
        score = score_session(run_payload["session"])
        run_payload["score"] = score_to_dict(score)
        return run_payload

    session = run_payload["session"]

    turns = []
    for t in session.get("turns", []):
        turns.append(Turn(**t))

    ss = SessionState(
        seed=session["seed"],
        run_key=session["run_key"],
        mode=session["mode"],
        created_at=session["created_at"],
        persona=session["persona"],
        persona_prompt=session["persona_prompt"],
        buyer_profile=session["buyer_profile"],
        buyer_profile_hash=session["buyer_profile_hash"],
        turns=turns,
        outcome=session.get("outcome"),
        notes=session.get("notes", []),
    )

    if "_internal_state" in session:
        ss.__dict__["_internal_state"] = session["_internal_state"]
    else:
        ss.__dict__["_internal_state"] = {}

    ss = step_session(ss, seller_text)
    run_payload["session"] = session_to_dict(ss)

    score = score_session(run_payload["session"])
    run_payload["score"] = score_to_dict(score)
    return run_payload
