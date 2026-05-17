# llm_reviewer.py
# HW3 AI-as-reviewer — rates briefings on stakeholder fit + conciseness (1-5)
# Coinbase Spot Reporter — DSAI 5381

# Topic: separate reviewer LLM (different from writer model) reads each Agent 3
# briefing and returns two ordinal ratings with rationales. This is what makes
# the validator a *qualitative content analysis* tool, not just a regex check.

from __future__ import annotations

import json
import re
from typing import Any

import requests

REVIEWER_SYSTEM = """You are an evaluation reviewer.

You read an executive briefing produced for a stated audience and rate it on
two ordinal scales:

1. STAKEHOLDER_FIT — does the language match the audience?
   - 1 very poor (jargon for retail; vague for desk; uncontrolled for risk)
   - 2 poor
   - 3 acceptable
   - 4 good
   - 5 excellent (clearly tuned to that audience)

2. CONCISENESS — is the briefing short, focused, free of fluff?
   - 1 very verbose / many empty filler sentences
   - 2 verbose
   - 3 acceptable
   - 4 concise
   - 5 very concise (every sentence carries information)

Reply with EXACTLY this JSON shape and nothing else:

{
  "stakeholder_fit": 1-5,
  "conciseness": 1-5,
  "rationale": "one sentence justifying both scores"
}
"""


def _chat(
    *,
    host: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    timeout: float = 90.0,
) -> dict[str, Any]:
    url = host.rstrip("/") + "/api/chat"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model, "messages": messages, "stream": False}
    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _parse_review(text: str) -> dict[str, Any]:
    """Be lenient — pull the JSON block out even if the model adds prose around it."""
    if not text:
        return {}
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def review_briefing(
    *,
    briefing: str,
    audience: str,
    reviewer_host: str,
    reviewer_api_key: str,
    reviewer_model: str = "gpt-oss:120b-cloud",
) -> dict[str, Any]:
    """Score one briefing. Returns dict with stakeholder_fit, conciseness, rationale."""
    user = (
        f"Audience: {audience}\n\n"
        f"=== Briefing under review ===\n{briefing}\n\n"
        f"=== End of briefing ==="
    )

    try:
        data = _chat(
            host=reviewer_host,
            api_key=reviewer_api_key,
            model=reviewer_model,
            messages=[
                {"role": "system", "content": REVIEWER_SYSTEM},
                {"role": "user", "content": user},
            ],
        )
    except requests.RequestException as exc:
        return {
            "stakeholder_fit": None,
            "conciseness": None,
            "rationale": f"reviewer error: {exc}",
            "raw": "",
        }

    raw = (data.get("message") or {}).get("content", "")
    parsed = _parse_review(raw)
    sf = parsed.get("stakeholder_fit")
    co = parsed.get("conciseness")

    def _coerce(v: Any) -> int | None:
        try:
            n = int(round(float(v)))
            return n if 1 <= n <= 5 else None
        except (TypeError, ValueError):
            return None

    return {
        "stakeholder_fit": _coerce(sf),
        "conciseness": _coerce(co),
        "rationale": str(parsed.get("rationale") or "")[:300],
        "raw": raw[:500],
    }
