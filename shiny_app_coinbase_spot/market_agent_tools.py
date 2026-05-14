# market_agent_tools.py
# Ollama function-calling tools + executor for Coinbase market snapshot
# Coinbase Spot Reporter — App V2 (tool calling) / V3 (operator alerts)

# Topic: expose pandas metrics + a stateful alert action to the model
# as structured JSON strings.

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from coinbase_query import CandleQueryConfig
from rag_retrieval import search_playbook

ALERTS_DIR = Path(__file__).resolve().parent / "output"
ALERTS_PATH = ALERTS_DIR / "alerts.csv"


def ollama_tool_definitions() -> list[dict[str, Any]]:
    """Tool schemas posted to Ollama /api/chat as `tools`."""
    return [
        {
            "type": "function",
            "function": {
                "name": "fetch_market_metrics",
                "description": (
                    "Return JSON summary of the latest Coinbase candle row and rolling metrics "
                    "for the current Streamlit query (same parameters the user selected). "
                    "Call this BEFORE any interpretation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "One sentence why you need the snapshot.",
                        }
                    },
                    "required": ["reason"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_playbook",
                "description": (
                    "Retrieve internal playbook text about metrics, regime reading, alert thresholds, "
                    "exchange caveats, and disclaimer language. Use for RAG context BEFORE classifying regime."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Question or keywords (e.g. relative volume threshold, disclaimer wording).",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "flag_threshold_alert",
                "description": (
                    "Record a non-trading operator alert when a metric breaches a playbook threshold. "
                    "Use ONLY when the snapshot clearly meets a documented threshold (see search_playbook)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "description": "Metric name (e.g. relative_volume_lookback, volatility_lookback_pct).",
                        },
                        "value": {
                            "type": "number",
                            "description": "Observed metric value from fetch_market_metrics.",
                        },
                        "threshold": {
                            "type": "number",
                            "description": "Documented threshold from playbook.",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["above", "below"],
                            "description": "Whether the value is above or below the threshold.",
                        },
                        "note": {
                            "type": "string",
                            "description": "One short reason; visible in alerts.csv.",
                        },
                    },
                    "required": ["metric", "value", "threshold", "direction", "note"],
                },
            },
        },
    ]


# Plain-English explanations for non-experts. Used by the agent (so it can echo
# them in a Glossary section) and by the Streamlit UI (always-visible expander).
METRIC_GLOSSARY: dict[str, str] = {
    "latest_close": "Last traded price in the most recent candle, in USD.",
    "return_1h_pct": "Percent change from the previous candle's close to this candle's close (one bar back).",
    "return_lookback_pct": "Total percent change in price across the whole lookback window (e.g. last 24 candles).",
    "volatility_lookback_pct": "How choppy each candle was on average inside the lookback window — standard deviation of one-bar returns. Higher = more turbulence.",
    "usd_volume_latest": "Trading volume of the latest candle, converted to approximate USD.",
    "relative_volume_lookback": "Latest candle volume divided by the average of the previous candles. 1.00 = normal; above 1 = busier than usual; below 1 = quieter.",
    "high_lookback": "Highest price seen during the lookback window.",
    "low_lookback": "Lowest price seen during the lookback window.",
    "distance_from_lookback_high_pct": "How far the latest close sits below the lookback high. Negative means below the high; closer to 0 means closer to the peak.",
    "distance_from_lookback_low_pct": "How far the latest close sits above the lookback low. Positive means above the low; closer to 0 means closer to the bottom.",
}


def _round_or_none(value: Any, digits: int) -> float | None:
    """Round float to `digits`, return None when null/NaN — keeps tool snapshot tidy."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return round(float(value), digits)


def summarize_df_for_tools(df: pd.DataFrame, cfg: CandleQueryConfig) -> dict[str, Any]:
    """Build a compact JSON-serializable snapshot for the data tool + grounding.

    Numbers are rounded to a reader-friendly precision (2 decimals for %, 2 for prices,
    0 for USD volume) so that downstream agents echo clean values like 22.13% instead
    of 22.126261440976293.
    """
    if df is None or df.empty:
        return {"error": "empty_dataframe"}

    latest = df.iloc[-1]
    tail_returns_raw = df["return_1h_pct"].dropna().tail(12).tolist()

    out: dict[str, Any] = {
        "product_id": cfg.product_id,
        "granularity_seconds": cfg.granularity_seconds,
        "rows": int(len(df)),
        "lookback_candles": cfg.lookback_candles,
        "latest_start_time_utc": str(latest.get("start_time_utc")),
        "latest_close": _round_or_none(latest.get("latest_close"), 2),
        "return_1h_pct": _round_or_none(latest.get("return_1h_pct"), 2),
        "return_lookback_pct": _round_or_none(latest.get("return_lookback_pct"), 2),
        "volatility_lookback_pct": _round_or_none(latest.get("volatility_lookback_pct"), 2),
        "usd_volume_latest": _round_or_none(latest.get("usd_volume_1h"), 0),
        "relative_volume_lookback": _round_or_none(latest.get("relative_volume_lookback"), 2),
        "high_lookback": _round_or_none(latest.get("high_lookback"), 2),
        "low_lookback": _round_or_none(latest.get("low_lookback"), 2),
        "distance_from_lookback_high_pct": _round_or_none(latest.get("distance_from_lookback_high_pct"), 2),
        "distance_from_lookback_low_pct": _round_or_none(latest.get("distance_from_lookback_low_pct"), 2),
        "recent_one_candle_returns_pct_tail12": [round(float(x), 2) for x in tail_returns_raw],
        "glossary": METRIC_GLOSSARY,
    }
    return out


def parse_function_arguments(raw: Any) -> dict[str, Any]:
    """Ollama may return function.arguments as dict or JSON string."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _record_alert(row: dict[str, Any]) -> None:
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not ALERTS_PATH.exists()
    with ALERTS_PATH.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def run_market_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    df: pd.DataFrame,
    cfg: CandleQueryConfig,
) -> str:
    """Execute one tool; return string content for role=tool messages."""
    if name == "fetch_market_metrics":
        payload = summarize_df_for_tools(df, cfg)
        return json.dumps(payload, indent=2)

    if name == "search_playbook":
        query = str(arguments.get("query") or "")
        return search_playbook(query, top_k=3)

    if name == "flag_threshold_alert":
        try:
            metric = str(arguments.get("metric") or "").strip() or "unknown"
            value = float(arguments.get("value") or 0)
            threshold = float(arguments.get("threshold") or 0)
            direction = str(arguments.get("direction") or "above").lower()
            note = str(arguments.get("note") or "").strip()
            row = {
                "ts_utc": datetime.now(UTC).isoformat(),
                "product_id": cfg.product_id,
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "direction": direction,
                "note": note[:240],
            }
            _record_alert(row)
            return json.dumps({"status": "recorded", "row": row})
        except Exception as exc:
            return json.dumps({"status": "error", "detail": str(exc)})

    return json.dumps({"status": "error", "detail": "unknown_tool", "name": name})
