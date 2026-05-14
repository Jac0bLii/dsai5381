from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from coinbase_query import CandleQueryConfig, fetch_coinbase_product_candles


SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR / ".env"
OUTPUT_PATH = SCRIPT_DIR / "06_ai_reporter_output.md"
OLLAMA_CLOUD_URL = "https://ollama.com/api/chat"


def build_market_snapshot() -> tuple[CandleQueryConfig, dict]:
    config = CandleQueryConfig(
        product_id="BTC-USD",
        granularity_seconds=3600,
        total_candles=72,
        lookback_candles=24,
    )
    df = fetch_coinbase_product_candles(config)
    if df.empty:
        raise ValueError("No Coinbase data was returned for the selected query.")

    latest = df.iloc[-1]
    recent_rows = df.tail(4).copy()
    recent_rows["start_time_utc"] = recent_rows["start_time_utc"].dt.strftime("%Y-%m-%d %H:%M UTC")
    full_period_return = ((float(latest["latest_close"]) / float(df.iloc[0]["latest_close"])) - 1) * 100
    avg_hourly_return = float(df["return_1h_pct"].dropna().mean())
    max_hourly_return = float(df["return_1h_pct"].dropna().max())
    min_hourly_return = float(df["return_1h_pct"].dropna().min())
    avg_hourly_volume = float(df["usd_volume_1h"].mean())

    snapshot = {
        "market": config.product_id,
        "granularity_seconds": config.granularity_seconds,
        "total_candles": config.total_candles,
        "lookback_candles": config.lookback_candles,
        "period_start_utc": df.iloc[0]["start_time_utc"].strftime("%Y-%m-%d %H:%M UTC"),
        "latest_timestamp_utc": latest["start_time_utc"].strftime("%Y-%m-%d %H:%M UTC"),
        "latest_close": round(float(latest["latest_close"]), 2),
        "full_period_return_pct": round(full_period_return, 2),
        "average_hourly_return_pct": round(avg_hourly_return, 2),
        "max_hourly_return_pct": round(max_hourly_return, 2),
        "min_hourly_return_pct": round(min_hourly_return, 2),
        "return_1h_pct": round(float(latest["return_1h_pct"]), 2),
        "return_lookback_pct": round(float(latest["return_lookback_pct"]), 2),
        "volatility_lookback_pct": round(float(latest["volatility_lookback_pct"]), 2),
        "usd_volume_1h": round(float(latest["usd_volume_1h"]), 2),
        "average_usd_volume_full_period": round(avg_hourly_volume, 2),
        "avg_usd_volume_lookback": round(float(latest["avg_usd_volume_lookback"]), 2),
        "relative_volume_lookback": round(float(latest["relative_volume_lookback"]), 2),
        "high_lookback": round(float(latest["high_lookback"]), 2),
        "low_lookback": round(float(latest["low_lookback"]), 2),
        "range_lookback_pct": round(float(latest["range_lookback_pct"]), 2),
        "distance_from_lookback_high_pct": round(float(latest["distance_from_lookback_high_pct"]), 2),
        "distance_from_lookback_low_pct": round(float(latest["distance_from_lookback_low_pct"]), 2),
        "recent_candles": recent_rows[
            [
                "start_time_utc",
                "latest_close",
                "return_1h_pct",
                "usd_volume_1h",
            ]
        ].round(2).to_dict(orient="records"),
    }

    return config, snapshot


def build_prompt(snapshot: dict) -> str:
    recent_lines = "\n".join(
        [
            (
                f"- {row['start_time_utc']}: close={row['latest_close']}, "
                f"return_1h_pct={row['return_1h_pct']}, usd_volume_1h={row['usd_volume_1h']}"
            )
            for row in snapshot["recent_candles"]
        ]
    )

    return f"""
You are a financial reporting assistant.
Write exactly 4 markdown bullet points.
Use only the data below. Do not mention outside news or speculation.
Interpret the latest market move in the context of the recent historical window.
Comment on trend, volatility, and whether current volume looks strong or weak relative to the averages.
Be thoughtful and analytical, but stay grounded in the provided numbers.

Market: {snapshot['market']}
Period start UTC: {snapshot['period_start_utc']}
Latest timestamp UTC: {snapshot['latest_timestamp_utc']}
Latest close: {snapshot['latest_close']}
Full period return (%): {snapshot['full_period_return_pct']}
Average hourly return (%): {snapshot['average_hourly_return_pct']}
Best hourly return (%): {snapshot['max_hourly_return_pct']}
Worst hourly return (%): {snapshot['min_hourly_return_pct']}
1-hour return (%): {snapshot['return_1h_pct']}
Lookback return (%): {snapshot['return_lookback_pct']}
Lookback volatility (%): {snapshot['volatility_lookback_pct']}
Current USD volume: {snapshot['usd_volume_1h']}
Average USD volume across full period: {snapshot['average_usd_volume_full_period']}
Average lookback USD volume: {snapshot['avg_usd_volume_lookback']}
Relative volume: {snapshot['relative_volume_lookback']}
Distance from lookback high (%): {snapshot['distance_from_lookback_high_pct']}
Distance from lookback low (%): {snapshot['distance_from_lookback_low_pct']}

Recent candles:
{recent_lines}
""".strip()


def query_ollama_cloud(prompt: str) -> str:
    load_dotenv(ENV_PATH)
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        raise ValueError(f"OLLAMA_API_KEY not found in {ENV_PATH}.")

    response = requests.post(
        OLLAMA_CLOUD_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-oss:20b-cloud",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=(10, 120),
    )
    response.raise_for_status()
    result = response.json()
    return result["message"]["content"].strip()


def save_report(config: CandleQueryConfig, prompt: str, report_text: str) -> None:
    document = "\n".join(
        [
            "# AI Market Report",
            "",
            f"- Market: `{config.product_id}`",
            f"- Granularity: `{config.granularity_seconds}` seconds",
            f"- Total candles: `{config.total_candles}`",
            f"- Lookback candles: `{config.lookback_candles}`",
            "",
            "## Prompt",
            "",
            "```text",
            prompt,
            "```",
            "",
            "## AI Output",
            "",
            report_text,
            "",
        ]
    )
    OUTPUT_PATH.write_text(document, encoding="utf-8")


def main() -> None:
    print("\nFetching Coinbase market data...\n")
    config, snapshot = build_market_snapshot()

    prompt = build_prompt(snapshot)

    print("Sending summarized market data to Ollama Cloud...\n")
    report_text = query_ollama_cloud(prompt)

    save_report(config, prompt, report_text)

    print("AI report generated successfully.\n")
    print(report_text)
    print(f"\nSaved markdown report to {OUTPUT_PATH}\n")


if __name__ == "__main__":
    main()
