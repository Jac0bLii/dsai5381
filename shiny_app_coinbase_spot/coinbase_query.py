"""
coinbase_query.py
Reusable Coinbase spot candle query + reporter-style metrics.
Pairs with `app.py` (Streamlit UI).
Tim Fraser

This module turns the "good API query" lab script into a parameterized function that
returns a tidy pandas DataFrame. This makes it easy to plug the API query into an app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import sqrt

import pandas as pd
import requests


COINBASE_EXCHANGE_API_BASE_URL = "https://api.exchange.coinbase.com"


@dataclass(frozen=True)
class CandleQueryConfig:
    product_id: str = "BTC-USD"
    granularity_seconds: int = 3600
    total_candles: int = 72
    lookback_candles: int = 24
    timeout_seconds: int = 30


def _pct_change(current_value: float, previous_value: float) -> float:
    return ((current_value / previous_value) - 1) * 100


def _sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_value = sum(values) / len(values)
    variance = sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)
    return sqrt(variance)


def _round_down_to_granularity(dt: datetime, granularity_seconds: int) -> datetime:
    seconds = int(dt.timestamp())
    rounded_seconds = seconds - (seconds % granularity_seconds)
    return datetime.fromtimestamp(rounded_seconds, UTC)


def fetch_coinbase_product_candles(config: CandleQueryConfig) -> pd.DataFrame:
    """
    Fetch Coinbase Exchange candles and compute rolling metrics.

    Coinbase response rows are arrays:
    [ time, low, high, open, close, volume ]

    Returns:
      A DataFrame sorted ascending by time, with one row per candle.
    """

    if not config.product_id or not isinstance(config.product_id, str):
        raise ValueError("product_id must be a non-empty string (example: 'BTC-USD').")
    if config.granularity_seconds <= 0:
        raise ValueError("granularity_seconds must be a positive integer.")
    if config.total_candles < 2:
        raise ValueError("total_candles must be at least 2.")
    if config.lookback_candles < 1:
        raise ValueError("lookback_candles must be at least 1.")
    if config.lookback_candles >= config.total_candles:
        raise ValueError("lookback_candles must be less than total_candles.")

    # Coinbase candles are returned on a time grid. If we request a window that is exactly
    # N * granularity wide, the API may include both endpoints, which can yield N+1 rows.
    # Using (N-1) * granularity is a simple way to target ~N candles.
    end_time = _round_down_to_granularity(datetime.now(UTC), config.granularity_seconds)
    start_time = end_time - timedelta(seconds=(config.total_candles - 1) * config.granularity_seconds)

    response = requests.get(
        f"{COINBASE_EXCHANGE_API_BASE_URL}/products/{config.product_id}/candles",
        params={
            "granularity": config.granularity_seconds,
            "start": start_time.isoformat().replace("+00:00", "Z"),
            "end": end_time.isoformat().replace("+00:00", "Z"),
        },
        headers={
            "Accept": "application/json",
            "User-Agent": "dsai5381-market-analysis",
        },
        timeout=config.timeout_seconds,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as err:
        detail = ""
        try:
            detail = f" body={response.json()!r}"
        except Exception:
            pass
        raise requests.HTTPError(f"{err}{detail}", response=response) from err

    rows = response.json()
    if not isinstance(rows, list):
        raise ValueError("Unexpected API response format: expected a JSON list of candles.")
    rows = sorted(rows, key=lambda row: row[0])

    records: list[dict] = []
    for row in rows:
        close_price = float(row[4])
        base_volume = float(row[5])
        usd_volume = close_price * base_volume

        records.append(
            {
                "start_time_utc": datetime.fromtimestamp(row[0], UTC),
                "low_price_raw": float(row[1]),
                "high_price_raw": float(row[2]),
                "open_price_raw": float(row[3]),
                "latest_close": close_price,
                "usd_volume_1h": usd_volume,
            }
        )

    # Rolling metrics
    for index, record in enumerate(records):
        record["return_1h_pct"] = (
            _pct_change(record["latest_close"], records[index - 1]["latest_close"]) if index >= 1 else None
        )

        if index >= config.lookback_candles:
            window = records[index - config.lookback_candles + 1:index + 1]
            prior_window = records[index - config.lookback_candles:index]

            returns_window = [
                _pct_change(window[j]["latest_close"], window[j - 1]["latest_close"])
                for j in range(1, len(window))
            ]
            high_n = max(item["high_price_raw"] for item in window)
            low_n = min(item["low_price_raw"] for item in window)
            avg_usd_volume_n = sum(item["usd_volume_1h"] for item in prior_window) / config.lookback_candles

            record["return_lookback_pct"] = _pct_change(
                record["latest_close"], records[index - config.lookback_candles]["latest_close"]
            )
            record["volatility_lookback_pct"] = _sample_std(returns_window)
            record["avg_usd_volume_lookback"] = avg_usd_volume_n
            record["relative_volume_lookback"] = record["usd_volume_1h"] / avg_usd_volume_n if avg_usd_volume_n else None
            record["high_lookback"] = high_n
            record["low_lookback"] = low_n
            record["range_lookback_pct"] = _pct_change(high_n, low_n) if low_n else None
            record["distance_from_lookback_high_pct"] = _pct_change(record["latest_close"], high_n) if high_n else None
            record["distance_from_lookback_low_pct"] = _pct_change(record["latest_close"], low_n) if low_n else None
        else:
            record["return_lookback_pct"] = None
            record["volatility_lookback_pct"] = None
            record["avg_usd_volume_lookback"] = None
            record["relative_volume_lookback"] = None
            record["high_lookback"] = None
            record["low_lookback"] = None
            record["range_lookback_pct"] = None
            record["distance_from_lookback_high_pct"] = None
            record["distance_from_lookback_low_pct"] = None

    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df

    df = df.sort_values("start_time_utc").reset_index(drop=True)
    df["start_time_utc"] = pd.to_datetime(df["start_time_utc"], utc=True)

    return df

