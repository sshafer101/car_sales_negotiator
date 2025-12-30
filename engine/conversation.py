from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
import random
import re
from datetime import datetime, timezone

from .buyer_profile import BuyerProfile, buyer_profile_to_dict, BuyerConstraints, BuyerStyle


@dataclass
class Turn:
    turn_index: int
    seller: str
    customer: str
    tags: List[str]


@dataclass
class SessionState:
    seed: int
    run_key: str
    mode: str
    created_at: str
    persona: Dict[str, Any]
    persona_prompt: str
    buyer_profile: Dict[str, Any]
    buyer_profile_hash: str
    turns: List[Turn]
    outcome: Optional[str]
    notes: List[str]


SAFE_REDIRECT = (
    "I want to keep this professional. Let's focus on the car needs, budget, and a fair deal. "
    "What are you hoping to keep your monthly payment around?"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _detect_disallowed(text: str) -> bool:
    lowered = text.lower()
    disallowed = [
        "race",
        "religion",
        "ethnicity",
        "sexual",
        "fake paystub",
        "forge",
        "fraud",
        "lie on the credit",
        "illegal",
    ]
    return any(x in lowered for x in disallowed)


def _extract_money(text: str) -> List[int]:
    vals: List[int] = []
    for m in re.findall(r"\$?\s*([0-9]{2,6})", text.replace(",", "")):
        try:
            vals.append(int(m))
        except Exception:
            continue
    return vals


def _extract_keywords(text: str) -> List[str]:
    t = text.lower()
    hits: List[str] = []
    keys = [
        ("budget", ["budget", "out the door", "otd", "price"]),
        ("payment", ["monthly", "payment", "per month"]),
        ("down_payment", ["down", "cash down", "put down"]),
        ("trade_in", ["trade", "trade-in", "trade in"]),
        ("timeline", ["today", "this week", "two weeks", "urgent", "timeline"]),
        ("features", ["awd", "4wd", "third row", "carplay", "mpg", "safety", "tow"]),
        ("trust", ["fee", "fees", "transparent", "breakdown", "no pressure"]),
    ]
    for tag, words in keys:
        if any(w in t for w in words):
            hits.append(tag)
    return hits


def _customer_opening(bp: BuyerProfile) -> str:
    c = bp.constraints
    s = bp.style

    if s.trust_baseline == "low_trust":
        opener = "Hey. Before we start, I just want this to be straightforward. I've had some rough dealer experiences."
    elif s.trust_baseline == "high_trust":
        opener = "Hey. Thanks for your time. I can tell you what I'm looking for and you can tell me what's realistic."
    else:
        opener = "Hey. I’m shopping around and trying to see what fits."

    if c.urgency in ["needs_today", "needs_this_week"]:
        urgency = "I do need to move fairly soon."
    elif c.urgency == "needs_within_2_weeks":
        urgency = "I’d like to figure something out within the next couple weeks."
    else:
        urgency = "I’m not rushing, but I’m serious if it makes sense."

    return f"{opener} {urgency}"


def _customer_reply(rng: random.Random, bp: BuyerProfile, seller_text: str, internal_state: Dict[str, Any]) -> Tuple[str, List[str]]:
    tags = _extract_keywords(seller_text)
    c = bp.constraints
    s = bp.style

    if _detect_disallowed(seller_text):
        return SAFE_REDIRECT, ["guardrail"]

    seller_lower = seller_text.lower()

    reveal_budget = ("budget" in tags) or ("out the door" in seller_lower) or ("otd" in seller_lower)
    reveal_down = ("down_payment" in tags) or ("down" in seller_lower)
    reveal_trade = ("trade_in" in tags) or ("trade" in seller_lower)
    reveal_features = ("features" in tags) or ("feature" in seller_lower)

    if s.objection_style == "payment_focused_skeptical":
        base = "I care most about the monthly payment and the total out-the-door price."
    elif s.objection_style == "trust_sensitive_needs_transparency":
        base = "I need everything broken down. I don't want surprises in the fees."
    elif s.objection_style == "feature_focused_picky":
        base = "I can be picky. If it doesn't match what I need, it's not worth it."
    elif s.objection_style == "conflict_avoidant_wants_to_think":
        base = "I don't want to rush. I need to think and compare calmly."
    else:
        base = "I'm comparing options and I don't want to overpay."

    response_parts = [base]

    if reveal_budget and not internal_state.get("revealed_budget"):
        response_parts.append(f"My max out-the-door budget is ${c.budget_max_otd}.")
        internal_state["revealed_budget"] = True

    if reveal_down and not internal_state.get("revealed_down"):
        response_parts.append(f"I can put about ${c.down_payment} down.")
        internal_state["revealed_down"] = True

    if reveal_trade and not internal_state.get("revealed_trade"):
        response_parts.append(f"For trade-in, it's {c.trade_in_status.replace('_', ' ')}.")
        internal_state["revealed_trade"] = True

    if reveal_features and not internal_state.get("revealed_features"):
        feats = ", ".join([f.replace("_", " ") for f in c.must_have_features])
        response_parts.append(f"Must-haves for me are: {feats}.")
        internal_state["revealed_features"] = True
        
    
    if (("payment" in tags) or ("budget" in tags)) and not internal_state.get("revealed_payment"):
        internal_state["revealed_payment"] = True
        return f"{base} I'm trying to stay around ${c.payment_target_monthly}/month.", tags


    pressure_words = ["today only", "sign now", "right now", "last chance"]
    if any(w in seller_lower for w in pressure_words):
        response_parts.append("That feels pushy. If we can't keep this calm, I'll walk.")

    if ("fee" in seller_lower or "fees" in seller_lower or "breakdown" in seller_lower) and ("asks_for_fee_breakdown" in s.negotiation_tactics):
        response_parts.append("Can you list the fees line by line and the out-the-door total?")

    nums = _extract_money(seller_text)
    if nums and ("payment" in tags):
        offered = nums[0]
        if offered > c.payment_target_monthly:
            response_parts.append(f"That's higher than my ${c.payment_target_monthly}/month target.")

    return " ".join(response_parts), tags


def new_session(
    seed: int,
    run_key: str,
    persona: Dict[str, Any],
    persona_prompt: str,
    buyer_profile: BuyerProfile,
    buyer_profile_hash: str,
) -> SessionState:
    st = SessionState(
        seed=seed,
        run_key=run_key,
        mode="strict",
        created_at=_now_iso(),
        persona=persona,
        persona_prompt=persona_prompt,
        buyer_profile=buyer_profile_to_dict(buyer_profile),
        buyer_profile_hash=buyer_profile_hash,
        turns=[],
        outcome="ongoing",
        notes=[],
    )
    opening = _customer_opening(buyer_profile)
    st.turns.append(Turn(turn_index=0, seller="", customer=opening, tags=["opening"]))
    st.__dict__["_internal_state"] = {}
    return st


def step_session(session: SessionState, seller_text: str) -> SessionState:
    turn_index = len(session.turns)
    rng_seed = abs(hash(f"{session.run_key}:{turn_index}")) % (2**31 - 1)
    rng = random.Random(rng_seed)

    internal_state = session.__dict__.setdefault("_internal_state", {})
    if not isinstance(internal_state, dict):
        internal_state = {}
        session.__dict__["_internal_state"] = internal_state

    bp_dict = session.buyer_profile
    c = BuyerConstraints(**bp_dict["constraints"])
    s = BuyerStyle(**bp_dict["style"])
    bp = BuyerProfile(constraints=c, style=s, good_exit_path=bp_dict["good_exit_path"])

    customer_text, tags = _customer_reply(rng, bp, seller_text, internal_state)

    session.turns.append(Turn(turn_index=turn_index, seller=seller_text, customer=customer_text, tags=tags))

    if "walk" in customer_text.lower():
        session.outcome = "bad_exit"

    if "appointment" in seller_text.lower() or "follow up" in seller_text.lower():
        if session.outcome == "ongoing":
            session.outcome = "good_exit"

    if "deal" in seller_text.lower() and ("out the door" in seller_text.lower() or "otd" in seller_text.lower()):
        if session.outcome == "ongoing":
            session.outcome = "deal"

    return session


def session_to_dict(session: SessionState) -> Dict[str, Any]:
    d = asdict(session)
    if "_internal_state" in session.__dict__:
        d["_internal_state"] = session.__dict__["_internal_state"]
    return d
