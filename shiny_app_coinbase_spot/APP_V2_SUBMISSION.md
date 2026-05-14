# App V2 Submission — Coinbase Spot Reporter

**Team:** [Chenxi Li]
**Members and roles:**


**GitHub repository:** [your GitHub URL]
**Live app:** [your Streamlit Cloud / Posit Connect URL]
**Password (if gate enabled):** [your password, or write “no password”]

---

## 1. Description

This app is a Streamlit dashboard that turns public Coinbase Exchange market data into a short, audience-aware market briefing. The user picks a product (e.g. `BTC-USD`), a candle granularity (e.g. 1-hour), how many candles to pull, and a lookback window. The app then queries the Coinbase Exchange candles API (`/products/{id}/candles`), builds a pandas DataFrame, and adds rolling metrics — latest close, one-candle return, lookback return, lookback volatility, relative volume, and distance from the lookback high and low. These metrics are displayed as value boxes, two reactive charts (close-price line, candle returns), and a recent-candles table. The dashboard is meant for someone who needs a quick read on whether the market is calm, busy, or stretched — not for placing trades.

On top of the data layer, App V2 adds an AI briefing pipeline that runs three coordinated agents on Ollama Cloud. **Agent 1 (Data Analyst)** has three tools: `fetch_market_metrics` returns a pre-rounded JSON snapshot of the latest candle and lookback metrics; `search_playbook` is a RAG step that retrieves matching excerpts from a curated Markdown knowledge base (`data/knowledge_base.md`) covering the glossary, regime reading, and alert thresholds; `flag_threshold_alert` appends a row to `output/alerts.csv` whenever a documented threshold is crossed (for example, `relative_volume_lookback` below `0.40`). **Agent 2 (Risk and Regime Analyst)** reads the JSON snapshot plus Agent 1’s bullets and produces a one-line classification — regime (calm / transitional / elevated), liquidity (thin / normal / elevated), range position (near low / mid / near high) — backed by an explicit comparison of values to playbook thresholds and a fenced machine-readable JSON block. **Agent 3 (Executive Briefing Officer)** turns that classification into a 3-line summary written for one of three audiences — trading desk, risk and compliance, or non-expert retail — and always ends with a disclaimer that the output is not investment advice.

The combination adds real value for distinct stakeholders. A **desk operator** gets a fast, plain-English read on whether the latest candle is acting normally or worth a second look. A **risk or compliance reviewer** gets an auditable trail — the alerts CSV, the structured regime JSON, and a JSONL run log (`output/agent_runs.jsonl`) — that records what the AI saw, which tools fired, and how the regime was classified on every run. A **non-expert retail user** gets the same dashboard but with a translated brief and a “What these terms mean” glossary so concepts like volatility, relative volume, and lookback range are not jargon. Quality control is built in: numeric grounding compares numbers in Agent 1’s text against the JSON snapshot, a contradiction check flags inconsistencies between Agent 2’s regime and Agent 1’s alerts, and the disclaimer line is auto-appended if Agent 3 omits it.

Technically, the app is a Python 3.11 Streamlit project with one main file (`app.py`) plus four small modules (`coinbase_query.py`, `agent_pipeline.py`, `market_agent_tools.py`, `rag_retrieval.py`, `qc_validation.py`). It depends on `streamlit`, `pandas`, `requests`, and `python-dotenv`; the AI layer talks to Ollama Cloud via `/api/chat` with function calling. Environment variables (`OLLAMA_API_KEY`, `OLLAMA_HOST`, `OLLAMA_MODEL`, optional `COINBASE_APP_PASSWORD`) are read from a local `.env` file when running locally and from the deployment platform’s secrets manager when deployed. Limitations: Coinbase candle endpoints are rate-limited so we cap candles per run; the AI runs are non-deterministic, which is exactly why the QC layer is in front of every output the user sees.

---

## 2. Process Diagram

```mermaid
flowchart LR
  subgraph User[" User "]
    U[Sidebar inputs:\nproduct • granularity • candles • lookback • audience]
  end

  subgraph Data[" Data layer "]
    API[(Coinbase Exchange API\n/products/{id}/candles)]
    DF[(Pandas DataFrame\n+ rolling metrics)]
  end

  subgraph Knowledge[" Knowledge base "]
    KB[(data/knowledge_base.md\nglossary • regime • thresholds)]
  end

  subgraph Agents[" Agentic orchestration (Ollama Cloud) "]
    A1["Agent 1\nData Analyst\n(tool loop)"]
    A2["Agent 2\nRisk and Regime\n(classifier + JSON)"]
    A3["Agent 3\nExecutive Brief\n(audience-aware)"]
  end

  subgraph Tools[" Tool calling "]
    T1[[fetch_market_metrics]]
    T2[[search_playbook  RAG]]
    T3[[flag_threshold_alert]]
  end

  subgraph Storage[" Audit + UI artifacts "]
    AL[(output/alerts.csv)]
    LOG[(output/agent_runs.jsonl)]
    UI[Streamlit dashboard:\nmetric tiles • charts • agent tabs • QC]
  end

  U --> API --> DF --> A1
  A1 -->|fetch_market_metrics| T1 --> DF
  A1 -->|search_playbook| T2 --> KB
  A1 -->|flag_threshold_alert| T3 --> AL
  T1 -.metrics JSON.-> A1
  T2 -.playbook excerpts.-> A1
  A1 --> A2
  A2 -->|structured JSON\nregime • liquidity • range| A3
  U --> A3
  A3 --> UI
  AL --> UI
  DF --> UI
  A2 --> LOG
```

*Figure 1. Data flow for the Coinbase Spot Reporter (V2). The user’s sidebar inputs trigger a Coinbase API query and a 3-agent pipeline. Agent 1 calls three tools — including a RAG retriever over `knowledge_base.md` and a side-effect tool that writes operator alerts — and hands off to Agent 2, which produces a structured regime classification consumed by the audience-aware Agent 3. The dashboard surfaces all artifacts (metric tiles, agent tabs, alerts, QC score).*

---

## 3. Technical Documentation

### 3.1 System Architecture

The app is a Streamlit dashboard organized as five small Python modules. A single entry point (`app.py`) renders the UI and routes user actions; the AI side lives in `agent_pipeline.py`, which orchestrates three agents on **Ollama Cloud**.

**Agent roles:**

| Agent | Role | Tools | Output consumed by |
|---|---|---|---|
| **Agent 1 — Data Analyst** | Pulls market metrics, retrieves playbook context (RAG), and fires threshold alerts | `fetch_market_metrics`, `search_playbook`, `flag_threshold_alert` | Agent 2 |
| **Agent 2 — Risk and Regime Analyst** | Classifies regime / liquidity / range position with explicit threshold comparisons; emits a fenced machine-readable JSON | none | Agent 3 + UI metric tiles |
| **Agent 3 — Executive Briefing Officer** | 3-line audience-aware summary (desk / risk / retail) with auto-appended disclaimer | none | User |

**Workflow** (`agent_pipeline.run_three_agent_pipeline`):

1. The user clicks **Generate 3-agent briefing**. The current Coinbase DataFrame is passed in.
2. Agent 1 enters a tool loop (`_run_tool_loop_agent1`, max 8 rounds): it must call `fetch_market_metrics` first, `search_playbook` at least once, and `flag_threshold_alert` only when thresholds are clearly breached.
3. After Agent 1 finishes, the pre-rounded JSON snapshot plus Agent 1’s bullets are passed to Agent 2.
4. Agent 2’s response is parsed by `_extract_agent2_structured` to pull the fenced `json` block (`regime`, `liquidity`, `range_position`, `watch_list`). `_detect_contradictions` cross-checks Agent 2’s regime against Agent 1’s fired alerts (e.g. `regime=calm` + an alert → flagged).
5. Agent 3 receives Agent 2’s text plus the chosen audience label and produces the final brief. `_enforce_disclaimer` appends the canonical disclaimer line if the model omitted it.
6. The full payload is returned to `app.py` (agent texts, structured JSON, tool events, contradictions) and appended as one record to `output/agent_runs.jsonl` for audit.

A separate module `qc_validation.py` scores the run (numeric grounding, tool presence, disclaimer presence, structured JSON presence, no-contradictions) and the UI surfaces both the score and the per-check details.

### 3.2 RAG / Tool Implementation

**RAG data source:** `data/knowledge_base.md`, a curated Markdown playbook covering:
- Metric glossary (latest close, returns, volatility, relative volume, distance from high/low)
- Regime reading and range position
- Coinbase API caveats and rate limits
- Alert thresholds (e.g. relative volume `<0.4` or `>2.0`, volatility `>3.0%`)
- Disclaimer language

**Search function:** `rag_retrieval.search_playbook(query, top_k=2)`.
- Splits the Markdown on `## headings` into `(title, body)` sections.
- Tokenizes both query and section with `re.findall(r"[a-z0-9]+", ...)` (lowercased, length ≥ 3).
- Scores each section as `|query ∩ section| / |query|` and returns the top-k as a labeled markdown block titled `### Retrieved playbook excerpts (RAG)`.
- Returned to the model as a `role: "tool"` message so the agent is grounded in retrieved text, not pre-training.

**Tool functions** (defined in `market_agent_tools.py::ollama_tool_definitions`):

| Tool | Parameters | Returns / side effect |
|---|---|---|
| `fetch_market_metrics` | `reason: string` (why the model needs the data) | JSON snapshot of the latest candle and lookback metrics — pre-rounded to 2 decimals — including `latest_close`, `return_1h_pct`, `return_lookback_pct`, `volatility_lookback_pct`, `relative_volume_lookback`, `high_lookback`, `low_lookback`, `distance_from_lookback_high_pct`, `distance_from_lookback_low_pct`, `recent_one_candle_returns_pct_tail12`, and a plain-English `glossary`. |
| `search_playbook` | `query: string` | Top-k labeled excerpts from `data/knowledge_base.md` (see RAG section above). |
| `flag_threshold_alert` | `metric: string, value: number, threshold: number, direction: "above"\|"below", note: string` | Appends one row to `output/alerts.csv` (`ts_utc, product_id, metric, value, threshold, direction, note`) and returns a confirmation JSON to the model. No trading action; pure audit trail. |

The dispatcher `run_market_tool` in `market_agent_tools.py` routes each tool call by name and serializes the result back to the model as a JSON string.

### 3.3 Technical Details

**Language and runtime:** Python ≥ 3.11.

**Packages** (`requirements.txt`):
- `requests >= 2.31` — Coinbase + Ollama HTTP calls
- `pandas >= 2.2` — candles DataFrame + rolling metrics
- `streamlit >= 1.36` — dashboard UI
- `python-dotenv >= 1.0` — local `.env` loader

**External endpoints:**
- Coinbase Exchange — `GET https://api.exchange.coinbase.com/products/{product_id}/candles`
- Ollama Cloud — `POST {OLLAMA_HOST}/api/chat` (function calling)

**Environment variables** (read from `.env` locally, from Streamlit Secrets / Connect env vars when deployed):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OLLAMA_API_KEY` | yes | — | Ollama Cloud key |
| `OLLAMA_HOST` | no | `https://ollama.com` | Ollama base URL |
| `OLLAMA_MODEL` | no | `nemotron-3-nano:30b-cloud` | Model name |
| `COINBASE_APP_PASSWORD` | optional | unset | If set, app shows a password gate on load |

**File structure** (`shiny_app_coinbase_spot/`):
- `app.py` — Streamlit UI, sidebar, charts, agent tabs, QC display, password gate.
- `coinbase_query.py` — Candle fetcher + rolling-metric computation.
- `agent_pipeline.py` — Three-agent orchestration, tool loop, structured parsing, disclaimer enforcement, contradiction detection, JSONL audit.
- `market_agent_tools.py` — Ollama tool schemas, snapshot serializer, alert writer, plain-English glossary.
- `rag_retrieval.py` — Keyword-overlap RAG over the playbook.
- `qc_validation.py` — Data and AI-output validation checks.
- `data/knowledge_base.md` — RAG corpus.
- `output/alerts.csv` — operator alerts (auto-created on first tool fire).
- `output/agent_runs.jsonl` — per-run audit log.
- `.env.example` — template for environment variables.
- `requirements.txt` — pinned floors for dependencies.

**Deployment platform:** Streamlit Community Cloud (free, GitHub-driven). Posit Connect / DigitalOcean also supported; all three honor the same env-var names. `.env` is gitignored; secrets are configured in the platform UI.

### 3.4 Usage Instructions

**Live app:** [paste your live URL here]
**Password (if gate enabled):** [paste your password here, or write “no password”]

**To use the deployed app:**

1. Open the live URL in any modern browser.
2. If a password gate appears, paste the password from the line above and press **Enter**.
3. In the left sidebar, choose:
   - **Product** (e.g. `BTC-USD`)
   - **Granularity (seconds)** (e.g. `3600` for 1-hour candles)
   - **Total candles** (e.g. `96`) and **Lookback candles** (e.g. `24`)
   - **Model name** (leave default `nemotron-3-nano:30b-cloud`)
   - **Audience** for the executive brief (`desk`, `risk`, or `retail`)
4. Click **Fetch Coinbase data**. The main area populates with metric tiles (latest close, lookback return, volatility, relative volume), two line charts, and a recent-candles table.
5. Click **Generate 3-agent briefing**. The pipeline runs Agents 1 → 2 → 3 (≈ 30–60 s). When it finishes, the page shows:
   - **Regime / Liquidity / Range** classification tiles.
   - Three agent tabs (Data + tools / Risk-regime / Executive).
   - “What these terms mean (plain English)” expander.
   - **AI QC score** plus an **AI validation checks** expander (numeric grounding, disclaimer presence, tool usage, etc.).
   - **Tool call trace** showing each tool invocation.
   - **Operator alerts** table (rows from `output/alerts.csv` whenever the AI flagged a threshold breach).
6. Change the sidebar (e.g. switch **Audience** from `desk` to `retail`) and click **Generate** again to compare briefings on the same data.

**To run locally (developer):**

```bash
cd shiny_app_coinbase_spot
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                  # then edit .env and fill OLLAMA_API_KEY
streamlit run app.py
```

Open `http://localhost:8501`. The same buttons and workflow apply.
