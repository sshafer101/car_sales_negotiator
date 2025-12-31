# engine/conversation_runner.py
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
from .storage import save_run, load_run
from .llm_client import customer_reply_llm_freeplay
from .reference_selector import select_reference_set, reference_set_hash


def _build_reference_excerpts(ref_ids: List[str], *, max_turns_per_run: int = 6, max_chars: int = 1200) -> List[str]:
    """Build short excerpts from prior runs for flavor mode. Deterministic given stored runs."""
    excerpts: List[str] = []
    remaining = max_chars

    for rid in ref_ids:
        if remaining <= 0:
            break
        try:
            payload = load_run(rid)
        except Exception:
            continue

        session = payload.get("session") or {}
        turns = session.get("turns") or []
        if not turns:
            continue

        slice_turns = turns[-max_turns_per_run:]
        parts: List[str] = []
        for t in slice_turns:
            s = (t.get("seller") or "").strip()
            c = (t.get("customer") or "").strip()
            if s:
                parts.append(f"Seller: {s}")
            if c:
                parts.append(f"Customer: {c}")
        text = "\n".join(parts).strip()
        if not text:
            continue

        header = f"[Reference run {str(rid)[:8]}]\n"
        block = header + text

        if len(block) > remaining:
            block = block[:remaining]

        excerpts.append(block)
        remaining -= len(block)

    return excerpts


def load_pack(pack_dir: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for fn in os.listdir(pack_dir):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(pack_dir, fn)
        with open(p, "r", encoding="utf-8") as f:
            out[fn] = json.load(f)
    return out


def _persona_to_dict(persona_obj: Any) -> Dict[str, Any]:
    # persona_engine Persona dataclass -> jsonable dict
    if hasattr(persona_obj, "__dict__"):
        return to_jsonable(persona_obj.__dict__)
    try:
        return to_jsonable(persona_obj)
    except Exception:
        return {"repr": repr(persona_obj)}


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
    pack_hash = stable_hash(pack)

    overrides_hash = stable_hash(overrides)

    run_key = stable_hash(
        {
            "seed": seed,
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
        "seed": seed,
        "run_key": run_key,
        "pack_hash": pack_hash,
        "overrides_hash": overrides_hash,
        "buyer_profile_hash": bp_hash,
        "mode": mode,
        "llm_model": llm_model if mode in ["flavor", "freeplay"] else "",
        "persona_prompt": persona_prompt,
        "persona": persona,
        "buyer_profile": buyer_profile_to_dict(bp),
        "session": session_to_dict(session),
        "score": None,
        "llm_cache": {},
        "reference_set": ref_ids,
        "reference_excerpts": _build_reference_excerpts(ref_ids) if mode == "flavor" else [],
        "reference_set_hash": ref_hash,
        "reference_k": reference_k,
    }

    save_run(run_id, payload)
    return run_id, payload


def _cache_key(run_payload: Dict[str, Any], turn_index: int, seller_text: str) -> str:
    seller_hash = stable_hash({"seller": seller_text})
    return stable_hash(
        {
            "run_key": run_payload.get("run_key", ""),
            "mode": run_payload.get("mode", ""),
            "llm_model": run_payload.get("llm_model", ""),
            "reference_set_hash": run_payload.get("reference_set_hash", ""),
            "turn_index": turn_index,
            "seller_hash": seller_hash,
        }
    )


def _append_freeplay_turn(run_payload: Dict[str, Any], seller_text: str) -> Dict[str, Any]:
    session = run_payload["session"]
    turns = session.get("turns", [])
    turn_index = len(turns)

    cache: Dict[str, str] = run_payload.get("llm_cache") or {}
    ck = _cache_key(run_payload, turn_index, seller_text)

    err: str | None = None
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
            reference_excerpts=run_payload.get("reference_excerpts", []),
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
    extra_tags = [f"llm_{run_payload.get('mode', 'freeplay')}"]
    if err:
        extra_tags.append(f"llm_fallback:{err}")

    new_turn = {
        "turn_index": turn_index,
        "seller": seller_text,
        "customer": customer_text,
        "tags": tags + extra_tags,
    }
    turns.append(new_turn)
    session["turns"] = turns
    run_payload["session"] = session
    return run_payload


def step_run(run_payload: Dict[str, Any], seller_text: str) -> Dict[str, Any]:
    mode = run_payload.get("mode", "strict")

    if mode in ("freeplay", "flavor"):
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

    session["_internal_state"] = ss.__dict__.get("_internal_state", {})
    session["turns"] = [t.__dict__ for t in ss.turns]

    run_payload["session"] = session
    score = score_session(session)
    run_payload["score"] = score_to_dict(score)
    return run_payload
