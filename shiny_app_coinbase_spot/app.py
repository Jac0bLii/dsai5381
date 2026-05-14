# app.py
# Coinbase Spot Reporter — Streamlit dashboard (Apps V1–V3)
# Prof. Tim Fraser pattern
#
# Topic: Coinbase candles + rolling metrics + optional Ollama Cloud multi-agent briefing
# (tool calling + RAG) with validation evidence for production-style QC.

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from agent_pipeline import run_three_agent_pipeline
from coinbase_query import CandleQueryConfig, fetch_coinbase_product_candles
from market_agent_tools import METRIC_GLOSSARY
from qc_validation import validate_ai_pipeline_result, validate_market_dataframe

# 0. Setup #################################

load_dotenv()

st.set_page_config(
    page_title="Coinbase Spot Reporter",
    page_icon="📈",
    layout="wide",
)


def env_pref(key: str, default: str = "") -> str:
    """Prefer OS env (local .env); fall back to Streamlit secrets on deploy."""
    v = os.getenv(key, "").strip()
    if v:
        return v
    try:
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return default


def gate_optional_password() -> None:
    """If COINBASE_APP_PASSWORD is set, require a simple login (V3 hardening)."""
    pwd = env_pref("COINBASE_APP_PASSWORD")
    if not pwd:
        return
    if st.session_state.get("coinbase_auth_ok"):
        return
    st.title("Coinbase Spot Reporter")
    st.caption("Password-protected instance.")
    entered = st.text_input("App password", type="password")
    if st.button("Continue", type="primary") and entered == pwd:
        st.session_state.coinbase_auth_ok = True
        st.rerun()
    st.stop()


gate_optional_password()


st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; padding-bottom: 2rem; }
      div[data-testid="metric-container"] { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 0.9rem 1rem; border-radius: 14px; }
      .stDataFrame { border-radius: 14px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Coinbase Spot Reporter")
st.caption("Reporter-style spot snapshot + optional 3-agent AI briefing (Ollama Cloud).")

# 1. Stakeholder context (V3 clarity) #################################

with st.expander("Who this is for & how to use it", expanded=False):
    st.markdown(
        """
**Stakeholders:** desk monitoring, risk awareness, and course demos — not a trade recommendation engine.

**Steps:** choose market and candle size → **Run query** → review charts → optionally **Generate AI briefing** (needs `OLLAMA_API_KEY`).

**AI path (App V2):** *Agent 1* calls **tools** (`fetch_market_metrics`, `search_playbook` RAG) → *Agent 2* regime/risk read → *Agent 3* executive lines + disclaimer.

**QC (App V3):** after each run we show validation tables you can screenshot for evidence.
        """
    )


def granularity_label(seconds: int) -> str:
    if seconds == 60:
        return "1 minute"
    if seconds == 300:
        return "5 minutes"
    if seconds == 900:
        return "15 minutes"
    if seconds == 3600:
        return "1 hour"
    if seconds == 21600:
        return "6 hours"
    if seconds == 86400:
        return "1 day"
    return f"{seconds} seconds"


# 2. Sidebar #################################

with st.sidebar:
    st.header("Query controls")
    product_preset = st.selectbox(
        "Market (product_id)",
        options=["BTC-USD", "ETH-USD", "SOL-USD", "Custom…"],
        index=0,
        help="Coinbase Exchange product identifier (example: BTC-USD).",
    )
    if product_preset == "Custom…":
        product_id = st.text_input("Custom product_id", value="BTC-USD")
    else:
        product_id = product_preset

    granularity_seconds = st.selectbox(
        "Candle size (granularity)",
        options=[60, 300, 900, 3600, 21600, 86400],
        format_func=granularity_label,
        index=3,
    )

    total_candles = st.slider(
        "How many candles to request?",
        min_value=20,
        max_value=300,
        value=72,
        step=4,
        help="Coinbase typically supports up to 300 candles per request for this endpoint.",
    )

    default_lookback = int(round(24 * 3600 / granularity_seconds))
    lookback_candles = st.slider(
        "Lookback window (candles) for rolling metrics",
        min_value=2,
        max_value=min(200, total_candles - 1),
        value=min(default_lookback, total_candles - 1),
        step=1,
        help="Used to compute rolling return/volatility/volume metrics.",
    )

    run_query = st.button("Run query", type="primary", use_container_width=True)

    st.divider()
    st.markdown("**AI briefing (Ollama Cloud)**")
    model_default = env_pref("OLLAMA_MODEL", "nemotron-3-nano:30b-cloud")
    ollama_model_sidebar = st.text_input("Model name", value=model_default)
    audience_choice = st.radio(
        "Audience for executive brief",
        options=["desk", "risk", "retail"],
        index=0,
        horizontal=True,
        help="Tunes Agent 3 tone — operational vs governance vs plain English.",
    )
    key_present = bool(env_pref("OLLAMA_API_KEY"))
    st.caption("API key from `.env` locally or Streamlit **Secrets** when deployed.")
    if not key_present:
        st.warning("`OLLAMA_API_KEY` not found — AI briefing disabled until configured.")

    st.divider()
    st.markdown("**Notes**")
    st.markdown("- Public Coinbase candles endpoint (no exchange login).")
    st.markdown("- AI uses cloud tokens; review outputs before sharing.")


# 3. Main layout — static intro #################################

left, right = st.columns([1.15, 0.85], gap="large")
with left:
    st.subheader("Session goal")
    st.write(
        "Pull recent **Coinbase Exchange** spot candles, compute rolling metrics, and optionally run a **three-agent** "
        "chain with **tool calling** and **RAG** from `data/knowledge_base.md`."
    )
with right:
    st.subheader("Current parameters")
    st.write(
        f"- **product_id**: `{product_id}`\n"
        f"- **granularity_seconds**: `{granularity_seconds}`\n"
        f"- **total_candles**: `{total_candles}`, **lookback_candles**: `{lookback_candles}`"
    )


# 4. Data fetch & dashboard #################################

if run_query:
    cfg_new = CandleQueryConfig(
        product_id=product_id.strip().upper(),
        granularity_seconds=int(granularity_seconds),
        total_candles=int(total_candles),
        lookback_candles=int(lookback_candles),
    )
    with st.spinner("Querying Coinbase and computing metrics..."):
        try:
            df_new = fetch_coinbase_product_candles(cfg_new)
        except Exception as exc:
            st.error(f"Query failed: {exc}")
            st.stop()
    if df_new.empty:
        st.warning("No data returned. Try a different product_id or granularity.")
        st.stop()
    st.session_state["stored_df"] = df_new
    st.session_state["stored_cfg"] = cfg_new
    st.session_state["data_qc"] = validate_market_dataframe(df_new, cfg_new)

df_live = st.session_state.get("stored_df")
cfg_live = st.session_state.get("stored_cfg")

if df_live is not None and cfg_live is not None:
    df = df_live
    cfg = cfg_live

    stale = (
        product_id.strip().upper() != cfg.product_id
        or int(granularity_seconds) != cfg.granularity_seconds
        or int(total_candles) != cfg.total_candles
        or int(lookback_candles) != cfg.lookback_candles
    )
    if stale:
        st.warning("Sidebar parameters differ from the loaded snapshot — click **Run query** to refresh data.")

    latest = df.iloc[-1]

    st.subheader("Data quality (pre-AI)")
    dqc = st.session_state["data_qc"]
    qcols = st.columns(4)
    qcols[0].metric("QC score", f"{dqc['score']:.0%}")
    qcols[1].metric("Rows", len(df))
    qcols[2].metric("QC pass" if dqc["ok"] else "QC issues", "✓" if dqc["ok"] else "⚠")
    with st.expander("Data validation detail"):
        st.dataframe(pd.DataFrame(dqc["checks"]), hide_index=True, use_container_width=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Latest close", f"{latest['latest_close']:,.2f}")
    m2.metric(
        "Return (1 candle)",
        "NA" if latest.get("return_1h_pct") is None else f"{latest['return_1h_pct']:.2f}%",
    )
    m3.metric(
        f"Return (lookback={cfg.lookback_candles})",
        "NA" if latest.get("return_lookback_pct") is None else f"{latest['return_lookback_pct']:.2f}%",
    )
    m4.metric(
        "Volatility (lookback)",
        "NA" if latest.get("volatility_lookback_pct") is None else f"{latest['volatility_lookback_pct']:.2f}%",
    )

    st.divider()
    c1, c2 = st.columns([0.58, 0.42], gap="large")
    with c1:
        st.subheader("Price")
        chart_df = df.set_index("start_time_utc")[["latest_close"]].rename(columns={"latest_close": "Close"})
        st.line_chart(chart_df)
    with c2:
        st.subheader("Volume (USD notional)")
        vol_df = df.set_index("start_time_utc")[["usd_volume_1h"]].rename(columns={"usd_volume_1h": "USD Volume"})
        st.bar_chart(vol_df)

    st.divider()
    st.subheader("Results table (last 100 rows)")
    display_cols = [
        "start_time_utc",
        "latest_close",
        "return_1h_pct",
        "return_lookback_pct",
        "volatility_lookback_pct",
        "usd_volume_1h",
        "avg_usd_volume_lookback",
        "relative_volume_lookback",
        "high_lookback",
        "low_lookback",
        "range_lookback_pct",
        "distance_from_lookback_high_pct",
        "distance_from_lookback_low_pct",
    ]
    df_out = df.copy()
    df_out["start_time_utc"] = df_out["start_time_utc"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    st.dataframe(df_out[display_cols].tail(100), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("AI multi-agent briefing")
    briefing_task = (
        f"Situational snapshot for {cfg.product_id} ({cfg.granularity_seconds}s candles, "
        f"lookback={cfg.lookback_candles}). Interpret latest close, lookback return, volatility, "
        f"relative volume, and distance from lookback high/low for an internal stakeholder who needs a fast read."
    )

    host = env_pref("OLLAMA_HOST", "https://ollama.com")
    key = env_pref("OLLAMA_API_KEY")
    model_name = ollama_model_sidebar.strip() or env_pref("OLLAMA_MODEL", "nemotron-3-nano:30b-cloud")

    if not key_present:
        st.info("Add `OLLAMA_API_KEY` to `.env` (or Streamlit secrets) to enable this section.")
    elif st.button(
        "Generate 3-agent briefing",
        type="secondary",
        use_container_width=True,
    ):
        with st.spinner("Running Agents 1→3 with tools + RAG — about 30–60s…"):
            main_result = run_three_agent_pipeline(
                task=briefing_task,
                df=df,
                cfg=cfg,
                host=host,
                api_key=key,
                model=model_name,
                audience=audience_choice,
            )
        st.session_state["last_ai_result"] = main_result
        st.session_state["last_ai_qc"] = validate_ai_pipeline_result(main_result)

    if st.session_state.get("last_ai_result"):
        res = st.session_state["last_ai_result"]
        ai_qc = st.session_state.get("last_ai_qc") or validate_ai_pipeline_result(res)

        if res.get("status") != "ok":
            st.error(res.get("detail", "AI pipeline failed."))
        else:
            st.success(
                f"Pipeline finished for audience: **{res.get('audience', 'desk')}** — review below."
            )

            structured = res.get("agent2_structured") or {}
            if structured.get("regime") or structured.get("liquidity"):
                hcols = st.columns(3)
                hcols[0].metric("Regime", str(structured.get("regime") or "—"))
                hcols[1].metric("Liquidity", str(structured.get("liquidity") or "—"))
                hcols[2].metric("Range position", str(structured.get("range_position") or "—"))

            contradictions = res.get("contradictions") or []
            if contradictions:
                for issue in contradictions:
                    st.warning(f"Consistency check: {issue}")

            t1, t2, t3 = st.tabs(["Agent 1 — Data + tools", "Agent 2 — Risk / regime", "Agent 3 — Executive"])
            with t1:
                st.markdown(res.get("agent1_data_analyst", ""))
                with st.expander("What these terms mean (plain English)"):
                    st.dataframe(
                        pd.DataFrame(
                            [{"field": k, "meaning": v} for k, v in METRIC_GLOSSARY.items()]
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
            with t2:
                st.markdown(res.get("agent2_risk", ""))
                if structured:
                    with st.expander("Structured fields parsed from Agent 2"):
                        st.json(structured)
            with t3:
                st.markdown(res.get("agent3_executive", ""))
                if res.get("agent3_disclaimer_appended"):
                    st.caption("Disclaimer auto-appended (model omitted it).")

            st.subheader("AI output quality (QC evidence)")
            ev_cols = st.columns(3)
            ev_cols[0].metric("AI QC score", f"{ai_qc['score']:.0%}")
            ev_cols[1].metric("API rounds", res.get("api_calls", "—"))
            ev_cols[2].metric("Tools used", len(res.get("tools_used") or []))
            with st.expander("AI validation checks (screenshot for App V3)"):
                st.dataframe(pd.DataFrame(ai_qc["checks"]), hide_index=True, use_container_width=True)
                st.json(ai_qc.get("summary") or {})

            tool_events = res.get("tool_events") or []
            if tool_events:
                with st.expander("Tool call trace"):
                    st.dataframe(pd.DataFrame(tool_events), hide_index=True, use_container_width=True)

    alerts_path = Path(__file__).resolve().parent / "output" / "alerts.csv"
    if alerts_path.exists():
        st.divider()
        st.subheader("Operator alerts (`output/alerts.csv`)")
        try:
            alerts_df = pd.read_csv(alerts_path)
            st.dataframe(alerts_df.tail(20), hide_index=True, use_container_width=True)
            st.caption("Alerts are non-trading flags written by the `flag_threshold_alert` tool.")
        except Exception as exc:
            st.caption(f"alerts.csv unreadable: {exc}")

else:
    st.info("Set parameters in the sidebar, then click **Run query**.")
