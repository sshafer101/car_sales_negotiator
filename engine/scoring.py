from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class ScoreBreakdown:
    total: int
    discovery: int
    objection_handling: int
    trust: int
    efficiency: int
    constraint_accuracy: int
    deal_quality: int
    coaching: List[str]
    detected_constraints: List[str]
    missed_constraints: List[str]


def _has_any(text: str, words: List[str]) -> bool:
    t = text.lower()
    return any(w in t for w in words)


def score_session(session: Dict[str, Any]) -> ScoreBreakdown:
    turns = session.get("turns", [])
    bp = session.get("buyer_profile", {})
    constraints = (bp.get("constraints") or {})
    musts = constraints.get("must_have_features", [])
    dealbreakers = constraints.get("dealbreakers", [])

    seller_text = " ".join([t.get("seller", "") for t in turns]).lower()

    asked_budget = _has_any(seller_text, ["budget", "out the door", "otd", "price"])
    asked_payment = _has_any(seller_text, ["payment", "per month", "monthly"])
    asked_down = _has_any(seller_text, ["down", "cash down"])
    asked_trade = _has_any(seller_text, ["trade", "trade-in", "trade in"])
    asked_features = _has_any(seller_text, ["features", "must-have", "awd", "4wd", "third row", "carplay", "mpg", "safety", "tow"])
    transparency = _has_any(seller_text, ["fee", "fees", "breakdown", "transparent", "out the door total"])

    discovery = 0
    discovery += 8 if asked_budget else 0
    discovery += 8 if asked_payment else 0
    discovery += 5 if asked_down else 0
    discovery += 5 if asked_trade else 0
    discovery += 6 if asked_features else 0
    discovery = min(discovery, 30)

    objection_handling = 0
    objection_handling += 5 if transparency else 0
    objection_handling += 5 if _has_any(seller_text, ["compare", "what would make you comfortable", "help me understand"]) else 0
    objection_handling = min(objection_handling, 15)

    trust = 0
    trust += 8 if transparency else 0
    trust += 4 if _has_any(seller_text, ["no pressure", "take your time", "happy to"]) else 0
    trust += -10 if _has_any(seller_text, ["today only", "sign now", "last chance"]) else 0
    trust = max(min(trust, 15), 0)

    n_turns = max(len(turns) - 1, 0)
    if n_turns <= 6:
        efficiency = 15
    elif n_turns <= 10:
        efficiency = 10
    else:
        efficiency = 5

    detected: List[str] = []
    missed: List[str] = []

    def mention_any(items: List[str]) -> bool:
        for it in items:
            token = it.replace("_", " ")
            if token in seller_text:
                return True
        return False

    for key in ["budget_max_otd", "payment_target_monthly", "down_payment", "credit_band", "urgency", "trade_in_status"]:
        if key.replace("_", " ") in seller_text or key.split("_")[0] in seller_text:
            detected.append(key)
        else:
            missed.append(key)

    if mention_any(musts):
        detected.append("must_have_features")
    else:
        missed.append("must_have_features")

    if mention_any(dealbreakers):
        detected.append("dealbreakers")
    else:
        missed.append("dealbreakers")

    constraint_accuracy = min(2 * len(set(detected)), 15)

    deal_quality = 0
    if _has_any(seller_text, ["out the door", "otd"]):
        deal_quality += 5
    if not _has_any(seller_text, ["today only", "sign now"]):
        deal_quality += 5
    deal_quality = min(deal_quality, 10)

    coaching: List[str] = []
    if not asked_budget:
        coaching.append("Ask for an out-the-door budget early.")
    if not asked_payment:
        coaching.append("Confirm the monthly payment target and term assumptions.")
    if not asked_features:
        coaching.append("Clarify must-have features before presenting options.")
    if not transparency:
        coaching.append("Offer a clear fee breakdown and out-the-door total.")
    if _has_any(seller_text, ["today only", "sign now", "last chance"]):
        coaching.append("Avoid pressure language. It reduces trust and score.")

    total = discovery + objection_handling + trust + efficiency + constraint_accuracy + deal_quality
    total = min(total, 100)

    return ScoreBreakdown(
        total=total,
        discovery=discovery,
        objection_handling=objection_handling,
        trust=trust,
        efficiency=efficiency,
        constraint_accuracy=constraint_accuracy,
        deal_quality=deal_quality,
        coaching=coaching,
        detected_constraints=sorted(set(detected)),
        missed_constraints=sorted(set(missed)),
    )


def score_to_dict(score: ScoreBreakdown) -> Dict[str, Any]:
    return asdict(score)
