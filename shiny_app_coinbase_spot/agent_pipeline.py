# agent_pipeline.py
# Three-agent orchestration with tool loop, JSONL audit, disclaimer enforcement,
# structured Agent 2 extraction, and contradiction detection.
# Coinbase Spot Reporter — Apps V2 + V3
# Prof. Tim Fraser pattern

# Topic: Agent 1 uses tools (market JSON + RAG + alert action) and writes
# field-cited bullets. Agent 2 emits a one-line decision header + rationale and
# a small machine-readable JSON. Agent 3 produces an audience-tuned, 3-line brief.

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import requests

from coinbase_query import CandleQueryConfig
from market_agent_tools import (
    ollama_tool_definitions,
    parse_function_arguments,
    run_market_tool,
    summarize_df_for_tools,
)

_LOG_DIR = Path(__file__).resolve().parent / "output"
_RUN_LOG = _LOG_DIR / "agent_runs.jsonl"

DEFAULT_DISCLAIMER = (
    "Reminder: this AI summary is informational only and is not investment advice; "
    "verify against primary data and follow your firm's compliance policy."
)

Audience = Literal["desk", "risk", "retail"]


AGENT1_SYSTEM = """You are Agent 1 — Market Data Analyst.

Tool order (mandatory):
1. `fetch_market_metrics` once.
2. `search_playbook` at least once for thresholds, regime guidance, or disclaimer wording.
3. `flag_threshold_alert` only when the snapshot clearly meets a documented playbook threshold.

After tools return, write markdown with EXACTLY these sections (in order):

**As of** <latest_start_time_utc> — <product_id>

**Snapshot facts** — at most 6 bullets. Each bullet uses this EXACT shape so a non-expert reader gets value + meaning + confidence on one line:

`- <Friendly label>: <value> (<plain-English meaning>) [confidence]`

Examples:
- Lookback return: 22.13% (Total percent change in price across the whole lookback window) [high]
- Volatility (lookback): 2.36% (How choppy each candle was on average — std-dev of one-bar returns. Higher = more turbulence) [high]
- Relative volume: 0.48 (Latest candle volume vs the average of prior candles; 1.00 = normal, below 1 = quieter than usual) [high]

Rules for each bullet:
- The plain-English meaning in parentheses MUST come verbatim (or paraphrased only to fit) from the snapshot's `glossary` object for the field you are quoting.
- Confidence tags: `[high]` when the JSON field is non-null, `[low]` when null, `[medium]` when derived from another field.
- For any null field, write `not available` instead of a number and tag it `[low]`.

NUMBER FORMATTING (mandatory, reader-friendly):
- The JSON snapshot is already pre-rounded — copy values verbatim, never invent extra decimals.
- Percent fields (anything ending in `_pct`): show 2 decimals followed by `%`, e.g. `22.13%`, `-5.39%`, `2.36%`. NEVER write `22.126261440976293`.
- Ratios (e.g. `relative_volume_lookback`): 2 decimals, no unit, e.g. `0.48`.
- Prices and lookback high/low: 2 decimals + ` USD`, e.g. `67,123.45 USD`. Use a comma thousands separator if the integer part is ≥ 1,000.
- USD volume: integer with thousands separator, e.g. `12,345,678 USD`.

**Playbook context** — up to 3 paraphrased bullets, each citing a section title from `search_playbook`, e.g. (section: Alert thresholds).

**Alerts triggered** — list each `flag_threshold_alert` you called as `metric direction threshold (value)`, formatted with the same rounding rules above, or write "none".

**Data gaps** — one sentence on what the snapshot does not cover.

Hard constraints:
- Do not produce trading recommendations, price targets, or forecasts.
- Do not use words like "will", "should buy", "should sell".
- If a JSON field is null, do NOT cite a value for it; mark it [low] and skip the number."""


AGENT2_SYSTEM = """You are Agent 2 — Risk and Regime Analyst.

Inputs (in user message):
1. The JSON snapshot Agent 1 used.
2. Agent 1's bullets and alerts.

Output format (markdown), EXACTLY in this order:

LINE 1 (decision row, single line, no markdown):
Regime: <calm|transitional|elevated> | Liquidity: <thin|normal|elevated> | Range: <near low|mid|near high>

**Rationale** — 3 short bullets that compare snapshot fields to playbook thresholds explicitly.
Use 2 decimals and `%` on percent fields, plain decimals on ratios. Examples:
- volatility_lookback_pct = 3.40% > 3.00% threshold → elevated regime.
- relative_volume_lookback = 2.60 > 2.00 → liquidity elevated, monitor.
- distance_from_lookback_high_pct = -0.40% → close near recent high.

**Watch list** — up to 3 bullets like `Monitor: <metric> over next <N> candles`. No trading advice.

**Limits** — one sentence on what this snapshot cannot tell us.

After the markdown, append a fenced code block tagged json with this exact shape and keys (use null when missing):

```json
{
  "regime": "calm|transitional|elevated|null",
  "liquidity": "thin|normal|elevated|null",
  "range_position": "near low|mid|near high|null",
  "watch_list": ["..."]
}
```

Hard constraints:
- Use only the JSON snapshot and Agent 1 text for facts.
- If a required field is null in the snapshot, write "insufficient fields" in the matching JSON value.
- Do NOT use forecasting language (will, should, expect, target).
- Do NOT recommend trades."""


AGENT3_SYSTEM_TEMPLATE = """You are Agent 3 — Executive Briefing Officer.

You write briefings for an audience of: {audience_label}.

Inputs (in user message): Agent 2's decision row, rationale, watch list, and the original task.

Output (markdown), EXACTLY in this 3-line format:

**As of** <latest_start_time_utc> — <product_id>

**What we see** — one sentence; reuse at least one phrase verbatim from Agent 2.
**What it means** — one sentence translated for the audience above; no new numbers.
**What we're monitoring** — one short sentence based on Agent 2's watch list.

End with a single line beginning "Reminder:" stating this is informational and not investment advice.

Audience tone:
- desk: short, operational, plain.
- risk: governance-flavored; mention controls or escalation only if Agent 2 implies it.
- retail: plain English; avoid jargon (no "regime", "liquidity"; use "calm/active market", "trading volume").

Hard constraints:
- No new numbers beyond those already present in Agent 2's text.
- No predictions, price targets, or buy/sell language."""


def _audience_label(audience: Audience) -> str:
    return {
        "desk": "trading desk operators",
        "risk": "risk and compliance staff",
        "retail": "non-expert end users",
    }.get(audience, "trading desk operators")


def _chat(
    *,
    host: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    url = host.rstrip("/") + "/api/chat"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
    if tools is not None:
        body["tools"] = tools
    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _run_tool_loop_agent1(
    *,
    task: str,
    df: pd.DataFrame,
    cfg: CandleQueryConfig,
    host: str,
    api_key: str,
    model: str,
    max_rounds: int = 8,
) -> tuple[str, list[dict[str, Any]], int, list[dict[str, Any]]]:
    """Returns (final_text, message_trace, api_calls, tool_events)."""
    tools = ollama_tool_definitions()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT1_SYSTEM},
        {"role": "user", "content": task},
    ]
    api_calls = 0
    final_text = ""
    tool_events: list[dict[str, Any]] = []

    for _ in range(max_rounds):
        api_calls += 1
        data = _chat(host=host, api_key=api_key, model=model, messages=messages, tools=tools)
        msg = dict(data.get("message") or {})
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                if not isinstance(fn, dict):
                    fn = {}
                name = str(fn.get("name") or "")
                args = parse_function_arguments(fn.get("arguments"))
                result = run_market_tool(name, args, df=df, cfg=cfg)
                tool_events.append({"tool": name, "args": args, "result_chars": len(result)})
                tool_msg: dict[str, Any] = {"role": "tool", "content": result}
                if name:
                    tool_msg["name"] = name
                tid = tc.get("id")
                if tid:
                    tool_msg["tool_call_id"] = tid
                messages.append(tool_msg)
            continue
        final_text = (msg.get("content") or "").strip()
        break

    return final_text, messages, api_calls, tool_events


def _run_plain_agent(
    *,
    system: str,
    user: str,
    host: str,
    api_key: str,
    model: str,
) -> tuple[str, int]:
    data = _chat(
        host=host,
        api_key=api_key,
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        tools=None,
    )
    msg = data.get("message") or {}
    return (msg.get("content") or "").strip(), 1


def _enforce_disclaimer(text: str) -> tuple[str, bool]:
    """Append the canonical disclaimer if Agent 3 forgot one."""
    lowered = (text or "").lower()
    if "not investment advice" in lowered or "reminder:" in lowered:
        return text, False
    sep = "\n\n" if text and not text.endswith("\n") else ""
    return f"{text}{sep}{DEFAULT_DISCLAIMER}", True


def _extract_agent2_structured(text: str) -> dict[str, Any]:
    """Parse the json fenced block from Agent 2; return {} on failure."""
    if not text:
        return {}
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return {}
    raw = match.group(1)
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _detect_contradictions(
    structured: dict[str, Any],
    tool_events: list[dict[str, Any]],
) -> list[str]:
    """Heuristic checks: flag obvious mismatches between Agent 2 and Agent 1 actions."""
    issues: list[str] = []
    regime = str(structured.get("regime") or "").lower()
    fired_alerts = [e for e in tool_events if e.get("tool") == "flag_threshold_alert"]
    if regime == "calm" and fired_alerts:
        issues.append(
            "Agent 2 classified regime=calm but Agent 1 fired threshold alert(s); "
            "either regime should escalate or alert was unwarranted."
        )
    liquidity = str(structured.get("liquidity") or "").lower()
    if liquidity == "elevated" and regime == "calm":
        issues.append("liquidity=elevated with regime=calm — review consistency.")
    return issues


def _append_run_log(record: dict[str, Any]) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _RUN_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Logging must never break the user-facing pipeline
        pass


def run_three_agent_pipeline(
    *,
    task: str,
    df: pd.DataFrame,
    cfg: CandleQueryConfig,
    host: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    audience: Audience = "desk",
) -> dict[str, Any]:
    """Full V2 orchestration + V3 evidence (log, disclaimer, structured + contradictions)."""
    host = host or os.getenv("OLLAMA_HOST", "https://ollama.com")
    api_key = api_key or os.getenv("OLLAMA_API_KEY", "")
    model = model or os.getenv("OLLAMA_MODEL", "nemotron-3-nano:30b-cloud")
    if not api_key:
        return {
            "status": "error",
            "detail": "OLLAMA_API_KEY is not set (add to .env or Streamlit secrets).",
        }

    run_id = str(uuid.uuid4())
    started_at = datetime.now(UTC).isoformat()
    metrics_snapshot = summarize_df_for_tools(df, cfg)
    metrics_json = json.dumps(metrics_snapshot, indent=2)

    try:
        a1_text, trace1, n1, tool_events = _run_tool_loop_agent1(
            task=task,
            df=df,
            cfg=cfg,
            host=host,
            api_key=api_key,
            model=model,
        )

        risk_user = (
            f"=== JSON snapshot (ground truth) ===\n{metrics_json}\n\n"
            f"=== Agent 1 report ===\n{a1_text}\n"
        )
        a2_text, n2 = _run_plain_agent(
            system=AGENT2_SYSTEM, user=risk_user, host=host, api_key=api_key, model=model
        )

        structured = _extract_agent2_structured(a2_text)
        contradictions = _detect_contradictions(structured, tool_events)

        agent3_system = AGENT3_SYSTEM_TEMPLATE.format(audience_label=_audience_label(audience))
        exec_user = (
            f"Agent 2 analysis:\n{a2_text}\n\n"
            f"Original task:\n{task}\n"
            f"Time anchor: latest_start_time_utc={metrics_snapshot.get('latest_start_time_utc')} "
            f"product_id={metrics_snapshot.get('product_id')}\n"
        )
        a3_text_raw, n3 = _run_plain_agent(
            system=agent3_system, user=exec_user, host=host, api_key=api_key, model=model
        )
        a3_text, disclaimer_appended = _enforce_disclaimer(a3_text_raw)

    except requests.HTTPError as exc:
        return {
            "status": "error",
            "detail": f"Ollama HTTP error: {exc}",
            "ollama_model": model,
        }
    except requests.RequestException as exc:
        return {
            "status": "error",
            "detail": f"Network error talking to Ollama: {exc}",
            "ollama_model": model,
        }

    tool_names = [evt["tool"] for evt in tool_events]

    payload: dict[str, Any] = {
        "status": "ok",
        "run_id": run_id,
        "started_at_utc": started_at,
        "task": task,
        "audience": audience,
        "agent1_data_analyst": a1_text,
        "agent2_risk": a2_text,
        "agent2_structured": structured,
        "agent3_executive": a3_text,
        "agent3_disclaimer_appended": disclaimer_appended,
        "contradictions": contradictions,
        "ollama_model": model,
        "api_calls": n1 + n2 + n3,
        "api_calls_breakdown": {"agent1": n1, "agent2": n2, "agent3": n3},
        "tools_used": tool_names,
        "tool_events": tool_events,
        "trace_message_count": len(trace1),
        "metrics_snapshot": metrics_snapshot,
    }

    _append_run_log(
        {
            "run_id": run_id,
            "started_at_utc": started_at,
            "product_id": cfg.product_id,
            "granularity_seconds": cfg.granularity_seconds,
            "audience": audience,
            "ollama_model": model,
            "tools_used": tool_names,
            "api_calls": payload["api_calls"],
            "agent2_regime": structured.get("regime"),
            "agent2_liquidity": structured.get("liquidity"),
            "agent3_disclaimer_appended": disclaimer_appended,
            "contradictions": contradictions,
        }
    )

    return payload
