# qc_validation.py
# Data + AI output validation for App V3 (production / QC evidence)
# Numeric grounding, disclaimer enforcement, tool usage.

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from coinbase_query import CandleQueryConfig


def _add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append({"check": name, "passed": passed, "detail": detail})


def validate_market_dataframe(df: pd.DataFrame, cfg: CandleQueryConfig) -> dict[str, Any]:
    """Structural checks before AI runs (and for UI evidence)."""
    checks: list[dict[str, Any]] = []

    _add_check(checks, "non_empty", not df.empty, f"rows={0 if df.empty else len(df)}")
    if df.empty:
        return {"ok": False, "checks": checks, "score": 0.0}

    _add_check(
        checks,
        "has_close",
        "latest_close" in df.columns and df["latest_close"].notna().any(),
        "latest_close column populated",
    )
    latest = df.iloc[-1]
    close_val = float(latest["latest_close"])
    _add_check(checks, "positive_close", close_val > 0, f"latest_close={close_val}")

    if cfg.lookback_candles < len(df):
        vol = latest.get("volatility_lookback_pct")
        _add_check(
            checks,
            "lookback_metrics_present",
            vol is not None and not pd.isna(vol),
            "volatility_lookback_pct populated on latest row",
        )

    rel_vol = latest.get("relative_volume_lookback")
    _add_check(
        checks,
        "relative_volume_present",
        rel_vol is not None and not pd.isna(rel_vol),
        "relative_volume_lookback populated on latest row",
    )

    passed_n = sum(1 for c in checks if c["passed"])
    score = passed_n / max(1, len(checks))
    return {
        "ok": all(c["passed"] for c in checks),
        "checks": checks,
        "score": round(score, 3),
    }


def _extract_numbers(text: str) -> list[float]:
    """Pull plausible numeric literals from agent text (strip commas)."""
    if not text:
        return []
    out: list[float] = []
    for raw in re.findall(r"-?\d[\d,]*\.?\d*", text):
        cleaned = raw.replace(",", "")
        if cleaned in {"-", "."}:
            continue
        try:
            out.append(float(cleaned))
        except ValueError:
            continue
    return out


def _flatten_numbers(payload: Any) -> list[float]:
    """Walk nested dict/list structure and collect numeric values."""
    nums: list[float] = []
    if isinstance(payload, dict):
        for v in payload.values():
            nums.extend(_flatten_numbers(v))
    elif isinstance(payload, list):
        for v in payload:
            nums.extend(_flatten_numbers(v))
    elif isinstance(payload, (int, float)) and payload is not None:
        try:
            nums.append(float(payload))
        except (TypeError, ValueError):
            pass
    return nums


def _grounded_fraction(agent_numbers: list[float], snapshot_numbers: list[float]) -> tuple[float, int, int]:
    """Fraction of agent numbers that match a snapshot number within tolerance."""
    if not agent_numbers:
        return 0.0, 0, 0
    matched = 0
    for a in agent_numbers:
        # Allow tiny floating slop (rounded display) and integer literal years/dates etc.
        if any(abs(a - s) <= max(0.01, abs(s) * 0.005) for s in snapshot_numbers):
            matched += 1
    return matched / len(agent_numbers), matched, len(agent_numbers)


def validate_ai_pipeline_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Heuristic QC on multi-agent outputs (evidence for graders / stakeholders)."""
    checks: list[dict[str, Any]] = []

    if payload.get("status") != "ok":
        _add_check(checks, "pipeline_ok", False, str(payload.get("detail", "unknown")))
        return {"ok": False, "checks": checks, "score": 0.0, "summary": {}}

    _add_check(checks, "pipeline_ok", True, "status ok")

    a1 = payload.get("agent1_data_analyst") or ""
    a2 = payload.get("agent2_risk") or ""
    a3 = payload.get("agent3_executive") or ""
    snapshot = payload.get("metrics_snapshot") or {}
    tools = payload.get("tools_used") or []

    _add_check(checks, "agent1_nonempty", len(a1.strip()) >= 80, f"chars={len(a1)}")
    _add_check(checks, "agent2_nonempty", len(a2.strip()) >= 60, f"chars={len(a2)}")
    _add_check(checks, "agent3_nonempty", len(a3.strip()) >= 80, f"chars={len(a3)}")

    snapshot_numbers = _flatten_numbers(snapshot)
    agent_numbers = _extract_numbers(a1)
    grounded_pct, matched, total = _grounded_fraction(agent_numbers, snapshot_numbers)
    _add_check(
        checks,
        "agent1_numeric_grounding",
        grounded_pct >= 0.6 and total >= 2,
        f"matched={matched}/{total} grounded_pct={grounded_pct:.2%}",
    )

    has_disclaimer = (
        "not investment advice" in a3.lower()
        or "reminder:" in a3.lower()
    )
    _add_check(checks, "agent3_has_disclaimer", has_disclaimer, "disclaimer line present in executive briefing")

    _add_check(checks, "tools_used_nonzero", len(tools) > 0, ",".join(tools) if tools else "none")
    _add_check(checks, "tool_fetch_present", "fetch_market_metrics" in tools, "expected data tool")
    _add_check(checks, "tool_rag_present", "search_playbook" in tools, "expected RAG tool")

    structured = payload.get("agent2_structured") or {}
    _add_check(
        checks,
        "agent2_structured_present",
        bool(structured.get("regime")) or bool(structured.get("liquidity")),
        f"keys={sorted(structured.keys())}" if structured else "missing JSON block",
    )

    contradictions = payload.get("contradictions") or []
    _add_check(
        checks,
        "no_contradictions",
        len(contradictions) == 0,
        contradictions[0] if contradictions else "ok",
    )

    passed_n = sum(1 for c in checks if c["passed"])
    score = passed_n / max(1, len(checks))
    summary = {
        "api_calls": payload.get("api_calls"),
        "ollama_model": payload.get("ollama_model"),
        "tools_used": tools,
        "agent3_disclaimer_appended": payload.get("agent3_disclaimer_appended", False),
        "numeric_grounding_pct": round(grounded_pct, 3),
        "matched_numbers": matched,
        "total_numbers_in_agent1": total,
        "agent2_structured": structured,
        "contradictions": contradictions,
        "audience": payload.get("audience"),
    }
    return {
        "ok": all(c["passed"] for c in checks),
        "checks": checks,
        "score": round(score, 3),
        "summary": summary,
    }
