from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List
import random


@dataclass
class BuyerConstraints:
    budget_max_otd: int
    payment_target_monthly: int
    down_payment: int
    credit_band: str
    urgency: str
    trade_in_status: str
    must_have_features: List[str]
    dealbreakers: List[str]


@dataclass
class BuyerStyle:
    objection_style: str
    negotiation_tactics: List[str]
    trust_baseline: str


@dataclass
class BuyerProfile:
    constraints: BuyerConstraints
    style: BuyerStyle
    good_exit_path: str


def _weighted_pick(rng: random.Random, items: List[Dict[str, Any]]) -> Any:
    values = [i["value"] for i in items]
    weights = [int(i.get("weight", 1)) for i in items]
    return rng.choices(values, weights=weights, k=1)[0]


def _weighted_pick_many(rng: random.Random, items: List[Dict[str, Any]], k: int, unique: bool = True) -> List[Any]:
    picked: List[Any] = []
    attempts = 0
    while len(picked) < k and attempts < 1000:
        v = _weighted_pick(rng, items)
        if not unique or v not in picked:
            picked.append(v)
        attempts += 1
    return picked


def build_buyer_profile(persona: Dict[str, Any], pack: Dict[str, Any], run_rng_seed: int) -> BuyerProfile:
    rng = random.Random(run_rng_seed)

    budgets = pack["budgets_max_otd"]
    payments = pack["payment_targets_monthly"]
    downs = pack["down_payments"]
    credit = pack["credit_bands"]
    musts = pack["must_have_features"]
    dealbreakers = pack["dealbreakers"]
    urgency = pack["urgency_levels"]
    trade = pack["trade_in_status"]
    objection_styles = pack["objection_styles"]
    tactics = pack["negotiation_tactics"]
    trust = pack["trust_baselines"]
    good_exits = pack["good_exit_paths"]

    risk = (persona.get("risk_tolerance") or "").lower()
    fin = (persona.get("financial_attitude") or "").lower()
    tech = (persona.get("tech_savviness") or "").lower()

    budget = _weighted_pick(rng, budgets)
    payment = _weighted_pick(rng, payments)

    if "risk" in risk and "averse" in risk:
        budget = min(int(budget), 35000)
        payment = min(int(payment), 500)

    if "frugal" in fin:
        budget = min(int(budget), 28000)
        payment = min(int(payment), 400)

    down = int(_weighted_pick(rng, downs))
    credit_band = str(_weighted_pick(rng, credit))
    urgency_level = str(_weighted_pick(rng, urgency))
    trade_status = str(_weighted_pick(rng, trade))

    must_count = 2 if "low" in tech else 3
    must_list = _weighted_pick_many(rng, musts, k=must_count, unique=True)

    dealbreaker_count = 2 if ("risk" in risk and "averse" in risk) else 1
    dealbreaker_list = _weighted_pick_many(rng, dealbreakers, k=dealbreaker_count, unique=True)

    objection_style = str(_weighted_pick(rng, objection_styles))
    trust_baseline = str(_weighted_pick(rng, trust))

    tactics_count = 2
    tactic_list = _weighted_pick_many(rng, tactics, k=tactics_count, unique=True)

    good_exit = str(_weighted_pick(rng, good_exits))

    constraints_obj = BuyerConstraints(
        budget_max_otd=int(budget),
        payment_target_monthly=int(payment),
        down_payment=int(down),
        credit_band=credit_band,
        urgency=urgency_level,
        trade_in_status=trade_status,
        must_have_features=list(must_list),
        dealbreakers=list(dealbreaker_list),
    )

    style_obj = BuyerStyle(
        objection_style=objection_style,
        negotiation_tactics=list(tactic_list),
        trust_baseline=trust_baseline,
    )

    return BuyerProfile(constraints=constraints_obj, style=style_obj, good_exit_path=good_exit)


def buyer_profile_to_dict(bp: BuyerProfile) -> Dict[str, Any]:
    return asdict(bp)
