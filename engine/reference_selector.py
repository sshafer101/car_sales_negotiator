from __future__ import annotations

from typing import Any, Dict, List, Tuple
import re

from .storage import list_runs, load_run
from .utils import stable_hash


def _extract_style(run_payload: Dict[str, Any]) -> Tuple[str, str]:
    bp = run_payload.get("buyer_profile") or {}
    style = bp.get("style") or {}
    return (
        str(style.get("objection_style", "")),
        str(style.get("trust_baseline", "")),
    )


def _same_pack(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return str(a.get("pack_hash", "")) != "" and str(a.get("pack_hash", "")) == str(b.get("pack_hash", ""))


def select_reference_set(
    *,
    current_run_key: str,
    current_seed: int,
    current_pack_hash: str,
    current_buyer_profile: Dict[str, Any],
    k: int = 3,
) -> List[str]:
    """
    Deterministically select up to k prior run_ids to use as references.
    Selection is deterministic given the current pool of runs.
    The selected list is frozen into the run payload for replay determinism.
    """
    runs = list_runs(limit=500)

    cur_style = current_buyer_profile.get("style") or {}
    cur_objection = str(cur_style.get("objection_style", ""))
    cur_trust = str(cur_style.get("trust_baseline", ""))

    candidates: List[Dict[str, Any]] = []
    for r in runs:
        if str(r.get("run_key", "")) == str(current_run_key):
            continue
        if str(r.get("seed", -1)) == int(current_seed):
            continue
        if str(r.get("pack_hash", "")) != str(current_pack_hash):
            continue
        if r.get("mode") != "flavor":
            # only use flavor runs for reference tone
            continue

        ro, rt = _extract_style(r)
        # strong match preferred: same objection style
        if ro == cur_objection:
            candidates.append(r)
        # weak match allowed if we have very few
        elif len(candidates) < k:
            candidates.append(r)

    # Deterministic ranking:
    # rank by (style similarity, stable hash of (current_run_key + candidate_run_id))
    ranked: List[Tuple[int, str, str]] = []
    for c in candidates:
        ro, rt = _extract_style(c)
        similarity = 0
        if ro == cur_objection:
            similarity += 2
        if rt == cur_trust:
            similarity += 1
        tiebreak = stable_hash({"cur": current_run_key, "rid": c.get("run_id", "")})
        ranked.append((similarity, tiebreak, str(c.get("run_id"))))

    ranked.sort(key=lambda x: (-x[0], x[1]))
    chosen = [rid for _, _, rid in ranked[:k] if rid and rid != "None"]
    return chosen


def build_reference_excerpts(reference_run_ids: List[str], max_turns_per_run: int = 4) -> List[str]:
    """
    Returns short text excerpts to inject into the prompt.
    Keeps it small to reduce prompt bloat and avoid leaking details.
    """
    excerpts: List[str] = []
    for rid in reference_run_ids:
        try:
            r = load_run(rid)
        except Exception:
            continue

        session = (r.get("session") or {})
        turns = session.get("turns") or []
        # pull last N turns that include seller + customer
        pairs: List[str] = []
        for t in turns:
            seller = (t.get("seller") or "").strip()
            customer = (t.get("customer") or "").strip()
            if not customer:
                continue
            if seller:
                pairs.append(f"SELLER: {seller}\nCUSTOMER: {customer}")
            else:
                pairs.append(f"CUSTOMER: {customer}")

        snippet = "\n\n".join(pairs[-max_turns_per_run:])
        if snippet:
            excerpts.append(snippet)

    return excerpts


def reference_set_hash(reference_run_ids: List[str]) -> str:
    return stable_hash({"reference_set": reference_run_ids})
