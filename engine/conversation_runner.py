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
from .llm_client import customer_reply_llm_freeplay
from .reference_selector import select_reference_set, reference_set_hash


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
    reference_k: int = 0,
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
            "llm_model": llm_model if mode in ["flavor", "freeplay"] else "",
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
    if mode in ["flavor", "freeplay"] and reference_k > 0:
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
            "mode": run_payload.get("mode", ""),
        }
    )


def _append_freeplay_turn(run_payload: Dict[str, Any], seller_text: str) -> Dict[str, Any]:
    session = run_payload["session"]
    turns = session.get("turns", [])
    turn_index = len(turns)

    cache: Dict[str, str] = run_payload.get("llm_cache") or {}
    ck = _cache_key(run_payload, turn_index, seller_text)

    err: Optional[str] = None
    if ck in cache:
        customer_text = cache[ck]
    else:
        prev_customer = ""
        if turns:
            prev_customer = str((turns[-1].get("customer") or "")).strip()

        customer_text, err = customer_reply_llm_freeplay(
            model=run_payload.get("llm_model", "gpt-5.2"),
            persona_prompt=run_payload["persona_prompt"],
            buyer_profile=run_payload["buyer_profile"],
            turns=turns,
            seller_message=seller_text,
            prev_customer_message=prev_customer,
        )

        if err:
            # deterministic fallback to strict
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
    extra_tags = ["llm_freeplay"]
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

    session["turns"] = turns
    run_payload["session"] = session
    return run_payload


def step_run(run_payload: Dict[str, Any], seller_text: str) -> Dict[str, Any]:
    mode = run_payload.get("mode", "strict")

    if mode == "freeplay":
        run_payload = _append_freeplay_turn(run_payload, seller_text)
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
