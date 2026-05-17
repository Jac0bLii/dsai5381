# run_experiment.py
# HW3 — generate N briefings per prompt variant; score each one; save results.csv
# Coinbase Spot Reporter — DSAI 5381

# Topic: hold data + Agents 1 + 2 constant, swap Agent 3 system prompt across
# Prompts A / B / C, run N times each, score each output with a hybrid validator
# (deterministic numeric grounding + AI reviewer ratings).

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Make sure we can import from shiny_app_coinbase_spot/
_HW3_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _HW3_DIR.parent
_APP_DIR = _REPO_ROOT / "shiny_app_coinbase_spot"
sys.path.insert(0, str(_APP_DIR))

# These imports require the shiny app folder on sys.path
import agent_pipeline  # noqa: E402
from agent_pipeline import (  # noqa: E402
    AGENT3_SYSTEM_TEMPLATE as ORIGINAL_AGENT3_TEMPLATE,
)
from coinbase_query import CandleQueryConfig, fetch_coinbase_product_candles  # noqa: E402
from qc_validation import validate_ai_pipeline_result  # noqa: E402

from prompts import PROMPT_VARIANTS, label_for_audience  # noqa: E402
from llm_reviewer import review_briefing  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(_APP_DIR / ".env")
except ImportError:
    pass


RESULTS_PATH = _HW3_DIR / "results.csv"

CSV_FIELDS = [
    "run_id",
    "ts_utc",
    "prompt_label",
    "audience",
    "numeric_grounding",
    "disclaimer_compliance",
    "stakeholder_fit",
    "conciseness",
    "review_rationale",
    "qc_score",
    "agent3_chars",
]


def _ensure_results_csv() -> None:
    if RESULTS_PATH.exists():
        return
    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()


def _append_row(row: dict[str, object]) -> None:
    with RESULTS_PATH.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})


def run_with_prompt_variant(
    *,
    variant_template: str,
    task: str,
    df,
    cfg: CandleQueryConfig,
    audience: str,
    host: str,
    api_key: str,
    model: str,
):
    """Monkey-patch Agent 3's template for one call, then restore it."""
    saved = agent_pipeline.AGENT3_SYSTEM_TEMPLATE
    try:
        agent_pipeline.AGENT3_SYSTEM_TEMPLATE = variant_template
        return agent_pipeline.run_three_agent_pipeline(
            task=task,
            df=df,
            cfg=cfg,
            host=host,
            api_key=api_key,
            model=model,
            audience=audience,
        )
    finally:
        agent_pipeline.AGENT3_SYSTEM_TEMPLATE = saved


def main() -> None:
    parser = argparse.ArgumentParser(description="HW3 prompt comparison experiment.")
    parser.add_argument("--runs", type=int, default=20, help="Runs per prompt variant (default 20).")
    parser.add_argument("--audience", type=str, default="retail", choices=["desk", "risk", "retail"])
    parser.add_argument("--product", type=str, default="BTC-USD")
    parser.add_argument("--granularity", type=int, default=3600)
    parser.add_argument("--total-candles", type=int, default=72)
    parser.add_argument("--lookback", type=int, default=24)
    parser.add_argument("--writer-model", type=str, default=None,
                        help="Override OLLAMA_MODEL for the agent pipeline.")
    parser.add_argument("--reviewer-model", type=str, default="gpt-oss:120b-cloud",
                        help="LLM that scores stakeholder_fit + conciseness.")
    args = parser.parse_args()

    host = os.getenv("OLLAMA_HOST", "https://ollama.com")
    api_key = os.getenv("OLLAMA_API_KEY", "").strip()
    writer_model = args.writer_model or os.getenv("OLLAMA_MODEL", "nemotron-3-nano:30b-cloud")
    if not api_key:
        sys.exit("ERROR: OLLAMA_API_KEY not set. Add it to shiny_app_coinbase_spot/.env or export it.")

    # 1. Fetch the data once — same input for every run
    print(f"[1/3] Fetching Coinbase candles ({args.product}, {args.granularity}s × {args.total_candles}) ...")
    cfg = CandleQueryConfig(
        product_id=args.product,
        granularity_seconds=args.granularity,
        total_candles=args.total_candles,
        lookback_candles=args.lookback,
    )
    df = fetch_coinbase_product_candles(cfg)
    print(f"    Got {len(df)} rows. Latest close = {df.iloc[-1]['latest_close']:.2f}")

    task = (
        f"Situational snapshot for {cfg.product_id} ({cfg.granularity_seconds}s candles, "
        f"lookback={cfg.lookback_candles}). Interpret latest close, lookback return, "
        f"volatility, relative volume, and distance from lookback high/low for an internal "
        f"stakeholder who needs a fast read."
    )

    _ensure_results_csv()
    label = label_for_audience(args.audience)

    # 2. Loop: for each prompt × runs
    total = len(PROMPT_VARIANTS) * args.runs
    done = 0
    print(f"[2/3] Running experiment: {len(PROMPT_VARIANTS)} prompts × {args.runs} runs = {total} reports.")
    for variant in PROMPT_VARIANTS:
        template = variant.system_template.replace("{audience_label}", label)
        for i in range(args.runs):
            done += 1
            t0 = time.time()
            run_id = str(uuid.uuid4())[:8]
            print(f"  [{done}/{total}] {variant.label} run {i + 1}/{args.runs} ...", end="", flush=True)

            try:
                payload = run_with_prompt_variant(
                    variant_template=template,
                    task=task,
                    df=df,
                    cfg=cfg,
                    audience=args.audience,
                    host=host,
                    api_key=api_key,
                    model=writer_model,
                )
            except Exception as exc:  # noqa: BLE001
                print(f" PIPELINE ERROR: {exc}")
                continue

            if payload.get("status") != "ok":
                print(f" SKIPPED ({payload.get('detail', 'unknown')})")
                continue

            qc = validate_ai_pipeline_result(payload)
            summary = qc.get("summary") or {}
            checks = {c.get("check") or c.get("name", ""): c for c in qc.get("checks") or []}
            briefing = payload.get("agent3_executive", "")

            review = review_briefing(
                briefing=briefing,
                audience=args.audience,
                reviewer_host=host,
                reviewer_api_key=api_key,
                reviewer_model=args.reviewer_model,
            )

            disclaimer_ok = 1 if (checks.get("agent3_has_disclaimer") or {}).get("passed") else 0
            row = {
                "run_id": run_id,
                "ts_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "prompt_label": variant.label,
                "audience": args.audience,
                "numeric_grounding": summary.get("numeric_grounding_pct"),
                "disclaimer_compliance": disclaimer_ok,
                "stakeholder_fit": review.get("stakeholder_fit"),
                "conciseness": review.get("conciseness"),
                "review_rationale": review.get("rationale"),
                "qc_score": qc.get("score"),
                "agent3_chars": len(briefing),
            }
            _append_row(row)
            print(
                f" ok ({time.time() - t0:.1f}s)  "
                f"sf={row['stakeholder_fit']} co={row['conciseness']} "
                f"ng={row['numeric_grounding']} dc={row['disclaimer_compliance']}"
            )

    print(f"[3/3] Done. Wrote {RESULTS_PATH}")
    print("Run `python homework3/analyze.py` next.")


if __name__ == "__main__":
    main()
