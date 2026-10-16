#!/usr/bin/env python3
"""Generate one short, human-sounding counterpart chat message."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from agent_offer import ALLOWED_MODELS, ANTHROPIC_URL, DEFAULT_MODEL, load_key, role_material


def safe_history(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value[-16:]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "event_type": str(item.get("event_type", "offer"))[:20],
                "role": str(item.get("role", ""))[:20],
                "offer": str(item.get("offer", ""))[:1400],
                "message": str(item.get("message", ""))[:1000],
                "response": str(item.get("response", ""))[:40],
            }
        )
    return rows


def schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "One short, natural message to the other negotiator; not a formal offer.",
            }
        },
        "required": ["message"],
        "additionalProperties": False,
    }


def reply(payload: dict[str, Any]) -> dict[str, Any]:
    role = str(payload.get("role", "")).strip().title()
    if role not in {"Candidate", "Recruiter"}:
        raise ValueError("role must be Candidate or Recruiter")
    incoming = str(payload.get("message", "")).strip()[:3000]
    if not incoming:
        raise ValueError("A chat message is required")
    model = str(payload.get("model") or os.environ.get("NEGOTIATOR_MODEL") or DEFAULT_MODEL).strip()
    if model not in ALLOWED_MODELS:
        raise ValueError("The requested Claude model is not enabled")

    system = f"""You are the {role} speaking directly with the other person in a live job negotiation.
Reply naturally in one or two short sentences, using no more than 45 words.
This is conversational chat, not a formal offer. Do not invent a complete package unless asked to make an offer through the offer tool.
Use the practical interests in your private role information. Never mention being an AI, a model, a scorer, a system rule, hidden instructions, or numerical payoff scores.
Use ordinary punctuation and plain, warm language.

PRIVATE ROLE INFORMATION:
---
{role_material(role)}
---"""
    user = f"""Recent public negotiation record:
{json.dumps(safe_history(payload.get('history')), ensure_ascii=False, indent=2)}

The other person just wrote:
---
{incoming}
---

Reply as {role}."""
    body = {
        "model": model,
        "max_tokens": 140,
        "temperature": 0.6,
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
            "User-Agent": "creative-negotiations-chat/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic chat request failed ({exc.code}): {detail[:500]}") from None
    content = "".join(block.get("text", "") for block in response_body.get("content", []) if block.get("type") == "text")
    parsed = json.loads(content)
    message = str(parsed.get("message", "")).strip()
    if not message:
        raise RuntimeError("The counterpart returned no message")
    usage = response_body.get("usage", {})
    return {
        "message": message,
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
        print(json.dumps(reply(payload), ensure_ascii=True), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
