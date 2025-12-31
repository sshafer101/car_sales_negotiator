# engine/llm_client.py
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import openai
from openai import OpenAI


def _supports_temperature(model: str) -> bool:
    """Some reasoning models reject temperature. Keep logic centralized."""
    m = (model or "").lower()
    # Conservative: omit temperature for gpt-5* family and any model that might reject it.
    return not m.startswith("gpt-5")


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def get_openai_client() -> OpenAI:
    # SDK reads OPENAI_API_KEY from env, Streamlit secrets can populate env in app code
    return OpenAI()


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
        "discriminate",
        "deny service to",
        "steal",
        "threaten",
        "harass",
    ]
    return any(x in lowered for x in disallowed)


def _sanitize_output(text: str) -> str:
    # Keep it short, plain text, no markdown links spam, no weird token soup
    t = text.strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[`*_]{2,}", "", t)
    return t.strip()


def _default_decision() -> Dict[str, Any]:
    return {
        "allow_reveal_constraints": True,
        "avoid_repeat_last_customer_line": True,
        "max_new_constraints_per_turn": 2,
        "tone": "natural",
    }


def build_conversation_context(turns: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for t in turns[-14:]:
        s = (t.get("seller") or "").strip()
        c = (t.get("customer") or "").strip()
        if s:
            lines.append(f"Seller: {s}")
        if c:
            lines.append(f"Customer: {c}")
    return "\n".join(lines).strip()


def build_customer_system_prompt(
    persona_prompt: str,
    buyer_profile: Dict[str, Any],
    reference_excerpts: List[str],
    decision: Dict[str, Any],
) -> str:
    bp_json = json.dumps(buyer_profile, indent=2, sort_keys=True)

    refs = ""
    if reference_excerpts:
        refs = "\n\nReference examples (prior runs, do not copy verbatim, use as guidance):\n"
        refs += "\n\n".join(reference_excerpts)

    return (
        f"{persona_prompt}\n\n"
        "You are the CUSTOMER in a car buying conversation.\n"
        "Stay consistent with the buyer_profile constraints and style.\n"
        "Do not repeat yourself unless the seller asks the same thing again.\n"
        "Do not reveal every constraint immediately. Reveal constraints only when asked or when it is natural.\n"
        "If the seller tries to do anything unsafe, illegal, discriminatory, or manipulative, refuse and steer to safe behavior.\n"
        "Keep responses short. Plain text only.\n\n"
        f"buyer_profile:\n{bp_json}\n\n"
        f"decision:\n{json.dumps(decision, indent=2, sort_keys=True)}"
        f"{refs}"
    )


def build_customer_user_prompt(context: str, seller_message: str, prev_customer_message: str) -> str:
    return (
        "Conversation so far:\n"
        f"{context}\n\n"
        f"Seller just said: {seller_message}\n\n"
        "Now respond as the customer with 1 to 3 sentences.\n"
        "Do not repeat the exact same line as your previous customer message:\n"
        f"{prev_customer_message}\n"
    )


def _repair_customer_reply(
    *,
    reason: str,
    buyer_profile: Dict[str, Any],
    seller_message: str,
    turns: List[Dict[str, Any]],
    persona_prompt: str,
) -> str:
    # Deterministic safe fallback reply that stays buyer-like
    constraints = buyer_profile.get("constraints") or {}
    payment = constraints.get("payment_target_monthly")
    budget = constraints.get("budget_max_otd")
    urgency = constraints.get("urgency")
    pieces: List[str] = []

    if reason == "disallowed_seller":
        pieces.append("I want to keep this professional and straightforward.")
    elif reason == "empty_output":
        pieces.append("Sorry, can you clarify what you mean?")

    if payment:
        pieces.append(f"I'm trying to stay around ${payment}/month.")
    elif budget:
        pieces.append(f"I'm trying to stay under ${budget} out the door.")
    elif urgency:
        pieces.append("I'm shopping around and comparing options.")

    if not pieces:
        pieces.append("I'm shopping around and comparing options.")

    out = " ".join(pieces)
    return _sanitize_output(out)


def customer_reply_llm_freeplay(*args: Any, **kwargs: Any) -> Tuple[str, Optional[str]]:
    """
    Backward compatible wrapper for older conversation_runner imports.
    Returns (text, err_reason). err_reason is only for availability errors.
    """
    if args and len(args) >= 5:
        model = args[0]
        persona_prompt = args[1]
        buyer_profile = args[2]
        turns = args[3]
        seller_message = args[4]
        reference_excerpts = args[5] if len(args) >= 6 else []
        max_output_tokens = kwargs.get("max_output_tokens", 220)
        decision = kwargs.get("decision") or _default_decision()
        prev_customer_message = kwargs.get("prev_customer_message") or ""
        return customer_reply_llm(
            model=model,
            persona_prompt=persona_prompt,
            buyer_profile=buyer_profile,
            turns=turns,
            seller_message=seller_message,
            reference_excerpts=reference_excerpts,
            decision=decision,
            prev_customer_message=prev_customer_message,
            max_output_tokens=max_output_tokens,
        )

    model = kwargs.get("model") or kwargs.get("llm_model") or "gpt-5.2"
    persona_prompt = kwargs.get("persona_prompt", "")
    buyer_profile = kwargs.get("buyer_profile") or {}
    turns = kwargs.get("turns") or []
    seller_message = kwargs.get("seller_message") or kwargs.get("seller_text") or ""
    reference_excerpts = kwargs.get("reference_excerpts") or kwargs.get("references") or []
    max_output_tokens = int(kwargs.get("max_output_tokens", 220))
    decision = kwargs.get("decision") or _default_decision()
    prev_customer_message = kwargs.get("prev_customer_message") or ""

    return customer_reply_llm(
        model=model,
        persona_prompt=persona_prompt,
        buyer_profile=buyer_profile,
        turns=turns,
        seller_message=seller_message,
        reference_excerpts=reference_excerpts,
        decision=decision,
        prev_customer_message=prev_customer_message,
        max_output_tokens=max_output_tokens,
    )


def customer_reply_llm(
    *,
    model: str,
    persona_prompt: str,
    buyer_profile: Dict[str, Any],
    turns: List[Dict[str, Any]],
    seller_message: str,
    reference_excerpts: List[str],
    decision: Dict[str, Any],
    prev_customer_message: str,
    max_output_tokens: int = 220,
) -> Tuple[str, Optional[str]]:
    """
    Returns (text, error_reason_if_unavailable).
    Output quality issues are repaired deterministically and returned with err=None.
    """
    if _detect_disallowed(seller_message):
        repaired = _repair_customer_reply(
            reason="disallowed_seller",
            buyer_profile=buyer_profile,
            seller_message=seller_message,
            turns=turns,
            persona_prompt=persona_prompt,
        )
        return repaired, None

    client = get_openai_client()

    system_prompt = build_customer_system_prompt(persona_prompt, buyer_profile, reference_excerpts, decision)
    context = build_conversation_context(turns)
    user_prompt = build_customer_user_prompt(context, seller_message, prev_customer_message)

    try:
        params: Dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "reasoning": {"effort": "none"},
            "text": {"verbosity": "low"},
            "max_output_tokens": max_output_tokens,
        }

        # Some GPT-5 family models reject temperature. Omit it unless supported.
        if _supports_temperature(model):
            params["temperature"] = 0

        response = client.responses.create(**params)
    except openai.RateLimitError:
        return "", "llm_unavailable_quota"
    except openai.AuthenticationError:
        return "", "llm_unavailable_auth"
    except openai.BadRequestError as e:
        msg = str(getattr(e, "message", "") or str(e))
        if "Unsupported parameter" in msg or "invalid_request_error" in msg:
            return "", "llm_unavailable_bad_request"
        return "", "llm_unavailable_bad_request"
    except (openai.APIConnectionError, openai.APIError):
        return "", "llm_unavailable_network"
    except Exception:
        return "", "llm_unknown_error"

    raw = (response.output_text or "").strip()
    if not raw:
        repaired = _repair_customer_reply(
            reason="empty_output",
            buyer_profile=buyer_profile,
            seller_message=seller_message,
            turns=turns,
            persona_prompt=persona_prompt,
        )
        return repaired, None

    text = _sanitize_output(raw)

    if text and prev_customer_message and decision.get("avoid_repeat_last_customer_line", True):
        if text.strip().lower() == prev_customer_message.strip().lower():
            text = _repair_customer_reply(
                reason="empty_output",
                buyer_profile=buyer_profile,
                seller_message=seller_message,
                turns=turns,
                persona_prompt=persona_prompt,
            )

    return text, None
