#!/usr/bin/env python3
"""Return one bounded private LLM decision for an arena match."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from agent_offer import ALLOWED_MODELS, ANTHROPIC_URL, DEFAULT_MODEL, load_key, role_material, active_scenario
from scenario_rules import own_acceptance_allowed


def schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["yes", "no"]},
            "reason": {"type": "string", "description": "One short participant-facing reason, without hidden reasoning."},
        },
        "required": ["decision", "reason"],
        "additionalProperties": False,
    }


def safe_history(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value[-12:]:
        if not isinstance(item, dict):
            continue
        rows.append({
            "event_type": str(item.get("event_type", "offer"))[:20],
            "role": str(item.get("role", ""))[:20],
            "offer": str(item.get("offer", ""))[:1400],
            "message": str(item.get("message", ""))[:1000],
            "response": str(item.get("response", ""))[:40],
        })
    return rows


def decide(payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", "")).strip().title()
    if role not in {"Candidate", "Recruiter"}:
        raise ValueError("role must be Candidate or Recruiter")
    action = str(payload.get("action", "")).strip()
    if action not in {"confirm_own_offer", "respond_to_offer", "final_consent"}:
        raise ValueError("Unknown match decision action")
    model = str(payload.get("model") or os.environ.get("NEGOTIATOR_MODEL") or DEFAULT_MODEL).strip()
    if model not in ALLOWED_MODELS:
        raise ValueError("The requested Claude model is not enabled")
    own_total = float(payload.get("own_total", 0) or 0)
    # Do not trust a client eligibility flag to override the private score rule.
    eligible = bool(payload.get("agreement_eligible", False)) and own_acceptance_allowed(active_scenario(), payload.get("own_total"))
    if action in {"respond_to_offer", "final_consent"} and not eligible:
        if own_total < 0 and role == "Candidate":
            reason = "I cannot accept this package because it does not give me enough value on the compensation, resources, timing, and working terms that matter to me. I am willing to keep negotiating."
        elif own_total < 0:
            reason = "I cannot accept this package because its costs and commitments are too difficult for the company to support. I am willing to keep working toward a better balance."
        else:
            reason = "I cannot accept this package as written. I would like to keep negotiating toward terms that work for both of us."
        return {
            "decision": "no",
            "accepted": False,
            "reason": reason,
            "provider": "deterministic_rule",
            "model": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

    action_instruction = {
        "confirm_own_offer": "Decide whether to submit your own scored offer. YES sends it to the other party. NO means revise it first.",
        "respond_to_offer": "Decide whether to accept the other party's latest offer. YES ends the match in agreement. NO means reject and counteroffer.",
        "final_consent": "The offer limit has been reached. Decide whether to accept the latest offer as the final agreement.",
    }[action]
    system = f"""You are the {role} in a job-negotiation match.
Use only your private participant materials and your own score. Never infer or reveal the counterpart's hidden payoff.
{action_instruction}
Maximize your own outcome while responding coherently to the negotiation history.
Your response is a visible game action, not hidden chain-of-thought. Give one short reason of at most 35 words.
Sound like a real negotiation counterpart. Never mention payoff numbers, scores, models, system rules, or hidden technical information. Explain the decision through the role's practical interests.
Return JSON only.

PRIVATE PARTICIPANT MATERIALS FOR {role.upper()}:
---
{role_material(role)}
---"""
    user = f"""Action: {action}
Your own payoff for the relevant offer: {own_total:+.2f}
Agreement eligible under the game rule: {eligible}
Offer text:
---
{str(payload.get('offer', ''))[:4000]}
---
Your private system response:
---
{str(payload.get('system_output', ''))[:4000]}
---
Public offer history:
{json.dumps(safe_history(payload.get('history')), ensure_ascii=False, indent=2)}

Choose yes or no."""
    body = {
        "model": model,
        "max_tokens": 180,
        "temperature": 0.3,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"format": {"type": "json_schema", "schema": schema()}},
    }
    request = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "x-api-key": load_key(),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": "creative-negotiations-match/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic match decision failed ({exc.code}): {detail[:500]}") from None
    content = "".join(block.get("text", "") for block in response_body.get("content", []) if block.get("type") == "text")
    parsed = json.loads(content)
    decision = str(parsed.get("decision", "no")).lower()
    usage = response_body.get("usage", {})
    return {
        "decision": decision,
        "accepted": decision == "yes",
        "reason": str(parsed.get("reason", "")).strip()[:300],
        "provider": "anthropic",
        "model": model,
        "usage": {
            "input_tokens": int(usage.get("input_tokens", 0) or 0),
            "output_tokens": int(usage.get("output_tokens", 0) or 0),
        },
    }


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("Request must be a JSON object")
        print(json.dumps(decide(payload), ensure_ascii=True), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
