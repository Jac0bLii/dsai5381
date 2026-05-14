## Glossary — candle and return fields

- **latest_close**: Last traded price in the candle interval (quote currency per unit base, e.g. USD per BTC).
- **return_1h_pct**: Percent change from the previous candle close to this candle’s close. Labels may say “1h” when granularity is one hour; the math is always one-candle back.
- **return_lookback_pct**: Total percent change from the close **N** candles ago to now, where **N** is the user’s lookback window.
- **volatility_lookback_pct**: Sample standard deviation of one-candle returns inside the lookback window — a scale-free “choppiness” measure, not annualized.
- **relative_volume_lookback**: Current candle USD notional volume divided by the average USD volume of the prior **N** candles (excluding the current bar in the average). Values above **1** suggest heavier-than-recent volume.

## How traders read regime

- **Calm regime**: Low volatility vs recent history, relative volume near **1**, price not hugging lookback extremes.
- **Elevated risk**: Rising volatility, **relative_volume_lookback** spiking, or price near **high_lookback** / **low_lookback** with large **distance_from_lookback_*_pct** magnitudes.
- **Range position**: **distance_from_lookback_high_pct** (negative means below the high) and **distance_from_lookback_low_pct** (positive means above the low) describe location inside the recent range.

## API and limitations

- Data comes from the **public** Coinbase Exchange candles endpoint (no login). It reflects exchange prints, not every off-exchange venue.
- One request returns up to about **300** candles per product; very short granularities over long horizons may require multiple requests (this app uses one batch).
- Past candles do not predict future prices; metrics are descriptive, not forecasts.

## Stakeholder use cases

- **Desk / risk**: Monitor vol spike + volume uptick for operational attention.
- **Research / education**: Teach how spot candles map to returns and rolling statistics.
- **Retail snapshot**: Quick “where are we vs recent range and volume” without order-book depth.

## Disclaimer language for briefings

Always remind end users that AI-generated commentary is **not investment advice** and must be checked against primary data and compliance policy.

## Alert thresholds (operator policy)

Internal monitoring uses **conservative defaults**, not trading triggers:

- **relative_volume_lookback** above **2.0** or below **0.4** → flag for human review.
- **volatility_lookback_pct** above **3.0** → mark "elevated risk" in the brief.
- **distance_from_lookback_high_pct** more negative than **-2.0** combined with rising volume → mark "stretched lower" for context, not a trade signal.
- All thresholds are reviewed quarterly and may differ per product (e.g. higher volatility tolerance for newer listings).

## Coinbase Exchange caveats

- The **public candles endpoint** reflects spot prints on Coinbase Exchange only; dark pools, OTC, and other venues are not included.
- **Granularity vs window:** very short candles over long windows may need multiple requests; this app uses one batch per query.
- Brief outages and rate limits can show as **HTTP 429** or **5xx** — the UI surfaces those as errors and the user can retry safely.
- Time stamps are **UTC**; align lookback windows mentally to your business calendar before quoting them.
